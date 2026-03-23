"""Tests for the stdlib control-plane API server."""

from __future__ import annotations

import io
import json
import threading
from email.message import Message
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from terraable import api_server
from terraable.aws_backend import AWSBackend
from terraable.azure_backend import AzureBackend
from terraable.local_lab import LocalLabBackend
from terraable.okd_backend import OKDBackend


def _headers(values: dict[str, str]) -> Message:
    headers: Message = Message()
    for key, value in values.items():
        headers[key] = value
    return headers


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

    def inject_synthetic_incident(self) -> dict[str, object]:
        return {
            "action": "inject_synthetic_incident",
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
def test_handler_returns_404_when_ui_index_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(api_server, "LocalLabBackend", _FakeBackend)
    handler = api_server.make_handler(tmp_path)
    server = api_server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with pytest.raises(HTTPError) as excinfo:
            urlopen(f"{base}/")
        assert excinfo.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.unit
def test_handler_returns_500_when_ui_index_is_invalid_utf8(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(api_server, "LocalLabBackend", _FakeBackend)
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_bytes(b"\xff\xfe")
    handler = api_server.make_handler(tmp_path)
    server = api_server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with pytest.raises(HTTPError) as excinfo:
            urlopen(f"{base}/")
        assert excinfo.value.code == 500
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.unit
def test_handler_configure_auth_accepts_non_object_json_payload(
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
            f"{base}/api/auth/configure?target=local-lab&portal=backstage",
            data=b"[]",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        payload = json.loads(urlopen(request).read().decode("utf-8"))
        assert payload["auth"]["authenticated"] is False

        backend = cast(Any, handler).backend
        assert isinstance(backend, _FakeBackend)
        assert backend.auth_configured == {}
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
            "inject_synthetic_incident",
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
def test_read_json_payload_returns_empty_dict_for_non_object_payload() -> None:
    handler = api_server.TerraableRequestHandler.__new__(api_server.TerraableRequestHandler)
    handler.headers = _headers({"Content-Length": "2"})
    handler.rfile = io.BytesIO(b"[]")

    payload = handler._read_json_payload()

    assert payload == {}


@pytest.mark.unit
def test_read_json_payload_rejects_invalid_content_length() -> None:
    handler = api_server.TerraableRequestHandler.__new__(api_server.TerraableRequestHandler)
    handler.headers = _headers({"Content-Length": "abc"})
    handler.rfile = io.BytesIO(b"{}")

    with pytest.raises(ValueError, match="Invalid Content-Length"):
        handler._read_json_payload()


@pytest.mark.unit
def test_read_json_payload_defaults_missing_content_length_to_empty_object() -> None:
    handler = api_server.TerraableRequestHandler.__new__(api_server.TerraableRequestHandler)
    handler.headers = _headers({})
    handler.rfile = io.BytesIO(b"")

    payload = handler._read_json_payload()

    assert payload == {}


@pytest.mark.unit
def test_read_json_payload_rejects_negative_content_length() -> None:
    handler = api_server.TerraableRequestHandler.__new__(api_server.TerraableRequestHandler)
    handler.headers = _headers({"Content-Length": "-1"})
    handler.rfile = io.BytesIO(b"{}")

    with pytest.raises(ValueError, match="Invalid Content-Length"):
        handler._read_json_payload()


@pytest.mark.unit
def test_read_json_payload_rejects_oversized_content_length() -> None:
    handler = api_server.TerraableRequestHandler.__new__(api_server.TerraableRequestHandler)
    too_large = api_server.TerraableRequestHandler.max_json_payload_bytes + 1
    handler.headers = _headers({"Content-Length": str(too_large)})
    handler.rfile = io.BytesIO(b"{}")

    with pytest.raises(ValueError, match="Content-Length exceeds maximum allowed size"):
        handler._read_json_payload()


class _FakeConnection:
    def __init__(self) -> None:
        self.timeout: float | None = None

    def gettimeout(self) -> float | None:
        return self.timeout

    def settimeout(self, value: float | None) -> None:
        self.timeout = value


class _TimeoutReader:
    def read(self, _length: int) -> bytes:
        raise TimeoutError("timed out")


class _SocketTimeoutReader:
    def read(self, _length: int) -> bytes:
        raise TimeoutError("timed out")


@pytest.mark.unit
def test_read_json_payload_rejects_incomplete_body() -> None:
    handler = api_server.TerraableRequestHandler.__new__(api_server.TerraableRequestHandler)
    handler.headers = _headers({"Content-Length": "10"})
    handler.rfile = io.BytesIO(b"{}")
    handler.connection = _FakeConnection()

    with pytest.raises(ValueError, match="Incomplete JSON payload"):
        handler._read_json_payload()


@pytest.mark.unit
def test_read_json_payload_restores_socket_timeout_after_read() -> None:
    handler = api_server.TerraableRequestHandler.__new__(api_server.TerraableRequestHandler)
    handler.headers = _headers({"Content-Length": "2"})
    handler.rfile = io.BytesIO(b"{}")
    fake_connection = _FakeConnection()
    fake_connection.settimeout(30.0)
    handler.connection = fake_connection

    payload = handler._read_json_payload()

    assert payload == {}
    assert handler.connection.gettimeout() == pytest.approx(30.0)


@pytest.mark.unit
def test_read_json_payload_reports_timeout_and_restores_socket_timeout() -> None:
    handler = api_server.TerraableRequestHandler.__new__(api_server.TerraableRequestHandler)
    handler.headers = _headers({"Content-Length": "2"})
    handler.rfile = cast(Any, _TimeoutReader())
    fake_connection = _FakeConnection()
    fake_connection.settimeout(15.0)
    handler.connection = fake_connection

    with pytest.raises(ValueError, match="Timed out while reading JSON payload"):
        handler._read_json_payload()

    assert handler.connection.gettimeout() == pytest.approx(15.0)


@pytest.mark.unit
def test_read_json_payload_reports_socket_timeout_and_restores_timeout() -> None:
    handler = api_server.TerraableRequestHandler.__new__(api_server.TerraableRequestHandler)
    handler.headers = _headers({"Content-Length": "2"})
    handler.rfile = cast(Any, _SocketTimeoutReader())
    fake_connection = _FakeConnection()
    fake_connection.settimeout(20.0)
    handler.connection = fake_connection

    with pytest.raises(ValueError, match="Timed out while reading JSON payload"):
        handler._read_json_payload()

    assert handler.connection.gettimeout() == pytest.approx(20.0)


@pytest.mark.unit
def test_loopback_host_helper_accepts_localhost_and_loopback_ip() -> None:
    assert api_server.TerraableRequestHandler._is_loopback_host("localhost")
    assert api_server.TerraableRequestHandler._is_loopback_host("127.0.0.1")
    assert api_server.TerraableRequestHandler._is_loopback_host("::1")
    assert not api_server.TerraableRequestHandler._is_loopback_host("example.com")


@pytest.mark.unit
def test_safe_post_request_rejects_non_loopback_client() -> None:
    handler = api_server.TerraableRequestHandler.__new__(api_server.TerraableRequestHandler)
    handler.client_address = ("10.0.0.2", 12345)
    handler.headers = _headers({})
    called: list[tuple[int, str]] = []

    def fake_send_error(code: int, message: str = "") -> None:
        called.append((code, message))

    handler.send_error = fake_send_error  # type: ignore[assignment]

    allowed = handler._require_safe_post_request()

    assert allowed is False
    assert called == [(403, "POST access restricted to localhost")]


@pytest.mark.unit
def test_safe_post_request_rejects_null_origin() -> None:
    handler = api_server.TerraableRequestHandler.__new__(api_server.TerraableRequestHandler)
    handler.client_address = ("127.0.0.1", 12345)
    handler.headers = _headers({"Origin": "null"})
    called: list[tuple[int, str]] = []

    def fake_send_error(code: int, message: str = "") -> None:
        called.append((code, message))

    handler.send_error = fake_send_error  # type: ignore[assignment]

    allowed = handler._require_safe_post_request()

    assert allowed is False
    assert called == [(403, "POST origin is not allowed")]


@pytest.mark.unit
def test_safe_post_request_rejects_hostname_less_origin() -> None:
    handler = api_server.TerraableRequestHandler.__new__(api_server.TerraableRequestHandler)
    handler.client_address = ("127.0.0.1", 12345)
    handler.headers = _headers({"Origin": "file:///tmp/index.html"})
    called: list[tuple[int, str]] = []

    def fake_send_error(code: int, message: str = "") -> None:
        called.append((code, message))

    handler.send_error = fake_send_error  # type: ignore[assignment]

    allowed = handler._require_safe_post_request()

    assert allowed is False
    assert called == [(403, "POST origin is not allowed")]


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
def test_post_rejects_non_local_origin(
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
        with pytest.raises(HTTPError) as excinfo:
            urlopen(
                Request(
                    f"{base}/api/actions/create_environment",
                    data=b"{}",
                    headers={
                        "Content-Type": "application/json",
                        "Origin": "https://evil.example",
                    },
                    method="POST",
                )
            )
        assert excinfo.value.code == 403
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


@pytest.mark.unit
def test_get_backend_dispatches_provider_backends(tmp_path: Path) -> None:
    assert isinstance(api_server.get_backend(tmp_path, "local-lab"), LocalLabBackend)
    assert isinstance(api_server.get_backend(tmp_path, "aws"), AWSBackend)
    assert isinstance(api_server.get_backend(tmp_path, "azure"), AzureBackend)
    assert isinstance(api_server.get_backend(tmp_path, "okd"), OKDBackend)
    assert isinstance(api_server.get_backend(tmp_path, "unknown"), LocalLabBackend)


@pytest.mark.unit
def test_make_handler_resets_backend_cache_per_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(api_server, "LocalLabBackend", _FakeBackend)
    workspace_one = tmp_path / "one"
    workspace_two = tmp_path / "two"
    (workspace_one / "ui").mkdir(parents=True)
    (workspace_two / "ui").mkdir(parents=True)
    (workspace_one / "ui" / "index.html").write_text("<html></html>", encoding="utf-8")
    (workspace_two / "ui" / "index.html").write_text("<html></html>", encoding="utf-8")

    handler_one = api_server.make_handler(workspace_one)
    handler_two = api_server.make_handler(workspace_two)

    backend_one = cast(Any, handler_one).backends["local-lab"]
    backend_two = cast(Any, handler_two).backends["local-lab"]
    assert backend_one.workspace_root == workspace_one
    assert backend_two.workspace_root == workspace_two
    assert cast(Any, handler_one).backends is not cast(Any, handler_two).backends


@pytest.mark.unit
def test_get_active_backend_prefers_handler_backend_for_local_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(api_server, "LocalLabBackend", _FakeBackend)
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    handler = api_server.make_handler(tmp_path)

    sentinel_backend = _FakeBackend(tmp_path)
    cast(Any, handler).backend = sentinel_backend
    backend = cast(Any, handler).get_active_backend("local-lab")

    assert backend is sentinel_backend
    assert cast(Any, handler).backends["local-lab"] is sentinel_backend


@pytest.mark.unit
def test_get_active_backend_normalises_unknown_targets_to_local_lab(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(api_server, "LocalLabBackend", _FakeBackend)
    ui_dir = tmp_path / "ui"
    ui_dir.mkdir()
    (ui_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    handler = api_server.make_handler(tmp_path)

    backend = cast(Any, handler).get_active_backend("foo123")

    assert isinstance(backend, _FakeBackend)
    assert backend is cast(Any, handler).backends["local-lab"]
    assert "foo123" not in cast(Any, handler).backends


@pytest.mark.unit
def test_action_failure_uses_target_backend_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class _TargetBackend(_FakeBackend):
        def __init__(self, workspace_root: Path, target_name: str) -> None:
            super().__init__(workspace_root)
            self.target_name = target_name

        def get_state(self) -> dict[str, object]:
            return {"mode": f"live-{self.target_name}", "controls": {"ssh_root_login": True}}

    def fake_get_backend(workspace_root: Path, target: str) -> _TargetBackend:
        return _TargetBackend(workspace_root, target)

    monkeypatch.setattr(api_server, "get_backend", fake_get_backend)
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
            data=json.dumps({"target": "aws"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        payload = json.loads(urlopen(request).read().decode("utf-8"))

        assert payload["status"] == "failed"
        assert payload["state"]["mode"] == "live-aws"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
