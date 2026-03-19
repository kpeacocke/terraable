# Contributing

Please use pull requests for all changes to `main`.

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
