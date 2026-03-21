"""Tests for the MVP demo orchestrator."""

from __future__ import annotations

import pytest

from terraable.contract import build_handoff_payload
from terraable.orchestrator import ActionName, ActionStatus, DemoOrchestrator


@pytest.mark.unit
def test_orchestrator_happy_path() -> None:
    orchestrator = DemoOrchestrator()
    payload = build_handoff_payload(
        environment_name="demo-aue1",
        terraform_run_id="run-xyz",
        target_platform="openshift",
        portal_impl="backstage",
        security_profile="strict",
        connection={
            "ansible_inventory_group": "demo_hosts",
            "ssh_user": "ansible",
            "ssh_port": 2222,
            "api_endpoint": "https://api.example.invalid",
        },
    )

    create = orchestrator.create_environment(payload)
    baseline = orchestrator.apply_baseline()
    scan = orchestrator.run_compliance_scan(drift_present=False)
    drift = orchestrator.inject_ssh_drift()
    service_drift = orchestrator.inject_service_drift()
    remediation = orchestrator.run_remediation()

    assert create.action == ActionName.CREATE_ENVIRONMENT
    assert create.status == ActionStatus.SUCCEEDED
    assert baseline.action == ActionName.APPLY_BASELINE
    assert scan.status == ActionStatus.SUCCEEDED
    assert drift.action == ActionName.INJECT_SSH_DRIFT
    assert service_drift.action == ActionName.INJECT_SERVICE_DRIFT
    assert remediation.action == ActionName.RUN_REMEDIATION
    assert len(orchestrator.evidence) == 6


@pytest.mark.unit
def test_orchestrator_scan_failure_when_drift_present() -> None:
    orchestrator = DemoOrchestrator()

    scan = orchestrator.run_compliance_scan(drift_present=True)

    assert scan.action == ActionName.RUN_COMPLIANCE_SCAN
    assert scan.status == ActionStatus.FAILED
    assert "drift" in scan.detail.lower()
