# terraable

Reference demo showing HCP Terraform provisioning and Ansible Automation Platform operationalising, validating, and remediating environments.

## Status

MVP foundation implemented.

## MVP Scope

- Deterministic Terraform-to-Ansible handoff contract.
- Initial OpenShift substrate Terraform module.
- HCP Terraform run status and output retrieval support.
- AAP-style operational playbooks for baseline, scan, and remediation.
- Selectable portal path for `rhdh` and `backstage`.
- SSH root login hardening control with validation and remediation flow.
- Control-plane MVP UI with action and evidence panels.

## Repository Layout

- `terraform/`: provisioning modules and contract-oriented outputs.
- `ansible/`: playbooks and roles for operationalisation controls.
- `integration/`: handoff and orchestration integration assets.
- `ui/`: control-plane demo user interface.
- `docs/`: architecture, contract, and runbook documentation.
- `terraable/`: typed Python models and orchestration support code.

## Modes

- Showcase mode: live provisioning and workflow execution.
- Lab mode: reduced-complexity local target path.
- Offline/mock mode: deterministic demo replay using simulated outcomes.

## Key Documentation

- [Architecture overview](docs/architecture-overview.md)
- [Handoff contract](docs/handoff-contract.md)
- [HCP Terraform integration](docs/hcp-terraform.md)
- [MVP demo runbook](docs/mvp-demo-runbook.md)
- [Repository labels](docs/repository-labels.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for workflow and local setup guidance, including Snyk user-local configuration in the [Snyk Configuration section](CONTRIBUTING.md#snyk-configuration).
