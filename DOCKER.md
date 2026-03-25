# Running Terraable in Docker

This guide explains how to run Terraable using Docker and docker-compose for local development and demos.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose v2 (`docker compose`) — available with Docker Desktop and Docker Engine 23+.
  If you only have the legacy `docker-compose` v1 binary, substitute `docker-compose` for `docker compose` in all commands below.
- Port 8888 available on localhost

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

The API server will be available at `http://localhost:8888`.

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
- **`terraable_state`** (named volume) → `/workspace/.terraable` (persistent state)
- **`terraform_cache`** (named volume) → `/workspace/.terraform` (persistent Terraform cache)

State and cache persist across container restarts, speeding up subsequent runs.

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

Verify volumes are created:

```bash
docker volume ls | grep terraable
docker volume inspect terraable_state
```

If volumes are missing, recreate them:

```bash
docker compose down -v
docker compose up
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
