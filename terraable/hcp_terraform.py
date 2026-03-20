"""HCP Terraform API helpers for MVP orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class HcpTerraformConfig:
    """Configuration for HCP Terraform API requests."""

    token: str
    hostname: str = "app.terraform.io"


class HcpTerraformClient:
    """Minimal HCP Terraform client for run status and outputs lookup."""

    def __init__(self, config: HcpTerraformConfig) -> None:
        self._config = config

    def _request(self, path: str) -> dict[str, Any]:
        request = Request(
            url=f"https://{self._config.hostname}{path}",
            headers={
                "Authorization": f"Bearer {self._config.token}",
                "Content-Type": "application/vnd.api+json",
            },
        )

        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            raise RuntimeError(f"HCP Terraform request failed for {path}") from exc

    def get_run(self, run_id: str) -> dict[str, Any]:
        """Return the run payload from HCP Terraform."""

        return self._request(f"/api/v2/runs/{run_id}")

    def get_run_status(self, run_id: str) -> str:
        """Return the current run status string."""

        run = self.get_run(run_id)
        return str(run["data"]["attributes"]["status"])

    def get_state_version_outputs(self, state_version_id: str) -> dict[str, Any]:
        """Return outputs for a state version keyed by output name."""

        response = self._request(f"/api/v2/state-versions/{state_version_id}/outputs")
        outputs: dict[str, Any] = {}
        for item in response.get("data", []):
            key = str(item["attributes"]["name"])
            outputs[key] = item["attributes"].get("value")
        return outputs

    def get_run_outputs(self, run_id: str) -> dict[str, Any]:
        """Resolve a run to its state version outputs."""

        run = self.get_run(run_id)
        state_version_id = run["data"]["relationships"]["apply"]["data"]["id"]
        return self.get_state_version_outputs(str(state_version_id))
