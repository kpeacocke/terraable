"""OKD backend for Terraform provisioning and Ansible operationalisation."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from .contract import build_handoff_payload
from .local_lab import (
    MOCK_MODE_ENV_VAR,
    CommandRunner,
    LocalLabBackend,
)
from .orchestrator import ActionName, ActionStatus


def _serialize_backend_action(
    method: Callable[..., dict[str, Any]],
) -> Callable[..., dict[str, Any]]:
    @wraps(method)
    def wrapped(self: LocalLabBackend, *args: Any, **kwargs: Any) -> dict[str, Any]:
        with self.action_lock:
            return method(self, *args, **kwargs)

    return wrapped


class OKDBackend(LocalLabBackend):
    """Run Terraform provisioning and Ansible operationalisation against OKD."""

    def __init__(
        self,
        workspace_root: Path,
        *,
        runner: CommandRunner | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """Initialise OKD backend with OKD-specific terraform module paths."""
        super().__init__(workspace_root, runner=runner, clock=clock)
        self.terraform_root = workspace_root / "terraform" / "modules" / "substrate_okd"
        self.runtime_root = workspace_root / ".terraable" / "okd"
        self.state_file = self.runtime_root / "state.json"
        self._mock_mode = os.getenv(MOCK_MODE_ENV_VAR, "").lower() in {"1", "true", "yes"}

    def get_auth_status(self, *, target: str, portal: str) -> dict[str, Any]:
        """Return authentication and readiness checks for OKD target."""
        if target != "okd":
            return {
                "authenticated": False,
                "ready": False,
                "required_credentials": [],
                "missing_credentials": [],
                "credential_sources": {"mode": "unsupported"},
                "blockers": [f"target={target} is not supported by OKD backend"],
            }

        status = super().get_auth_status(target=target, portal=portal)
        if self._mock_mode:
            return status

        blockers = [str(item) for item in status.get("blockers", [])]
        filtered_blockers = [
            blocker
            for blocker in blockers
            if "target=okd is not executable in live mode" not in blocker
        ]

        cluster_name = os.getenv(
            "TF_VAR_CLUSTER_NAME", os.getenv("TF_VAR_cluster_name", "")
        ).strip()
        base_domain = os.getenv("TF_VAR_BASE_DOMAIN", os.getenv("TF_VAR_base_domain", "")).strip()
        if not cluster_name:
            filtered_blockers.append(
                "TF_VAR_cluster_name environment variable is required for OKD provisioning"
            )
        if not base_domain:
            filtered_blockers.append(
                "TF_VAR_base_domain environment variable is required for OKD provisioning"
            )

        status["blockers"] = filtered_blockers
        status["ready"] = bool(status.get("authenticated")) and not filtered_blockers
        return status

    def get_state(self) -> dict[str, Any]:
        """Return persisted UI state with OKD-specific execution mode label."""
        state = super().get_state()
        state["mode"] = "offline-mock" if self._mock_mode else "live-okd"
        return state

    @_serialize_backend_action
    def create_environment(
        self,
        *,
        target: str,
        portal: str,
        profile: str,
        eda: str,
    ) -> dict[str, Any]:
        """Create an OKD environment and its Terraform-to-Ansible handoff contract."""
        if target != "okd":
            return self._record_action(
                ActionName.CREATE_ENVIRONMENT.value,
                ActionStatus.FAILED.value,
                f"OKD backend does not support target={target}",
                "fail",
            )

        if self._mock_mode:
            environment_name = f"mock-okd-{int(self._clock())}"
            run_id = environment_name
            self._set_terraform_status(
                status="applied",
                detail=f"mock terraform apply completed for {environment_name}",
                run_id=run_id,
            )
            env_dir = self._ensure_environment(
                environment_name,
                ansible_inventory_group="okd_cluster",
            )
            runtime_vars: dict[str, Any] = {
                "environment_name": environment_name,
                "terraform_run_id": run_id,
                "target_platform": "okd",
                "portal_impl": portal,
                "security_profile": profile,
                "connection": {
                    "ansible_inventory_group": "okd_cluster",
                    "ssh_user": "core",
                    "ssh_port": 22,
                    "api_endpoint": "https://api.okd.example.local:6443",
                },
                "metadata": {"mode": "offline-mock", "runtime_dir": str(env_dir)},
            }
            state = self._load_state()
            state["current"] = {
                "environment_name": environment_name,
                "target": "okd",
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
                f"create_environment succeeded (mock): {environment_name} provisioned on OKD",
                "ok",
            )

        auth = self.get_auth_status(target="okd", portal=portal)
        if not auth["ready"]:
            return self._record_action(
                ActionName.CREATE_ENVIRONMENT.value,
                ActionStatus.FAILED.value,
                "create_environment blocked: " + "; ".join(auth["blockers"]),
                "fail",
            )

        environment_name = f"okd-{int(self._clock())}"
        run_id = environment_name
        env_dir = self._ensure_environment(
            environment_name,
            ansible_inventory_group="okd_cluster",
        )
        self._set_terraform_status(
            status="running",
            detail=f"terraform apply started for {environment_name}",
            run_id=run_id,
        )

        try:
            # OKD-specific terraform apply with required variables
            outputs = self._terraform_apply_okd(
                env_dir,
                environment_name=environment_name,
                portal=portal,
                profile=profile,
            )
            tf_target = str(outputs.get("target_platform", "okd"))
            payload = build_handoff_payload(
                environment_name=str(outputs["environment_name"]),
                terraform_run_id=run_id,
                target_platform=tf_target,
                portal_impl=str(outputs["portal_impl"]),
                security_profile=str(outputs["security_profile"]),
                connection=dict(outputs["connection"]),
                metadata={"mode": "okd", "runtime_dir": str(env_dir)},
            )
        except Exception as exc:
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
                f"portal={portal}, profile={profile}, eda={eda}; "
                f"Terraform state written to {env_dir / 'terraform.tfstate'}"
            ),
            "ok",
        )

    def _terraform_apply_okd(
        self,
        env_dir: Path,
        *,
        environment_name: str,
        portal: str,
        profile: str,
    ) -> dict[str, Any]:
        """Execute Terraform apply for OKD substrate module with required variables."""
        # Check for required OKD cluster configuration
        cluster_name = os.getenv(
            "TF_VAR_CLUSTER_NAME", os.getenv("TF_VAR_cluster_name", "")
        ).strip()
        if not cluster_name:
            raise ValueError(
                "TF_VAR_cluster_name environment variable is required for OKD provisioning"
            )

        base_domain = os.getenv("TF_VAR_BASE_DOMAIN", os.getenv("TF_VAR_base_domain", "")).strip()
        if not base_domain:
            raise ValueError(
                "TF_VAR_base_domain environment variable is required for OKD provisioning"
            )

        # Initialise terraform
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

        # Apply terraform with OKD-specific variables
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
                f"cluster_name={cluster_name}",
                "-var",
                f"base_domain={base_domain}",
                "-var",
                f"portal_impl={portal}",
                "-var",
                f"security_profile={profile}",
                "-var",
                "ansible_inventory_group=okd_cluster",
                "-var",
                "ssh_user=core",
                "-var",
                "ssh_port=22",
            ],
            cwd=self.workspace_root,
            env=None,
        )

        # Extract outputs
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
