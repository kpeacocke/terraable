"""HCP Terraform API helpers for MVP orchestration."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.error import URLError
from urllib.request import Request, urlopen

TFC_HOSTNAME_ENV_VAR = "TERRAABLE_TFC_HOSTNAME"


def _hostname_to_token_env_var(hostname: str) -> str:
    """Convert hostname to TF_TOKEN_* environment variable name.

    Matches Terraform CLI convention: lowercase and replace any non-alphanumeric
    characters with underscores.
    E.g.
    - "app.terraform.io" → "TF_TOKEN_app_terraform_io"
    - "tfc.my-company.internal" → "TF_TOKEN_tfc_my_company_internal"
    """
    normalized = re.sub(r"[^a-z0-9]", "_", hostname.lower())
    return f"TF_TOKEN_{normalized}"


def _as_str_dict(value: Any) -> dict[str, Any]:
    """Return a dictionary with string keys, or an empty dictionary."""

    if not isinstance(value, dict):
        return {}

    # JSON object keys are strings by specification.
    return cast("dict[str, Any]", value)


def _extract_relationship_data_id(relationship: dict[str, Any]) -> str | None:
    """Return relationship data ID for either object or list relationship payloads."""

    rel_data = relationship.get("data")
    if isinstance(rel_data, dict):
        rel_id = rel_data.get("id")
        return rel_id if isinstance(rel_id, str) and rel_id else None

    if isinstance(rel_data, list) and rel_data:
        first = rel_data[0]
        if isinstance(first, dict):
            rel_id = first.get("id")
            return rel_id if isinstance(rel_id, str) and rel_id else None

    return None


def _get_state_version_id(relationships: dict[str, Any]) -> str | None:
    """Return a state version ID from common JSON:API relationship key variants."""

    for key in ("state_version", "state-version", "state_versions", "state-versions"):
        state_version_rel = _as_str_dict(relationships.get(key))
        state_version_id = _extract_relationship_data_id(state_version_rel)
        if state_version_id:
            return state_version_id
    return None


@dataclass(frozen=True, slots=True)
class HcpTerraformConfig:
    """Configuration for HCP Terraform API requests."""

    token: str = field(repr=False)
    hostname: str = "app.terraform.io"

    @classmethod
    def from_env(
        cls,
        *,
        token: str | None = None,
        hostname: str | None = None,
    ) -> HcpTerraformConfig:
        """Build configuration from explicit values and environment variables.

        Precedence:
        1. Explicit keyword arguments.
        2. Environment variables. Token env var is derived from hostname:
           - app.terraform.io → TF_TOKEN_app_terraform_io
           - tfe.example.com → TF_TOKEN_tfe_example_com
        3. Built-in defaults (hostname only).
        """

        resolved_hostname = hostname or os.getenv(TFC_HOSTNAME_ENV_VAR) or "app.terraform.io"
        token_env_var = _hostname_to_token_env_var(resolved_hostname)
        resolved_token = token or os.getenv(token_env_var)

        if not resolved_token:
            raise ValueError(
                f"Missing HCP Terraform token. Provide token explicitly or set {token_env_var}."
            )

        return cls(token=resolved_token, hostname=resolved_hostname)


class HcpTerraformClient:
    """Minimal HCP Terraform client for run status and outputs lookup."""

    def __init__(self, config: HcpTerraformConfig) -> None:
        self._config = config

    def _request(self, path: str) -> dict[str, Any]:
        request = Request(
            url=f"https://{self._config.hostname}{path}",
            headers={
                "Authorization": f"Bearer {self._config.token}",
                "Accept": "application/vnd.api+json",
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


    def get_apply(self, apply_id: str) -> dict[str, Any]:
        """Return the apply payload from HCP Terraform."""

        return self._request(f"/api/v2/applies/{apply_id}")

    def get_state_version_outputs(self, state_version_id: str) -> dict[str, Any]:
        """Return outputs for a state version keyed by output name."""

        response = self._request(f"/api/v2/state-versions/{state_version_id}/outputs")
        outputs: dict[str, Any] = {}
        for item in response.get("data", []):
            key = str(item["attributes"]["name"])
            outputs[key] = item["attributes"].get("value")
        return outputs

    def get_run_outputs(self, run_id: str) -> dict[str, Any]:
        """Resolve a run to its state version outputs.

        Follows API resolution chain: run -> apply -> state-version -> outputs.
        """

        run = self.get_run(run_id)

        data = _as_str_dict(run.get("data"))
        attributes = _as_str_dict(data.get("attributes"))
        status = attributes.get("status")
        relationships = _as_str_dict(data.get("relationships"))

        # Some API shapes expose a run-level state-version relationship directly.
        run_state_version_id = _get_state_version_id(relationships)
        if run_state_version_id:
            return self.get_state_version_outputs(run_state_version_id)

        apply_rel = _as_str_dict(relationships.get("apply"))
        apply_id = _extract_relationship_data_id(apply_rel)

        if not isinstance(apply_id, str) or not apply_id:
            status_msg = f" (current status: {status})" if status is not None else ""
            raise RuntimeError(
                f"HCP Terraform run {run_id} does not have an apply state yet; "
                f"outputs are only available after a successful apply{status_msg}."
            )

        apply = self.get_apply(apply_id)
        apply_data_obj = _as_str_dict(apply.get("data"))
        apply_relationships = _as_str_dict(apply_data_obj.get("relationships"))
        state_version_id = _get_state_version_id(apply_relationships)

        if not isinstance(state_version_id, str) or not state_version_id:
            status_msg = f" (current status: {status})" if status is not None else ""
            raise RuntimeError(
                f"HCP Terraform run {run_id} does not have an apply state yet; "
                f"outputs are only available after a successful apply{status_msg}."
            )
        return self.get_state_version_outputs(state_version_id)
