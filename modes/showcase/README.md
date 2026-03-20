# Showcase Mode

Showcase mode runs with live infrastructure — HCP Terraform for provisioning and AAP for operational workflows. Use this path for customer-facing and product demonstrations.

## Prerequisites

- HCP Terraform organisation with at least one workspace
- AAP subscription with controller access
- AWS, Azure, OKD, or OpenShift target with appropriate credentials
- Environment variables from `.env.example` fully populated

## Supported targets

All substrate targets are available in showcase mode:

| Target | Module |
|--------|--------|
| `openshift` | `terraform/modules/substrate_openshift` |
| `aws` | `terraform/modules/substrate_aws` |
| `azure` | `terraform/modules/substrate_azure` |
| `okd` | `terraform/modules/substrate_okd` |

## Demo flow

See [docs/mvp-demo-runbook.md](../../docs/mvp-demo-runbook.md) for the detailed presenter guide including exact timing, expected outcomes, and fallback steps.

## Security note

Showcase mode uses real credentials and live infrastructure. Follow least-privilege guidance:

- Use short-lived API tokens or role-bound service accounts
- Rotate credentials after each demo
- Do not log or share `.env` files
