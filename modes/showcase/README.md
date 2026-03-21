# Showcase Mode

Showcase mode is the live-infrastructure presentation path for Terraable. In this branch, HCP Terraform modules exist for multiple substrates, but the only control-plane backend wired end-to-end remains `local-lab + backstage`.

## Prerequisites

- HCP Terraform organisation with at least one workspace
- AAP subscription with controller access
- AWS, Azure, OKD, or OpenShift target with appropriate credentials
- Environment variables from `.env.example` fully populated

## Target status

The repository contains substrate scaffolding for multiple targets, but executable control-plane support is still staged:

| Target | Module | Current status |
|--------|--------|----------------|
| `local-lab` | `integration/local_lab/terraform` | Executable end-to-end via the control plane |
| `openshift` | `terraform/modules/substrate_openshift` | Module and contract scaffolding only |
| `aws` | `terraform/modules/substrate_aws` | Module groundwork only |
| `azure` | `terraform/modules/substrate_azure` | Module groundwork only |
| `okd` | `terraform/modules/substrate_okd` | Module and contract scaffolding only |

Use showcase mode to narrate the target roadmap and live credentials model. Do not present AWS, Azure, OpenShift, or OKD as executable control-plane targets in this branch.

## Demo flow

See [docs/mvp-demo-runbook.md](../../docs/mvp-demo-runbook.md) for the detailed presenter guide including exact timing, expected outcomes, and fallback steps.

## Security note

Showcase mode uses real credentials and live infrastructure. Follow least-privilege guidance:

- Use short-lived API tokens or role-bound service accounts
- Rotate credentials after each demo
- Do not log or share `.env` files
