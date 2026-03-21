"""Small stdlib HTTP server for the Terraable control plane."""

from __future__ import annotations

import argparse
import ipaddress
import json
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar, cast
from urllib.parse import ParseResult, parse_qs, urlparse

from .local_lab import LocalLabBackend


class TerraableRequestHandler(BaseHTTPRequestHandler):
    backend: ClassVar[LocalLabBackend]
    ui_path: ClassVar[Path]

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_html(self.ui_path.read_text(encoding="utf-8"))
        elif parsed.path == "/api/state":
            self._send_json({"state": self.backend.get_state()})
        elif parsed.path == "/api/auth/status":
            self._handle_auth_status(parsed)
        elif parsed.path == "/healthz":
            self._send_json({"status": "ok"})
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def _handle_auth_status(self, parsed: ParseResult) -> None:
        query = parse_qs(parsed.query)
        target = query.get("target", ["local-lab"])[0]
        portal = query.get("portal", ["backstage"])[0]
        self._send_json(
            {
                "auth": self.backend.get_auth_status(
                    target=str(target),
                    portal=str(portal),
                )
            }
        )

    def do_POST(self) -> None:
        if not self._require_safe_post_request():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/auth/configure":
            self._handle_auth_configure()
            return
        if not parsed.path.startswith("/api/actions/"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._handle_action(parsed)

    def _handle_auth_configure(self) -> None:
        try:
            payload = self._read_json_payload()
            raw_credentials = payload.get("credentials")
            target = str(payload.get("target", "local-lab"))
            portal = str(payload.get("portal", "backstage"))
            credentials: dict[str, str] = {}
            if isinstance(raw_credentials, dict):
                typed_credentials = cast(dict[object, object], raw_credentials)
                credential_items = typed_credentials.items()
                for key, value in credential_items:
                    if isinstance(key, str) and isinstance(value, str):
                        credentials[key] = value
            self._send_json(
                {
                    "auth": self.backend.configure_credentials(
                        credentials, target=target, portal=portal
                    )
                }
            )
        except Exception as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def _handle_action(self, parsed: ParseResult) -> None:
        action = parsed.path.rsplit("/", 1)[-1]
        response: dict[str, Any] | None
        try:
            payload = self._read_json_payload()
            response = self._dispatch_action(action, payload)
        except Exception as exc:
            response = {
                "action": action,
                "status": "failed",
                "detail": str(exc),
                "tone": "fail",
                "state": self.backend.get_state(),
            }
        if response is not None:
            self._send_json(response)

    def _require_safe_post_request(self) -> bool:
        client_host = self.client_address[0] if self.client_address else ""
        if not self._is_loopback_host(client_host):
            self.send_error(HTTPStatus.FORBIDDEN, "POST access restricted to localhost")
            return False

        origin = self.headers.get("Origin") or self.headers.get("Referer")
        if origin:
            parsed_origin = urlparse(origin)
            origin_host = parsed_origin.hostname or ""
            if origin_host and not self._is_loopback_host(origin_host):
                self.send_error(HTTPStatus.FORBIDDEN, "POST origin must be localhost")
                return False

        return True

    @staticmethod
    def _is_loopback_host(hostname: str) -> bool:
        if hostname in {"localhost", ""}:
            return True

        try:
            return ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            return False

    def _dispatch_action(
        self,
        action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if action == "create_environment":
            return self.backend.create_environment(
                target=str(payload.get("target", "")),
                portal=str(payload.get("portal", "")),
                profile=str(payload.get("profile", "baseline")),
                eda=str(payload.get("eda", "disabled")),
            )
        simple: dict[str, Callable[[], dict[str, Any]]] = {
            "apply_baseline": self.backend.apply_baseline,
            "run_compliance_scan": self.backend.run_compliance_scan,
            "inject_ssh_drift": self.backend.inject_ssh_drift,
            "inject_service_drift": self.backend.inject_service_drift,
            "run_remediation": self.backend.run_remediation,
        }
        handler = simple.get(action)
        if handler is not None:
            return handler()
        self.send_error(HTTPStatus.NOT_FOUND)
        return None

    def _read_json_payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        try:
            raw_payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON payload: {exc}") from exc
        if isinstance(raw_payload, dict):
            normalized_payload: dict[str, Any] = {}
            typed_payload = cast(dict[object, object], raw_payload)
            payload_items = typed_payload.items()
            for key, value in payload_items:
                normalized_payload[str(key)] = value
            return normalized_payload
        return {}

    def log_message(self, format: str, *args: object) -> None:
        del format, args
        return None

    def _send_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def make_handler(workspace_root: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(TerraableRequestHandler):
        backend = LocalLabBackend(workspace_root)
        ui_path = workspace_root / "ui" / "index.html"

    return Handler


def main() -> None:
    """Start the local control-plane API server."""

    parser = argparse.ArgumentParser(description="Run the Terraable local control plane")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--workspace", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()

    workspace_root = Path(args.workspace).resolve()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(workspace_root))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":  # pragma: no cover
    main()
