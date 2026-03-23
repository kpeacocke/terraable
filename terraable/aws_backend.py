"""AWS backend for Terraform provisioning and Ansible operationalisation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .contract import build_handoff_payload
from .local_lab import (
    CREDENTIAL_KEYS,
    EXECUTION_MODE_ENV_VAR,
    HCP_TOKEN_REQUIREMENT,
    MOCK_MODE_ENV_VAR,
    CommandResult,
    CommandRunner,
    LocalLabBackend,
    default_runner,
)
from .orchestrator import ActionName, ActionStatus


class AWSBackend(LocalLabBackend):
    """Run Terraform provisioning and Ansible operationalisation against AWS."""

    def __init__(
        self,
        workspace_root: Path,
        *,
        runner: CommandRunner | None = None,
        clock: callable | None = None,
    ) -> None:
        """Initialise AWS backend with AWS-specific terraform module paths."""
        super().__init__(workspace_root, runner=runner, clock=clock)
        self.terraform_root = workspace_root / "terraform" / "modules" / "substrate_aws"
        self.runtime_root = workspace_root / ".terraable" / "aws"
        self.state_file = self.runtime_root / "state.json"
        self._mock_mode = os.getenv(MOCK_MODE_ENV_VAR, "").lower() in {"1", "true", "yes"}
        self._execution_mode = os.getenv(EXECUTION_MODE_ENV_VAR, "direct").strip().lower()

    def get_auth_status(self, *, target: str, portal: str) -> dict[str, Any]:
        """Return authentication and readiness checks for AWS target."""
        if target != "aws":
            return {
                "authenticated": False,
                "ready": False,
                "required_credentials": [],
                "missing_credentials": [],
                "credential_sources": {"mode": "unsupported"},
                "blockers": [f"target={target} is not supported by AWS backend"],
            }

        return super().get_auth_status(target=target, portal=portal)

    def create_environment(
        self,
        *,
        target: str,
        portal: str,
        profile: str,
        eda: str,
    ) -> dict[str, Any]:
        """Create an AWS environment and its Terraform-to-Ansible handoff contract."""
        if target != "aws":
            return self._record_action(
                ActionName.CREATE_ENVIRONMENT.value,
                ActionStatus.FAILED.value,
                f"AWS backend does not support target={target}",
                "fail",
            )

        if self._mock_mode:
            environment_name = f"mock-aws-{int(self._clock())}"
            run_id = f"mock-aws-{environment_name}"
            self._set_terraform_status(
                status="applied",
                detail=f"mock terraform apply completed for {environment_name}",
                run_id=run_id,
            )
            env_dir = self._ensure_environment(environment_name)
            runtime_vars: dict[str, Any] = {
                "environment_name": environment_name,
                "terraform_run_id": run_id,
                "target_platform": "aws",
                "portal_impl": portal,
                "security_profile": profile,
                "connection": {
                    "ansible_inventory_group": "aws_instances",
                    "ssh_user": "ec2-user",
                    "ssh_port": 22,
                    "api_endpoint": "https://us-east-1.api.aws.example.com",
                },
                "metadata": {"mode": "offline-mock", "runtime_dir": str(env_dir)},
            }
            state = self._load_state()
            state["current"] = {
                "environment_name": environment_name,
                "target": "aws",
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
                f"create_environment succeeded (mock): {environment_name} provisioned on AWS",
                "ok",
            )

        auth = self.get_auth_status(target="aws", portal=portal)
        if not auth["ready"]:
            return self._record_action(
                ActionName.CREATE_ENVIRONMENT.value,
                ActionStatus.FAILED.value,
                "create_environment blocked: " + "; ".join(auth["blockers"]),
                "fail",
            )

        environment_name = f"aws-{int(self._clock())}"
        run_id = f"aws-{environment_name}"
        env_dir = self._ensure_environment(environment_name)
        self._set_terraform_status(
            status="running",
            detail=f"terraform apply started for {environment_name}",
            run_id=run_id,
        )

        try:
            # AWS-specific terraform apply with required variables
            outputs = self._terraform_apply_aws(
                env_dir,
                environment_name=environment_name,
                portal=portal,
                profile=profile,
            )
            tf_target = str(outputs.get("target_platform", "aws"))
            payload = build_handoff_payload(
                environment_name=str(outputs["environment_name"]),
                terraform_run_id=run_id,
                target_platform=tf_target,
                portal_impl=str(outputs["portal_impl"]),
                security_profile=str(outputs["security_profile"]),
                connection=dict(outputs["connection"]),
                metadata={"mode": "aws", "runtime_dir": str(env_dir)},
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

    def _terraform_apply_aws(
        self,
        env_dir: Path,
        *,
        environment_name: str,
        portal: str,
        profile: str,
    ) -> dict[str, Any]:
        """Execute Terraform apply for AWS substrate module with required variables."""
        # Check for SSH public key
        ssh_public_key = os.getenv("TF_VAR_ssh_public_key", "").strip()
        if not ssh_public_key:
            raise ValueError(
                "TF_VAR_ssh_public_key environment variable is required for AWS provisioning"
            )

        allowed_cidr = os.getenv("TF_VAR_allowed_cidr_blocks", "").strip()
        if not allowed_cidr:
            raise ValueError(
                "TF_VAR_allowed_cidr_blocks environment variable is required for AWS provisioning"
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

        # Apply terraform with AWS-specific variables
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
                "-var",
                f"ansible_inventory_group=aws_instances",
                "-var",
                f"ssh_user=ec2-user",
                "-var",
                f"ssh_port=22",
                "-var",
                f"ssh_public_key={ssh_public_key}",
                "-var",
                f'allowed_cidr_blocks=["{allowed_cidr}"]',
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
