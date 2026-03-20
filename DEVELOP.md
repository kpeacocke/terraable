# Development Setup

## Quick start

```bash
# Clone your fork or the canonical repo URL shown on GitHub
git clone https://github.com/<your-org-or-username>/terraable.git
cd terraable

# Option A: Use VS Code dev container (recommended — all tooling pre-installed)
# Open in VS Code and select "Reopen in Container"

# Option B: Local setup (macOS/Linux/Windows with WSL)
python3 -m venv .venv
source .venv/bin/activate  # or .\.venv\Scripts\activate on Windows
pip install --upgrade pip
```

## Prerequisites

### VS Code dev container (recommended)

- VS Code with Dev Containers extension.
- Docker or Podman.
- ~2GB free disk space.

The dev container installs all required tooling automatically on first launch via `.devcontainer/post-create.sh`. No manual tool installation is needed.

#### SSH access inside the container

The dev container forwards your host SSH agent socket (`SSH_AUTH_SOCK`) rather than
bind-mounting `~/.ssh`. This keeps private key material off the container filesystem
and works correctly on Linux, macOS, and WSL without path-concatenation issues.

Ensure your SSH agent is running on the host before opening the container:

```bash
# Linux / macOS / WSL
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519  # or your preferred key
```

### Local setup — tool versions

| Tool | Minimum version | Install |
|------|----------------|---------|
| Python | 3.11 | <https://python.org> |
| Poetry | 1.8 | `curl -sSL https://install.python-poetry.org \| python3 -` |
| Terraform CLI | 1.5 | <https://developer.hashicorp.com/terraform/install> |
| Ansible | 2.15 (ansible-core) | `pip install ansible` |
| ansible-rulebook | 1.0 | `pip install ansible-rulebook` |
| shellcheck | 0.9 | `apt install shellcheck` or `brew install shellcheck` |
| markdownlint-cli2 | 0.13 | `npm install -g markdownlint-cli2` |
| yamllint | 1.35 | `pip install yamllint` |
| Git | 2.40 | System package manager |

To verify all tools are available after local setup, run:

```bash
bash scripts/check-tools.sh
```

## Installation

```bash
# Install Python dependencies via Poetry
poetry install

# Verify installed tool versions
poetry run python -c "import terraable; print('terraable OK')"
terraform version
ansible --version
```

## Running checks locally

The following commands mirror the checks run in CI. Run all of them before opening a PR.

### Unit tests with coverage

```bash
poetry run pytest tests -v --cov=terraable --cov-fail-under=100
```

### Type checking

```bash
poetry run mypy terraable
```

### Linting and formatting

```bash
# Ruff: code style and import order
poetry run ruff check terraable tests

# Auto-format code
poetry run ruff format terraable tests

# YAML lint
yamllint .

# Markdown lint
markdownlint-cli2 "**/*.md"

# Shell lint
shellcheck scripts/*.sh
```

### Terraform validation

```bash
terraform fmt -check -recursive terraform/
terraform validate
```

### Integration tests

```bash
poetry run pytest tests -m integration -v
```

## Development workflow

1. **Pick an issue** from the MVP, Phase 2, or Phase 3 milestone.
2. **Create a feature branch**: `git checkout -b feat/issue-123-short-title`
3. **Implement** using the appropriate agent:
   - Architecture/design → `mvp-architect` agent
   - Implementation → `platform-builder` agent
   - Security/compliance → `security-compliance` agent
   - Demo/runbook → `demo-readiness` agent
4. **Test**: Run `pytest tests -v --cov`, `ruff check`, `mypy`, `yamllint`, and `terraform validate`.
5. **Docs**: Update relevant `.md` files in Australian English.
6. **Push and open a PR**: Include test evidence and security implications in the PR summary.

## Repository structure

