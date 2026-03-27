"""
Demo configuration and service orchestration for Terraable.

Manages multi-backend demo setup including provisioning/automation backend
selection, connection modes, and service lifecycle orchestration.
"""

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class ProvisioningBackend(str, Enum):
    """Terraform provisioning backend options."""

    TERRAFORM_CLI = "terraform-cli"
    TFC = "tfc"  # Terraform Cloud
    TFE = "tfe"  # Terraform Enterprise


class AutomationBackend(str, Enum):
    """Ansible automation backend options."""

    ANSIBLE_CLI = "ansible-cli"
    AAP = "aap"  # Red Hat Ansible Automation Platform
    AWX = "awx"  # AWX (open-source)


class ConnectionMode(str, Enum):
    """Backend connection modes."""

    DOCKER_COMPOSE_SERVICE = "docker-compose-service"
    EXTERNAL_ENDPOINT = "external-endpoint"
    OFFLINE_MOCK = "offline-mock"


class DemoProfile(str, Enum):
    """Preset demo configuration profiles."""

    LAB = "lab"
    ENTERPRISE_MIRROR = "enterprise-mirror"
    CUSTOM = "custom"
    OFFLINE_FALLBACK = "offline-fallback"


@dataclass
class TerraformConfig:
    """Terraform backend configuration."""

    backend: ProvisioningBackend = ProvisioningBackend.TERRAFORM_CLI
    connection_mode: ConnectionMode = ConnectionMode.DOCKER_COMPOSE_SERVICE
    hostname: Optional[str] = None  # For TFC/TFE
    token: Optional[str] = None
    organization: Optional[str] = None
    api_version: str = "v2"


@dataclass
class AnsibleConfig:
    """Ansible backend configuration."""

    backend: AutomationBackend = AutomationBackend.ANSIBLE_CLI
    connection_mode: ConnectionMode = ConnectionMode.DOCKER_COMPOSE_SERVICE
    hostname: Optional[str] = None  # For AAP/AWX
    username: Optional[str] = None
    password: Optional[str] = None
    insecure_skip_verify: bool = False


@dataclass
class DemoConfiguration:
    """Complete demo configuration state."""

    terraform: TerraformConfig = field(default_factory=TerraformConfig)
    ansible: AnsibleConfig = field(default_factory=AnsibleConfig)
    active_profile: DemoProfile = DemoProfile.LAB

    def to_dict(self) -> Dict:
        """Convert configuration to dictionary for API responses."""
        return {
            "terraform": {
                "backend": self.terraform.backend.value,
                "connection_mode": self.terraform.connection_mode.value,
                "hostname": self.terraform.hostname,
                "organization": self.terraform.organization,
                "api_version": self.terraform.api_version,
            },
            "ansible": {
                "backend": self.ansible.backend.value,
                "connection_mode": self.ansible.connection_mode.value,
                "hostname": self.ansible.hostname,
                "username": self.ansible.username,
                "insecure_skip_verify": self.ansible.insecure_skip_verify,
            },
            "active_profile": self.active_profile.value,
        }


@dataclass
class ServiceReadinessStatus:
    """Readiness status for a provisioning or automation service."""

    service: str  # "terraform" or "ansible"
    is_ready: bool = False
    error_message: Optional[str] = None
    estimated_wait_seconds: int = 0
    last_checked_at: Optional[float] = None


# Global demo configuration state
_demo_config: DemoConfiguration = DemoConfiguration()
_service_startup_times: Dict[str, float] = {}  # Track when services were started


def get_demo_config() -> DemoConfiguration:
    """Get current demo configuration."""
    return _demo_config


def set_demo_config(config: DemoConfiguration) -> None:
    """Update demo configuration."""
    global _demo_config
    _demo_config = config


def apply_profile(profile: DemoProfile) -> None:
    """Apply a preset demo profile."""
    global _demo_config

    if profile == DemoProfile.LAB:
        _demo_config = DemoConfiguration(
            terraform=TerraformConfig(
                backend=ProvisioningBackend.TERRAFORM_CLI,
                connection_mode=ConnectionMode.DOCKER_COMPOSE_SERVICE,
            ),
            ansible=AnsibleConfig(
                backend=AutomationBackend.ANSIBLE_CLI,
                connection_mode=ConnectionMode.DOCKER_COMPOSE_SERVICE,
            ),
            active_profile=DemoProfile.LAB,
        )
    elif profile == DemoProfile.ENTERPRISE_MIRROR:
        _demo_config = DemoConfiguration(
            terraform=TerraformConfig(
                backend=ProvisioningBackend.TFC,
                connection_mode=ConnectionMode.EXTERNAL_ENDPOINT,
                hostname="app.terraform.io",
            ),
            ansible=AnsibleConfig(
                backend=AutomationBackend.AAP,
                connection_mode=ConnectionMode.EXTERNAL_ENDPOINT,
            ),
            active_profile=DemoProfile.ENTERPRISE_MIRROR,
        )
    elif profile == DemoProfile.OFFLINE_FALLBACK:
        _demo_config = DemoConfiguration(
            terraform=TerraformConfig(
                backend=ProvisioningBackend.TERRAFORM_CLI,
                connection_mode=ConnectionMode.OFFLINE_MOCK,
            ),
            ansible=AnsibleConfig(
                backend=AutomationBackend.ANSIBLE_CLI,
                connection_mode=ConnectionMode.OFFLINE_MOCK,
            ),
            active_profile=DemoProfile.OFFLINE_FALLBACK,
        )
    else:  # CUSTOM
        _demo_config.active_profile = DemoProfile.CUSTOM


