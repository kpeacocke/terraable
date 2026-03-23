"""Executable local-lab backend for safe end-to-end demo flows."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, Concatenate, ParamSpec, TypeVar, cast
from urllib.error import URLError
from urllib.request import Request, urlopen

from .contract import build_handoff_payload
from .hcp_terraform import TFC_HOSTNAME_ENV_VAR, hostname_to_token_env_var
from .local_detect import detect_local_target
from .orchestrator import ActionName, ActionStatus

DRIFT_SERVICE_PLAYBOOK = "playbooks/drift_service_health.yml"
MOCK_MODE_ENV_VAR = "TERRAABLE_MOCK_MODE"
EXECUTION_MODE_ENV_VAR = "TERRAABLE_EXECUTION_MODE"
PORTAL_SERVICE_STATE_FILE = "portal_service.state"
SUPPORTED_EXECUTION_TARGET = "local-lab"
SUPPORTED_EXECUTION_TARGETS = {
    "local-lab",
    "vmware",
    "parallels",
    "hyper-v",
}
# Targets that this local-lab backend treats as wired to a live Terraform config.
# vmware/parallels/hyper-v substrate modules are scaffolded (contract outputs only)
# and not yet connected to _terraform_apply(); they run correctly in mock mode only.
# AWS, Azure, and OKD are handled via their own backend classes and API-dispatch
# paths, not via LIVE_EXECUTION_TARGETS in this module.
LIVE_EXECUTION_TARGETS = {"local-lab"}
HCP_TOKEN_REQUIREMENT = "__HCP_TF_TOKEN__"
STATE_LOG_LIMIT = 50
CREDENTIAL_KEYS = (
    "HCP_TERRAFORM_TOKEN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "ARM_CLIENT_ID",
    "ARM_CLIENT_SECRET",
    "ARM_TENANT_ID",
    "ARM_SUBSCRIPTION_ID",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "OPENSHIFT_API_URL",
    "OPENSHIFT_TOKEN",
)
CredentialRequirements = tuple[str, ...]
CredentialEntry = dict[str, str]

TARGET_CREDENTIAL_REQUIREMENTS: dict[str, CredentialRequirements] = {
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
    "gcp": (HCP_TOKEN_REQUIREMENT, "GOOGLE_APPLICATION_CREDENTIALS"),
    "vmware": (HCP_TOKEN_REQUIREMENT,),
    "parallels": (HCP_TOKEN_REQUIREMENT,),
    "hyper-v": (HCP_TOKEN_REQUIREMENT,),
}


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Captured output from a subprocess execution."""

    stdout: str
    stderr: str


CommandRunner = Callable[[list[str], Path | None, dict[str, str] | None], CommandResult]
StateMutator = Callable[[dict[str, Any]], None]
P = ParamSpec("P")
R = TypeVar("R")


def _as_str_any_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return cast(dict[str, Any], value)


