# HCP Terraform Integration

## Intent

Define the MVP integration path for retrieving HCP Terraform run status and outputs for downstream operational workflows.

## Environment Variables

- `TF_TOKEN_*`: API token for HCP Terraform API calls. The env var name is derived from the resolved hostname by replacing dots with underscores (e.g., `TF_TOKEN_app_terraform_io` for `app.terraform.io`, `TF_TOKEN_tfe_example_com` for `tfe.example.com`). This matches Terraform CLI conventions.
- `TERRAABLE_TFC_HOSTNAME`: Optional hostname override (default `app.terraform.io`).

## Configuration Mechanism

Configuration is provided through `HcpTerraformConfig` using either explicit constructor values or `from_env()`.

Precedence for `from_env()`:

1. Explicit keyword arguments (`token`, `hostname`).
2. Environment variables. The token env var is derived from the resolved hostname by replacing dots with underscores (matching Terraform CLI syntax):
   - `app.terraform.io` → `TF_TOKEN_app_terraform_io`
   - `tfe.example.com` → `TF_TOKEN_tfe_example_com`
   - `TERRAABLE_TFC_HOSTNAME` for custom hostname.
3. Built-in default for hostname (`app.terraform.io`).

If no token is provided via arguments or environment, `from_env()` raises a `ValueError` indicating the expected token env var name.

Example with custom TFE hostname:

```python
from terraable.hcp_terraform import HcpTerraformClient, HcpTerraformConfig

# With env var TF_TOKEN_tfe_example_com and TERRAABLE_TFC_HOSTNAME=tfe.example.com
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

- Token env var not found: verify the token env var name matches your hostname. For hostname `tfe.example.com`, the env var should be `TF_TOKEN_tfe_example_com`. Error messages show the expected name.
- API authentication failure: verify the token has workspace/run read access on the HCP Terraform instance.
- Missing run/apply relationship: ensure run reached apply/state publication stage.
- Missing expected output keys: verify Terraform module outputs and workspace variables.
