"""Tests for AWS, Azure, and OKD backend execution paths."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from terraable.aws_backend import AWSBackend
from terraable.azure_backend import AzureBackend
from terraable.local_lab import MOCK_MODE_ENV_VAR, CommandResult, LocalLabBackend
from terraable.okd_backend import OKDBackend


class _ActionLockProbeAWSBackend(AWSBackend):
    def __init__(self, workspace_root: Path) -> None:
        super().__init__(workspace_root, clock=lambda: 1_700_000_000.0)
        self._probe_lock = threading.Lock()
        self._active_ensures = 0
        self.max_active_ensures = 0

    def _ensure_environment(
        self,
        environment_name: str,
        *,
        ansible_inventory_group: str = "local_lab",
    ) -> Path:
        with self._probe_lock:
            self._active_ensures += 1
            self.max_active_ensures = max(self.max_active_ensures, self._active_ensures)
        try:
            time.sleep(0.05)
            return super()._ensure_environment(
                environment_name,
                ansible_inventory_group=ansible_inventory_group,
            )
        finally:
            with self._probe_lock:
                self._active_ensures -= 1


def _terraform_outputs(target: str, portal: str = "backstage") -> dict[str, Any]:
    return {
        "environment_name": f"{target}-env",
        "target_platform": target,
        "portal_impl": portal,
        "security_profile": "baseline",
        "connection": {
            "ansible_inventory_group": f"{target}_group",
            "ssh_user": "user",
            "ssh_port": 22,
            "api_endpoint": f"https://api.{target}.example.local",
        },
    }


@pytest.mark.unit
def test_aws_get_auth_status_relaxes_live_target_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = AWSBackend(tmp_path)

    def fake_super(self: LocalLabBackend, *, target: str, portal: str) -> dict[str, Any]:
        del self, target, portal
        return {
            "authenticated": True,
            "ready": False,
            "required_credentials": ["HCP_TOKEN_app_terraform_io"],
            "missing_credentials": [],
            "credential_sources": {},
            "blockers": [
                "target=aws is not executable in live mode; supported live targets: local-lab"
            ],
        }

    monkeypatch.setattr(LocalLabBackend, "get_auth_status", fake_super)

    status = backend.get_auth_status(target="aws", portal="backstage")

    assert status["ready"] is True
    assert status["blockers"] == []


@pytest.mark.unit
def test_azure_get_auth_status_relaxes_live_target_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = AzureBackend(tmp_path)

    def fake_super(self: LocalLabBackend, *, target: str, portal: str) -> dict[str, Any]:
        del self, target, portal
        return {
            "authenticated": True,
            "ready": False,
            "required_credentials": ["HCP_TOKEN_app_terraform_io"],
            "missing_credentials": [],
            "credential_sources": {},
            "blockers": [
                "target=azure is not executable in live mode; supported live targets: local-lab"
            ],
        }

    monkeypatch.setattr(LocalLabBackend, "get_auth_status", fake_super)

    status = backend.get_auth_status(target="azure", portal="rhdh")

    assert status["ready"] is True
    assert status["blockers"] == []


@pytest.mark.unit
def test_okd_get_auth_status_requires_cluster_vars(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = OKDBackend(tmp_path)

    def fake_super(self: LocalLabBackend, *, target: str, portal: str) -> dict[str, Any]:
        del self, target, portal
        return {
            "authenticated": True,
            "ready": False,
            "required_credentials": ["HCP_TOKEN_app_terraform_io"],
            "missing_credentials": [],
            "credential_sources": {},
            "blockers": [
                "target=okd is not executable in live mode; supported live targets: local-lab"
            ],
        }

    monkeypatch.setattr(LocalLabBackend, "get_auth_status", fake_super)
    monkeypatch.delenv("TF_VAR_cluster_name", raising=False)
    monkeypatch.delenv("TF_VAR_base_domain", raising=False)
    monkeypatch.delenv("TF_VAR_CLUSTER_NAME", raising=False)
    monkeypatch.delenv("TF_VAR_BASE_DOMAIN", raising=False)

    status = backend.get_auth_status(target="okd", portal="backstage")

    assert status["ready"] is False
    assert (
        "TF_VAR_cluster_name environment variable is required for OKD provisioning"
        in status["blockers"]
    )
    assert (
        "TF_VAR_base_domain environment variable is required for OKD provisioning"
        in status["blockers"]
    )


@pytest.mark.unit
def test_aws_create_environment_mock_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(MOCK_MODE_ENV_VAR, "true")
    backend = AWSBackend(tmp_path, clock=lambda: 1_700_000_000.0)

    result = backend.create_environment(
        target="aws",
        portal="backstage",
        profile="baseline",
        eda="enabled",
    )

    assert result["status"] == "succeeded"
    state = backend.get_state()
    assert state["current"]["target"] == "aws"


@pytest.mark.unit
def test_azure_create_environment_mock_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(MOCK_MODE_ENV_VAR, "true")
    backend = AzureBackend(tmp_path, clock=lambda: 1_700_000_000.0)

    result = backend.create_environment(
        target="azure",
        portal="rhdh",
        profile="strict",
        eda="disabled",
    )

    assert result["status"] == "succeeded"
    state = backend.get_state()
    assert state["current"]["target"] == "azure"


@pytest.mark.unit
def test_okd_create_environment_mock_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(MOCK_MODE_ENV_VAR, "true")
    backend = OKDBackend(tmp_path, clock=lambda: 1_700_000_000.0)

    result = backend.create_environment(
        target="okd",
        portal="backstage",
        profile="baseline",
        eda="enabled",
    )

    assert result["status"] == "succeeded"
    state = backend.get_state()
    assert state["current"]["target"] == "okd"


@pytest.mark.unit
def test_cloud_backends_reject_wrong_target(tmp_path: Path) -> None:
    assert (
        AWSBackend(tmp_path).create_environment(
            target="azure", portal="backstage", profile="baseline", eda="disabled"
        )["status"]
        == "failed"
    )
    assert (
        AzureBackend(tmp_path).create_environment(
            target="okd", portal="backstage", profile="baseline", eda="disabled"
        )["status"]
        == "failed"
    )
    assert (
        OKDBackend(tmp_path).create_environment(
            target="aws", portal="backstage", profile="baseline", eda="disabled"
        )["status"]
        == "failed"
    )


@pytest.mark.unit
def test_cloud_backends_get_auth_status_rejects_wrong_target(tmp_path: Path) -> None:
    aws_status = AWSBackend(tmp_path).get_auth_status(target="azure", portal="backstage")
    azure_status = AzureBackend(tmp_path).get_auth_status(target="okd", portal="backstage")
    okd_status = OKDBackend(tmp_path).get_auth_status(target="aws", portal="backstage")

    assert aws_status["ready"] is False
    assert aws_status["authenticated"] is False
    assert aws_status["blockers"] == ["target=azure is not supported by AWS backend"]

    assert azure_status["ready"] is False
    assert azure_status["authenticated"] is False
    assert azure_status["blockers"] == ["target=okd is not supported by Azure backend"]

    assert okd_status["ready"] is False
    assert okd_status["authenticated"] is False
    assert okd_status["blockers"] == ["target=aws is not supported by OKD backend"]


@pytest.mark.unit
def test_aws_create_environment_live_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = AWSBackend(tmp_path, clock=lambda: 1_700_000_000.0)
    monkeypatch.setattr(backend, "get_auth_status", lambda **_: {"ready": True, "blockers": []})
    monkeypatch.setattr(backend, "_terraform_apply_aws", lambda *_, **__: _terraform_outputs("aws"))
    monkeypatch.setattr(backend, "_read_controls", lambda _env_dir: {"ssh_root_login": True})
    monkeypatch.setattr(
        backend,
        "_read_compliance_controls",
        lambda _env_dir: {"ssh_root_login": True, "ssh_password_authentication": True},
    )

    result = backend.create_environment(
        target="aws",
        portal="backstage",
        profile="baseline",
        eda="disabled",
    )

    assert result["status"] == "succeeded"
    assert "Terraform state written to" in result["detail"]


@pytest.mark.unit
def test_aws_create_environment_live_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = AWSBackend(tmp_path)
    monkeypatch.setattr(
        backend,
        "get_auth_status",
        lambda **_: {"ready": False, "blockers": ["missing credentials: AWS_ACCESS_KEY_ID"]},
    )

    result = backend.create_environment(
        target="aws",
        portal="backstage",
        profile="baseline",
        eda="disabled",
    )

    assert result["status"] == "failed"
    assert "create_environment blocked:" in result["detail"]


@pytest.mark.unit
def test_aws_create_environment_live_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = AWSBackend(tmp_path, clock=lambda: 1_700_000_000.0)
    monkeypatch.setattr(backend, "get_auth_status", lambda **_: {"ready": True, "blockers": []})

    def boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        raise RuntimeError("terraform apply failed")

    monkeypatch.setattr(backend, "_terraform_apply_aws", boom)

    result = backend.create_environment(
        target="aws",
        portal="backstage",
        profile="baseline",
        eda="disabled",
    )

    assert result["status"] == "failed"
    assert "terraform apply failed" in result["detail"]


@pytest.mark.unit
def test_azure_create_environment_live_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = AzureBackend(tmp_path)
    monkeypatch.setattr(
        backend,
        "get_auth_status",
        lambda **_: {"ready": False, "blockers": ["missing credentials: ARM_CLIENT_ID"]},
    )

    result = backend.create_environment(
        target="azure",
        portal="backstage",
        profile="baseline",
        eda="disabled",
    )

    assert result["status"] == "failed"
    assert "create_environment blocked:" in result["detail"]


@pytest.mark.unit
def test_azure_create_environment_live_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = AzureBackend(tmp_path, clock=lambda: 1_700_000_000.0)
    monkeypatch.setattr(backend, "get_auth_status", lambda **_: {"ready": True, "blockers": []})
    monkeypatch.setattr(
        backend,
        "_terraform_apply_azure",
        lambda *_, **__: _terraform_outputs("azure", portal="rhdh"),
    )
    monkeypatch.setattr(backend, "_read_controls", lambda _env_dir: {"ssh_root_login": True})
    monkeypatch.setattr(
        backend,
        "_read_compliance_controls",
        lambda _env_dir: {"ssh_root_login": True, "ssh_password_authentication": True},
    )

    result = backend.create_environment(
        target="azure",
        portal="rhdh",
        profile="baseline",
        eda="enabled",
    )

    assert result["status"] == "succeeded"


@pytest.mark.unit
def test_azure_create_environment_live_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = AzureBackend(tmp_path, clock=lambda: 1_700_000_000.0)
    monkeypatch.setattr(backend, "get_auth_status", lambda **_: {"ready": True, "blockers": []})

    def boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        raise RuntimeError("azure terraform failed")

    monkeypatch.setattr(backend, "_terraform_apply_azure", boom)

    result = backend.create_environment(
        target="azure",
        portal="backstage",
        profile="baseline",
        eda="disabled",
    )

    assert result["status"] == "failed"
    assert "azure terraform failed" in result["detail"]


@pytest.mark.unit
def test_okd_create_environment_live_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = OKDBackend(tmp_path, clock=lambda: 1_700_000_000.0)
    monkeypatch.setattr(backend, "get_auth_status", lambda **_: {"ready": True, "blockers": []})

    def boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        raise RuntimeError("terraform failed")

    monkeypatch.setattr(backend, "_terraform_apply_okd", boom)

    result = backend.create_environment(
        target="okd",
        portal="backstage",
        profile="baseline",
        eda="disabled",
    )

    assert result["status"] == "failed"
    assert "terraform failed" in result["detail"]


@pytest.mark.unit
def test_okd_create_environment_live_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = OKDBackend(tmp_path)
    monkeypatch.setattr(
        backend,
        "get_auth_status",
        lambda **_: {
            "ready": False,
            "blockers": [
                "TF_VAR_cluster_name environment variable is required for OKD provisioning"
            ],
        },
    )

    result = backend.create_environment(
        target="okd",
        portal="backstage",
        profile="baseline",
        eda="disabled",
    )

    assert result["status"] == "failed"
    assert "create_environment blocked:" in result["detail"]


@pytest.mark.unit
def test_okd_create_environment_live_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = OKDBackend(tmp_path, clock=lambda: 1_700_000_000.0)
    monkeypatch.setattr(backend, "get_auth_status", lambda **_: {"ready": True, "blockers": []})
    monkeypatch.setattr(backend, "_terraform_apply_okd", lambda *_, **__: _terraform_outputs("okd"))
    monkeypatch.setattr(backend, "_read_controls", lambda _env_dir: {"ssh_root_login": True})
    monkeypatch.setattr(
        backend,
        "_read_compliance_controls",
        lambda _env_dir: {"ssh_root_login": True, "ssh_password_authentication": True},
    )

    result = backend.create_environment(
        target="okd",
        portal="backstage",
        profile="baseline",
        eda="enabled",
    )

    assert result["status"] == "succeeded"


@pytest.mark.unit
def test_aws_terraform_apply_parses_comma_cidrs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str], cwd: Path | None, env: dict[str, str] | None) -> CommandResult:
        del cwd, env
        calls.append(argv)
        if "output" in argv:
            return CommandResult(
                stdout=json.dumps(
                    {
                        "environment_name": {"value": "aws-env"},
                        "target_platform": {"value": "aws"},
                        "portal_impl": {"value": "backstage"},
                        "security_profile": {"value": "baseline"},
                        "connection": {
                            "value": {
                                "ansible_inventory_group": "aws_instances",
                                "ssh_user": "ec2-user",
                                "ssh_port": 22,
                                "api_endpoint": "https://api.aws.example.local",
                            }
                        },
                    }
                ),
                stderr="",
            )
        return CommandResult(stdout="", stderr="")

    backend = AWSBackend(tmp_path, runner=runner)
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True)
    monkeypatch.setenv("TF_VAR_ssh_public_key", "ssh-rsa AAAA")
    monkeypatch.setenv("TF_VAR_allowed_cidr_blocks", "10.0.0.0/24,192.168.1.0/24")

    result = backend._terraform_apply_aws(
        env_dir,
        environment_name="aws-env",
        portal="backstage",
        profile="baseline",
    )

    apply_call = next(call for call in calls if "apply" in call)
    assert 'allowed_cidr_blocks=["10.0.0.0/24", "192.168.1.0/24"]' in apply_call
    assert result["environment_name"] == "aws-env"


@pytest.mark.unit
def test_aws_terraform_apply_rejects_invalid_json_cidrs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = AWSBackend(tmp_path, runner=lambda *_, **__: CommandResult(stdout="", stderr=""))
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True)
    monkeypatch.setenv("TF_VAR_ssh_public_key", "ssh-rsa AAAA")
    monkeypatch.setenv("TF_VAR_allowed_cidr_blocks", "[invalid-json")

    with pytest.raises(ValueError, match="must be valid JSON"):
        backend._terraform_apply_aws(
            env_dir,
            environment_name="aws-env",
            portal="backstage",
            profile="baseline",
        )


@pytest.mark.unit
def test_aws_terraform_apply_requires_ssh_public_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = AWSBackend(tmp_path, runner=lambda *_, **__: CommandResult(stdout="", stderr=""))
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True)
    monkeypatch.delenv("TF_VAR_ssh_public_key", raising=False)
    monkeypatch.delenv("TF_VAR_SSH_PUBLIC_KEY", raising=False)

    with pytest.raises(ValueError, match="TF_VAR_ssh_public_key"):
        backend._terraform_apply_aws(
            env_dir,
            environment_name="aws-env",
            portal="backstage",
            profile="baseline",
        )


@pytest.mark.unit
def test_aws_terraform_apply_requires_allowed_cidrs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = AWSBackend(tmp_path, runner=lambda *_, **__: CommandResult(stdout="", stderr=""))
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True)
    monkeypatch.setenv("TF_VAR_ssh_public_key", "ssh-rsa AAAA")
    monkeypatch.delenv("TF_VAR_allowed_cidr_blocks", raising=False)
    monkeypatch.delenv("TF_VAR_ALLOWED_CIDR_BLOCKS", raising=False)

    with pytest.raises(ValueError, match="TF_VAR_allowed_cidr_blocks"):
        backend._terraform_apply_aws(
            env_dir,
            environment_name="aws-env",
            portal="backstage",
            profile="baseline",
        )


@pytest.mark.unit
def test_aws_terraform_apply_rejects_non_string_json_list(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backend = AWSBackend(tmp_path, runner=lambda *_, **__: CommandResult(stdout="", stderr=""))
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True)
    monkeypatch.setenv("TF_VAR_ssh_public_key", "ssh-rsa AAAA")
    monkeypatch.setenv("TF_VAR_allowed_cidr_blocks", '["10.0.0.0/24", 42]')

    with pytest.raises(ValueError, match="list of CIDR strings"):
        backend._terraform_apply_aws(
            env_dir,
            environment_name="aws-env",
            portal="backstage",
            profile="baseline",
        )


@pytest.mark.unit
def test_aws_terraform_apply_rejects_empty_json_list(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backend = AWSBackend(tmp_path, runner=lambda *_, **__: CommandResult(stdout="", stderr=""))
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True)
    monkeypatch.setenv("TF_VAR_ssh_public_key", "ssh-rsa AAAA")
    monkeypatch.setenv("TF_VAR_allowed_cidr_blocks", '["   "]')

    with pytest.raises(ValueError, match="must contain at least one CIDR"):
        backend._terraform_apply_aws(
            env_dir,
            environment_name="aws-env",
            portal="backstage",
            profile="baseline",
        )


@pytest.mark.unit
def test_azure_terraform_apply_requires_resource_group(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = AzureBackend(tmp_path, runner=lambda *_, **__: CommandResult(stdout="", stderr=""))
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True)
    monkeypatch.delenv("TF_VAR_resource_group_name", raising=False)
    monkeypatch.delenv("TF_VAR_RESOURCE_GROUP_NAME", raising=False)

    with pytest.raises(ValueError, match="TF_VAR_resource_group_name"):
        backend._terraform_apply_azure(
            env_dir,
            environment_name="azure-env",
            portal="backstage",
            profile="baseline",
        )


@pytest.mark.unit
def test_azure_terraform_apply_requires_ssh_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = AzureBackend(tmp_path, runner=lambda *_, **__: CommandResult(stdout="", stderr=""))
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True)
    monkeypatch.setenv("TF_VAR_resource_group_name", "rg-demo")
    monkeypatch.delenv("TF_VAR_ssh_public_key", raising=False)
    monkeypatch.delenv("TF_VAR_SSH_PUBLIC_KEY", raising=False)

    with pytest.raises(ValueError, match="TF_VAR_ssh_public_key"):
        backend._terraform_apply_azure(
            env_dir,
            environment_name="azure-env",
            portal="backstage",
            profile="baseline",
        )


@pytest.mark.unit
def test_azure_terraform_apply_requires_allowed_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backend = AzureBackend(tmp_path, runner=lambda *_, **__: CommandResult(stdout="", stderr=""))
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True)
    monkeypatch.setenv("TF_VAR_resource_group_name", "rg-demo")
    monkeypatch.setenv("TF_VAR_ssh_public_key", "ssh-rsa AAAA")
    monkeypatch.delenv("TF_VAR_allowed_source_prefix", raising=False)
    monkeypatch.delenv("TF_VAR_ALLOWED_SOURCE_PREFIX", raising=False)

    with pytest.raises(ValueError, match="TF_VAR_allowed_source_prefix"):
        backend._terraform_apply_azure(
            env_dir,
            environment_name="azure-env",
            portal="backstage",
            profile="baseline",
        )


@pytest.mark.unit
def test_azure_terraform_apply_parses_outputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def runner(argv: list[str], cwd: Path | None, env: dict[str, str] | None) -> CommandResult:
        del cwd, env
        if "output" in argv:
            return CommandResult(
                stdout=json.dumps(
                    {
                        "environment_name": {"value": "azure-env"},
                        "target_platform": {"value": "azure"},
                        "portal_impl": {"value": "backstage"},
                        "security_profile": {"value": "baseline"},
                        "connection": {
                            "value": {
                                "ansible_inventory_group": "azure_vms",
                                "ssh_user": "azureuser",
                                "ssh_port": 22,
                                "api_endpoint": "https://api.azure.example.local",
                            }
                        },
                    }
                ),
                stderr="",
            )
        return CommandResult(stdout="", stderr="")

    backend = AzureBackend(tmp_path, runner=runner)
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True)
    monkeypatch.setenv("TF_VAR_resource_group_name", "rg-demo")
    monkeypatch.setenv("TF_VAR_ssh_public_key", "ssh-rsa AAAA")
    monkeypatch.setenv("TF_VAR_allowed_source_prefix", "203.0.113.0/24")

    result = backend._terraform_apply_azure(
        env_dir,
        environment_name="azure-env",
        portal="backstage",
        profile="baseline",
    )

    assert result["target_platform"] == "azure"


@pytest.mark.unit
def test_okd_terraform_apply_requires_cluster_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = OKDBackend(tmp_path, runner=lambda *_, **__: CommandResult(stdout="", stderr=""))
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True)
    monkeypatch.delenv("TF_VAR_cluster_name", raising=False)
    monkeypatch.delenv("TF_VAR_CLUSTER_NAME", raising=False)

    with pytest.raises(ValueError, match="TF_VAR_cluster_name"):
        backend._terraform_apply_okd(
            env_dir,
            environment_name="okd-env",
            portal="backstage",
            profile="baseline",
        )


@pytest.mark.unit
def test_okd_terraform_apply_requires_base_domain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backend = OKDBackend(tmp_path, runner=lambda *_, **__: CommandResult(stdout="", stderr=""))
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True)
    monkeypatch.setenv("TF_VAR_cluster_name", "demo")
    monkeypatch.delenv("TF_VAR_base_domain", raising=False)
    monkeypatch.delenv("TF_VAR_BASE_DOMAIN", raising=False)

    with pytest.raises(ValueError, match="TF_VAR_base_domain"):
        backend._terraform_apply_okd(
            env_dir,
            environment_name="okd-env",
            portal="backstage",
            profile="baseline",
        )


@pytest.mark.unit
def test_okd_terraform_apply_parses_outputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def runner(argv: list[str], cwd: Path | None, env: dict[str, str] | None) -> CommandResult:
        del cwd, env
        if "output" in argv:
            return CommandResult(
                stdout=json.dumps(
                    {
                        "environment_name": {"value": "okd-env"},
                        "target_platform": {"value": "okd"},
                        "portal_impl": {"value": "backstage"},
                        "security_profile": {"value": "baseline"},
                        "connection": {
                            "value": {
                                "ansible_inventory_group": "okd_cluster",
                                "ssh_user": "core",
                                "ssh_port": 22,
                                "api_endpoint": "https://api.okd.example.local:6443",
                            }
                        },
                    }
                ),
                stderr="",
            )
        return CommandResult(stdout="", stderr="")

    backend = OKDBackend(tmp_path, runner=runner)
    env_dir = tmp_path / "env"
    env_dir.mkdir(parents=True)
    monkeypatch.setenv("TF_VAR_cluster_name", "demo")
    monkeypatch.setenv("TF_VAR_base_domain", "example.local")

    result = backend._terraform_apply_okd(
        env_dir,
        environment_name="okd-env",
        portal="backstage",
        profile="baseline",
    )

    assert result["target_platform"] == "okd"


@pytest.mark.unit
def test_aws_action_lock_serialises_create_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(MOCK_MODE_ENV_VAR, "true")
    backend = _ActionLockProbeAWSBackend(tmp_path)

    errors: list[Exception] = []

    def run_once() -> None:
        try:
            backend.create_environment(
                target="aws",
                portal="backstage",
                profile="baseline",
                eda="disabled",
            )
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    thread_1 = threading.Thread(target=run_once, daemon=True)
    thread_2 = threading.Thread(target=run_once, daemon=True)
    thread_1.start()
    thread_2.start()
    thread_1.join(timeout=2)
    thread_2.join(timeout=2)

    assert not thread_1.is_alive(), "thread_1 did not finish; create_environment may be deadlocked"
    assert not thread_2.is_alive(), "thread_2 did not finish; create_environment may be deadlocked"
    assert errors == []
    assert backend.max_active_ensures == 1
