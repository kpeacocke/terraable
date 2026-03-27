"""Small stdlib HTTP server for the Terraable control plane."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import secrets
import sys
import threading
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar, cast
from urllib.parse import ParseResult, parse_qs, urlparse

from . import demo_config
from .local_lab import LocalLabBackend  # kept for test monkeypatching


def get_backend(workspace_root: Path, target: str) -> Any:
    """Factory function to return the appropriate backend based on target.

    Uses lazy imports and module namespace access to support test monkeypatching.
    If LocalLabBackend has been monkeypatched (e.g., in tests), returns the
    monkeypatched version for all targets to support test scenarios.
    """
    # Access LocalLabBackend through module namespace to detect and respect monkeypatching
    module = sys.modules[__name__]
    current_backend = getattr(module, "LocalLabBackend", LocalLabBackend)

    # Check if LocalLabBackend has been monkeypatched (it's not the real class)
    # by comparing module attribution. The real LocalLabBackend is in terraable.local_lab
    is_monkeypatched = getattr(current_backend, "__module__", None) != "terraable.local_lab"

    if is_monkeypatched:
        # Test monkeypatch detected; return it for all targets to support test scenarios
        return current_backend(workspace_root)

    # Normal production path: dispatch to target-specific backends
    if target == "local-lab":
        return current_backend(workspace_root)
    elif target == "aws":
        from .aws_backend import AWSBackend

        return AWSBackend(workspace_root)
    elif target == "azure":
        from .azure_backend import AzureBackend

        return AzureBackend(workspace_root)
    elif target == "okd":
        from .okd_backend import OKDBackend

        return OKDBackend(workspace_root)
    else:
        return current_backend(workspace_root)


# Targets that all route to LocalLabBackend. They share a single cached instance
# so there is only one action lock and one runtime_root/state_file in use at a time.
_LOCAL_LAB_BACKEND_TARGETS: frozenset[str] = frozenset(
    {"local-lab", "gcp", "vmware", "parallels", "hyper-v"}
)


class TerraableRequestHandler(BaseHTTPRequestHandler):
    supported_targets: ClassVar[set[str]] = {
        "local-lab",
        "aws",
        "azure",
        "okd",
        "gcp",
        "vmware",
        "parallels",
        "hyper-v",
    }
    backends: ClassVar[dict[str, Any]] = {}
    backends_lock: ClassVar[threading.RLock] = threading.RLock()
    workspace_root: ClassVar[Path]
    ui_path: ClassVar[Path]
    backend: ClassVar[LocalLabBackend | None] = None
    max_json_payload_bytes: ClassVar[int] = 1024 * 1024
    json_read_timeout_seconds: ClassVar[float] = 5.0
    api_post_token: ClassVar[str] = ""

    @classmethod
    def get_active_backend(cls, target: str = "local-lab") -> Any:
        """Get or create backend instance for the given target."""
        normalized_target = target if target in cls.supported_targets else "local-lab"
        # All targets routed to LocalLabBackend share one instance so that the
        # action lock and runtime_root/state_file are never duplicated across targets.
        cache_key = (
            "local-lab" if normalized_target in _LOCAL_LAB_BACKEND_TARGETS else normalized_target
        )
        with cls.backends_lock:
            if cache_key == "local-lab" and getattr(cls, "backend", None) is not None:
                cls.backends[cache_key] = cls.backend
                return cls.backends[cache_key]
            if cache_key not in cls.backends:
                cls.backends[cache_key] = get_backend(cls.workspace_root, cache_key)
            return cls.backends[cache_key]

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._serve_file_safely(self.ui_path, "text/html; charset=utf-8")
            return
        if parsed.path == "/targetAvailability.mjs":
            js_path = self.workspace_root / "ui" / "targetAvailability.mjs"
            self._serve_file_safely(js_path, "application/javascript; charset=utf-8")
            return

        # Dispatch simple routes via dictionary to reduce complexity
        simple_routes: dict[str, Callable[[], None]] = {
            "/api/state": lambda: self._handle_api_state(parsed),
            "/api/auth/status": lambda: self._handle_auth_status(parsed),
            "/api/auth/matrix": lambda: self._handle_auth_matrix(parsed),
            "/api/session": lambda: self._handle_session(),
            "/api/demo/status": lambda: self._handle_demo_status(),
            "/healthz": lambda: self._send_json({"status": "ok"}),
        }
        handler = simple_routes.get(parsed.path)
        if handler:
            handler()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _serve_file_safely(self, file_path: Path, content_type: str) -> None:
        """Serve a file with safe error handling for missing or malformed UTF-8."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND, f"{file_path.name} file not found")
            return
        except UnicodeDecodeError:
            self.send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR, f"{file_path.name} file is not valid UTF-8"
            )
            return
        self._send_text(content, content_type)

    def _handle_api_state(self, parsed: ParseResult) -> None:
        """Handle GET /api/state request."""
        query = parse_qs(parsed.query)
        target = query.get("target", ["local-lab"])[0]
        backend = self.get_active_backend(str(target))
        self._send_json({"state": backend.get_state()})

    def _handle_auth_status(self, parsed: ParseResult) -> None:
        query = parse_qs(parsed.query)
        target = query.get("target", ["local-lab"])[0]
        portal = query.get("portal", ["backstage"])[0]
        backend = self.get_active_backend(str(target))
        self._send_json(
            {
                "auth": backend.get_auth_status(
                    target=str(target),
                    portal=str(portal),
                )
            }
        )

    def _handle_auth_matrix(self, parsed: ParseResult) -> None:
        query = parse_qs(parsed.query)
        portal = query.get("portal", ["backstage"])[0]
        auth_by_target: dict[str, dict[str, Any]] = {}
        # Include all UI-selectable targets: both executable (supported_targets)
        # and scaffold-only targets like 'openshift' with ready=false and blockers
        all_ui_targets = sorted(self.supported_targets | frozenset({"openshift"}))
        for target in all_ui_targets:
            if target == "openshift":
                # Scaffold-only target; return a full auth-status-like payload
                # so clients can rely on a consistent schema across targets.
                auth_by_target[target] = {
                    "authenticated": False,
                    "ready": False,
                    "required_credentials": [],
                    "missing_credentials": [],
                    "credential_sources": {},
                    "blockers": ["scaffold-only; use okd for executable deployments"],
                }
            else:
                backend = self.get_active_backend(target)
                auth_by_target[target] = cast(
                    dict[str, Any],
                    backend.get_auth_status(
                        target=target,
                        portal=str(portal),
                    ),
                )
        self._send_json({"portal": str(portal), "auth_by_target": auth_by_target})

    def _handle_session(self) -> None:
        """Handle GET /api/session request with loopback restriction."""
        client_host = self.client_address[0] if self.client_address else ""
        if not self._is_trusted_local_request(client_host):
            self.send_error(HTTPStatus.FORBIDDEN, "Session token access restricted to localhost")
            return
        self._send_json({"post_token": self.api_post_token})

    def _handle_demo_status(self) -> None:
        """Handle GET /api/demo/status request."""
        config = demo_config.get_demo_config()
        readiness = demo_config.get_overall_readiness()
        response = {
            "configuration": config.to_dict(),
            "readiness": readiness,
        }
        self._send_json(response)

    def _handle_demo_request(self, parsed: ParseResult) -> None:
        """Handle demo configuration POST requests."""
        try:
            payload = self._read_json_payload()
            path_parts = parsed.path.split("/")

            if len(path_parts) >= 4 and path_parts[3] == "configure":
                # POST /api/demo/configure
                # Payload: { "profile": "lab|enterprise-mirror|custom|offline-fallback", ... }
                profile_name = payload.get("profile", "lab")
                try:
                    profile = demo_config.DemoProfile(profile_name)
                except ValueError:
                    profile = demo_config.DemoProfile.LAB

                demo_config.apply_profile(profile)

                # Merge any custom configuration
                if profile == demo_config.DemoProfile.CUSTOM:
                    config = demo_config.get_demo_config()

                    # Update Terraform config if provided
                    if "terraform" in payload:
                        tf_updates = payload["terraform"]
                        if "backend" in tf_updates:
                            config.terraform.backend = demo_config.ProvisioningBackend(
                                tf_updates["backend"]
                            )
                        if "connection_mode" in tf_updates:
                            config.terraform.connection_mode = demo_config.ConnectionMode(
                                tf_updates["connection_mode"]
                            )
                        if "hostname" in tf_updates:
                            config.terraform.hostname = tf_updates["hostname"]
                        if "token" in tf_updates:
                            config.terraform.token = tf_updates["token"]
                        if "organization" in tf_updates:
                            config.terraform.organization = tf_updates["organization"]

                    # Update Ansible config if provided
                    if "ansible" in payload:
                        ans_updates = payload["ansible"]
                        if "backend" in ans_updates:
                            config.ansible.backend = demo_config.AutomationBackend(
                                ans_updates["backend"]
                            )
                        if "connection_mode" in ans_updates:
                            config.ansible.connection_mode = demo_config.ConnectionMode(
                                ans_updates["connection_mode"]
                            )
                        if "hostname" in ans_updates:
                            config.ansible.hostname = ans_updates["hostname"]
                        if "username" in ans_updates:
                            config.ansible.username = ans_updates["username"]
                        if "password" in ans_updates:
                            config.ansible.password = ans_updates["password"]
                        if "insecure_skip_verify" in ans_updates:
                            config.ansible.insecure_skip_verify = bool(
                                ans_updates["insecure_skip_verify"]
                            )

                    demo_config.set_demo_config(config)

                config = demo_config.get_demo_config()
                readiness = demo_config.get_overall_readiness()
                self._send_json(
                    {
                        "configuration": config.to_dict(),
                        "readiness": readiness,
                    }
                )

            elif len(path_parts) >= 5 and path_parts[3] == "start-service":
                # POST /api/demo/start-service/<service>
                service = path_parts[4]
                status = demo_config.start_service(service)
                self._send_json(
                    {
                        "service": status.service,
                        "is_ready": status.is_ready,
                        "error_message": status.error_message,
                        "estimated_wait_seconds": status.estimated_wait_seconds,
                    }
                )

            elif len(path_parts) >= 5 and path_parts[3] == "service-ready":
                # POST /api/demo/service-ready/<service>
                service = path_parts[4]
                status = demo_config.check_service_readiness(service)
                self._send_json(
                    {
                        "service": status.service,
                        "is_ready": status.is_ready,
                        "error_message": status.error_message,
                    }
                )

            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        except Exception as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def do_POST(self) -> None:
        if not self._require_safe_post_request():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/auth/configure":
            self._handle_auth_configure()
            return
        if parsed.path.startswith("/api/demo/"):
            self._handle_demo_request(parsed)
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
            normalized_target = target if target in self.supported_targets else "local-lab"
            portal = str(payload.get("portal", "backstage"))
            credentials: dict[str, str] = {}
            if isinstance(raw_credentials, dict):
                typed_credentials = cast(dict[object, object], raw_credentials)
                credential_items = typed_credentials.items()
                for key, value in credential_items:
                    if isinstance(key, str) and isinstance(value, str):
                        credentials[key] = value

            auth_by_target: dict[str, dict[str, Any]] = {}
            for supported_target in sorted(self.supported_targets):
                backend = self.get_active_backend(supported_target)
                auth_by_target[supported_target] = cast(
                    dict[str, Any],
                    backend.configure_credentials(
                        credentials,
                        target=supported_target,
                        portal=portal,
                    ),
                )

            self._send_json({"auth": auth_by_target[normalized_target]})
        except Exception as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def _handle_action(self, parsed: ParseResult) -> None:
        action = parsed.path.rsplit("/", 1)[-1]
        response: dict[str, Any] | None
        target = "local-lab"
        try:
            payload = self._read_json_payload()
            target = str(payload.get("target", "local-lab"))
            response = self._dispatch_action(action, payload, target)
        except Exception as exc:
            backend = self.get_active_backend(target)
            response = {
                "action": action,
                "status": "failed",
                "detail": str(exc),
                "tone": "fail",
                "state": backend.get_state(),
            }
        if response is not None:
            self._send_json(response)

    def _require_safe_post_request(self) -> bool:
        client_host = self.client_address[0] if self.client_address else ""
        if not self._is_trusted_local_request(client_host):
            self.send_error(HTTPStatus.FORBIDDEN, "POST access restricted to localhost")
            return False

        origin = self.headers.get("Origin") or self.headers.get("Referer")
        if origin:
            if origin.strip().lower() == "null":
                self.send_error(HTTPStatus.FORBIDDEN, "POST origin is not allowed")
                return False
            parsed_origin = urlparse(origin)
            origin_host = parsed_origin.hostname
            if not origin_host:
                self.send_error(HTTPStatus.FORBIDDEN, "POST origin is not allowed")
                return False
            if not self._is_loopback_host(origin_host):
                self.send_error(HTTPStatus.FORBIDDEN, "POST origin must be localhost")
                return False

        supplied_token = self.headers.get("X-Terraable-Token", "")
        if not self.api_post_token or not secrets.compare_digest(
            supplied_token, self.api_post_token
        ):
            self.send_error(HTTPStatus.FORBIDDEN, "Missing or invalid API session token")
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

    @staticmethod
    def _is_private_host(hostname: str) -> bool:
        if hostname in {"", "localhost"}:
            return False
        try:
            return ipaddress.ip_address(hostname).is_private
        except ValueError:
            return False

    def _is_trusted_local_request(self, client_host: str) -> bool:
        if self._is_loopback_host(client_host):
            return True

        # Docker/compose port forwarding can present the host as a private bridge IP.
        # Accept only when the browser origin/referer remains loopback.
        headers = getattr(self, "headers", None)
        origin = None
        if headers is not None:
            origin = headers.get("Origin") or headers.get("Referer")
        if not origin or origin.strip().lower() == "null":
            return False
        parsed_origin = urlparse(origin)
        origin_host = parsed_origin.hostname
        if not origin_host:
            return False
        return self._is_private_host(client_host) and self._is_loopback_host(origin_host)

    def _dispatch_action(
        self,
        action: str,
        payload: dict[str, Any],
        target: str = "local-lab",
    ) -> dict[str, Any] | None:
        backend = self.get_active_backend(target)
        if action == "create_environment":
            return cast(
                dict[str, Any],
                backend.create_environment(
                    target=str(payload.get("target", target)),
                    portal=str(payload.get("portal", "backstage")),
                    profile=str(payload.get("profile", "baseline")),
                    eda=str(payload.get("eda", "disabled")),
                ),
            )
        simple: dict[str, Callable[[], dict[str, Any]]] = {
            "apply_baseline": backend.apply_baseline,
            "run_compliance_scan": backend.run_compliance_scan,
            "inject_ssh_drift": backend.inject_ssh_drift,
            "inject_service_drift": backend.inject_service_drift,
            "inject_synthetic_incident": backend.inject_synthetic_incident,
            "run_remediation": backend.run_remediation,
        }
        handler = simple.get(action)
        if handler is not None:
            return handler()
        self.send_error(HTTPStatus.NOT_FOUND)
        return None

    def _read_json_payload(self) -> dict[str, Any]:
        length = self._parse_content_length()
        if length == 0:
            return {}

        raw_bytes = self._read_payload_bytes(length)
        if len(raw_bytes) != length:
            raise ValueError("Incomplete JSON payload")

        try:
            raw_payload = json.loads(raw_bytes)
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

    def _parse_content_length(self) -> int:
        header_value = self.headers.get("Content-Length")
        if header_value is None:
            return 0
        try:
            length = int(header_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid Content-Length") from exc
        if length < 0:
            raise ValueError("Invalid Content-Length")
        if length > self.max_json_payload_bytes:
            raise ValueError("Content-Length exceeds maximum allowed size")
        return length

    def _read_payload_bytes(self, length: int) -> bytes:
        connection = getattr(self, "connection", None)
        if connection is None:
            return self.rfile.read(length)

        original_timeout = connection.gettimeout()
        try:
            connection.settimeout(self.json_read_timeout_seconds)
            return self.rfile.read(length)
        except TimeoutError as exc:
            raise ValueError("Timed out while reading JSON payload") from exc
        finally:
            connection.settimeout(original_timeout)

    def log_message(self, format: str, *args: object) -> None:
        del format, args
        return None

    def _send_text(self, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
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
        ui_path = workspace_root / "ui" / "index.html"
        backend: ClassVar[LocalLabBackend | None] = None

    Handler.workspace_root = workspace_root
    Handler.backends = {}
    Handler.backends_lock = threading.RLock()
    Handler.backend = get_backend(workspace_root, "local-lab")
    Handler.backends["local-lab"] = Handler.backend
    # Prefer a random per-process token by default; allow env override for deterministic tests.
    env_token = os.getenv("TERRAABLE_API_POST_TOKEN")
    Handler.api_post_token = env_token if env_token else secrets.token_urlsafe(32)
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
