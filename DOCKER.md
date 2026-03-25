# Running Terraable in Docker

## Purpose and scope

This runbook explains how to run the Terraable backend container for local development and demo workflows using Docker Compose. It covers the backend API, the static UI served from the same container, persistent state and Terraform cache handling, and the recovery steps for the most common operational failures.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose v2 (`docker compose`) — available with Docker Desktop and Docker Engine 23+.
  If you only have the legacy `docker-compose` v1 binary, substitute `docker-compose` for `docker compose` in all commands below.
- Port 8888 available on localhost

## Inputs and configuration

The default compose configuration uses these effective inputs:

- `TERRAABLE_MODE=live-local-lab`
- `TERRAABLE_MOCK_MODE=false`
- `TF_LOG=`
- `TF_LOG_PATH=/workspace/.terraable/terraform.log`
- `ANSIBLE_VERBOSITY=0`
- `ANSIBLE_HOST_KEY_CHECKING=True`
- Optional credentials via `HCP_TERRAFORM_TOKEN` or `TF_TOKEN_app_terraform_io`

Runtime data is written under the repo root bind mounts:

- `./.terraable/` for Terraable state and Terraform logs
- `./.terraform/` for Terraform plugin and module cache

## Quick Start

### Build and run the backend service

```bash
# Build the image
docker compose build

# Start the service
docker compose up -d

# Check logs
docker compose logs -f backend

# Stop the service
docker compose down
```

## Expected outputs

A healthy startup produces these operator-visible outcomes:

- The API server is reachable at `http://localhost:8888`
- `GET /healthz` returns a successful response
- The UI loads from the same origin at `http://localhost:8888`
- Container logs are available with `docker compose logs -f backend`
- State files and logs land under `./.terraable/`, and Terraform cache lands under `./.terraform/`

### Verify it's working

```bash
# Check health
curl http://localhost:8888/healthz

# Access the UI
open http://localhost:8888

# See active backend logs
docker compose logs -f backend
```

## Configuration

Environment variables for the container can be set in `.env` or passed via `docker-compose`:

```bash
# Run with mock mode enabled
TERRAABLE_MOCK_MODE=true docker compose up

# Set Terraform verbosity
TF_LOG=DEBUG docker compose up

# Provide HCP Terraform credentials
HCP_TERRAFORM_TOKEN=xxxx docker compose up
```

### Persistent Configuration

Create a `.env` file in the project root:

```env
# .env (local, not committed)
TERRAABLE_MODE=live-local-lab
TERRAABLE_MOCK_MODE=false
TF_LOG=
HCP_TERRAFORM_TOKEN=your-token-here
ANSIBLE_VERBOSITY=0
```

Then run:

```bash
docker compose up
```

## Volume Mounts

The docker-compose setup mounts:

- **`.`** → `/workspace` (full project, read-write for state/logs)
- **`ansible/`** → `/workspace/ansible` (read-only, playbooks/roles)
- **`ui/`** → `/workspace/ui` (read-only, web interface)
- **`./.terraable/`** → `/workspace/.terraable` (bind mount for Terraable state and logs)
- **`./.terraform/`** → `/workspace/.terraform` (bind mount for Terraform plugin and module cache)

State and cache persist across container restarts because they are written to bind-mounted host directories. `docker compose down -v` will not remove these directories; delete `./.terraable/` and `./.terraform/` manually if you need a clean reset.

## Development Workflow

### Edit code and see live changes

```bash
# Code changes are visible immediately (delegated mounts)
# Edit terraable/*.py files and restart the service:
docker compose restart backend

# Or rebuild if dependencies changed:
docker compose build
docker compose up -d
```

### Run tests from host or devcontainer

```bash
# From the project root on your host or in a devcontainer
poetry run pytest
poetry run mypy .
poetry run ruff check .
```

### Access the container shell

```bash
docker compose exec backend /bin/bash
```

### Clean up volumes

```bash
# Remove containers only (keep volumes)
docker compose down

# Remove everything including volumes
docker compose down -v
```

## For Production / Demos

### Build a production image tag

```bash
docker build -t <your-registry>/<your-org>/terraable:latest .
docker push <your-registry>/<your-org>/terraable:latest
```

### Run without source mounts (clean demo)

```bash
docker run -p 127.0.0.1:8888:8000 \
  --env TERRAABLE_MOCK_MODE=true \
  --env TERRAABLE_MODE=offline-mock \
  <your-registry>/<your-org>/terraable:latest
```

### Using named volumes for state storage

State is automatically persisted in the `terraable_state` volume, allowing demos to maintain state across container restarts:

```bash
# Start fresh with clean state
docker compose down -v
docker compose up
```

## Networking

The backend binds to `0.0.0.0:8000` inside the container. The docker-compose configuration publishes this
as `127.0.0.1:8888:8000` — accessible on the Docker host at `http://localhost:8888`.

> **Important:** The API server enforces loopback-only access for all POST endpoints and `/api/session`
> in the server code itself — not just at the network layer. Requests from non-loopback clients to these
> endpoints will be rejected with HTTP 403 regardless of how the port is exposed.

This means:
- If you change `ports` in docker-compose.yml to `"0.0.0.0:8888:8000"`, the UI static files
  will load from remote clients, but `/api/session` and all action POSTs will still return 403.
- For local development and demos, run the browser on the same host as Docker and access
  `http://localhost:8888`.
- For remote access, use SSH port forwarding (`ssh -L 8888:localhost:8888 yourhost`) so
  requests originate from loopback on the Docker host.

## Troubleshooting

### Port 8888 already in use

```bash
# Find process using port 8888
lsof -i :8888

# Use a different host port
ports: ["127.0.0.1:8889:8000"]
```

### Container exits immediately

```bash
docker compose logs backend
```

Check for errors in the log output. Common issues:
- Missing Python packages (rebuild)
- Permission issues (check volume mounts)
- Workspace path issues (verify absolute paths)

### State/cache not persisting

Verify the runtime directories exist and are writable on the host:

```bash
ls -ld .terraable .terraform
```

If they are missing or have stale root-owned contents, recreate them:

```bash
rm -rf .terraable .terraform
mkdir -p .terraable .terraform
docker compose up
```

### Recovery

Use these recovery actions when the demo state or cache is no longer trustworthy:

```bash
# Stop containers and remove runtime state/cache
rm -rf .terraable .terraform

# Recreate clean runtime directories and restart
mkdir -p .terraable .terraform
docker compose up --build
```

### Can't reach API from outside localhost

By design, the server rejects session and POST requests from non-loopback clients (HTTP 403).
Changing the docker-compose port binding to `0.0.0.0` only exposes the TCP port — it does not
relax the server's loopback check. Use SSH port forwarding for secure remote access.

## Next Steps

- Set up `docker-compose.yml` with additional services (mock Ansible runner, local AWX, etc.)
- Create CI/CD pipeline to build and push images to registry
- Build Kubernetes manifests (Helm chart) for cluster deployment
- Document offline-mode image variants for air-gapped environments
