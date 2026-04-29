"""Tests for demo configuration and service orchestration."""

import subprocess
from email.message import Message
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest

from terraable import demo_config
from terraable.demo_config import (
    AnsibleConfig,
    AutomationBackend,
    ConnectionMode,
    DemoConfiguration,
    DemoProfile,
    ProvisioningBackend,
    ServiceReadinessStatus,
    TerraformConfig,
    apply_profile,
    check_service_readiness,
    get_demo_config,
    get_overall_readiness,
    set_demo_config,
    start_service,
)


def _sample_credential() -> str:
    return "demo-" + "credential"


class TestEnums:
    """Test enum definitions."""

    def test_provisioning_backend_values(self) -> None:
        """Test ProvisioningBackend enum values."""
        assert ProvisioningBackend.TERRAFORM_CLI.value == "terraform-cli"
        assert ProvisioningBackend.TFC.value == "tfc"
        assert ProvisioningBackend.TFE.value == "tfe"

    def test_automation_backend_values(self) -> None:
        """Test AutomationBackend enum values."""
        assert AutomationBackend.ANSIBLE_CLI.value == "ansible-cli"
        assert AutomationBackend.AAP.value == "aap"
        assert AutomationBackend.AWX.value == "awx"

    def test_connection_mode_values(self) -> None:
        """Test ConnectionMode enum values."""
        assert ConnectionMode.DOCKER_COMPOSE_SERVICE.value == "docker-compose-service"
        assert ConnectionMode.EXTERNAL_ENDPOINT.value == "external-endpoint"
        assert ConnectionMode.OFFLINE_MOCK.value == "offline-mock"

    def test_demo_profile_values(self) -> None:
        """Test DemoProfile enum values."""
        assert DemoProfile.LAB.value == "lab"
        assert DemoProfile.ENTERPRISE_MIRROR.value == "enterprise-mirror"
        assert DemoProfile.CUSTOM.value == "custom"
        assert DemoProfile.OFFLINE_FALLBACK.value == "offline-fallback"


class TestTerraformConfig:
    """Test TerraformConfig dataclass."""

    def test_default_terraform_config(self) -> None:
        """Test default TerraformConfig values."""
        config = TerraformConfig()
        assert config.backend == ProvisioningBackend.TERRAFORM_CLI
        assert config.connection_mode == ConnectionMode.DOCKER_COMPOSE_SERVICE
        assert config.hostname is None
        assert config.token is None
        assert config.organization is None
        assert config.api_version == "v2"

    def test_custom_terraform_config(self) -> None:
        """Test custom TerraformConfig values."""
        config = TerraformConfig(
            backend=ProvisioningBackend.TFC,
            connection_mode=ConnectionMode.EXTERNAL_ENDPOINT,
            hostname="app.terraform.io",
            token="token123",
            organization="my-org",
        )
        assert config.backend == ProvisioningBackend.TFC
        assert config.connection_mode == ConnectionMode.EXTERNAL_ENDPOINT
        assert config.hostname == "app.terraform.io"
        assert config.token == "token123"
        assert config.organization == "my-org"


class TestAnsibleConfig:
    """Test AnsibleConfig dataclass."""

    def test_default_ansible_config(self) -> None:
        """Test default AnsibleConfig values."""
        config = AnsibleConfig()
        assert config.backend == AutomationBackend.ANSIBLE_CLI
        assert config.connection_mode == ConnectionMode.DOCKER_COMPOSE_SERVICE
        assert config.hostname is None
        assert config.username is None
        assert config.password is None
        assert config.insecure_skip_verify is False

    def test_custom_ansible_config(self) -> None:
        """Test custom AnsibleConfig values."""
        config = AnsibleConfig(
            backend=AutomationBackend.AWX,
            connection_mode=ConnectionMode.EXTERNAL_ENDPOINT,
            hostname="awx.example.com",
            username="admin",
            password=_sample_credential(),
            insecure_skip_verify=True,
        )
        assert config.backend == AutomationBackend.AWX
        assert config.hostname == "awx.example.com"
        assert config.username == "admin"
        assert config.password == _sample_credential()
        assert config.insecure_skip_verify is True