```text
.
├── .devcontainer/              # VS Code dev container setup
├── .github/                    # Copilot, agents, workflows, and PR metadata
├── ansible/
│   ├── awx/                    # AWX lab-mode bootstrap playbook and config
│   ├── eda/                    # EDA rulebooks, sources, and vars
│   ├── inventory.yml           # Inventory stub (copy to inventory.local.yml for real use)
│   ├── playbooks/              # Operational workflow playbooks
│   └── roles/                  # Ansible roles (baseline_hardening, portal_deploy, ssh_root_control)
├── docs/                       # Architecture, handoff contract, runbook, lab guide
├── modes/
│   ├── lab/                    # AWX-backed lab mode
│   ├── offline/                # Offline/mock mode with pre-seeded data
│   └── showcase/               # Live demo mode with HCP Terraform and AAP
├── scripts/                    # Contributor helper scripts
├── terraform/
│   └── modules/
│       ├── substrate_aws/      # AWS substrate module
│       ├── substrate_azure/    # Azure substrate module
│       ├── substrate_local/    # Local lab substrate module
│       ├── substrate_okd/      # OKD substrate module
│       └── substrate_openshift/ # OpenShift substrate module
├── terraable/                  # Python package: contract, orchestrator, HCP Terraform client
├── tests/                      # Python tests (100% coverage gate)
├── ui/
│   └── index.html              # Control-plane UI
├── .env.example                # Sample environment variable reference
├── CODEOWNERS
├── CONTRIBUTING.md
├── DEVELOP.md                  # This file
├── README.md
└── SECURITY.md
```

## Troubleshooting

**pytest not found:**

```bash
poetry install
```

**Poetry not found:**

```bash
curl -sSL https://install.python-poetry.org | python3 -
export PATH="$HOME/.local/bin:$PATH"
```

**Terraform errors:**

```bash
terraform init
terraform validate
```

**Ansible connectivity issues:**

Check [`ansible/inventory.yml`](ansible/inventory.yml) and ensure target systems are reachable.
Copy it to `ansible/inventory.local.yml` (git-ignored) and populate with your actual hosts.
Do not commit real hostnames or credentials.

**AWX bootstrap fails:**

Verify `AWX_HOST`, `AWX_USERNAME`, and `AWX_PASSWORD` are set in `.env` and that the AWX instance
is reachable. Check TLS certificate validity with `curl -v $AWX_HOST`.


## Prerequisites

### VS Code dev container (recommended)

- VS Code with Dev Containers extension.
- Docker or Podman.
- ~2GB free disk space.

#### SSH access inside the container

The dev container forwards your host SSH agent socket (`SSH_AUTH_SOCK`) rather than
bind-mounting `~/.ssh`. This keeps private key material off the container filesystem
and works correctly on Linux, macOS, and WSL without path-concatenation issues.

Ensure your SSH agent is running on the host before opening the container:

```bash
# Linux / macOS / WSL
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519  # or your preferred key
```

If you need to mount `~/.ssh` directly (e.g. for tooling that reads `known_hosts`
or `config` from disk), create a `.devcontainer/devcontainer.local.json`
(gitignored) and add:

```json
{
  "mounts": [
    "source=${localEnv:HOME}/.ssh,target=/home/vscode/.ssh,type=bind,consistency=cached,readonly"
  ]
}
```

Note the `readonly` flag. It limits exposure if the container is compromised.

### Local setup

- Python 3.11+
- Poetry (install via `curl -sSL https://install.python-poetry.org | python3 -`)
- Terraform 1.5+
- Ansible 10 (ansible-core 2.17+)
- Git

## Installation

```bash
# Install dependencies via Poetry
poetry install

# Verify Terraform
terraform version

# Verify Ansible
ansible --version
```

## Running tests

This branch currently contains scaffold directories for `terraable/` and `tests/`.
Use the commands below as the baseline once implementation files are added.

### Unit tests with coverage

```bash
poetry run pytest tests -v
```

### Mutation testing

Mutation testing becomes meaningful after unit tests are implemented.

```bash
poetry run mutmut run
poetry run mutmut results
```

### Type checking

Type checking becomes meaningful after Python modules are added under `terraable/`.

