# HCP Terraform Integration

## Intent
Define the MVP integration path for retrieving HCP Terraform run status and outputs for downstream operational workflows.

## Environment Variables
- `TF_TOKEN_app_terraform_io`: API token used for HCP Terraform API calls.
- `TERRAABLE_TFC_HOSTNAME`: Optional hostname override (default `app.terraform.io`).

## Configuration Mechanism
Configuration is provided through `HcpTerraformConfig` using either explicit constructor values or `from_env()`.

Precedence for `from_env()`:
1. Explicit keyword arguments (`token`, `hostname`).
2. Environment variables (`TF_TOKEN_app_terraform_io`, `TERRAABLE_TFC_HOSTNAME`).
3. Built-in default for hostname (`app.terraform.io`).

If no token is provided via arguments or environment, `from_env()` raises a `ValueError`.

Example:

```python
from terraable.hcp_terraform import HcpTerraformClient, HcpTerraformConfig

config = HcpTerraformConfig.from_env()
client = HcpTerraformClient(config)
status = client.get_run_status("run-abc123")
```

## Runtime Integration
`terraable.hcp_terraform.HcpTerraformClient` provides:
- `get_run_status(run_id)` for status retrieval.
- `get_run_outputs(run_id)` for output retrieval.

## Downstream Consumption
Outputs are consumed by contract assembly logic before dispatching runtime variables to Ansible workflows.

## Failure Modes and Remediation
- API authentication failure: verify `TF_TOKEN_app_terraform_io` has workspace/run read access.
- Missing run/apply relationship: ensure run reached apply/state publication stage.
- Missing expected output keys: verify Terraform module outputs and workspace variables.
