# Showcase Mode

Showcase mode is the live-infrastructure presentation path for Terraable. The MVP narrative remains `local-lab + backstage`, while additional target backends are available for extended live demonstrations.

## Prerequisites

- HCP Terraform organisation with at least one workspace
- AAP subscription with controller access
- AWS, Azure, OKD, or OpenShift target with appropriate credentials
- Environment variables from `.env.example` fully populated

## Target status

The repository contains substrate modules for multiple targets. Use the status table below to choose a path that matches your demo risk profile:

| Target | Module | Current status |
|--------|--------|----------------|
| `local-lab` | `integration/local_lab/terraform` | Executable end-to-end via the control plane |
| `openshift` | `terraform/modules/substrate_openshift` | Module and contract scaffolding only |
| `aws` | `terraform/modules/substrate_aws` | Executable via dedicated backend (`AWSBackend`) |
| `azure` | `terraform/modules/substrate_azure` | Executable via dedicated backend (`AzureBackend`) |
| `okd` | `terraform/modules/substrate_okd` | Executable via dedicated backend (`OKDBackend`) |

Use showcase mode to narrate the target roadmap and live credentials model. For predictable presenter flow, prefer `local-lab + backstage` first, then use AWS/Azure/OKD as credential-complete extended paths. Keep OpenShift as roadmap/scaffolding in this branch.

## Demo flow

See [docs/mvp-demo-runbook.md](../../docs/mvp-demo-runbook.md) for the detailed presenter guide including exact timing, expected outcomes, and fallback steps.

## Security note

Showcase mode uses real credentials and live infrastructure. Follow least-privilege guidance:

- Use short-lived API tokens or role-bound service accounts
- Rotate credentials after each demo
- Do not log or share `.env` files