```bash
poetry run mypy terraable
```

### Linting and formatting

```bash
# Check code style
poetry run ruff check terraable tests

# Auto-format code
poetry run ruff format terraable tests
```

### Terraform validation

```bash
terraform fmt -check -recursive
terraform validate
```

### Integration tests

Integration test scaffolding exists under `tests/`, but integration suites are not
implemented in this branch yet. When they are added, run:

```bash
poetry run pytest tests -m integration -v
```

## Development workflow

1. **Pick an issue** from the MVP, Phase 2, or Phase 3 milestone.
2. **Create a feature branch**: `git checkout -b issue/123-short-title`
3. **Implement** the feature using the appropriate agent:
   - Architecture/design -> `mvp-architect` agent
   - Implementation -> `platform-builder` agent
   - Security/compliance -> `security-compliance` agent
   - Demo/runbook -> `demo-readiness` agent
4. **Test**: For scaffold changes, run `pytest tests -v` and
  `ruff check terraable tests`. Add `mypy terraable` once Python modules are in
  place. Add coverage and mutation gates (`pytest --cov`, `mutmut run`) once
  baseline tests exist. Run integration tests (`pytest tests -m integration -v`)
  after integration suites are added.
5. **Docs**: Update relevant `.md` files in Australian English.
6. **Push and open a PR**: Include test evidence and security review in the PR summary.

## Structure

```text
.
├── .devcontainer/                  # VS Code dev container setup
│   ├── devcontainer.json
│   └── post-create.sh
├── .github/                        # Copilot, agent, and PR metadata
│   ├── AGENTS.md
│   ├── agents/
│   ├── copilot-instructions.md
│   ├── instructions/
│   └── pull_request_template.md
├── terraable/                      # Python package scaffold
├── tests/                          # Test scaffold
├── CODEOWNERS
├── CONTRIBUTING.md
├── DEVELOP.md
├── README.md
├── SECURITY.md
├── poetry.lock
├── pyproject.toml                  # Poetry and tool configuration
└── ruff.toml                       # Ruff linter/formatter configuration
```

## Troubleshooting

**pytest not found:**

```bash
poetry install
```

**Poetry not found:**

```bash
# In the dev container, rebuild the container to reapply the Poetry feature.
# For local setup, install Poetry and ensure the user-local bin directory is on PATH.
curl -sSL https://install.python-poetry.org | python3 -
export PATH="$HOME/.local/bin:$PATH"
```

**Terraform errors:**

```bash
terraform init
terraform plan
```

**Ansible connectivity issues:**

Check [`ansible/inventory.yml`](ansible/inventory.yml) and ensure target systems are reachable.
This file is a stub — copy it to `ansible/inventory.local.yml` (git-ignored) and populate it
with your actual hosts before running playbooks. Do not commit real hostnames or credentials.

**Coverage gaps:**

```bash
# Run this after adding test modules and package code.
poetry run coverage report -m
poetry run pytest --cov=terraable --cov-report=html
```

**Type checking errors:**

```bash
poetry run mypy terraable --show-error-codes
```

## Security notes

- Never commit secrets. Use environment variables (for local development, use an untracked `.env` file or your shell environment).
- Validate externally sourced input in automation workflows.
- Run `snyk code test` before pushing feature branches with first-party code.
- Snyk organisation: the extension auto-selects based on your authenticated account. If you need to
  pin a specific org, add `"snyk.advanced.organization": "<your-org-id>"` to your personal
  `.vscode/settings.json` (not committed) or configure it via the Snyk extension settings UI.
  Never commit org IDs or account identifiers to version control.
- Responsible disclosure expectations are in [SECURITY.md](SECURITY.md).

## Questions?

See [.github/copilot-instructions.md](.github/copilot-instructions.md) for project context,
or ask the appropriate agent:

- Architecture/design -> `mvp-architect`
- Implementation -> `platform-builder`
- Security -> `security-compliance`
- Demo -> `demo-readiness`