class TestDemoConfiguration:
    """Test DemoConfiguration dataclass."""

    def test_default_demo_configuration(self) -> None:
        """Test default DemoConfiguration values."""
        config = DemoConfiguration()
        assert config.terraform.backend == ProvisioningBackend.TERRAFORM_CLI
        assert config.ansible.backend == AutomationBackend.ANSIBLE_CLI
        assert config.active_profile == DemoProfile.LAB

    def test_demo_configuration_to_dict(self) -> None:
        """Test DemoConfiguration.to_dict() method."""
        config = DemoConfiguration(
            terraform=TerraformConfig(
                backend=ProvisioningBackend.TFC,
                hostname="app.terraform.io",
                organization="my-org",
            ),
            ansible=AnsibleConfig(
                backend=AutomationBackend.AWX,
                hostname="awx.example.com",
            ),
            active_profile=DemoProfile.ENTERPRISE_MIRROR,
        )
        result = config.to_dict()
        assert result["terraform"]["backend"] == "tfc"
        assert result["terraform"]["hostname"] == "app.terraform.io"
        assert result["terraform"]["organization"] == "my-org"
        assert result["ansible"]["backend"] == "awx"
        assert result["ansible"]["hostname"] == "awx.example.com"
        assert result["active_profile"] == "enterprise-mirror"


class TestServiceReadinessStatus:
    """Test ServiceReadinessStatus dataclass."""

    def test_ready_status(self) -> None:
        """Test ready service status."""
        status = ServiceReadinessStatus(service="terraform", is_ready=True)
        assert status.service == "terraform"
        assert status.is_ready is True
        assert status.error_message is None

    def test_not_ready_status(self) -> None:
        """Test not ready service status."""
        status = ServiceReadinessStatus(
            service="ansible",
            is_ready=False,
            error_message="Connection refused",
            estimated_wait_seconds=30,
        )
        assert status.service == "ansible"
        assert status.is_ready is False
        assert status.error_message == "Connection refused"
        assert status.estimated_wait_seconds == 30


