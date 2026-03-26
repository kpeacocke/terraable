"""Tests for Terraform-to-Ansible handoff contract models."""

from __future__ import annotations

import pytest

from terraable.contract import (
    PortalImplementation,
    TargetPlatform,
    build_handoff_payload,
    validate_target_combination,
)


@pytest.mark.unit
def test_build_handoff_payload_to_runtime_vars() -> None:
    payload = build_handoff_payload(
        environment_name="demo-aue1",
        terraform_run_id="run-123",
        target_platform="openshift",
        portal_impl="rhdh",
        security_profile="baseline",
        connection={
            "ansible_inventory_group": "demo_hosts",
            "ssh_user": "ansible",
            "ssh_port": 22,
            "api_endpoint": "https://api.example.invalid",
        },
        metadata={"source": "unit-test"},
    )

    runtime_vars = payload.to_runtime_vars()

    assert runtime_vars["environment_name"] == "demo-aue1"
    assert runtime_vars["target_platform"] == "openshift"
    assert runtime_vars["portal_impl"] == "rhdh"
    assert runtime_vars["security_profile"] == "baseline"
    assert runtime_vars["connection"]["ssh_port"] == 22


@pytest.mark.unit
def test_local_lab_rhdh_combination_is_allowed() -> None:
    validate_target_combination(
        TargetPlatform.LOCAL_LAB,
        PortalImplementation.RHDH,
    )


@pytest.mark.unit
def test_supported_target_portal_combination_accepted() -> None:
    validate_target_combination(
        TargetPlatform.AWS,
        PortalImplementation.BACKSTAGE,
    )
