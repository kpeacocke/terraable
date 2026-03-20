"""Tests for the stdlib control-plane API server."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from terraable import api_server


class _FakeBackend:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.auth_configured: dict[str, str] = {}

    def get_state(self) -> dict[str, object]:
        return {"mode": "live-local-lab", "controls": {"ssh_root_login": True}}

    def create_environment(self, **kwargs: object) -> dict[str, object]:
        return {
            "action": "create_environment",
            "status": "succeeded",
            "detail": json.dumps(kwargs, sort_keys=True),
            "tone": "ok",
            "state": self.get_state(),
        }

    def apply_baseline(self) -> dict[str, object]:
        raise RuntimeError("boom")

    def run_compliance_scan(self) -> dict[str, object]:
        return {
            "action": "run_compliance_scan",
            "status": "succeeded",
            "detail": "ok",
            "tone": "ok",
            "state": self.get_state(),
        }

    def inject_ssh_drift(self) -> dict[str, object]:
        return {
            "action": "inject_ssh_drift",
            "status": "succeeded",
            "detail": "ok",
            "tone": "warn",
            "state": self.get_state(),
        }

    def inject_service_drift(self) -> dict[str, object]:
        return {
            "action": "inject_service_drift",
            "status": "succeeded",
            "detail": "ok",
            "tone": "warn",
            "state": self.get_state(),
        }

    def run_remediation(self) -> dict[str, object]:
        return {
            "action": "run_remediation",
            "status": "succeeded",
            "detail": "ok",
            "tone": "ok",
            "state": self.get_state(),
        }

    def get_auth_status(self, *, target: str, portal: str) -> dict[str, object]:
        return {
            "authenticated": True,
            "ready": target == "local-lab" and portal in {"backstage", "rhdh"},
            "required_credentials": ["HCP_TERRAFORM_TOKEN"],
            "missing_credentials": [],
            "credential_sources": {"HCP_TERRAFORM_TOKEN": "dotenv"},
            "blockers": [],
        }

    def configure_credentials(
        self,
        credentials: dict[str, str],
        *,
        target: str = "local-lab",
        portal: str = "backstage",
    ) -> dict[str, object]:
        del target, portal
        self.auth_configured = credentials
        return {
            "authenticated": bool(credentials.get("HCP_TERRAFORM_TOKEN")),
            "ready": bool(credentials.get("HCP_TERRAFORM_TOKEN")),
            "required_credentials": ["HCP_TERRAFORM_TOKEN"],
            "missing_credentials": [],
            "credential_sources": {"HCP_TERRAFORM_TOKEN": "ui"},
            "blockers": [],
        }


@pytest.mark.unit
def test_handler_serves_ui_state_and_action(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api_server, "LocalLabBackend", _FakeBackend)
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html><body>ui</body></html>", encoding="utf-8")
    handler = api_server.make_handler(tmp_path)
    server = api_server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base = f"http://127.0.0.1:{server.server_port}"
        index_body = urlopen(f"{base}/").read().decode("utf-8")
        assert "ui" in index_body

        state_payload = json.loads(urlopen(f"{base}/api/state").read().decode("utf-8"))
        assert state_payload["state"]["mode"] == "live-local-lab"

        request = Request(
            f"{base}/api/actions/create_environment",
            data=json.dumps(
                {
                    "target": "local-lab",
                    "portal": "backstage",
                    "profile": "baseline",
                    "eda": "enabled",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        action_payload = json.loads(urlopen(request).read().decode("utf-8"))
        assert action_payload["status"] == "succeeded"
        assert '"target": "local-lab"' in action_payload["detail"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.unit
def test_handler_returns_fail_payload_for_runtime_error_and_404(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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
            f"{base}/api/actions/apply_baseline",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        error_payload = json.loads(urlopen(request).read().decode("utf-8"))
        assert error_payload["status"] == "failed"
        assert error_payload["detail"] == "boom"

        with pytest.raises(HTTPError) as excinfo:
            urlopen(f"{base}/missing")
        assert excinfo.value.code == 404

        with pytest.raises(HTTPError) as post_excinfo:
            urlopen(
                Request(
                    f"{base}/not-an-action",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            )
        assert post_excinfo.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.unit
def test_handler_serves_healthz_and_other_actions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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
        health_payload = json.loads(urlopen(f"{base}/healthz").read().decode("utf-8"))
        assert health_payload == {"status": "ok"}

        for action in (
            "run_compliance_scan",
            "inject_ssh_drift",
            "inject_service_drift",
            "run_remediation",
        ):
            request = Request(
                f"{base}/api/actions/{action}",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            payload = json.loads(urlopen(request).read().decode("utf-8"))
            assert payload["action"] == action
            assert payload["status"] == "succeeded"

        with pytest.raises(HTTPError) as excinfo:
            urlopen(
                Request(
                    f"{base}/api/actions/unknown",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            )
        assert excinfo.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.unit
def test_handler_serves_auth_endpoints(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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
        auth_payload = json.loads(
            urlopen(f"{base}/api/auth/status?target=local-lab&portal=backstage")
            .read()
            .decode("utf-8")
        )
        assert auth_payload["auth"]["ready"] is True

        request = Request(
            f"{base}/api/auth/configure",
            data=json.dumps({"credentials": {"HCP_TERRAFORM_TOKEN": "token"}}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        configure_payload = json.loads(urlopen(request).read().decode("utf-8"))
        assert configure_payload["auth"]["authenticated"] is True

        bad_request = Request(
            f"{base}/api/auth/configure",
            data=json.dumps({"credentials": []}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        bad_payload = json.loads(urlopen(bad_request).read().decode("utf-8"))
        assert bad_payload["auth"]["authenticated"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.unit
def test_handler_returns_400_for_malformed_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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
        # Malformed JSON to /api/auth/configure should return 400.
        with pytest.raises(HTTPError) as excinfo:
            urlopen(
                Request(
                    f"{base}/api/auth/configure",
                    data=b"not-json{{",
                    headers={"Content-Type": "application/json", "Content-Length": "10"},
                    method="POST",
                )
            )
        assert excinfo.value.code == 400

        # Malformed JSON to an action should return a JSON failure payload (not crash).
        action_request = Request(
            f"{base}/api/actions/run_compliance_scan",
            data=b"not-json{{",
            headers={"Content-Type": "application/json", "Content-Length": "10"},
            method="POST",
        )
        error_payload = json.loads(urlopen(action_request).read().decode("utf-8"))
        assert error_payload["status"] == "failed"
        assert "Invalid JSON" in error_payload["detail"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.unit
def test_handler_configure_passes_target_and_portal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, str] = {}

    class _CapturingBackend(_FakeBackend):
        def configure_credentials(
            self,
            credentials: dict[str, str],
            *,
            target: str = "local-lab",
            portal: str = "backstage",
        ) -> dict[str, object]:
            captured["target"] = target
            captured["portal"] = portal
            return super().configure_credentials(credentials, target=target, portal=portal)

    monkeypatch.setattr(api_server, "LocalLabBackend", _CapturingBackend)
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
            f"{base}/api/auth/configure",
            data=json.dumps(
                {
                    "credentials": {"HCP_TERRAFORM_TOKEN": "tok"},
                    "target": "aws",
                    "portal": "rhdh",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urlopen(request)
        assert captured == {"target": "aws", "portal": "rhdh"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.unit
def test_main_starts_and_closes_server(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    events: dict[str, object] = {}

    class _FakeServer:
        def __init__(self, addr: tuple[str, int], handler: type[object]) -> None:
            events["addr"] = addr
            events["handler"] = handler
            events["closed"] = False

        def serve_forever(self) -> None:
            raise KeyboardInterrupt

        def server_close(self) -> None:
            events["closed"] = True

    monkeypatch.setattr(api_server, "ThreadingHTTPServer", _FakeServer)
    monkeypatch.setattr(
        "sys.argv",
        [
            "terraable-api",
            "--host",
            "127.0.0.1",
            "--port",
            "8123",
            "--workspace",
            str(tmp_path),
        ],
    )
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>", encoding="utf-8")

    api_server.main()

    assert events["addr"] == ("127.0.0.1", 8123)
    assert events["closed"] is True