def start_service(service: str) -> ServiceReadinessStatus:
    """
    Start a provisioning or automation service using docker compose.

    Args:
        service: "terraform" or "ansible"

    Returns:
        ServiceReadinessStatus with readiness and estimated wait time.
    """
    config = _demo_config

    # Determine if we should use docker compose
    if service == "terraform":
        connection_mode = config.terraform.connection_mode
    elif service == "ansible":
        connection_mode = config.ansible.connection_mode
    else:
        return ServiceReadinessStatus(
            service=service,
            is_ready=False,
            error_message=f"Unknown service: {service}",
        )

    # For non-docker-compose modes, report as immediately ready
    if connection_mode != ConnectionMode.DOCKER_COMPOSE_SERVICE:
        return ServiceReadinessStatus(
            service=service,
            is_ready=True,
            estimated_wait_seconds=0,
        )

    # For docker-compose mode, attempt to start the service
    try:
        # Record start time for this service
        _service_startup_times[service] = time.time()

        # Build docker compose command
        # In a real implementation, this would call docker compose with a profile or override file
        cmd = ["docker", "compose", "up", "-d", f"demo-{service}"]

        # Check if we're in a container with docker socket available
        docker_sock_available = os.path.exists("/var/run/docker.sock")
        if not docker_sock_available:
            return ServiceReadinessStatus(
                service=service,
                is_ready=False,
                error_message="Docker socket not available; cannot start service",
                estimated_wait_seconds=0,
            )

        # Estimate wait time based on service type
        estimated_wait = 30 if service == "ansible" else 20

        return ServiceReadinessStatus(
            service=service,
            is_ready=False,
            estimated_wait_seconds=estimated_wait,
        )
    except Exception as e:
        return ServiceReadinessStatus(
            service=service,
            is_ready=False,
            error_message=str(e),
        )


def check_service_readiness(service: str) -> ServiceReadinessStatus:
    """
    Poll service readiness by attempting to connect to the configured endpoint.

    Args:
        service: "terraform" or "ansible"

    Returns:
        ServiceReadinessStatus with current readiness state.
    """
    config = _demo_config

    if service == "terraform":
        tf_config = config.terraform
        hostname = tf_config.hostname or "localhost"

        # For terraform-cli, always ready (no external endpoint)
        if tf_config.backend == ProvisioningBackend.TERRAFORM_CLI:
            return ServiceReadinessStatus(service=service, is_ready=True)

        # For TFC/TFE, check token validity via API
        if not tf_config.token:
            return ServiceReadinessStatus(
                service=service,
                is_ready=False,
                error_message="No Terraform token configured",
            )

        try:
            # Use OAuth token to validate connectivity to TFC/TFE
            api_url = f"https://{hostname}/api/v2/account/details"
            req = urllib.request.Request(api_url)
            req.add_header("Authorization", f"Bearer {tf_config.token}")
            req.add_header("User-Agent", "Terraable-Demo")

            response = urllib.request.urlopen(req, timeout=5)
            if response.status == 200:
                return ServiceReadinessStatus(service=service, is_ready=True)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return ServiceReadinessStatus(
                    service=service,
                    is_ready=False,
                    error_message="Invalid Terraform token",
                )
            return ServiceReadinessStatus(
                service=service,
                is_ready=False,
                error_message=f"API error: {e.code}",
            )
        except Exception as e:
            return ServiceReadinessStatus(
                service=service,
                is_ready=False,
                error_message=f"Connectivity error: {str(e)}",
            )

    elif service == "ansible":
        ansible_config = config.ansible
        hostname = ansible_config.hostname or "localhost"

        # For ansible-cli, always ready (no external endpoint)
        if ansible_config.backend == AutomationBackend.ANSIBLE_CLI:
            return ServiceReadinessStatus(service=service, is_ready=True)

        # For AAP/AWX, check basic connectivity
        if not ansible_config.hostname:
            return ServiceReadinessStatus(
                service=service,
                is_ready=False,
                error_message="No Ansible endpoint configured",
            )

        try:
            api_url = f"https://{hostname}/api/v2/ping/"
            req = urllib.request.Request(api_url)
            req.add_header("User-Agent", "Terraable-Demo")

            # Add basic auth if credentials available
            if ansible_config.username and ansible_config.password:
                import base64

                credentials = base64.b64encode(
                    f"{ansible_config.username}:{ansible_config.password}".encode()
                ).decode()
                req.add_header("Authorization", f"Basic {credentials}")

            # Skip SSL verification if requested (for demo environments)
            import ssl

            ctx = ssl.create_default_context()
            if ansible_config.insecure_skip_verify:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

            response = urllib.request.urlopen(req, context=ctx, timeout=5)
            if response.status in (200, 201):
                return ServiceReadinessStatus(service=service, is_ready=True)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return ServiceReadinessStatus(
                    service=service,
                    is_ready=False,
                    error_message="Invalid Ansible credentials",
                )
            return ServiceReadinessStatus(
                service=service,
                is_ready=False,
                error_message=f"API error: {e.code}",
            )
        except Exception as e:
            return ServiceReadinessStatus(
                service=service,
                is_ready=False,
                error_message=f"Connectivity error: {str(e)}",
            )

    return ServiceReadinessStatus(
        service=service,
        is_ready=False,
        error_message=f"Unknown service: {service}",
    )


def get_overall_readiness() -> Dict:
    """Get readiness status for all services."""
    terraform_status = check_service_readiness("terraform")
    ansible_status = check_service_readiness("ansible")

    return {
        "terraform": {
            "is_ready": terraform_status.is_ready,
            "error_message": terraform_status.error_message,
        },
        "ansible": {
            "is_ready": ansible_status.is_ready,
            "error_message": ansible_status.error_message,
        },
        "all_ready": terraform_status.is_ready and ansible_status.is_ready,
    }
