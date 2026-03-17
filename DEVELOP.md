# Development Setup

## Quick start

```bash
# Clone
git clone https://github.com/kpeacocke/terraable.git
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

### Local setup
- Python 3.11+
- Poetry (install via `curl -sSL https://install.python-poetry.org | python3 -`)
- Terraform 1.5+
- Ansible 2.10+
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

### Unit tests with coverage
```bash
poetry run pytest --cov=terraable --cov-report=html --cov-report=term
```

### Mutation testing
```bash
poetry run mutmut run
poetry run mutmut results
```

### Type checking
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
```bashoetry run pytest --cov` to verify 100% coverage.
   - Run `poetry run mutmut run` and verify mutation score ≥ 80%.
   - Run `poetry run mypy terraable` for strict type checking.
   - Run `poetry run ruff check . && poetry run ruff format .` for linting and formatting.
   - Run integration tests: `poetry run 

## Development workflow

1. **Pick an issue** from the MVP, Phase 2, or Phase 3 milestone.
2. **Create a feature branch**: `git checkout -b issue/123-short-title`
3. **Implement** the feature using the appropriate agent:
   - Architecture/design → `mvp-architect` agent
   - Implementation → `platform-builder` agent
   - Security/compliance → `security-compliance` agent
   - Demo/runbook → `demo-readiness` agent
4. **Test**:
   - Run `pytest --cov` to verify 100% coverage.
   - Run `mutmut run` and verify mutation score ≥ 80%.
   - Run integration tests: `pytest tests/integration/ -v`
5. **Docs**: Update relevant `.md` files in Australian English.
6. **Push and open a PR**: Include test evidence and security review in PR summary.

## Structure

```devcontainer/                  # VS Code dev container
├── tests/
│   ├── unit/                       # Unit tests
│   └── integration/                # Integration tests
├── pyproject.toml                  # Poetry configuration + tool settings
├── ruff.toml                       # Ruff linter/formatter config
├── mypy.ini                        # Mypy type checker config
└── terraform/                      # Provisioning (HCP Terraform)er
├── .venv/                          # Virtual environment (gitignored)
└── requirements-dev.txt            # Python dependencies
```

## Troubleshooting

**pytest not found:**
```bash
pip install pytest pytest-cov
```

**Terraform errors:**
`oetry run pytest
```

**Poetry not found:**
```bash
curl -sSL https://install.python-poetry.org | python3 -
export PATH="/root/.local/bin:$PATH"
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
poetry run coverage report -m  # Show lines needing coverage
poetry run pytest --cov=. --cov-report=html  # Open htmlcov/index.html
```

**Type checking errors:**
```bash
poetry run mypy terraable --show-error-codes  # Show error codes for investigation
- **Never commit secrets**: Use environment variables (`.env.example` provided).
- **Validate inputs**: All automation scripts validate externally sourced input.
- **Snyk scans**: Run `snyk code test` before pushing feature branches.
- **Responsible disclosure**: See [SECURITY.md](../SECURITY.md).

## Questions?

See [copilot-instructions.md](.github/copilot-instructions.md) for project context, or ask the appropriate agent:
- Architecture/design → `mvp-architect`
- Implementation → `platform-builder`
- Security → `security-compliance`
- Demo → `demo-readiness`
