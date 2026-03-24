#!/bin/bash
set -euo pipefail

echo "Installing dependencies and validating tooling..."

if ! command -v poetry >/dev/null 2>&1; then
  echo "Poetry is not available in the dev container PATH. Rebuild the container so the Poetry feature is installed." >&2
  exit 1
fi

# Install dependencies via Poetry
poetry install --no-root

# Terraform is normally provided by the devcontainer feature. Keep a fallback
# install path so local/custom rebuilds remain functional.
if ! command -v terraform >/dev/null 2>&1; then
  echo "Terraform not found; attempting fallback installation..."

  if ! command -v sudo >/dev/null 2>&1; then
    echo "Error: sudo is required to install Terraform in fallback mode." >&2
    exit 1
  fi

  sudo apt-get update
  sudo apt-get install -y wget gpg lsb-release
  wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor | sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg > /dev/null
  echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list > /dev/null
  sudo apt-get update
  sudo apt-get install -y terraform
fi

terraform --version

if command -v docker >/dev/null 2>&1; then
  echo "Docker CLI detected in dev container."
  if ! docker version >/dev/null 2>&1; then
    echo "Warning: Docker CLI is installed but daemon is unreachable from the container." >&2
    echo "Ensure Docker Desktop is running and rebuild/reopen the dev container." >&2
  fi
else
  echo "Warning: Docker CLI not found in container PATH." >&2
fi

echo "Installation complete."
echo ""
echo "Quick start:"
echo "  poetry run pytest --cov=terraable --cov-report=term"
echo "  poetry run mutmut run"
echo "  poetry run mypy terraable"
echo "  poetry run ruff check terraable tests && poetry run ruff format terraable tests"
echo "  terraform validate"
echo "  poetry run ansible-lint"
