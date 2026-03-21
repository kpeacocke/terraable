# Fork-and-Run Lab Guide

This guide walks you through forking the repository and running the Terraable demo in a local lab environment with minimal dependencies.

## Prerequisites

| Tool | Minimum version | Purpose |
|------|----------------|---------|
| Git | 2.40 | Clone and branch management |
| Python | 3.11 | `terraable` package and tests |
| Terraform CLI | 1.9 | Substrate module validation |
| Ansible | 10.0 | Playbook and role execution |
| Docker or Podman | latest | Optional: local container target |

Not all tools are required for every demo path. See [Choosing a lab mode](#choosing-a-lab-mode) below.

---

## 1. Fork and clone

1. Fork the repository on GitHub.
2. Clone your fork:

   ```bash
   git clone https://github.com/<your-username>/terraable.git
   cd terraable
   ```

3. Confirm the default branch is `main`:

   ```bash
   git branch
   ```

---

## 2. Set up your Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install poetry
poetry install
```

Verify the setup:

```bash
pytest
```

All tests should pass.

---

## 3. Configure environment variables

Copy the sample environment file and populate it with your values:

```bash
cp .env.example .env
```

Open `.env` and fill in the required values. See [.env.example](../.env.example) for field descriptions. Do **not** commit `.env` — it is in `.gitignore`.

Minimum required variables for the offline/mock mode:

```
TERRAABLE_MOCK_MODE=true
TERRAABLE_TFC_HOSTNAME=app.terraform.io
```

---

## 4. Choosing a lab mode

| Mode | Description | Location |
|------|-------------|----------|
| `showcase` | Full live demo with HCP Terraform and AAP | [modes/showcase](../modes/showcase/README.md) |
| `lab` | AWX-backed, suitable for workshops | [modes/lab](../modes/lab/README.md) |
| `offline` | No live infra — uses mock data | [modes/offline](../modes/offline/README.md) |

For a first fork-and-run, start with **offline mode**.

---

## 5. Running the offline demo

```bash
TERRAABLE_MOCK_MODE=true python -m terraable.api_server --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` in a browser. All actions use pre-seeded mock state — no live credentials required.

---

## 6. Advancing to lab mode

1. Stand up an AWX instance (community.general or via operator).
2. Set environment variables in `.env`:

   ```
   AWX_HOST=https://awx.example.local
   AWX_USERNAME=admin
   AWX_PASSWORD=<redacted>
   TERRAABLE_SCM_URL=https://github.com/<your-username>/terraable.git
   ```

3. Bootstrap AWX with the Terraable project and job templates:

   ```bash
   ansible-playbook ansible/awx/bootstrap_awx.yml
   ```

4. Point the UI to your AWX-backed instance.

---

## 7. Troubleshooting

| Symptom | Likely cause | Remedy |
|---------|-------------|--------|
| Tests fail on import | Missing dependencies | Re-run `poetry install` |
| AWX bootstrap fails auth | Wrong credentials | Check `AWX_HOST`, `AWX_USERNAME`, `AWX_PASSWORD` in `.env` |
| EDA webhook not firing | EDA mode disabled | Set EDA mode to `enabled` in the UI |
| `local-lab + rhdh` rejected | Unsupported combination | Use `backstage` portal with `local-lab` target |

---

## 8. Contributing back

Refer to [CONTRIBUTING.md](../CONTRIBUTING.md) for branch conventions, PR requirements, and testing guidance.
