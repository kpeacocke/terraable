# Contributing

Please use pull requests for all changes to `main`.

## Fork and run

New contributors can get a fully offline demo running in under five minutes:

1. Fork this repository on GitHub and clone your fork:

  ```bash
  git clone https://github.com/<your-username>/terraable.git && cd terraable
  ```

2. Copy the sample environment file and start the control plane in offline mode:

  ```bash
  cp .env.example .env   # TERRAABLE_MOCK_MODE=true is already set
  python3 -m venv .venv && source .venv/bin/activate
  pip install poetry && poetry install
  TERRAABLE_MOCK_MODE=true python -m terraable.api_server --host 127.0.0.1 --port 8000
  ```

3. Open `http://127.0.0.1:8000`. All UI actions return pre-seeded responses — no live credentials required.

For target-specific credential setup, lab mode, and AWX bootstrap, see
[docs/lab-guide.md](docs/lab-guide.md).

## Branching

- Create feature branches from `main`
- Open a pull request
- Require review before merge

## Quality

Keep documentation in Australian English.

## Snyk Configuration

Do not commit Snyk tenant or organisation identifiers to repository workspace settings.

Set Snyk organisation values in user-local settings only, for example in your VS Code User `settings.json`:

```json
{
  "snyk.advanced.organization": "<your-org-uuid>",
  "snyk.advanced.autoSelectOrganization": true
}
```

## Dev Container SSH Access

The default dev container configuration does not mount host SSH keys.

Preferred approach:

- Use SSH agent forwarding to avoid exposing private keys inside the container filesystem.

Optional approach (opt-in only):

- If key files must be mounted for a local workflow, add a user-local override rather than changing the shared project config.
- Example override in `.devcontainer/devcontainer.local.json`:

```json
{
  "mounts": [
    "source=${localEnv:HOME}${localEnv:USERPROFILE}/.ssh,target=/home/vscode/.ssh,type=bind,consistency=cached"
  ]
}
```
