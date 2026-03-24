"""Shared pytest fixtures for the terraable test suite."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _deterministic_api_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set a predictable API post token for all tests so server and client agree."""
    monkeypatch.setenv("TERRAABLE_API_POST_TOKEN", "terraable-local-token")
