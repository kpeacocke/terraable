"""Executable local-lab backend for safe end-to-end demo flows."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contract import build_handoff_payload
from .hcp_terraform import TFC_HOSTNAME_ENV_VAR, _hostname_to_token_env_var
from .orchestrator import ActionName, ActionStatus

DRIFT_SERVICE_PLAYBOOK = "playbooks/drift_service_health.yml"
MOCK_MODE_ENV_VAR = "TERRAABLE_MOCK_MODE"
PORTAL_SERVICE_STATE_FILE = "portal_service.state"
SUPPORTED_EXECUTION_TARGET = "local-lab"
HCP_TOKEN_REQUIREMENT = "__HCP_TF_TOKEN__"
CREDENTIAL_KEYS = (
    "HCP_TERRAFORM_TOKEN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "ARM_CLIENT_ID",
    "ARM_CLIENT_SECRET",
    "ARM_TENANT_ID",
    "ARM_SUBSCRIPTION_ID",
    "OPENSHIFT_API_URL",
    "OPENSHIFT_TOKEN",
)
TARGET_CREDENTIAL_REQUIREMENTS = {
    "local-lab": (HCP_TOKEN_REQUIREMENT,),
    "openshift": (HCP_TOKEN_REQUIREMENT, "OPENSHIFT_API_URL", "OPENSHIFT_TOKEN"),
    "okd": (HCP_TOKEN_REQUIREMENT, "OPENSHIFT_API_URL", "OPENSHIFT_TOKEN"),
    "aws": (HCP_TOKEN_REQUIREMENT, "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"),
    "azure": (
        HCP_TOKEN_REQUIREMENT,
        "ARM_CLIENT_ID",
        "ARM_CLIENT_SECRET",
        "ARM_TENANT_ID",
        "ARM_SUBSCRIPTION_ID",
    ),
}


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Captured output from a subprocess execution."""

    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class LabActionResult:
    """Serializable response for a UI action."""

    action: str
    status: str
    detail: str
    tone: str


CommandRunner = Callable[[list[str], Path | None, dict[str, str] | None], CommandResult]


def default_runner(
    argv: list[str],
    cwd: Path | None,
    env: dict[str, str] | None,
) -> CommandResult:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    return CommandResult(stdout=completed.stdout, stderr=completed.stderr)


