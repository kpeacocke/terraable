"""Tests for demo configuration API endpoints."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from terraable import api_server


def _post_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return standard POST request headers."""
    headers = {
        "Content-Type": "application/json",
        "X-Terraable-Token": "terraable-local-token",
    }
    if extra:
        headers.update(extra)
    return headers


class _FakeBackend:
    """Minimal fake backend for testing."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root

    def get_state(self) -> dict[str, object]:
        return {"mode": "live-local-lab", "controls":  {"ssh_root_login": True}}

    def configure_credentials(self, credentials: dict[str, str], **kwargs: object) -> dict[str, object]:
        return {"authenticated": True, "ready": True}


@pytest.mark.unit
def test_demo_status_endpoint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test GET /api/demo/status endpoint."""
    monkeypatch.setattr(api_server, "LocalLabBackend", _FakeBackend)
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    handler = api_server.make_handler(tmp_path)
    server = api_server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base = f"http://127.0.0.1:{server.server_port}"
        status_payload = json.loads(urlopen(f"{base}/api/demo/status").read().decode("utf-8"))
        
        assert "configuration" in status_payload
        assert "readiness" in status_payload
        assert status_payload["readiness"]["all_ready"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.unit
def test_demo_configure_all_fields(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test POST /api/demo/configure with all custom fields."""
    monkeypatch.setattr(api_server, "LocalLabBackend", _FakeBackend)
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    handler = api_server.make_handler(tmp_path)
    server = api_server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base = f"http://127.0.0.1:{server.server_port}"
        
        # Set all possible config fields - this exercises all if branches
        request = Request(
            f"{base}/api/demo/configure",
            data=json.dumps({
                "profile": "custom",
                "terraform": {
                    "backend": "tfe",
                    "connection_mode": "docker-compose-service",
                    "hostname": "tfe.example.com",
                    "token": "tfe-secret-token",
                    "organization": "tfe-org",
                },
                "ansible": {
                    "backend": "awx",
                    "connection_mode": "external-endpoint",
                    "hostname": "awx.example.com",
                    "username": "awx-user",
                    "password": "awx-password",
                    "insecure_skip_verify": True,
                },
            }).encode("utf-8"),
            headers=_post_headers(),
            method="POST",
        )
        payload = json.loads(urlopen(request).read().decode("utf-8"))
        
        # Verify all terraform fields are set
        assert payload["configuration"]["terraform"]["backend"] == "tfe"
        assert payload["configuration"]["terraform"]["connection_mode"] == "docker-compose-service"
        assert payload["configuration"]["terraform"]["hostname"] == "tfe.example.com"
        assert payload["configuration"]["terraform"]["organization"] == "tfe-org"
        
        # Verify all ansible fields  are set
        assert payload["configuration"]["ansible"]["backend"] == "awx"
        assert payload["configuration"]["ansible"]["connection_mode"] == "external-endpoint"
        assert payload["configuration"]["ansible"]["hostname"] == "awx.example.com"
        assert payload["configuration"]["ansible"]["insecure_skip_verify"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.unit
def test_demo_configure_invalid_profile_defaults_to_lab(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test invalid profile name defaults to lab."""
    monkeypatch.setattr(api_server, "LocalLabBackend", _FakeBackend)
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    handler = api_server.make_handler(tmp_path)
    server = api_server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base = f"http://127.0.0.1:{server.server_port}"
        request = Request(
            f"{base}/api/demo/configure",
            data=json.dumps({"profile": "nonexistent"}).encode("utf-8"),
            headers=_post_headers(),
            method="POST",
        )
        payload = json.loads(urlopen(request).read().decode("utf-8"))
        assert payload["configuration"]["active_profile"] == "lab"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.unit
def test_demo_configure_invalid_enum_raises_400(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test invalid enum value raises 400 error."""
    monkeypatch.setattr(api_server, "LocalLabBackend", _FakeBackend)
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    handler = api_server.make_handler(tmp_path)
    server = api_server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with pytest.raises(HTTPError) as excinfo:
            urlopen(
                Request(
                    f"{base}/api/demo/configure",
                    data=json.dumps({"profile": "custom", "terraform": {"backend": "invalid"}}).encode("utf-8"),
                    headers=_post_headers(),
                    method="POST",
                )
            )
        assert excinfo.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.unit
def test_demo_start_service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test POST /api/demo/start-service/<service> in offline mode."""
    monkeypatch.setattr(api_server, "LocalLabBackend", _FakeBackend)
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    handler = api_server.make_handler(tmp_path)
    server = api_server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base = f"http://127.0.0.1:{server.server_port}"
        
        # Set to offline mode
        config_req = Request(
            f"{base}/api/demo/configure",
            data=json.dumps({"profile": "offline-fallback"}).encode("utf-8"),
            headers=_post_headers(),
            method="POST",
        )
        urlopen(config_req)
        
        # Start service
        start_req = Request(
            f"{base}/api/demo/start-service/terraform",
            data=json.dumps({}).encode("utf-8"),
            headers=_post_headers(),
            method="POST",
        )
        payload = json.loads(urlopen(start_req).read().decode("utf-8"))
        assert payload["service"] == "terraform"
        assert payload["is_ready"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.unit
def test_demo_service_ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test POST /api/demo/service-ready/<service>."""
    monkeypatch.setattr(api_server, "LocalLabBackend", _FakeBackend)
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    handler = api_server.make_handler(tmp_path)
    server = api_server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base = f"http://127.0.0.1:{server.server_port}"
        ready_req = Request(
            f"{base}/api/demo/service-ready/terraform",
            data=json.dumps({}).encode("utf-8"),
            headers=_post_headers(),
            method="POST",
        )
        payload = json.loads(urlopen(ready_req).read().decode("utf-8"))
        assert payload["service"] == "terraform"
        assert payload["is_ready"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
