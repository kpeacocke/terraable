# Running Terraable in Docker

This guide explains how to run Terraable using Docker and docker-compose for local development and demos.

## Prerequisites

- Docker Engine 20.10+
- docker-compose 1.29+
- Port 8000 available on localhost

## Quick Start

### Build and run the backend service

```bash
# Build the image
docker-compose build

# Start the service
docker-compose up -d

# Check logs
docker-compose logs -f backend

# Stop the service
docker-compose down
```

The API server will be available at `http://localhost:8000`.

### Verify it's working

```bash
# Check health
curl http://localhost:8000/healthz

# Access the UI
open http://localhost:8000

# See active backend logs
docker-compose logs -f backend
```

## Configuration

Environment variables for the container can be set in `.env` or passed via `docker-compose`:

```bash
# Run with mock mode enabled
TERRAABLE_MOCK_MODE=true docker-compose up

# Set Terraform verbosity
TF_LOG=DEBUG docker-compose up

# Provide HCP Terraform credentials
HCP_TERRAFORM_TOKEN=xxxx docker-compose up
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
docker-compose up
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
docker-compose restart backend

# Or rebuild if dependencies changed:
docker-compose build
docker-compose up -d
```

### Run tests inside container

```bash
docker-compose exec backend poetry run pytest
docker-compose exec backend poetry run mypy .
docker-compose exec backend ruff check .
```

### Access the container shell

```bash
docker-compose exec backend /bin/bash
```

### Clean up volumes

```bash
# Remove containers only (keep volumes)
docker-compose down

# Remove everything including volumes
docker-compose down -v
```

## For Production / Demos

### Build a production image tag

```bash
docker build -t kpeacocke/terraable:latest .
docker push kpeacocke/terraable:latest
```

### Run without source mounts (clean demo)

```bash
docker run -p 127.0.0.1:8000:8000 \
  --env TERRAABLE_MOCK_MODE=true \
  --env TERRAABLE_MODE=offline-mock \
  kpeacocke/terraable:latest
```

### Using named volumes for state storage

State is automatically persisted in the `terraable_state` volume, allowing demos to maintain state across container restarts:

```bash
# Start fresh with clean state
docker-compose down -v
docker-compose up
```

## Networking

- Backend serves on `127.0.0.1:8000` (localhost-only for security)
- For remote access (e.g., from VM/remote machine), adjust `ports` in docker-compose.yml:

```yaml
ports:
  - "0.0.0.0:8000:8000"  # Accessible from any network interface
```

## Troubleshooting

### Port 8000 already in use

```bash
# Find process using port 8000
lsof -i :8000

# Use a different port
ports: ["127.0.0.1:8001:8000"]
```

### Container exits immediately

```bash
docker-compose logs backend
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
docker-compose down -v
docker-compose up
```

### Can't reach API from outside localhost

Change docker-compose.yml `ports` from `127.0.0.1:8000:8000` to `0.0.0.0:8000:8000`.

Note: This exposes the API to the network. Ensure `/api/session` rate-limiting or IP restrictions are in place for untrusted networks.

## Next Steps

- Set up `docker-compose.yml` with additional services (mock Ansible runner, local AWX, etc.)
- Create CI/CD pipeline to build and push images to registry
- Build Kubernetes manifests (Helm chart) for cluster deployment
- Document offline-mode image variants for air-gapped environments
