"""Azure backend for Terraform provisioning and Ansible operationalisation."""

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


def _serialize_backend_action(method: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    @wraps(method)
    def wrapped(self: LocalLabBackend, *args: Any, **kwargs: Any) -> dict[str, Any]:
        with self.action_lock:
            return method(self, *args, **kwargs)

    return wrapped


class AzureBackend(LocalLabBackend):
    """Run Terraform provisioning and Ansible operationalisation against Azure."""

    def __init__(
        self,
        workspace_root: Path,
        *,
        runner: CommandRunner | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """Initialise Azure backend with Azure-specific terraform module paths."""
        super().__init__(workspace_root, runner=runner, clock=clock)
        self.terraform_root = workspace_root / "terraform" / "modules" / "substrate_azure"
        self.runtime_root = workspace_root / ".terraable" / "azure"
        self.state_file = self.runtime_root / "state.json"
        self._mock_mode = os.getenv(MOCK_MODE_ENV_VAR, "").lower() in {"1", "true", "yes"}

    def get_auth_status(self, *, target: str, portal: str) -> dict[str, Any]:
        """Return authentication and readiness checks for Azure target."""
        if target != "azure":
            return {
                "authenticated": False,
                "ready": False,
                "required_credentials": [],
                "missing_credentials": [],
                "credential_sources": {"mode": "unsupported"},
                "blockers": [f"target={target} is not supported by Azure backend"],
            }

        status = super().get_auth_status(target=target, portal=portal)
        if self._mock_mode:
            return status

        blockers = [str(item) for item in status.get("blockers", [])]
        status["blockers"] = [
            blocker
            for blocker in blockers
            if "target=azure is not executable in live mode" not in blocker
        ]
        if status.get("authenticated") and portal in {"backstage", "rhdh"}:
            status["ready"] = True
        return status

    @_serialize_backend_action
    def create_environment(
        self,
        *,
        target: str,
        portal: str,
        profile: str,
        eda: str,
    ) -> dict[str, Any]:
        """Create an Azure environment and its Terraform-to-Ansible handoff contract."""
        if target != "azure":
            return self._record_action(
                ActionName.CREATE_ENVIRONMENT.value,
                ActionStatus.FAILED.value,
                f"Azure backend does not support target={target}",
                "fail",
            )

        if self._mock_mode:
            environment_name = f"mock-azure-{int(self._clock())}"
            run_id = f"mock-azure-{environment_name}"
            self._set_terraform_status(
                status="applied",
                detail=f"mock terraform apply completed for {environment_name}",
                run_id=run_id,
            )
            env_dir = self._ensure_environment(environment_name)
            runtime_vars: dict[str, Any] = {
                "environment_name": environment_name,
                "terraform_run_id": run_id,
                "target_platform": "azure",
                "portal_impl": portal,
                "security_profile": profile,
                "connection": {
                    "ansible_inventory_group": "azure_vms",
                    "ssh_user": "azureuser",
                    "ssh_port": 22,
                    "api_endpoint": "https://australiaeast.provider.azure.example.com",
                },
                "metadata": {"mode": "offline-mock", "runtime_dir": str(env_dir)},
            }
            state = self._load_state()
            state["current"] = {
                "environment_name": environment_name,
                "target": "azure",
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
                f"create_environment succeeded (mock): {environment_name} provisioned on Azure",
                "ok",
            )

        auth = self.get_auth_status(target="azure", portal=portal)
        if not auth["ready"]:
            return self._record_action(
                ActionName.CREATE_ENVIRONMENT.value,
                ActionStatus.FAILED.value,
                "create_environment blocked: " + "; ".join(auth["blockers"]),
                "fail",
            )

        environment_name = f"azure-{int(self._clock())}"
        run_id = f"azure-{environment_name}"
        env_dir = self._ensure_environment(environment_name)
        self._set_terraform_status(
            status="running",
            detail=f"terraform apply started for {environment_name}",
            run_id=run_id,
        )

        try:
            # Azure-specific terraform apply with required variables
            outputs = self._terraform_apply_azure(
                env_dir,
                environment_name=environment_name,
                portal=portal,
                profile=profile,
            )
            tf_target = str(outputs.get("target_platform", "azure"))
            payload = build_handoff_payload(
                environment_name=str(outputs["environment_name"]),
                terraform_run_id=run_id,
                target_platform=tf_target,
                portal_impl=str(outputs["portal_impl"]),
                security_profile=str(outputs["security_profile"]),
                connection=dict(outputs["connection"]),
                metadata={"mode": "azure", "runtime_dir": str(env_dir)},
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

    def _terraform_apply_azure(
        self,
        env_dir: Path,
        *,
        environment_name: str,
        portal: str,
        profile: str,
    ) -> dict[str, Any]:
        """Execute Terraform apply for Azure substrate module with required variables."""
        # Check for required Azure credentials and configuration
        resource_group = os.getenv(
            "TF_VAR_RESOURCE_GROUP_NAME", os.getenv("TF_VAR_resource_group_name", "")
        ).strip()
        if not resource_group:
            raise ValueError(
                "TF_VAR_resource_group_name environment variable is required for Azure provisioning"
            )

        ssh_public_key = os.getenv(
            "TF_VAR_SSH_PUBLIC_KEY", os.getenv("TF_VAR_ssh_public_key", "")
        ).strip()
        if not ssh_public_key:
            raise ValueError(
                "TF_VAR_ssh_public_key environment variable is required for Azure provisioning"
            )

        allowed_source = os.getenv(
            "TF_VAR_ALLOWED_SOURCE_PREFIX", os.getenv("TF_VAR_allowed_source_prefix", "")
        ).strip()
        if not allowed_source:
            raise ValueError(
                "TF_VAR_allowed_source_prefix environment variable is required for Azure provisioning"
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

        # Apply terraform with Azure-specific variables
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
                f"resource_group_name={resource_group}",
                "-var",
                f"portal_impl={portal}",
                "-var",
                f"security_profile={profile}",
                "-var",
                "ansible_inventory_group=azure_vms",
                "-var",
                "ssh_user=azureuser",
                "-var",
                "ssh_port=22",
                "-var",
                f"ssh_public_key={ssh_public_key}",
                "-var",
                f"allowed_source_prefix={allowed_source}",
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
