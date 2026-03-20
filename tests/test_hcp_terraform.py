"""Tests for the HCP Terraform client helpers."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch
from urllib.error import URLError

import pytest

from terraable.hcp_terraform import HcpTerraformClient, HcpTerraformConfig


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


@pytest.mark.unit
def test_get_run_status() -> None:
    client = HcpTerraformClient(HcpTerraformConfig(token="token-123"))

    with patch(
        "terraable.hcp_terraform.urlopen",
        return_value=_FakeResponse(
            {
                "data": {
                    "attributes": {"status": "applied"},
                    "relationships": {"apply": {"data": {"id": "apply-1"}}},
                }
            }
        ),
    ):
        assert client.get_run_status("run-1") == "applied"


@pytest.mark.unit
def test_get_run_outputs() -> None:
    """Test correct resolution chain: run -> apply -> state-version -> outputs."""
    client = HcpTerraformClient(HcpTerraformConfig(token="token-123"))

    responses = [
        _FakeResponse(
            {
                "data": {
                    "attributes": {"status": "applied"},
                    "relationships": {"apply": {"data": {"id": "apply-1"}}},
                }
            }
        ),
        _FakeResponse(
            {
                "data": {
                    "relationships": {"state_version": {"data": {"id": "sv-1"}}},
                }
            }
        ),
        _FakeResponse(
            {
                "data": [
                    {"attributes": {"name": "environment_name", "value": "demo-aue1"}},
                    {"attributes": {"name": "api_endpoint", "value": "https://api.example"}},
                ]
            }
        ),
    ]

    with patch("terraable.hcp_terraform.urlopen", side_effect=responses):
        outputs = client.get_run_outputs("run-2")

    assert outputs["environment_name"] == "demo-aue1"
    assert outputs["api_endpoint"] == "https://api.example"


@pytest.mark.unit
def test_get_run_outputs_uses_run_level_state_version_when_present() -> None:
    client = HcpTerraformClient(HcpTerraformConfig(token="token-123"))

    responses = [
        _FakeResponse(
            {
                "data": {
                    "attributes": {"status": "applied"},
                    "relationships": {"state-version": {"data": {"id": "sv-2"}}},
                }
            }
        ),
        _FakeResponse(
            {
                "data": [
                    {"attributes": {"name": "environment_name", "value": "demo-direct"}},
                ]
            }
        ),
    ]

    with patch("terraable.hcp_terraform.urlopen", side_effect=responses):
        outputs = client.get_run_outputs("run-direct")

    assert outputs["environment_name"] == "demo-direct"


@pytest.mark.unit
def test_get_run_outputs_resolves_hyphenated_state_version_from_apply() -> None:
    client = HcpTerraformClient(HcpTerraformConfig(token="token-123"))

    responses = [
        _FakeResponse(
            {
                "data": {
                    "attributes": {"status": "applied"},
                    "relationships": {"apply": {"data": {"id": "apply-7"}}},
                }
            }
        ),
        _FakeResponse(
            {
                "data": {
                    "relationships": {"state-version": {"data": {"id": "sv-7"}}},
                }
            }
        ),
        _FakeResponse(
            {
                "data": [
                    {"attributes": {"name": "api_endpoint", "value": "https://api.hyphen"}},
                ]
            }
        ),
    ]

    with patch("terraable.hcp_terraform.urlopen", side_effect=responses):
        outputs = client.get_run_outputs("run-7")

    assert outputs["api_endpoint"] == "https://api.hyphen"


@pytest.mark.unit
def test_get_run_outputs_resolves_state_version_from_list_relationship() -> None:
    client = HcpTerraformClient(HcpTerraformConfig(token="token-123"))

    responses = [
        _FakeResponse(
            {
                "data": {
                    "attributes": {"status": "applied"},
                    "relationships": {
                        "state-versions": {"data": [{"id": "sv-list-1"}]},
                    },
                }
            }
        ),
        _FakeResponse(
            {
                "data": [
                    {"attributes": {"name": "environment_name", "value": "demo-list"}},
                ]
            }
        ),
    ]

    with patch("terraable.hcp_terraform.urlopen", side_effect=responses):
        outputs = client.get_run_outputs("run-list")

    assert outputs["environment_name"] == "demo-list"


@pytest.mark.unit
def test_api_error_raises_runtime_error() -> None:
    client = HcpTerraformClient(HcpTerraformConfig(token="token-123"))

    with (
        patch("terraable.hcp_terraform.urlopen", side_effect=URLError("network down")),
        pytest.raises(RuntimeError, match="HCP Terraform request failed"),
    ):
        client.get_run("run-3")


@pytest.mark.unit
def test_get_run_outputs_raises_when_apply_state_missing() -> None:
    """Test error when apply lacks state_version relationship."""
    client = HcpTerraformClient(HcpTerraformConfig(token="token-123"))

    responses = [
        _FakeResponse(
            {
                "data": {
                    "attributes": {"status": "planned_and_finished"},
                    "relationships": {"apply": {"data": {"id": "apply-2"}}},
                }
            }
        ),
        _FakeResponse(
            {
                "data": {
                    "relationships": {"state_version": {"data": None}},
                }
            }
        ),
    ]

    with patch("terraable.hcp_terraform.urlopen", side_effect=responses):
        with pytest.raises(RuntimeError, match="does not have an apply state yet"):
            client.get_run_outputs("run-4")


@pytest.mark.unit
def test_config_from_env_reads_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TF_TOKEN_tfc_example_internal", "env-token")
    monkeypatch.setenv("TERRAABLE_TFC_HOSTNAME", "tfc.example.internal")

    config = HcpTerraformConfig.from_env()

    assert config.token == "env-token"
    assert config.hostname == "tfc.example.internal"


@pytest.mark.unit
def test_config_from_env_prefers_explicit_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TF_TOKEN_env_host", "env-token")
    monkeypatch.setenv("TERRAABLE_TFC_HOSTNAME", "env-host")

    config = HcpTerraformConfig.from_env(token="explicit-token", hostname="explicit-host")

    assert config.token == "explicit-token"
    assert config.hostname == "explicit-host"


@pytest.mark.unit
def test_config_from_env_uses_default_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TF_TOKEN_app_terraform_io", "env-token")
    monkeypatch.delenv("TERRAABLE_TFC_HOSTNAME", raising=False)

    config = HcpTerraformConfig.from_env()

    assert config.hostname == "app.terraform.io"


@pytest.mark.unit
def test_config_from_env_raises_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TF_TOKEN_app_terraform_io", raising=False)

    with pytest.raises(ValueError, match="Missing HCP Terraform token"):
        HcpTerraformConfig.from_env()


@pytest.mark.unit
def test_config_from_env_derives_token_env_var_from_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TF_TOKEN_tfe_example_com", "custom-token")

    config = HcpTerraformConfig.from_env(hostname="tfe.example.com")

    assert config.token == "custom-token"
    assert config.hostname == "tfe.example.com"


@pytest.mark.unit
def test_config_from_env_error_shows_derived_env_var_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TF_TOKEN_app_terraform_io", raising=False)

    with pytest.raises(ValueError, match="TF_TOKEN_app_terraform_io"):
        HcpTerraformConfig.from_env()


@pytest.mark.unit
def test_get_run_outputs_raises_when_state_version_id_missing() -> None:
    """Test error when apply has state_version but with no ID."""
    client = HcpTerraformClient(HcpTerraformConfig(token="token-123"))

    responses = [
        _FakeResponse(
            {
                "data": {
                    "attributes": {"status": "applied"},
                    "relationships": {"apply": {"data": {"id": "apply-3"}}},
                }
            }
        ),
        _FakeResponse(
            {
                "data": {
                    "relationships": {"state_version": {"data": {}}},
                }
            }
        ),
    ]

    with patch("terraable.hcp_terraform.urlopen", side_effect=responses):
        with pytest.raises(RuntimeError, match="does not have an apply state yet"):
            client.get_run_outputs("run-5")


@pytest.mark.unit
def test_get_run_outputs_raises_when_apply_is_missing() -> None:
    """Test error when run has no apply relationship."""
    client = HcpTerraformClient(HcpTerraformConfig(token="token-123"))

    responses = [
        _FakeResponse(
            {
                "data": {
                    "attributes": {"status": "planned"},
                    "relationships": {"apply": {"data": None}},
                }
            }
        ),
    ]

    with patch("terraable.hcp_terraform.urlopen", side_effect=responses):
        with pytest.raises(RuntimeError, match="does not have an apply state yet"):
            client.get_run_outputs("run-6")