class LocalLabBackend:
    """Run a safe local-lab flow against workspace-local files and tools."""

    def __init__(
        self,
        workspace_root: Path,
        *,
        runner: CommandRunner | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.runtime_root = workspace_root / ".terraable" / "local-lab"
        self.state_file = self.runtime_root / "state.json"
        self.ansible_root = workspace_root / "ansible"
        self.terraform_root = workspace_root / "integration" / "local_lab" / "terraform"
        self._runner = runner or default_runner
        self._clock = clock or time.time
        self._mock_mode = os.getenv(MOCK_MODE_ENV_VAR, "").lower() in {"1", "true", "yes"}
        self._state_lock = threading.RLock()
        self._credentials = self._bootstrap_credentials()

    def get_state(self) -> dict[str, Any]:
        """Return persisted UI state."""

        state = self._load_state()
        state["mode"] = "offline-mock" if self._mock_mode else "live-local-lab"
        current = state.get("current")
        target = (
            str(current.get("target", SUPPORTED_EXECUTION_TARGET))
            if isinstance(current, dict)
            else SUPPORTED_EXECUTION_TARGET
        )
        portal = (
            str(current.get("portal", "backstage")) if isinstance(current, dict) else "backstage"
        )
        state["auth"] = self.get_auth_status(target=target, portal=portal)
        return state

    def configure_credentials(
        self,
        credentials: dict[str, str],
        *,
        target: str = SUPPORTED_EXECUTION_TARGET,
        portal: str = "backstage",
    ) -> dict[str, Any]:
        """Merge credentials from the UI and report current auth status for target/portal."""

        for key, value in credentials.items():
            if key not in CREDENTIAL_KEYS:
                continue
            trimmed = value.strip()
            if trimmed:
                self._credentials[key] = {"value": trimmed, "source": "ui"}
            elif key in self._credentials and self._credentials[key]["source"] == "ui":
                # Clearing a UI field should remove only user-entered values.
                self._credentials.pop(key)

        return self.get_auth_status(target=target, portal=portal)

    def get_auth_status(self, *, target: str, portal: str) -> dict[str, Any]:
        """Return authentication and readiness checks for a selected environment request."""

        if self._mock_mode:
            return {
                "authenticated": True,
                "ready": True,
                "required_credentials": [],
                "missing_credentials": [],
                "credential_sources": {"mode": "mock"},
                "blockers": [],
            }

        requirements = TARGET_CREDENTIAL_REQUIREMENTS.get(target, ("HCP_TERRAFORM_TOKEN",))
        missing = [key for key in requirements if not self._credential_value(key)]
        authenticated = not missing
        source = self._auth_source(requirements)

        target_ready = target == SUPPORTED_EXECUTION_TARGET
        portal_ready = portal in {"backstage", "rhdh"}
        ready = authenticated and target_ready and portal_ready

        blockers: list[str] = []
        if missing:
            blockers.append(f"missing credentials: {', '.join(missing)}")
        if not target_ready:
            blockers.append(
                f"target={target} is not executable yet; select {SUPPORTED_EXECUTION_TARGET}"
            )
        if not portal_ready:
            blockers.append(f"portal={portal} is not supported")

        display_requirements = [self._display_requirement_key(key) for key in requirements]
        display_missing = [self._display_requirement_key(key) for key in missing]

        return {
            "authenticated": authenticated,
            "ready": ready,
            "required_credentials": display_requirements,
            "missing_credentials": display_missing,
            "credential_sources": source,
            "blockers": blockers,
        }

    def create_environment(
        self,
        *,
        target: str,
        portal: str,
        profile: str,
        eda: str,
    ) -> dict[str, Any]:
        """Create a lab environment and its Terraform-to-Ansible handoff contract."""

        if self._mock_mode:
            environment_name = f"mock-demo-{int(self._clock())}"
            state = self._load_state()
            state["current"] = {
                "environment_name": environment_name,
                "target": target,
                "portal": portal,
                "profile": profile,
                "eda": eda,
            }
            state["controls"] = {"ssh_root_login": True, "portal_service_health": True}
            state["eda_enabled"] = eda == "enabled"
            self._save_state(state)
            return self._record_action(
                ActionName.CREATE_ENVIRONMENT.value,
                ActionStatus.SUCCEEDED.value,
                f"create_environment succeeded (mock): {environment_name} provisioned",
                "ok",
            )

        if target != "local-lab":
            return self._record_action(
                ActionName.CREATE_ENVIRONMENT.value,
                ActionStatus.FAILED.value,
                f"target={target} is not executable yet; only local-lab is wired end-to-end.",
                "fail",
            )

        auth = self.get_auth_status(target=target, portal=portal)
        if not auth["ready"]:
            return self._record_action(
                ActionName.CREATE_ENVIRONMENT.value,
                ActionStatus.FAILED.value,
                "create_environment blocked: " + "; ".join(auth["blockers"]),
                "fail",
            )

        environment_name = f"local-lab-{int(self._clock())}"
        env_dir = self._ensure_environment(environment_name)

        try:
            outputs = self._terraform_apply(
                env_dir,
                environment_name=environment_name,
                portal=portal,
                profile=profile,
            )
            payload = build_handoff_payload(
                environment_name=str(outputs["environment_name"]),
                terraform_run_id=f"local-{environment_name}",
                target_platform=str(outputs["target_platform"]),
                portal_impl=str(outputs["portal_impl"]),
                security_profile=str(outputs["security_profile"]),
                connection=dict(outputs["connection"]),
                metadata={"mode": "local-lab", "runtime_dir": str(env_dir)},
            )
        except Exception as exc:  # pragma: no cover - exercised via tests with fakes
            return self._record_action(
                ActionName.CREATE_ENVIRONMENT.value,
                ActionStatus.FAILED.value,
                f"create_environment failed: {exc}",
                "fail",
            )

        state = self._load_state()
        state["current"] = {
            "environment_name": payload.environment_name,
            "target": payload.target_platform.value,
            "portal": payload.portal_impl.value,
            "profile": payload.security_profile.value,
            "eda": eda,
            "runtime_dir": str(env_dir),
            "runtime_vars": payload.to_runtime_vars(),
        }
        state["eda_enabled"] = eda == "enabled"
        state["controls"] = self._read_controls(env_dir)
        self._save_state(state)

        return self._record_action(
            ActionName.CREATE_ENVIRONMENT.value,
            ActionStatus.SUCCEEDED.value,
            (
                "create_environment succeeded: "
                f"target={target}, portal={portal}, profile={profile}, eda={eda}; "
                f"Terraform state written to {env_dir / 'terraform.tfstate'}"
            ),
            "ok",
        )

    def apply_baseline(self) -> dict[str, Any]:
        """Apply the baseline operational workflow to the active local lab."""

        if self._mock_mode:
            controls: dict[str, bool] = {"ssh_root_login": True, "portal_service_health": True}
            return self._record_action(
                ActionName.APPLY_BASELINE.value,
                ActionStatus.SUCCEEDED.value,
                "apply_baseline succeeded (mock): operational workflow applied",
                "ok",
                controls=controls,
            )

        current = self._current_environment()
        env_dir = Path(str(current["runtime_dir"]))
        extra_vars = self._ansible_vars(env_dir)
        extra_vars["portal_impl"] = str(current["portal"])
        extra_vars["security_profile"] = str(current["profile"])
        self._run_playbook("playbooks/aap_operationalise.yml", extra_vars)
        controls = self._read_controls(env_dir)
        return self._record_action(
            ActionName.APPLY_BASELINE.value,
            ActionStatus.SUCCEEDED.value,
            f"apply_baseline succeeded: operational workflow applied to {current['environment_name']}",
            "ok",
            controls=controls,
        )

    def run_compliance_scan(self) -> dict[str, Any]:
        """Run executable compliance checks against the active local lab."""

        if self._mock_mode:
            state = self._load_state()
            raw = state.get("controls") or {"ssh_root_login": True, "portal_service_health": True}
            mock_controls: dict[str, bool] = {
                "ssh_root_login": bool(raw.get("ssh_root_login", True)),
                "portal_service_health": bool(raw.get("portal_service_health", True)),
            }
            failing = [name for name, passed in mock_controls.items() if not passed]
            state["scan_count"] = int(state.get("scan_count", 0)) + 1
            pct = self._score_pct(mock_controls)
            trend = state.setdefault("trend", [])
            trend.insert(0, {"pct": pct, "label": f"Scan #{state['scan_count']}"})
            del trend[8:]
            self._save_state(state)
            detail = (
                f"run_compliance_scan detected drift: {', '.join(failing)}"
                if failing
                else "run_compliance_scan succeeded (mock): all controls compliant"
            )
            response = self._record_action(
                ActionName.RUN_COMPLIANCE_SCAN.value,
                ActionStatus.FAILED.value if failing else ActionStatus.SUCCEEDED.value,
                detail,
                "fail" if failing else "ok",
                controls=mock_controls,
            )
            if state.get("eda_enabled") and failing:
                self._append_eda_event(
                    f"compliance_drift event emitted for {', '.join(failing)}",
                    "warn",
                )
                response["state"] = self.get_state()
            return response

        current = self._current_environment()
        env_dir = Path(str(current["runtime_dir"]))
        ssh_scan_path = env_dir / "ssh_scan.json"
        service_scan_path = env_dir / "service_scan.json"

        ssh_vars = self._ansible_vars(env_dir)
        ssh_vars["scan_output_path"] = str(ssh_scan_path)
        self._run_playbook("playbooks/compliance_scan.yml", ssh_vars)

        svc_vars = self._ansible_vars(env_dir)
        svc_vars.update(
            {
                "drift_action": "validate",
                "portal_service": str(current["portal"]),
                "scan_output_path": str(service_scan_path),
            }
        )
        self._run_playbook(DRIFT_SERVICE_PLAYBOOK, svc_vars)

        ssh_scan = json.loads(ssh_scan_path.read_text(encoding="utf-8"))
        service_scan = json.loads(service_scan_path.read_text(encoding="utf-8"))
        controls = {
            "ssh_root_login": ssh_scan.get("status") == "pass",
            "portal_service_health": service_scan.get("status") == "pass",
        }
        failing = [name for name, passed in controls.items() if not passed]
        state = self._load_state()
        state["controls"] = controls
        state["scan_count"] = int(state.get("scan_count", 0)) + 1
        pct = self._score_pct(controls)
        trend = state.setdefault("trend", [])
        trend.insert(0, {"pct": pct, "label": f"Scan #{state['scan_count']}"})
        del trend[8:]
        self._save_state(state)

        if failing:
            response = self._record_action(
                ActionName.RUN_COMPLIANCE_SCAN.value,
                ActionStatus.FAILED.value,
                f"run_compliance_scan failed: drift detected on {', '.join(failing)}",
                "fail",
                controls=controls,
            )
            if state.get("eda_enabled"):
                self._append_eda_event(
                    f"compliance_drift event emitted for {', '.join(failing)}",
                    "warn",
                )
                response["state"] = self.get_state()
            return response

        return self._record_action(
            ActionName.RUN_COMPLIANCE_SCAN.value,
            ActionStatus.SUCCEEDED.value,
            "run_compliance_scan succeeded: all baseline controls compliant",
            "ok",
            controls=controls,
        )

    def inject_ssh_drift(self) -> dict[str, Any]:
        """Inject SSH drift into the lab state using Ansible."""

        if self._mock_mode:
            state = self._load_state()
            raw = state.get("controls") or {}
            ssh_controls: dict[str, bool] = {
                "ssh_root_login": False,
                "portal_service_health": bool(raw.get("portal_service_health", True)),
            }
            state["controls"] = ssh_controls
            self._save_state(state)
            response = self._record_action(
                ActionName.INJECT_SSH_DRIFT.value,
                ActionStatus.SUCCEEDED.value,
                "inject_ssh_drift succeeded (mock): PermitRootLogin set to yes",
                "warn",
                controls=ssh_controls,
            )
            if self._load_state().get("eda_enabled"):
                self._append_eda_event("ssh_root_login drift injected - rulebook triggered", "warn")
                response["state"] = self.get_state()
            return response

        current = self._current_environment()
        env_dir = Path(str(current["runtime_dir"]))
        self._run_playbook("playbooks/drift_ssh_root.yml", self._ansible_vars(env_dir))
        controls = self._read_controls(env_dir)
        response = self._record_action(
            ActionName.INJECT_SSH_DRIFT.value,
            ActionStatus.SUCCEEDED.value,
            "inject_ssh_drift succeeded: set PermitRootLogin yes",
            "warn",
            controls=controls,
        )
        if self._load_state().get("eda_enabled"):
            self._append_eda_event("ssh_root_login drift injected - rulebook triggered", "warn")
            response["state"] = self.get_state()
        return response

    def inject_service_drift(self) -> dict[str, Any]:
        """Inject portal service drift into the lab state using Ansible."""

        if self._mock_mode:
            state = self._load_state()
            raw = state.get("controls") or {}
            svc_controls: dict[str, bool] = {
                "ssh_root_login": bool(raw.get("ssh_root_login", True)),
                "portal_service_health": False,
            }
            state["controls"] = svc_controls
            self._save_state(state)
            response = self._record_action(
                ActionName.INJECT_SERVICE_DRIFT.value,
                ActionStatus.SUCCEEDED.value,
                "inject_service_drift succeeded (mock): portal service stopped",
                "warn",
                controls=svc_controls,
            )
            if self._load_state().get("eda_enabled"):
                self._append_eda_event(
                    "portal_service_health drift injected - rulebook triggered", "warn"
                )
                response["state"] = self.get_state()
            return response

        current = self._current_environment()
        env_dir = Path(str(current["runtime_dir"]))
        extra_vars = self._ansible_vars(env_dir)
        extra_vars.update({"drift_action": "inject", "portal_service": str(current["portal"])})
        self._run_playbook(DRIFT_SERVICE_PLAYBOOK, extra_vars)
        controls = self._read_controls(env_dir)
        response = self._record_action(
            ActionName.INJECT_SERVICE_DRIFT.value,
            ActionStatus.SUCCEEDED.value,
            "inject_service_drift succeeded: portal service stopped",
            "warn",
            controls=controls,
        )
        if self._load_state().get("eda_enabled"):
            self._append_eda_event(
                "portal_service_health drift injected - rulebook triggered", "warn"
            )
            response["state"] = self.get_state()
        return response

    def run_remediation(self) -> dict[str, Any]:
        """Restore the approved state for all local-lab controls."""

        if self._mock_mode:
            rem_controls: dict[str, bool] = {
                "ssh_root_login": True,
                "portal_service_health": True,
            }
            response = self._record_action(
                ActionName.RUN_REMEDIATION.value,
                ActionStatus.SUCCEEDED.value,
                "run_remediation succeeded (mock): all controls restored",
                "ok",
                controls=rem_controls,
            )
            if self._load_state().get("eda_enabled"):
                self._append_eda_event("remediation complete - all drift cleared", "ok")
                response["state"] = self.get_state()
            return response

        current = self._current_environment()
        env_dir = Path(str(current["runtime_dir"]))
        self._run_playbook("playbooks/remediate_ssh_root.yml", self._ansible_vars(env_dir))
        svc_vars = self._ansible_vars(env_dir)
        svc_vars.update({"drift_action": "remediate", "portal_service": str(current["portal"])})
        self._run_playbook(DRIFT_SERVICE_PLAYBOOK, svc_vars)
        controls = self._read_controls(env_dir)
        response = self._record_action(
            ActionName.RUN_REMEDIATION.value,
            ActionStatus.SUCCEEDED.value,
            "run_remediation succeeded: restored PermitRootLogin no and portal service running",
            "ok",
            controls=controls,
        )
        if self._load_state().get("eda_enabled"):
            self._append_eda_event("remediation complete - all drift cleared", "ok")
            response["state"] = self.get_state()
        return response

    def _current_environment(self) -> dict[str, Any]:
        state = self._load_state()
        current = state.get("current")
        if not isinstance(current, dict):
            raise RuntimeError("No environment has been created yet.")
        return current

    def _terraform_apply(
        self,
        env_dir: Path,
        *,
        environment_name: str,
        portal: str,
        profile: str,
    ) -> dict[str, Any]:
        self._run(
            [
                "terraform",
                f"-chdir={self.terraform_root}",
                "init",
                "-input=false",
                "-no-color",
            ],
            cwd=self.workspace_root,
            env=None,
        )
        state_path = env_dir / "terraform.tfstate"
        self._run(
            [
                "terraform",
                f"-chdir={self.terraform_root}",
                "apply",
                "-auto-approve",
                "-input=false",
                "-no-color",
                f"-state={state_path}",
                "-var",
                f"environment_name={environment_name}",
                "-var",
                f"portal_impl={portal}",
                "-var",
                f"security_profile={profile}",
            ],
            cwd=self.workspace_root,
            env=None,
        )
        output = self._run(
            [
                "terraform",
                f"-chdir={self.terraform_root}",
                "output",
                "-json",
                f"-state={state_path}",
            ],
            cwd=self.workspace_root,
            env=None,
        )
        raw = json.loads(output.stdout)
        return {key: value["value"] for key, value in raw.items()}

    def _run_playbook(self, playbook: str, extra_vars: dict[str, Any]) -> None:
        vars_path = self.runtime_root / (
            f"extra-vars-{Path(playbook).stem}-{threading.get_ident()}-{time.time_ns()}.json"
        )
        vars_path.parent.mkdir(parents=True, exist_ok=True)
        vars_path.write_text(json.dumps(extra_vars), encoding="utf-8")
        env = os.environ.copy()
        env.setdefault("ANSIBLE_CONFIG", str(self.ansible_root / "ansible.cfg"))
        inventory_path = Path(str(extra_vars["inventory_path"]))
        try:
            self._run(
                [
                    sys.executable,
                    "-m",
                    "ansible.cli.playbook",
                    "-i",
                    str(inventory_path),
                    playbook,
                    "--extra-vars",
                    f"@{vars_path}",
                ],
                cwd=self.ansible_root,
                env=env,
            )
        finally:
            vars_path.unlink(missing_ok=True)

    def _ansible_vars(self, env_dir: Path) -> dict[str, Any]:
        current = self._current_environment()
        runtime_vars = dict(current["runtime_vars"])
        runtime_vars.update(
            {
                "lab_mode": True,
                "inventory_path": str(env_dir / "inventory.yml"),
                "sshd_config_path": str(env_dir / "sshd_config"),
                "service_state_path": str(env_dir / PORTAL_SERVICE_STATE_FILE),
                "portal_release_path": str(env_dir / "portal_release.txt"),
            }
        )
        return runtime_vars

    def _read_controls(self, env_dir: Path) -> dict[str, bool]:
        ssh_text = (env_dir / "sshd_config").read_text(encoding="utf-8")
        service_text = (env_dir / PORTAL_SERVICE_STATE_FILE).read_text(encoding="utf-8").strip()
        return {
            "ssh_root_login": "PermitRootLogin no" in ssh_text,
            "portal_service_health": service_text == "active",
        }

    def _ensure_environment(self, environment_name: str) -> Path:
        env_dir = self.runtime_root / environment_name
        env_dir.mkdir(parents=True, exist_ok=True)
        inventory = env_dir / "inventory.yml"
        inventory.write_text(
            "all:\n"
            "  children:\n"
            "    local_lab:\n"
            "      hosts:\n"
            "        localhost:\n"
            "          ansible_connection: local\n",
            encoding="utf-8",
        )
        (env_dir / "sshd_config").write_text(
            "PermitRootLogin yes\nPasswordAuthentication yes\n",
            encoding="utf-8",
        )
        (env_dir / PORTAL_SERVICE_STATE_FILE).write_text("inactive\n", encoding="utf-8")
        return env_dir

    def _record_action(
        self,
        action: str,
        status: str,
        detail: str,
        tone: str,
        *,
        controls: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        state = self._load_state()
        state.setdefault("evidence", []).insert(0, {"message": detail, "tone": tone})
        if controls is not None:
            state["controls"] = controls
        self._save_state(state)
        return {
            "action": action,
            "status": status,
            "detail": detail,
            "tone": tone,
            "state": self.get_state(),
        }

    def _append_eda_event(self, detail: str, tone: str) -> None:
        state = self._load_state()
        state.setdefault("eda_history", []).insert(0, {"message": detail, "tone": tone})
        self._save_state(state)

    def _score_pct(self, controls: dict[str, bool]) -> int:
        total = len(controls)
        passed = sum(1 for value in controls.values() if value)
        return round((passed / total) * 100) if total else 0

    def _load_state(self) -> dict[str, Any]:
        with self._state_lock:
            if not self.state_file.exists():
                return {
                    "current": None,
                    "controls": {
                        "ssh_root_login": False,
                        "portal_service_health": False,
                    },
                    "evidence": [],
                    "eda_history": [],
                    "trend": [],
                    "scan_count": 0,
                    "eda_enabled": False,
                }
            raw_state = json.loads(self.state_file.read_text(encoding="utf-8"))
            return raw_state if isinstance(raw_state, dict) else {}

    def _save_state(self, state: dict[str, Any]) -> None:
        with self._state_lock:
            self.runtime_root.mkdir(parents=True, exist_ok=True)
            temp_path = self.runtime_root / f"state-{threading.get_ident()}-{time.time_ns()}.json"
            temp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            temp_path.replace(self.state_file)

    def _run(
        self,
        argv: list[str],
        *,
        cwd: Path | None,
        env: dict[str, str] | None,
    ) -> CommandResult:
        try:
            return self._runner(argv, cwd, env)
        except FileNotFoundError as exc:
            raise RuntimeError(str(exc)) from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else ""
            stdout = exc.stdout.strip() if exc.stdout else ""
            detail = stderr or stdout or str(exc)
            raise RuntimeError(detail) from exc

    def _bootstrap_credentials(self) -> dict[str, dict[str, str]]:
        creds: dict[str, dict[str, str]] = {}
        dotenv_values = self._read_dotenv(self.workspace_root / ".env")
        for key in self._credential_keys():
            env_value = os.environ.get(key, "").strip()
            if env_value:
                creds[key] = {"value": env_value, "source": "env"}
                continue

            dotenv_value = dotenv_values.get(key, "").strip()
            if dotenv_value:
                creds[key] = {"value": dotenv_value, "source": "dotenv"}
        return creds

    def _read_dotenv(self, dotenv_path: Path) -> dict[str, str]:
        if not dotenv_path.exists():
            return {}

        allowed_keys = self._credential_keys()
        loaded: dict[str, str] = {}
        for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key in allowed_keys:
                loaded[key] = value
        return loaded

    def _credential_value(self, key: str) -> str:
        if key == HCP_TOKEN_REQUIREMENT:
            tf_key = self._tf_token_env_var()
            tf_item = self._credentials.get(tf_key)
            if tf_item and tf_item["value"]:
                return tf_item["value"]
            alias_item = self._credentials.get("HCP_TERRAFORM_TOKEN")
            return alias_item["value"] if alias_item else ""

        item = self._credentials.get(key)
        if not item:
            return ""
        return item["value"]

    def _auth_source(self, requirements: tuple[str, ...]) -> dict[str, str]:
        sources: dict[str, str] = {}
        for key in requirements:
            display_key = self._display_requirement_key(key)
            if key == HCP_TOKEN_REQUIREMENT:
                tf_key = self._tf_token_env_var()
                tf_item = self._credentials.get(tf_key)
                if tf_item:
                    sources[display_key] = tf_item["source"]
                    continue
                alias_item = self._credentials.get("HCP_TERRAFORM_TOKEN")
                if alias_item:
                    sources[display_key] = f"{alias_item['source']} (from HCP_TERRAFORM_TOKEN)"
                continue

            item = self._credentials.get(key)
            if item:
                sources[display_key] = item["source"]
        return sources

    def _display_requirement_key(self, key: str) -> str:
        return self._tf_token_env_var() if key == HCP_TOKEN_REQUIREMENT else key

    def _credential_keys(self) -> tuple[str, ...]:
        return (*CREDENTIAL_KEYS, self._tf_token_env_var())

    def _tf_token_env_var(self) -> str:
        hostname = os.getenv(TFC_HOSTNAME_ENV_VAR, "app.terraform.io")
        return _hostname_to_token_env_var(hostname)
