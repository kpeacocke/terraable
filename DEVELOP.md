# Development Setup

## Quick start

```bash
# Clone your fork or the canonical repo URL shown on GitHub
git clone https://github.com/<your-org-or-username>/terraable.git
cd terraable

# Option A: Use VS Code dev container
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

Check `ansible/inventory.yml` and ensure target systems are reachable.

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

- Never commit secrets. Use environment variables (`.env.example` provided).
- Validate externally sourced input in automation workflows.
- Run `snyk code test` before pushing feature branches with first-party code.
- Responsible disclosure expectations are in [SECURITY.md](SECURITY.md).

## Questions?

See [.github/copilot-instructions.md](.github/copilot-instructions.md) for project context,
or ask the appropriate agent:

- Architecture/design -> `mvp-architect`
- Implementation -> `platform-builder`
- Security -> `security-compliance`
- Demo -> `demo-readiness`
