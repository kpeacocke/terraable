# terraable

Reference demo showing HCP Terraform provisioning and Ansible Automation Platform operationalising, validating, and remediating environments.


## Quick Start

Get an offline demo running in under five minutes — no live credentials required:

```bash
git clone https://github.com/<your-username>/terraable.git && cd terraable
cp .env.example .env          # Optional: sample credential template
python3 -m venv .venv && source .venv/bin/activate
pip install poetry && poetry install
TERRAABLE_MOCK_MODE=true python -m terraable.api_server --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. All actions (create, baseline, scan, drift, remediate) return
pre-seeded responses — no HCP Terraform or Ansible credentials required.

For the full walkthrough, credential setup, and advancing to live execution, see
[docs/lab-guide.md](docs/lab-guide.md).

## Status

Local-lab now has an executable end-to-end path: UI -> Python API -> Terraform contract apply -> Ansible operational workflows against workspace-local lab files.

## MVP Scope

- Deterministic Terraform-to-Ansible handoff contract.
- Initial OpenShift substrate Terraform module.
- HCP Terraform run status and output retrieval support.
- AAP-style operational playbooks for baseline, scan, and remediation.
- Selectable portal path for `rhdh` and `backstage`.
- SSH root login hardening control with validation and remediation flow.
- Control-plane MVP UI with action and evidence panels.

## Phase 3 Additions

- Added substrate modules for `gcp`, `vmware`, `parallels`, and `hyper-v`.
- Added local target auto-detection helper and UI suggestion rendering.
- Added synthetic incident feed action and UI panel for demo storytelling.
- Added expanded compliance control visibility beyond SSH root login.
- Added observability dashboard panel for Terraform and workflow stage tracing.

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

## Source Of Truth

- Scripted MVP flow: `local-lab + backstage` is the default presenter path.
- Extended live targets: `aws`, `azure`, `okd`, `gcp`, `vmware`, `parallels`, and `hyper-v` are executable when credentials and platform prerequisites are satisfied.
- Scaffold-only in this branch: `openshift` remains contract/module scaffolding and is not selectable as a live control-plane target.
- Token convention: use `TF_TOKEN_<hostname>` as primary. `HCP_TERRAFORM_TOKEN` is supported as a backwards-compatible alias in UI-driven auth flows.

## Running The Control Plane

Preconditions:

- `terraform` available on `PATH`.
- Python environment has `ansible` installed.

Run:

```bash
python -m terraable.api_server --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000`.

Credential authentication:

- Credentials can be provided from `.env` and/or entered in the UI Authentication panel.
- Action buttons stay disabled until the selected target and portal are authenticated and executable.
- For the current executable path (`local-lab`), provide an HCP Terraform token via Terraform CLI convention (`TF_TOKEN_<hostname>`, with `TERRAABLE_TFC_HOSTNAME` defaulting to `app.terraform.io`). The UI also accepts `HCP_TERRAFORM_TOKEN` as a backwards-compatible alias.

Current executable scope:

- `local-lab + backstage` is wired end-to-end.
- `local-lab + rhdh` is wired end-to-end.
- `gcp`, `vmware`, `parallels`, and `hyper-v` are wired through executable Terraform contract applies in live mode.
- AWS, Azure, and OKD execute via their dedicated backend classes.
- OpenShift remains module-level contract scaffolding in this branch.

## Key Documentation

- [Architecture overview](docs/architecture-overview.md)
- [Credential matrix](docs/credentials-matrix.md)
- [Handoff contract](docs/handoff-contract.md)
- [HCP Terraform integration](docs/hcp-terraform.md)
- [MVP demo runbook](docs/mvp-demo-runbook.md)
- [Repository labels](docs/repository-labels.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for workflow and local setup guidance, including Snyk user-local configuration in the [Snyk Configuration section](CONTRIBUTING.md#snyk-configuration).
