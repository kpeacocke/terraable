#!/bin/bash
set -e

echo "Installing dependencies..."

if ! command -v poetry >/dev/null 2>&1; then
	echo "Poetry is not available in the dev container PATH. Rebuild the container so the Poetry feature is installed." >&2
	exit 1
fi

# Install dependencies via Poetry
poetry install --no-root

echo "Installation complete."
echo ""
echo "Quick start:"
echo "  poetry run pytest --cov=. --cov-report=term"
echo "  poetry run mutmut run"
echo "  poetry run mypy ."
echo "  poetry run ruff check . && poetry run ruff format ."
echo "  terraform validate"
echo "  ansible-lint"