def _serialize_action(
    method: Callable[Concatenate[LocalLabBackend, P], R],
) -> Callable[Concatenate[LocalLabBackend, P], R]:
    @wraps(method)
    def wrapped(self: LocalLabBackend, *args: P.args, **kwargs: P.kwargs) -> R:
        with self.action_lock:
            return method(self, *args, **kwargs)

    return wrapped


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
        self._execution_mode = os.getenv(EXECUTION_MODE_ENV_VAR, "direct").strip().lower()
        if self._execution_mode not in {"direct", "awx"}:
            self._execution_mode = "direct"
        self.action_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._credentials_lock = threading.RLock()
        self._credentials = self._bootstrap_credentials()

    def get_state(self) -> dict[str, Any]:
        """Return persisted UI state."""

        state = self._load_state()
        state["mode"] = "offline-mock" if self._mock_mode else "live-local-lab"
        state["controller_mode"] = self._execution_mode
        state["target_suggestion"] = detect_local_target()
        state["observability"] = self._build_observability(state)
        current = _as_str_any_dict(state.get("current"))
        target = str(current.get("target", SUPPORTED_EXECUTION_TARGET))
        portal = str(current.get("portal", "backstage"))
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

        with self._credentials_lock:
            for key, value in credentials.items():
                if key not in CREDENTIAL_KEYS:
                    continue
                self._apply_credential_value(key, value)

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

        requirements: CredentialRequirements = TARGET_CREDENTIAL_REQUIREMENTS.get(
            target,
            (HCP_TOKEN_REQUIREMENT,),
        )
        missing = [key for key in requirements if not self._credential_value(key)]
        authenticated = not missing
        source = self._auth_source(requirements)

        target_ready = target in LIVE_EXECUTION_TARGETS
        portal_ready = portal in {"backstage", "rhdh"}
        ready = authenticated and target_ready and portal_ready

        display_requirements = [self._display_requirement_key(key) for key in requirements]
        display_missing = [self._display_requirement_key(key) for key in missing]

        blockers: list[str] = []
        if missing:
            blockers.append(f"missing credentials: {', '.join(display_missing)}")
        if not target_ready:
            supported = ", ".join(sorted(LIVE_EXECUTION_TARGETS))
            blockers.append(
                f"target={target} is not executable in live mode; supported live targets: {supported}"
            )
        if not portal_ready:
            blockers.append(f"portal={portal} is not supported")
        if self._execution_mode == "awx":
            awx_host = os.getenv("AWX_HOST", "").strip()
            awx_username = os.getenv("AWX_USERNAME", "").strip()
            awx_password = os.getenv("AWX_PASSWORD", "").strip()
            if not awx_host or not awx_username or not awx_password:
                blockers.append(
                    "awx execution mode requires AWX_HOST, AWX_USERNAME, and AWX_PASSWORD"
                )
                ready = False
            elif not awx_host.startswith("https://"):
                blockers.append("AWX_HOST must use an https:// URL")
                ready = False

        return {
            "authenticated": authenticated,
            "ready": ready,
            "required_credentials": display_requirements,
            "missing_credentials": display_missing,
            "credential_sources": source,
            "blockers": blockers,
        }

    @_serialize_action
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
            run_id = f"mock-{environment_name}"
            self._set_terraform_status(
                status="applied",
                detail=f"mock terraform apply completed for {environment_name}",
                run_id=run_id,
            )
            env_dir = self._ensure_environment(environment_name)
            runtime_vars: dict[str, Any] = {
                "environment_name": environment_name,
                "terraform_run_id": run_id,
                "target_platform": target,
                "portal_impl": portal,
                "security_profile": profile,
                "connection": {
                    "ansible_inventory_group": "local_lab",
                    "ssh_user": "localhost",
                    "ssh_port": 22,
                    "api_endpoint": "https://127.0.0.1",
                },
                "metadata": {"mode": "offline-mock", "runtime_dir": str(env_dir)},
            }
            state = self._load_state()
            state["current"] = {
                "environment_name": environment_name,
                "target": target,
                "portal": portal,
                "profile": profile,
                "eda": eda,
                "runtime_dir": str(env_dir),
                "runtime_vars": runtime_vars,
            }
            state["controls"] = {"ssh_root_login": True, "portal_service_health": True}
            state["compliance_controls"] = {
                "ssh_root_login": True,
                "ssh_password_authentication": True,
            }
            state["eda_enabled"] = eda == "enabled"
            self._save_state(state)
            return self._record_action(
                ActionName.CREATE_ENVIRONMENT.value,
                ActionStatus.SUCCEEDED.value,
                f"create_environment succeeded (mock): {environment_name} provisioned",
                "ok",
            )

        if target not in LIVE_EXECUTION_TARGETS:
            return self._record_action(
                ActionName.CREATE_ENVIRONMENT.value,
                ActionStatus.FAILED.value,
                (
                    f"target={target} is not wired to a live Terraform config; "
                    f"supported live targets: {', '.join(sorted(LIVE_EXECUTION_TARGETS))}. "
                    "Use mock mode (TERRAABLE_MOCK_MODE=true) to exercise other targets."
                ),
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
        run_id = f"local-{environment_name}"
        env_dir = self._ensure_environment(environment_name)
        self._set_terraform_status(
            status="running",
            detail=f"terraform apply started for {environment_name}",
            run_id=run_id,
        )

        try:
            outputs = self._terraform_apply(
                env_dir,
                environment_name=environment_name,
                portal=portal,
                profile=profile,
                target=target,
            )
            # Use the Terraform output target to ensure payload matches the actual provisioned infrastructure
            tf_target = str(outputs.get("target_platform", target))
            payload = build_handoff_payload(
                environment_name=str(outputs["environment_name"]),
                terraform_run_id=run_id,
                target_platform=tf_target,
                portal_impl=str(outputs["portal_impl"]),
                security_profile=str(outputs["security_profile"]),
                connection=dict(outputs["connection"]),
                metadata={"mode": "local-lab", "runtime_dir": str(env_dir)},
            )
        except Exception as exc:  # pragma: no cover - exercised via tests with fakes
            self._set_terraform_status(
                status="failed",
                detail=f"terraform apply failed for {environment_name}: {exc}",
                run_id=run_id,
            )
            return self._record_action(
                ActionName.CREATE_ENVIRONMENT.value,
                ActionStatus.FAILED.value,
                f"create_environment failed: {exc}",
                "fail",
            )

        self._set_terraform_status(
            status="applied",
            detail=f"terraform apply completed for {payload.environment_name}",
            run_id=run_id,
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
        state["compliance_controls"] = self._read_compliance_controls(env_dir)
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

    @_serialize_action
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
        try:
            job = self._run_playbook("playbooks/aap_operationalise.yml", extra_vars)
            self._set_job_status(
                action=ActionName.APPLY_BASELINE.value,
                status="succeeded",
                detail="baseline workflow completed",
                job=job,
            )
            controls = self._read_controls(env_dir)
            compliance_controls = self._read_compliance_controls(env_dir)
            return self._record_action(
                ActionName.APPLY_BASELINE.value,
                ActionStatus.SUCCEEDED.value,
                f"apply_baseline succeeded: operational workflow applied to {current['environment_name']}",
                "ok",
                controls=controls,
                compliance_controls=compliance_controls,
            )
        except Exception as exc:
            self._set_job_status(
                action=ActionName.APPLY_BASELINE.value,
                status="failed",
                detail=f"baseline workflow failed: {exc}",
                job={"backend": self._execution_mode, "job_id": ""},
            )
            raise

    @_serialize_action
    def run_compliance_scan(self) -> dict[str, Any]:
        """Run executable compliance checks against the active local lab."""

        if self._mock_mode:
            return self._run_compliance_scan_mock()

        return self._run_compliance_scan_live()

    def _run_compliance_scan_mock(self) -> dict[str, Any]:
        state = self._load_state()
        raw = state.get("controls") or {"ssh_root_login": True, "portal_service_health": True}
        raw_compliance = state.get("compliance_controls") or {
            "ssh_root_login": True,
            "ssh_password_authentication": True,
        }
        controls: dict[str, bool] = {
            "ssh_root_login": bool(raw.get("ssh_root_login", True)),
            "portal_service_health": bool(raw.get("portal_service_health", True)),
        }
        compliance_controls: dict[str, bool] = {
            # Mirror ssh_root_login from primary controls so drift/remediation stays in sync
            "ssh_root_login": bool(raw.get("ssh_root_login", True)),
            "ssh_password_authentication": bool(
                raw_compliance.get("ssh_password_authentication", True)
            ),
        }
        all_failing = list(
            dict.fromkeys(
                [name for name, passed in controls.items() if not passed]
                + [name for name, passed in compliance_controls.items() if not passed]
            )
        )

        state["scan_count"] = int(state.get("scan_count", 0)) + 1
        # Score on the union of controls and compliance_controls; shared keys require both to pass
        all_control_names = set(controls.keys()) | set(compliance_controls.keys())
        all_controls: dict[str, bool] = {}
        for name in all_control_names:
            passed = True
            if name in controls:
                passed = passed and controls[name]
            if name in compliance_controls:
                passed = passed and compliance_controls[name]
            all_controls[name] = passed
        pct = self._score_pct(all_controls)
        trend = state.setdefault("trend", [])
        trend.insert(0, {"pct": pct, "label": f"Scan #{state['scan_count']}"})
        del trend[8:]
        state["compliance_controls"] = compliance_controls
        self._save_state(state)

        detail = (
            f"run_compliance_scan detected drift: {', '.join(all_failing)}"
            if all_failing
            else "run_compliance_scan succeeded (mock): all controls compliant"
        )
        response = self._record_action(
            ActionName.RUN_COMPLIANCE_SCAN.value,
            ActionStatus.FAILED.value if all_failing else ActionStatus.SUCCEEDED.value,
            detail,
            "fail" if all_failing else "ok",
            controls=controls,
            compliance_controls=compliance_controls,
        )
        if state.get("eda_enabled") and all_failing:
            self._append_eda_event(
                f"compliance_drift event emitted for {', '.join(all_failing)}",
                "warn",
            )
            response["state"] = self.get_state()
        return response

    def _run_compliance_scan_live(self) -> dict[str, Any]:
        current = self._current_environment()
        env_dir = Path(str(current["runtime_dir"]))
        ssh_scan_path = env_dir / "ssh_scan.json"
        service_scan_path = env_dir / "service_scan.json"

        try:
            ssh_vars = self._ansible_vars(env_dir)
            ssh_vars["scan_output_path"] = str(ssh_scan_path)
            ssh_job = self._run_playbook("playbooks/compliance_scan.yml", ssh_vars)

            svc_vars = self._ansible_vars(env_dir)
            svc_vars.update(
                {
                    "drift_action": "validate",
                    "portal_service": str(current["portal"]),
                    "scan_output_path": str(service_scan_path),
                }
            )
            service_job = self._run_playbook(DRIFT_SERVICE_PLAYBOOK, svc_vars)

            ssh_scan = json.loads(ssh_scan_path.read_text(encoding="utf-8"))
            service_scan = json.loads(service_scan_path.read_text(encoding="utf-8"))

            self._set_job_status(
                action=ActionName.RUN_COMPLIANCE_SCAN.value,
                status="succeeded",
                detail="compliance scan workflow completed",
                job={
                    "backend": service_job.get("backend", ssh_job.get("backend", "direct")),
                    "job_id": service_job.get("job_id", ssh_job.get("job_id", "")),
                    "jobs": [ssh_job, service_job],
                },
            )
        except Exception as exc:
            self._set_job_status(
                action=ActionName.RUN_COMPLIANCE_SCAN.value,
                status="failed",
                detail=f"compliance scan workflow failed: {exc}",
                job={"backend": self._execution_mode, "job_id": ""},
            )
            raise

        controls = {
            "ssh_root_login": ssh_scan.get("status") == "pass",
            "portal_service_health": service_scan.get("status") == "pass",
        }
        compliance_controls = self._read_compliance_controls(env_dir)
        all_failing = list(
            dict.fromkeys(
                [name for name, passed in controls.items() if not passed]
                + [name for name, passed in compliance_controls.items() if not passed]
            )
        )

        state = self._load_state()
        state["controls"] = controls
        state["compliance_controls"] = compliance_controls
        state["scan_count"] = int(state.get("scan_count", 0)) + 1
        # Score on union of all controls so trend is consistent with pass/fail determination.
        # For shared keys (e.g. ssh_root_login), AND logic: control only passes if it passes in all sources.
        all_control_names = set(controls.keys()) | set(compliance_controls.keys())
        all_controls: dict[str, bool] = {}
        for name in all_control_names:
            passed = True
            if name in controls:
                passed = passed and controls[name]
            if name in compliance_controls:
                passed = passed and compliance_controls[name]
            all_controls[name] = passed
        pct = self._score_pct(all_controls)
        trend = state.setdefault("trend", [])
        trend.insert(0, {"pct": pct, "label": f"Scan #{state['scan_count']}"})
        del trend[8:]
        self._save_state(state)

        if all_failing:
            response = self._record_action(
                ActionName.RUN_COMPLIANCE_SCAN.value,
                ActionStatus.FAILED.value,
                f"run_compliance_scan failed: drift detected on {', '.join(all_failing)}",
                "fail",
                controls=controls,
                compliance_controls=compliance_controls,
            )
            if state.get("eda_enabled"):
                self._append_eda_event(
                    f"compliance_drift event emitted for {', '.join(all_failing)}",
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
            compliance_controls=compliance_controls,
        )

    @_serialize_action
    def inject_ssh_drift(self) -> dict[str, Any]:
        """Inject SSH drift into the lab state using Ansible."""

        if self._mock_mode:
            state = self._load_state()
            raw = self._controls_from_state(
                state,
                ssh_root_login=True,
                portal_service_health=True,
            )
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
        try:
            job = self._run_playbook("playbooks/drift_ssh_root.yml", self._ansible_vars(env_dir))
            self._set_job_status(
                action=ActionName.INJECT_SSH_DRIFT.value,
                status="succeeded",
                detail="ssh drift injection completed",
                job=job,
            )
        except Exception as exc:
            self._set_job_status(
                action=ActionName.INJECT_SSH_DRIFT.value,
                status="failed",
                detail=f"ssh drift injection failed: {exc}",
                job={"backend": self._execution_mode, "job_id": ""},
            )
            raise
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

    @_serialize_action
    def inject_service_drift(self) -> dict[str, Any]:
        """Inject portal service drift into the lab state using Ansible."""

        if self._mock_mode:
            state = self._load_state()
            raw = self._controls_from_state(
                state,
                ssh_root_login=True,
                portal_service_health=True,
            )
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
        try:
            job = self._run_playbook(DRIFT_SERVICE_PLAYBOOK, extra_vars)
            self._set_job_status(
                action=ActionName.INJECT_SERVICE_DRIFT.value,
                status="succeeded",
                detail="service drift injection completed",
                job=job,
            )
        except Exception as exc:
            self._set_job_status(
                action=ActionName.INJECT_SERVICE_DRIFT.value,
                status="failed",
                detail=f"service drift injection failed: {exc}",
                job={"backend": self._execution_mode, "job_id": ""},
            )
            raise
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

    @_serialize_action
    def run_remediation(self) -> dict[str, Any]:
        """Restore the approved state for all local-lab controls."""

        if self._mock_mode:
            rem_controls: dict[str, bool] = {
                "ssh_root_login": True,
                "portal_service_health": True,
            }
            rem_compliance: dict[str, bool] = {
                "ssh_root_login": True,
                "ssh_password_authentication": True,
            }
            response = self._record_action(
                ActionName.RUN_REMEDIATION.value,
                ActionStatus.SUCCEEDED.value,
                "run_remediation succeeded (mock): all controls restored",
                "ok",
                controls=rem_controls,
                compliance_controls=rem_compliance,
            )
            if self._load_state().get("eda_enabled"):
                self._append_eda_event("remediation complete - all drift cleared", "ok")
                response["state"] = self.get_state()
            return response

        current = self._current_environment()
        env_dir = Path(str(current["runtime_dir"]))
        try:
            ssh_job = self._run_playbook(
                "playbooks/remediate_ssh_root.yml", self._ansible_vars(env_dir)
            )
            svc_vars = self._ansible_vars(env_dir)
            svc_vars.update({"drift_action": "remediate", "portal_service": str(current["portal"])})
            svc_job = self._run_playbook(DRIFT_SERVICE_PLAYBOOK, svc_vars)
            self._set_job_status(
                action=ActionName.RUN_REMEDIATION.value,
                status="succeeded",
                detail="remediation workflow completed",
                job={
                    "backend": svc_job.get("backend", ssh_job.get("backend", "direct")),
                    "job_id": svc_job.get("job_id", ssh_job.get("job_id", "")),
                    "jobs": [ssh_job, svc_job],
                },
            )
        except Exception as exc:
            self._set_job_status(
                action=ActionName.RUN_REMEDIATION.value,
                status="failed",
                detail=f"remediation workflow failed: {exc}",
                job={"backend": self._execution_mode, "job_id": ""},
            )
            raise
        controls = self._read_controls(env_dir)
        compliance_controls = self._read_compliance_controls(env_dir)
        response = self._record_action(
            ActionName.RUN_REMEDIATION.value,
            ActionStatus.SUCCEEDED.value,
            "run_remediation succeeded: restored PermitRootLogin no and portal service running",
            "ok",
            controls=controls,
            compliance_controls=compliance_controls,
        )
        if self._load_state().get("eda_enabled"):
            self._append_eda_event("remediation complete - all drift cleared", "ok")
            response["state"] = self.get_state()
        return response

    @_serialize_action
    def inject_synthetic_incident(self) -> dict[str, Any]:
        """Emit a synthetic incident event for demo storytelling."""

        timestamp = int(self._clock())
        incident: dict[str, Any] = {
            "id": f"incident-{timestamp}",
            "severity": "high",
            "component": "control-plane",
            "message": "Synthetic incident emitted for demo narrative control.",
            "created_at": timestamp,
        }

        def mutate(state: dict[str, Any]) -> None:
            incidents = state.setdefault("incidents", [])
            incidents.insert(0, incident)
            del incidents[STATE_LOG_LIMIT:]

        self._mutate_state(mutate)
        state = self._load_state()
        if state.get("eda_enabled"):
            self._append_eda_event("synthetic incident emitted", "warn")
            return self._record_action(
                ActionName.INJECT_SYNTHETIC_INCIDENT.value,
                ActionStatus.SUCCEEDED.value,
                "synthetic incident injected: demo incident added to feed",
                "warn",
            )
        return self._record_action(
            ActionName.INJECT_SYNTHETIC_INCIDENT.value,
            ActionStatus.SUCCEEDED.value,
            "synthetic incident injected: demo incident added to feed",
            "ok",
        )

    def _current_environment(self) -> dict[str, Any]:
        state = self._load_state()
        current = _as_str_any_dict(state.get("current"))
        if not current:
            raise RuntimeError("No environment has been created yet.")
        required_keys = ("runtime_dir", "runtime_vars")
        missing = [key for key in required_keys if key not in current]
        if missing:
            missing_joined = ", ".join(missing)
            raise RuntimeError(
                f"Current environment is missing runtime context ({missing_joined}). "
                "Recreate the environment."
            )
        return current

    def _terraform_apply(
        self,
        env_dir: Path,
        *,
        environment_name: str,
        portal: str,
        profile: str,
        target: str = "local-lab",  # noqa: ARG002  # NOSONAR
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

    def _run_playbook(self, playbook: str, extra_vars: dict[str, Any]) -> dict[str, Any]:
        if self._execution_mode == "awx":
            return self._run_awx_job_template(playbook, extra_vars)

        vars_path = self.runtime_root / (
            f"extra-vars-{Path(playbook).stem}-{threading.get_ident()}-{time.time_ns()}.json"
        )
        vars_path.parent.mkdir(parents=True, exist_ok=True)
        vars_path.write_text(json.dumps(extra_vars), encoding="utf-8")
        env = os.environ.copy()
        env["ANSIBLE_CONFIG"] = str(self.ansible_root / "ansible.cfg")
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
            return {
                "backend": "direct",
                "job_id": f"local-{time.time_ns()}",
                "playbook": playbook,
                "status": "successful",
            }
        finally:
            vars_path.unlink(missing_ok=True)

    def _run_awx_job_template(self, playbook: str, extra_vars: dict[str, Any]) -> dict[str, Any]:
        template_map = {
            "playbooks/aap_operationalise.yml": "terraable-operationalise",
            "playbooks/compliance_scan.yml": "terraable-compliance-scan",
            "playbooks/drift_ssh_root.yml": "terraable-drift-ssh-root",
            "playbooks/remediate_ssh_root.yml": "terraable-remediate-ssh",
            DRIFT_SERVICE_PLAYBOOK: "terraable-drift-second-scenario",
        }
        template_name = template_map.get(playbook)
        if not template_name:
            raise RuntimeError(f"No AWX template mapping configured for playbook {playbook}")

        awx_host = os.getenv("AWX_HOST", "").strip().rstrip("/")
        awx_username = os.getenv("AWX_USERNAME", "").strip()
        awx_password = os.getenv("AWX_PASSWORD", "").strip()
        if not awx_host or not awx_username or not awx_password:
            raise RuntimeError("AWX execution requires AWX_HOST, AWX_USERNAME, and AWX_PASSWORD")
        if not awx_host.startswith("https://"):
            raise RuntimeError("AWX_HOST must use an https:// URL")

        template_response = self._awx_request(
            awx_host,
            awx_username,
            awx_password,
            f"/api/v2/job_templates/?name={template_name}",
            method="GET",
        )
        results = template_response.get("results", [])
        first_result = cast(
            dict[str, Any], results[0] if isinstance(results, list) and results else {}
        )
        template_id = int(first_result.get("id", 0))
        if not template_id:
            raise RuntimeError(f"AWX template not found: {template_name}")

        launch_payload = json.dumps({"extra_vars": extra_vars}).encode("utf-8")
        launch_response = self._awx_request(
            awx_host,
            awx_username,
            awx_password,
            f"/api/v2/job_templates/{template_id}/launch/",
            method="POST",
            body=launch_payload,
        )
        job_id = int(launch_response.get("job", launch_response.get("id", 0)))
        if not job_id:
            raise RuntimeError(f"AWX did not return job id for template {template_name}")

        max_polls = 300
        for _ in range(max_polls):
            job_response = self._awx_request(
                awx_host,
                awx_username,
                awx_password,
                f"/api/v2/jobs/{job_id}/",
                method="GET",
            )
            status = str(job_response.get("status", "")).lower()
            if status == "successful":
                return {
                    "backend": "awx",
                    "job_id": str(job_id),
                    "playbook": playbook,
                    "template": template_name,
                    "status": status,
                }
            if status in {"failed", "error", "canceled"}:
                raise RuntimeError(
                    f"AWX job {job_id} for {template_name} ended with status {status}"
                )
            time.sleep(1)

        raise RuntimeError(f"AWX job {job_id} for {template_name} timed out")

    def _awx_request(
        self,
        host: str,
        username: str,
        password: str,
        path: str,
        *,
        method: str,
        body: bytes | None = None,
    ) -> dict[str, Any]:
        token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        request = Request(
            url=f"{host}{path}",
            method=method,
            data=body,
            headers={
                "Authorization": f"Basic {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                try:
                    payload = json.loads(response.read().decode("utf-8"))
                except ValueError as exc:
                    raise RuntimeError(f"AWX API response parse failed for {path}") from exc
                if isinstance(payload, dict):
                    return cast(dict[str, Any], payload)
                raise RuntimeError("AWX API response is not a JSON object")
        except URLError as exc:
            raise RuntimeError(f"AWX API request failed for {path}") from exc

    def _ansible_vars(self, env_dir: Path) -> dict[str, Any]:
        current = self._current_environment()
        runtime_vars = _as_str_any_dict(current["runtime_vars"]).copy()
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

    def _read_compliance_controls(self, env_dir: Path) -> dict[str, bool]:
        ssh_text = (env_dir / "sshd_config").read_text(encoding="utf-8")
        return {
            "ssh_root_login": "PermitRootLogin no" in ssh_text,
            "ssh_password_authentication": "PasswordAuthentication no" in ssh_text,
        }

    def _ensure_environment(
        self,
        environment_name: str,
        *,
        ansible_inventory_group: str = "local_lab",
    ) -> Path:
        env_dir = self.runtime_root / environment_name
        env_dir.mkdir(parents=True, exist_ok=True)
        inventory = env_dir / "inventory.yml"
        inventory.write_text(
            "all:\n"
            "  children:\n"
            f"    {ansible_inventory_group}:\n"
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
        compliance_controls: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        def mutate(state: dict[str, Any]) -> None:
            evidence = state.setdefault("evidence", [])
            evidence.insert(0, {"message": detail, "tone": tone})
            del evidence[STATE_LOG_LIMIT:]
            if controls is not None:
                state["controls"] = controls
            if compliance_controls is not None:
                state["compliance_controls"] = compliance_controls

        self._mutate_state(mutate)
        return {
            "action": action,
            "status": status,
            "detail": detail,
            "tone": tone,
            "state": self.get_state(),
        }

    def _append_eda_event(self, detail: str, tone: str) -> None:
        def mutate(state: dict[str, Any]) -> None:
            history = state.setdefault("eda_history", [])
            history.insert(0, {"message": detail, "tone": tone})
            del history[STATE_LOG_LIMIT:]

        self._mutate_state(mutate)

    def _set_terraform_status(self, *, status: str, detail: str, run_id: str) -> None:
        def mutate(state: dict[str, Any]) -> None:
            state["terraform"] = {
                "run_id": run_id,
                "status": status,
                "detail": detail,
                "updated_at": int(self._clock()),
            }

        self._mutate_state(mutate)

    def _set_job_status(
        self,
        *,
        action: str,
        status: str,
        detail: str,
        job: dict[str, Any],
    ) -> None:
        def mutate(state: dict[str, Any]) -> None:
            jobs = _as_str_any_dict(state.get("jobs"))
            history = cast(list[dict[str, Any]], jobs.get("history", []))
            record: dict[str, Any] = {
                "action": action,
                "status": status,
                "detail": detail,
                "backend": str(job.get("backend", "direct")),
                "job_id": str(job.get("job_id", "")),
                "updated_at": int(self._clock()),
            }
            history.insert(0, record)
            del history[STATE_LOG_LIMIT:]
            state["jobs"] = {
                "last_action": action,
                "last_status": status,
                "last_detail": detail,
                "last_backend": record["backend"],
                "last_job_id": record["job_id"],
                "history": history,
            }

        self._mutate_state(mutate)

    def _score_pct(self, controls: dict[str, bool]) -> int:
        total = len(controls)
        passed = sum(1 for value in controls.values() if value)
        return round((passed / total) * 100) if total else 0

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return {
            "current": None,
            "controls": {
                "ssh_root_login": False,
                "portal_service_health": False,
            },
            "compliance_controls": {
                "ssh_root_login": False,
                "ssh_password_authentication": False,
            },
            "terraform": {
                "run_id": None,
                "status": "idle",
                "detail": "terraform has not run yet",
                "updated_at": 0,
            },
            "jobs": {
                "last_action": None,
                "last_status": "idle",
                "last_detail": "no workflow has run yet",
                "last_backend": None,
                "last_job_id": None,
                "history": [],
            },
            "evidence": [],
            "eda_history": [],
            "incidents": [],
            "trend": [],
            "scan_count": 0,
            "eda_enabled": False,
        }

    def _build_observability(self, state: dict[str, Any]) -> dict[str, Any]:
        terraform = _as_str_any_dict(state.get("terraform"))
        jobs = _as_str_any_dict(state.get("jobs"))
        job_history = cast(list[dict[str, Any]], jobs.get("history", []))

        traces: list[dict[str, Any]] = []
        terraform_updated_at = int(terraform.get("updated_at", 0) or 0)
        if terraform_updated_at:
            traces.append(
                {
                    "stage": "terraform",
                    "status": str(terraform.get("status", "unknown")),
                    "at": terraform_updated_at,
                    "depends_on": [],
                }
            )

        for job in job_history[:8]:
            traces.append(
                {
                    "stage": str(job.get("action", "workflow")),
                    "status": str(job.get("status", "unknown")),
                    "at": int(job.get("updated_at", 0) or 0),
                    "depends_on": ["terraform"],
                }
            )

        return {
            "stages": traces,
            "summary": {
                "last_stage": str(jobs.get("last_action") or "terraform"),
                "last_status": str(jobs.get("last_status") or terraform.get("status", "idle")),
            },
        }

    def _load_state(self) -> dict[str, Any]:
        with self._state_lock:
            if not self.state_file.exists():
                return self._default_state()
            try:
                raw_state = json.loads(self.state_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return self._default_state()
            return (
                cast(dict[str, Any], raw_state)
                if isinstance(raw_state, dict)
                else self._default_state()
            )

    def _save_state(self, state: dict[str, Any]) -> None:
        with self._state_lock:
            self.runtime_root.mkdir(parents=True, exist_ok=True)
            temp_path = self.runtime_root / f"state-{threading.get_ident()}-{time.time_ns()}.json"
            temp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            temp_path.replace(self.state_file)

    def _mutate_state(self, mutator: StateMutator) -> None:
        with self._state_lock:
            state = self._load_state()
            mutator(state)
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
        with self._credentials_lock:
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
        with self._credentials_lock:
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
        return hostname_to_token_env_var(hostname)

    def _apply_credential_value(self, key: str, value: str) -> None:
        trimmed = value.strip()
        existing = self._credentials.get(key)
        if trimmed:
            self._credentials[key] = self._ui_credential_entry(trimmed, existing)
            return
        if existing and existing.get("source") == "ui":
            restored = self._restore_credential_entry(existing)
            if restored is not None:
                self._credentials[key] = restored
            else:
                self._credentials.pop(key, None)

    def _ui_credential_entry(
        self,
        value: str,
        existing: CredentialEntry | None,
    ) -> CredentialEntry:
        next_item: CredentialEntry = {"value": value, "source": "ui"}
        if not existing:
            return next_item

        existing_source = existing.get("source", "")
        if existing_source != "ui":
            next_item["fallback_value"] = existing.get("value", "")
            next_item["fallback_source"] = existing_source
            return next_item

        fallback_value = existing.get("fallback_value", "")
        fallback_source = existing.get("fallback_source", "")
        if fallback_value and fallback_source:
            next_item["fallback_value"] = fallback_value
            next_item["fallback_source"] = fallback_source
        return next_item

    def _restore_credential_entry(self, existing: CredentialEntry) -> CredentialEntry | None:
        fallback_value = existing.get("fallback_value", "").strip()
        fallback_source = existing.get("fallback_source", "").strip()
        if fallback_value and fallback_source:
            return {"value": fallback_value, "source": fallback_source}
        return None

    def _controls_from_state(
        self,
        state: dict[str, Any],
        *,
        ssh_root_login: bool,
        portal_service_health: bool,
    ) -> dict[str, bool]:
        raw = _as_str_any_dict(state.get("controls"))
        return {
            "ssh_root_login": bool(raw.get("ssh_root_login", ssh_root_login)),
            "portal_service_health": bool(raw.get("portal_service_health", portal_service_health)),
        }
