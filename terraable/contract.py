"""Canonical Terraform-to-Ansible handoff contract utilities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class TargetPlatform(StrEnum):
    """Supported target platforms."""

    OPENSHIFT = "openshift"
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    OKD = "okd"
    VMWARE = "vmware"
    PARALLELS = "parallels"
    HYPER_V = "hyper-v"
    LOCAL_LAB = "local-lab"


class PortalImplementation(StrEnum):
    """Supported portal implementations for MVP."""

    RHDH = "rhdh"
    BACKSTAGE = "backstage"


class SecurityProfile(StrEnum):
    """Supported baseline security profiles."""

    BASELINE = "baseline"
    STRICT = "strict"


@dataclass(frozen=True, slots=True)
class ConnectionDetails:
    """Connection data required by downstream workflow tooling."""

    ansible_inventory_group: str
    ssh_user: str
    ssh_port: int
    api_endpoint: str


@dataclass(frozen=True, slots=True)
class HandoffPayload:
    """Payload exchanged from Terraform stage to Ansible operational stage."""

    environment_name: str
    terraform_run_id: str
    target_platform: TargetPlatform
    portal_impl: PortalImplementation
    security_profile: SecurityProfile
    connection: ConnectionDetails
    metadata: dict[str, str]

    def to_runtime_vars(self) -> dict[str, Any]:
        """Convert payload to runtime variables consumable by workflow engines."""

        payload = asdict(self)
        payload["target_platform"] = self.target_platform.value
        payload["portal_impl"] = self.portal_impl.value
        payload["security_profile"] = self.security_profile.value
        return payload


def validate_target_combination(
    target_platform: TargetPlatform,
    portal_impl: PortalImplementation,
) -> None:
    """Validate target and portal combinations when a matrix rule is defined.

    Currently all enum combinations are accepted. The helper is retained so
    target-specific restrictions can be reintroduced without changing callers.
    """
    del target_platform, portal_impl


def build_handoff_payload(
    *,
    environment_name: str,
    terraform_run_id: str,
    target_platform: str,
    portal_impl: str,
    security_profile: str,
    connection: dict[str, Any],
    metadata: dict[str, str] | None = None,
) -> HandoffPayload:
    """Create and validate a handoff payload from primitive input values."""

    payload = HandoffPayload(
        environment_name=environment_name,
        terraform_run_id=terraform_run_id,
        target_platform=TargetPlatform(target_platform),
        portal_impl=PortalImplementation(portal_impl),
        security_profile=SecurityProfile(security_profile),
        connection=ConnectionDetails(
            ansible_inventory_group=str(connection["ansible_inventory_group"]),
            ssh_user=str(connection["ssh_user"]),
            ssh_port=int(connection["ssh_port"]),
            api_endpoint=str(connection["api_endpoint"]),
        ),
        metadata=metadata or {},
    )

    validate_target_combination(payload.target_platform, payload.portal_impl)
    return payload
