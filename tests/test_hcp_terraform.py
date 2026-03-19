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

    def __enter__(self) -> "_FakeResponse":
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
                    "relationships": {"apply": {"data": {"id": "sv-1"}}},
                }
            }
        ),
    ):
        assert client.get_run_status("run-1") == "applied"


@pytest.mark.unit
def test_get_run_outputs() -> None:
    client = HcpTerraformClient(HcpTerraformConfig(token="token-123"))

    responses = [
        _FakeResponse(
            {
                "data": {
                    "attributes": {"status": "applied"},
                    "relationships": {"apply": {"data": {"id": "sv-1"}}},
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
def test_api_error_raises_runtime_error() -> None:
    client = HcpTerraformClient(HcpTerraformConfig(token="token-123"))

    with patch("terraable.hcp_terraform.urlopen", side_effect=URLError("network down")):
        with pytest.raises(RuntimeError, match="HCP Terraform request failed"):
            client.get_run("run-3")
