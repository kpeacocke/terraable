#!/bin/bash
set -e

echo "Installing Poetry and dependencies..."
curl -sSL https://install.python-poetry.org | python3 -

export PATH="/root/.local/bin:$PATH"

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
