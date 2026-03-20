"""Small stdlib HTTP server for the Terraable control plane."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .local_lab import LocalLabBackend


def make_handler(workspace_root: Path) -> type[BaseHTTPRequestHandler]:
    backend = LocalLabBackend(workspace_root)
    ui_path = workspace_root / "ui" / "index.html"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self._send_html(ui_path.read_text(encoding="utf-8"))
                return

            if parsed.path == "/api/state":
                self._send_json({"state": backend.get_state()})
                return

            if parsed.path == "/api/auth/status":
                query = parse_qs(parsed.query)
                target = query.get("target", ["local-lab"])[0]
                portal = query.get("portal", ["backstage"])[0]
                self._send_json(
                    {
                        "auth": backend.get_auth_status(
                            target=str(target),
                            portal=str(portal),
                        )
                    }
                )
                return

            if parsed.path == "/healthz":
                self._send_json({"status": "ok"})
                return

            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/auth/configure":
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                credentials = payload.get("credentials")
                if not isinstance(credentials, dict):
                    credentials = {}
                self._send_json({"auth": backend.configure_credentials(credentials)})
                return

            if not parsed.path.startswith("/api/actions/"):
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            action = parsed.path.rsplit("/", 1)[-1]

            try:
                if action == "create_environment":
                    response = backend.create_environment(
                        target=str(payload.get("target", "")),
                        portal=str(payload.get("portal", "")),
                        profile=str(payload.get("profile", "baseline")),
                        eda=str(payload.get("eda", "disabled")),
                    )
                elif action == "apply_baseline":
                    response = backend.apply_baseline()
                elif action == "run_compliance_scan":
                    response = backend.run_compliance_scan()
                elif action == "inject_ssh_drift":
                    response = backend.inject_ssh_drift()
                elif action == "inject_service_drift":
                    response = backend.inject_service_drift()
                elif action == "run_remediation":
                    response = backend.run_remediation()
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
            except RuntimeError as exc:
                response = {
                    "action": action,
                    "status": "failed",
                    "detail": str(exc),
                    "tone": "fail",
                    "state": backend.get_state(),
                }

            self._send_json(response)

        def log_message(self, format: str, *args: object) -> None:
            return None

        def _send_html(self, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_json(self, payload: dict[str, object]) -> None:
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

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