class TestGetSetDemoConfig:
    """Test get_demo_config and set_demo_config functions."""

    def test_initial_config_is_lab_profile(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test initial demo config is lab profile."""
        # Reset to default state
        monkeypatch.setattr(demo_config, "_demo_config", DemoConfiguration())
        config = get_demo_config()
        assert config.active_profile == DemoProfile.LAB
        assert config.terraform.backend == ProvisioningBackend.TERRAFORM_CLI
        assert config.ansible.backend == AutomationBackend.ANSIBLE_CLI

    def test_set_demo_config_updates_global_state(self) -> None:
        """Test set_demo_config updates global configuration."""
        new_config = DemoConfiguration(
            terraform=TerraformConfig(backend=ProvisioningBackend.TFC),
            ansible=AnsibleConfig(backend=AutomationBackend.AWX),
            active_profile=DemoProfile.CUSTOM,
        )
        set_demo_config(new_config)
        retrieved_config = get_demo_config()
        assert retrieved_config.terraform.backend == ProvisioningBackend.TFC
        assert retrieved_config.ansible.backend == AutomationBackend.AWX
        assert retrieved_config.active_profile == DemoProfile.CUSTOM


class TestApplyProfile:
    """Test apply_profile function."""

    def test_apply_lab_profile(self) -> None:
        """Test applying lab profile."""
        apply_profile(DemoProfile.LAB)
        config = get_demo_config()
        assert config.active_profile == DemoProfile.LAB
        assert config.terraform.backend == ProvisioningBackend.TERRAFORM_CLI
        assert config.terraform.connection_mode == ConnectionMode.DOCKER_COMPOSE_SERVICE
        assert config.ansible.backend == AutomationBackend.ANSIBLE_CLI
        assert config.ansible.connection_mode == ConnectionMode.DOCKER_COMPOSE_SERVICE

    def test_apply_enterprise_mirror_profile(self) -> None:
        """Test applying enterprise mirror profile."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        assert config.active_profile == DemoProfile.ENTERPRISE_MIRROR
        assert config.terraform.backend == ProvisioningBackend.TFC
        assert config.terraform.connection_mode == ConnectionMode.EXTERNAL_ENDPOINT
        assert config.terraform.hostname == "app.terraform.io"
        assert config.ansible.backend == AutomationBackend.AAP
        assert config.ansible.connection_mode == ConnectionMode.EXTERNAL_ENDPOINT

    def test_apply_offline_fallback_profile(self) -> None:
        """Test applying offline fallback profile."""
        apply_profile(DemoProfile.OFFLINE_FALLBACK)
        config = get_demo_config()
        assert config.active_profile == DemoProfile.OFFLINE_FALLBACK
        assert config.terraform.backend == ProvisioningBackend.TERRAFORM_CLI
        assert config.terraform.connection_mode == ConnectionMode.OFFLINE_MOCK
        assert config.ansible.backend == AutomationBackend.ANSIBLE_CLI
        assert config.ansible.connection_mode == ConnectionMode.OFFLINE_MOCK

    def test_apply_custom_profile_sets_profile_only(self) -> None:
        """Test applying custom profile only sets profile flag."""
        # First set to a known state
        apply_profile(DemoProfile.LAB)
        # Then apply custom, which should leave existing config intact
        apply_profile(DemoProfile.CUSTOM)
        config = get_demo_config()
        assert config.active_profile == DemoProfile.CUSTOM
        # Note: custom profile doesn't reset other config, just sets active_profile


class TestStartService:
    """Test start_service function."""

    def test_start_terraform_local_lab_mode(self) -> None:
        """Test starting terraform in local lab mode via docker compose."""
        apply_profile(DemoProfile.LAB)
        with (
            patch("os.path.exists", side_effect=lambda p: p == "/var/run/docker.sock"),
            patch("subprocess.run"),
        ):
            status = start_service("terraform")

        assert status.service == "terraform"
        assert status.is_ready is False
        assert status.estimated_wait_seconds == 20

    def test_start_terraform_offline_mode(self) -> None:
        """Test starting terraform in offline mode (always immediately ready)."""
        apply_profile(DemoProfile.OFFLINE_FALLBACK)
        status = start_service("terraform")
        assert status.service == "terraform"
        assert status.is_ready is True
        assert status.estimated_wait_seconds == 0

    def test_start_terraform_external_mode(self) -> None:
        """Test starting terraform in external endpoint mode (always immediately ready)."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        status = start_service("terraform")
        assert status.service == "terraform"
        assert status.is_ready is True
        assert status.estimated_wait_seconds == 0

    def test_start_ansible_offline_mode(self) -> None:
        """Test starting ansible in offline mode (always immediately ready)."""
        apply_profile(DemoProfile.OFFLINE_FALLBACK)
        status = start_service("ansible")
        assert status.service == "ansible"
        assert status.is_ready is True
        assert status.estimated_wait_seconds == 0

    def test_start_invalid_service(self) -> None:
        """Test starting invalid service returns error."""
        status = start_service("invalid-service")
        assert status.service == "invalid-service"
        assert status.is_ready is False
        assert "Unknown service" in (status.error_message or "")

    def test_start_service_orchestration_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test docker-compose service start is blocked when orchestration is disabled."""
        apply_profile(DemoProfile.LAB)
        monkeypatch.setenv("TERRAABLE_DEMO_ENABLE_DOCKER_ORCHESTRATION", "false")
        status = start_service("terraform")
        assert status.service == "terraform"
        assert status.is_ready is False
        assert "orchestration disabled" in (status.error_message or "")

    def test_start_service_docker_cli_missing(self) -> None:
        """Test service start error when docker CLI is unavailable."""
        apply_profile(DemoProfile.LAB)
        with (
            patch("os.path.exists", side_effect=lambda p: p == "/var/run/docker.sock"),
            patch("subprocess.run", side_effect=FileNotFoundError),
        ):
            status = start_service("terraform")

        assert status.is_ready is False
        assert status.error_message == "docker CLI is not available"

    def test_start_service_docker_compose_failure(self) -> None:
        """Test service start error when docker compose command fails."""
        apply_profile(DemoProfile.LAB)
        error = subprocess.CalledProcessError(
            returncode=1,
            cmd=["docker", "compose"],
            stderr="compose failed",
        )
        with (
            patch("os.path.exists", side_effect=lambda p: p == "/var/run/docker.sock"),
            patch("subprocess.run", side_effect=error),
        ):
            status = start_service("ansible")

        assert status.is_ready is False
        assert "docker compose failed" in (status.error_message or "")


class TestCheckServiceReadiness:
    """Test check_service_readiness function."""

    def test_check_terraform_cli_always_ready(self) -> None:
        """Test terraform-cli is always ready."""
        apply_profile(DemoProfile.LAB)
        status = check_service_readiness("terraform")
        assert status.service == "terraform"
        assert status.is_ready is True

    def test_check_ansible_cli_always_ready(self) -> None:
        """Test ansible-cli is always ready."""
        apply_profile(DemoProfile.LAB)
        status = check_service_readiness("ansible")
        assert status.service == "ansible"
        assert status.is_ready is True

    def test_check_service_readiness_during_startup_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test docker-compose startup window keeps service not-ready temporarily."""
        apply_profile(DemoProfile.LAB)
        monkeypatch.setattr(demo_config, "_service_startup_times", {"terraform": 100.0})
        with patch("time.time", return_value=110.0):
            status = check_service_readiness("terraform")

        assert status.service == "terraform"
        assert status.is_ready is False
        assert status.estimated_wait_seconds == 10

    def test_check_terraform_tfc_no_token(self) -> None:
        """Test terraform TFC with no token configured is not ready."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        config.terraform.token = None
        status = check_service_readiness("terraform")
        assert status.service == "terraform"
        assert status.is_ready is False
        assert "No Terraform token configured" in (status.error_message or "")

    def test_check_ansible_aap_no_endpoint(self) -> None:
        """Test ansible AAP with no endpoint configured is not ready."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        config.ansible.hostname = None
        status = check_service_readiness("ansible")
        assert status.service == "ansible"
        assert status.is_ready is False
        assert "No Ansible endpoint configured" in (status.error_message or "")

    def test_check_terraform_tfc_invalid_token(self) -> None:
        """Test terraform TFC with invalid token is not ready."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        config.terraform.token = "invalid-token"
        # Don't actually make HTTP request; just verify the logic path
        status = check_service_readiness("terraform")
        assert status.service == "terraform"
        assert status.is_ready is False
        # Could be connectivity error or invalid token

    def test_check_invalid_service(self) -> None:
        """Test checking readiness of invalid service."""
        status = check_service_readiness("invalid-service")
        assert status.service == "invalid-service"
        assert status.is_ready is False
        assert "Unknown service" in (status.error_message or "")


class TestGetOverallReadiness:
    """Test get_overall_readiness function."""

    def test_overall_readiness_lab_profile(self) -> None:
        """Test overall readiness for lab profile (both services ready)."""
        apply_profile(DemoProfile.LAB)
        readiness = get_overall_readiness()
        assert readiness["terraform"]["is_ready"] is True
        assert readiness["ansible"]["is_ready"] is True
        assert readiness["all_ready"] is True

    def test_overall_readiness_offline_profile(self) -> None:
        """Test overall readiness for offline profile (both services ready)."""
        apply_profile(DemoProfile.OFFLINE_FALLBACK)
        readiness = get_overall_readiness()
        assert readiness["terraform"]["is_ready"] is True
        assert readiness["ansible"]["is_ready"] is True
        assert readiness["all_ready"] is True

    def test_overall_readiness_enterprise_mirror_no_creds(self) -> None:
        """Test overall readiness for enterprise mirror without credentials."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        config.terraform.token = None
        config.ansible.hostname = None
        readiness = get_overall_readiness()
        assert readiness["terraform"]["is_ready"] is False
        assert readiness["ansible"]["is_ready"] is False
        assert readiness["all_ready"] is False

    def test_overall_readiness_partial(self) -> None:
        """Test overall readiness with partially configured services."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        # Configure only terraform
        config.terraform.token = None  # Will fail
        config.ansible.backend = AutomationBackend.ANSIBLE_CLI  # Will be ready
        readiness = get_overall_readiness()
        assert readiness["terraform"]["is_ready"] is False
        assert readiness["ansible"]["is_ready"] is True
        assert readiness["all_ready"] is False


class TestCheckServiceReadinessMocked:
    """Test check_service_readiness with mocked HTTP calls."""

    def test_terraform_tfc_valid_token_http_200(self) -> None:
        """Test terraform TFC with valid token (HTTP 200 response)."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        config.terraform.token = "valid-token"

        mock_response = MagicMock()
        mock_response.status = 200

        with patch("urllib.request.urlopen", return_value=mock_response):
            status = check_service_readiness("terraform")
            assert status.is_ready is True

    def test_terraform_tfc_unexpected_status_code(self) -> None:
        """Test terraform TFC when response returns an unexpected status code (not 200/201)."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        config.terraform.token = "valid-token"

        mock_response = MagicMock()
        mock_response.status = 202

        with patch("urllib.request.urlopen", return_value=mock_response):
            status = check_service_readiness("terraform")
            assert status.is_ready is False
            assert "Terraform service readiness check failed" in (status.error_message or "")

    def test_terraform_tfc_invalid_token_401(self) -> None:
        """Test terraform TFC with invalid token (HTTP 401 response)."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        config.terraform.token = "invalid-token"

        with patch(
            "urllib.request.urlopen",
            side_effect=HTTPError(
                "https://app.terraform.io/api/v2/account/details",
                401,
                "Unauthorized",
                Message(),
                None,
            ),
        ):
            status = check_service_readiness("terraform")
            assert status.is_ready is False
            assert "Invalid Terraform token" in (status.error_message or "")

    def test_terraform_tfc_api_error_500(self) -> None:
        """Test terraform TFC with API error (HTTP 500 response)."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        config.terraform.token = "valid-token"

        with patch(
            "urllib.request.urlopen",
            side_effect=HTTPError(
                "https://app.terraform.io/api/v2/account/details",
                500,
                "Internal Server Error",
                Message(),
                None,
            ),
        ):
            status = check_service_readiness("terraform")
            assert status.is_ready is False
            assert "API error: 500" in (status.error_message or "")

    def test_terraform_tfc_connectivity_error(self) -> None:
        """Test terraform TFC with connectivity error."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        config.terraform.token = "valid-token"

        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            status = check_service_readiness("terraform")
            assert status.is_ready is False
            assert "Connectivity error" in (status.error_message or "")

    def test_ansible_awx_valid_credentials_http_200(self) -> None:
        """Test ansible AWX with valid credentials (HTTP 200 response)."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        config.ansible.backend = AutomationBackend.AWX
        config.ansible.hostname = "awx.example.com"
        config.ansible.username = "admin"
        config.ansible.password = _sample_credential()

        mock_response = MagicMock()
        mock_response.status = 200

        with patch("urllib.request.urlopen", return_value=mock_response):
            status = check_service_readiness("ansible")
            assert status.is_ready is True

    def test_ansible_awx_valid_credentials_http_201(self) -> None:
        """Test ansible AWX with valid credentials (HTTP 201 response)."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        config.ansible.backend = AutomationBackend.AWX
        config.ansible.hostname = "awx.example.com"
        config.ansible.username = "admin"
        config.ansible.password = _sample_credential()

        mock_response = MagicMock()
        mock_response.status = 201

        with patch("urllib.request.urlopen", return_value=mock_response):
            status = check_service_readiness("ansible")
            assert status.is_ready is True

    def test_ansible_awx_unexpected_status_code(self) -> None:
        """Test ansible AWX when response returns an unexpected status code (not 200/201)."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        config.ansible.backend = AutomationBackend.AWX
        config.ansible.hostname = "awx.example.com"
        config.ansible.username = "admin"
        config.ansible.password = _sample_credential()

        mock_response = MagicMock()
        mock_response.status = 202

        with patch("urllib.request.urlopen", return_value=mock_response):
            status = check_service_readiness("ansible")
            assert status.is_ready is False
            assert "Ansible service readiness check failed" in (status.error_message or "")

    def test_ansible_awx_invalid_credentials_401(self) -> None:
        """Test ansible AWX with invalid credentials (HTTP 401 response)."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        config.ansible.backend = AutomationBackend.AWX
        config.ansible.hostname = "awx.example.com"
        config.ansible.username = "admin"
        config.ansible.password = "wrong-password"

        with patch(
            "urllib.request.urlopen",
            side_effect=HTTPError(
                "https://awx.example.com/api/v2/ping/",
                401,
                "Unauthorized",
                Message(),
                None,
            ),
        ):
            status = check_service_readiness("ansible")
            assert status.is_ready is False
            assert "Invalid Ansible credentials" in (status.error_message or "")

    def test_ansible_awx_api_error_500(self) -> None:
        """Test ansible AWX with API error (HTTP 500 response)."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        config.ansible.backend = AutomationBackend.AWX
        config.ansible.hostname = "awx.example.com"
        config.ansible.username = "admin"
        config.ansible.password = _sample_credential()

        with patch(
            "urllib.request.urlopen",
            side_effect=HTTPError(
                "https://awx.example.com/api/v2/ping/",
                500,
                "Internal Server Error",
                Message(),
                None,
            ),
        ):
            status = check_service_readiness("ansible")
            assert status.is_ready is False
            assert "API error: 500" in (status.error_message or "")

    def test_ansible_awx_connectivity_error(self) -> None:
        """Test ansible AWX with connectivity error."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        config.ansible.backend = AutomationBackend.AWX
        config.ansible.hostname = "awx.example.com"

        with patch("urllib.request.urlopen", side_effect=Exception("Network unreachable")):
            status = check_service_readiness("ansible")
            assert status.is_ready is False
            assert "Connectivity error" in (status.error_message or "")

    def test_ansible_awx_insecure_skip_verify(self) -> None:
        """Test ansible AWX with insecure SSL verification."""
        apply_profile(DemoProfile.ENTERPRISE_MIRROR)
        config = get_demo_config()
        config.ansible.backend = AutomationBackend.AWX
        config.ansible.hostname = "awx.example.com"
        config.ansible.insecure_skip_verify = True

        mock_response = MagicMock()
        mock_response.status = 200

        with patch("urllib.request.urlopen", return_value=mock_response):
            status = check_service_readiness("ansible")
            assert status.is_ready is True


class TestStartServiceDocker:
    """Test start_service with docker socket availability."""

    def test_start_ansible_docker_compose_mode_with_socket(self) -> None:
        """Test starting ansible in docker-compose mode with socket available."""
        apply_profile(DemoProfile.LAB)

        with (
            patch("os.path.exists", side_effect=lambda p: p == "/var/run/docker.sock"),
            patch("subprocess.run"),
        ):
            status = start_service("ansible")

        assert status.service == "ansible"
        assert status.is_ready is False
        # Ansible service estimated wait is 30 seconds
        assert status.estimated_wait_seconds == 30

    def test_start_terraform_docker_compose_mode_with_socket(self) -> None:
        """Test starting terraform in docker-compose mode with socket available."""
        apply_profile(DemoProfile.LAB)

        with (
            patch("os.path.exists", side_effect=lambda p: p == "/var/run/docker.sock"),
            patch("subprocess.run"),
        ):
            status = start_service("terraform")

        assert status.service == "terraform"
        assert status.is_ready is False
        # Terraform service estimated wait is 20 seconds
        assert status.estimated_wait_seconds == 20

    def test_start_service_docker_compose_with_override_file(self) -> None:
        """Test compose command includes base and override files when both exist."""
        apply_profile(DemoProfile.LAB)

        def fake_exists(path: str) -> bool:
            return path in {
                "/var/run/docker.sock",
                "/workspace/docker-compose.yml",
                "/workspace/docker-compose.demo-overrides.yml",
            }

        with (
            patch("os.path.exists", side_effect=fake_exists),
            patch("os.getcwd", return_value="/workspace"),
            patch("subprocess.run") as run_mock,
        ):
            status = start_service("ansible")

        assert status.is_ready is False
        cmd = run_mock.call_args.args[0]
        assert cmd == [
            "docker",
            "compose",
            "-f",
            "/workspace/docker-compose.yml",
            "-f",
            "/workspace/docker-compose.demo-overrides.yml",
            "up",
            "-d",
            "demo-ansible",
        ]

    def test_start_service_docker_compose_no_base_file(self) -> None:
        """Test compose command falls back when workspace compose files are missing."""
        apply_profile(DemoProfile.LAB)

        with (
            patch("os.path.exists", side_effect=lambda p: p == "/var/run/docker.sock"),
            patch("subprocess.run") as run_mock,
        ):
            status = start_service("terraform")

        assert status.is_ready is False
        cmd = run_mock.call_args.args[0]
        assert cmd == ["docker", "compose", "up", "-d", "demo-terraform"]

    def test_start_service_docker_compose_no_socket(self) -> None:
        """Test starting service in docker-compose mode without socket."""
        apply_profile(DemoProfile.LAB)

        with patch("os.path.exists", return_value=False):
            status = start_service("ansible")
        assert status.service == "ansible"
        assert status.is_ready is False
        assert "Docker socket not available" in (status.error_message or "")

    def test_start_service_docker_compose_exception(self) -> None:
        """Test starting service in docker-compose mode with exception."""
        apply_profile(DemoProfile.LAB)

        # Simulate time.time() raising an exception
        with (
            patch("os.path.exists", side_effect=lambda p: p == "/var/run/docker.sock"),
            patch("subprocess.run"),
            patch("time.time", side_effect=Exception("Time error")),
        ):
            status = start_service("terraform")
        assert status.service == "terraform"
        assert status.is_ready is False
        assert "Time error" in (status.error_message or "")

    def test_run_compose_up_unknown_service_raises(self) -> None:
        """Test compose helper rejects unknown service names."""
        with pytest.raises(ValueError, match="Unknown service"):
            demo_config._run_compose_up("unknown")
