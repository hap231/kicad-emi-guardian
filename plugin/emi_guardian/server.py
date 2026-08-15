"""Token-protected localhost dashboard server.

The server binds to loopback by default, serves only bundled static assets, and
serializes every KiCad operation through :class:`GuardianController`.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import mimetypes
import secrets
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from .controller import GuardianController
from .errors import EmiGuardianError

LOGGER = logging.getLogger(__name__)
MAX_REQUEST_BYTES = 2 * 1024 * 1024


class DashboardServer:
    """Serve the EMI Guardian dashboard to the local browser."""

    def __init__(self, controller: GuardianController) -> None:
        """Create a server using the controller's UI settings."""

        self._controller = controller
        self._token = secrets.token_urlsafe(32)
        self._static_root = Path(__file__).resolve().parent / "web"
        self._last_activity = time.monotonic()
        self._shutdown_started = False
        handler = self._handler_class()
        bind_address = controller.config.ui.bind_address or "127.0.0.1"
        self._httpd = ThreadingHTTPServer((bind_address, 0), handler)
        self._httpd.daemon_threads = True
        self._watchdog = threading.Thread(target=self._watch_inactivity, daemon=True)

    @property
    def url(self) -> str:
        """Return the authenticated dashboard URL."""

        raw_host, port = self._httpd.server_address[:2]
        host = bytes(raw_host).decode("ascii") if isinstance(raw_host, (bytes, bytearray)) else raw_host
        browser_host = _browser_url_host(host)
        return f"http://{browser_host}:{port}/?token={self._token}"

    def run(self) -> None:
        """Open the browser when configured and run until shutdown."""

        self._watchdog.start()
        if self._controller.config.ui.open_browser:
            webbrowser.open(self.url, new=1, autoraise=True)
        try:
            self._httpd.serve_forever(poll_interval=0.25)
        finally:
            self._controller.close()
            self._httpd.server_close()

    def shutdown(self) -> None:
        """Request server shutdown exactly once."""

        if self._shutdown_started:
            return
        self._shutdown_started = True
        threading.Thread(target=self._httpd.shutdown, daemon=True).start()

    def _watch_inactivity(self) -> None:
        """Stop long-abandoned plugin processes."""

        timeout_minutes = self._controller.config.ui.inactivity_timeout_minutes
        if timeout_minutes <= 0:
            return
        timeout_seconds = timeout_minutes * 60
        while not self._shutdown_started:
            time.sleep(min(30, timeout_seconds))
            if time.monotonic() - self._last_activity >= timeout_seconds:
                LOGGER.info("Dashboard stopped after %d minutes of inactivity", timeout_minutes)
                self.shutdown()
                return

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        """Create a request handler bound to this server instance."""

        outer = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "EMIGuardian"

            def do_GET(self) -> None:  # noqa: N802
                """Handle static files and read-only API calls."""

                outer._last_activity = time.monotonic()
                parsed = urlparse(self.path)
                if parsed.path.startswith("/api/"):
                    if not self._authorized(parsed):
                        return
                    self._handle_api_get(parsed.path)
                    return
                self._serve_static(parsed.path)

            def do_POST(self) -> None:  # noqa: N802
                """Handle state-changing API calls."""

                outer._last_activity = time.monotonic()
                parsed = urlparse(self.path)
                if not self._authorized(parsed):
                    return
                self._handle_api_post(parsed.path)

            def log_message(self, format_string: str, *args: object) -> None:
                """Route HTTP logs through the plugin logger."""

                LOGGER.debug("Dashboard: " + format_string, *args)

            def _authorized(self, parsed: Any) -> bool:
                """Require the random session token for every API request."""

                query_token = parse_qs(parsed.query).get("token", [""])[0]
                header_token = self.headers.get("X-EMI-Guardian-Token", "")
                if secrets.compare_digest(query_token or header_token, outer._token):
                    return True
                self._json_error(HTTPStatus.FORBIDDEN, "Invalid or missing dashboard token.")
                return False

            def _handle_api_get(self, path: str) -> None:
                """Dispatch read-only API endpoints."""

                routes: dict[str, Callable[[], Any]] = {
                    "/api/status": lambda: outer._controller.status(),
                    "/api/ping": lambda: outer._controller.keep_alive(),
                    "/api/config": lambda: outer._controller.get_config(),
                    "/api/analysis": lambda: outer._controller.analysis_payload(),
                    "/api/fix-plan": lambda: outer._controller.current_fix_plan(),
                    "/api/silkscreen-plan": lambda: outer._controller.current_silkscreen_plan(),
                    "/api/edge-proposal": lambda: outer._controller.current_edge_proposal(),
                    "/api/stitching-plan": lambda: outer._controller.current_stitching_plan(),
                    "/api/placement-plan": lambda: outer._controller.current_component_placement_plan(),
                    "/api/manufacturing/catalog": lambda: outer._controller.manufacturing_catalog(),
                    "/api/manufacturing/report": lambda: outer._controller.current_manufacturing_report(),
                }
                callback = routes.get(path)
                if callback is None:
                    self._json_error(HTTPStatus.NOT_FOUND, "Unknown API endpoint.")
                    return
                self._invoke(callback)

            def _handle_api_post(self, path: str) -> None:
                """Dispatch analysis, planning, export, and mutation endpoints."""

                body = self._read_json()
                if body is None:
                    return
                routes: dict[str, Callable[[], Any]] = {
                    "/api/config": lambda: outer._controller.update_config(body),
                    "/api/analyze": lambda: outer._controller.analyze(bool(body.get("refresh", True))),
                    "/api/locate": lambda: outer._controller.locate_finding(str(body.get("finding_id", ""))),
                    "/api/manufacturing/profile": lambda: outer._controller.apply_manufacturing_profile(body),
                    "/api/manufacturing/check": lambda: outer._controller.check_manufacturing(
                        bool(body.get("refresh", True))
                    ),
                    "/api/manufacturing/export": lambda: outer._controller.export_manufacturing(
                        str(body.get("output_directory", ""))
                    ),
                    "/api/fixes/plan": lambda: outer._controller.plan_fixes(),
                    "/api/fixes/apply": lambda: outer._controller.apply_fixes(
                        bool(body.get("confirmed", False)),
                        _optional_string_array(body.get("action_ids"), "action_ids"),
                    ),
                    "/api/silkscreen/plan": lambda: outer._controller.plan_silkscreen(),
                    "/api/silkscreen/apply": lambda: outer._controller.apply_silkscreen(
                        bool(body.get("confirmed", False)),
                        _optional_string_array(body.get("placement_ids"), "placement_ids"),
                    ),
                    "/api/edge/plan": lambda: outer._controller.plan_edge(
                        str(body.get("operation", "optimize"))
                    ),
                    "/api/placement/plan": lambda: outer._controller.plan_component_placement(),
                    "/api/placement/apply": lambda: outer._controller.apply_component_placement(
                        bool(body.get("confirmed", False)),
                        _optional_string_array(body.get("placement_ids"), "placement_ids"),
                    ),
                    "/api/stitching/plan": lambda: outer._controller.plan_stitching(
                        _optional_bool(body.get("rebuild_perimeter")),
                        bool(body.get("use_edge_proposal", True)),
                    ),
                    "/api/stitching/apply": lambda: outer._controller.apply_stitching(
                        bool(body.get("confirmed", False)),
                        _optional_string_array(body.get("candidate_ids"), "candidate_ids"),
                        _optional_bool(body.get("rebuild_perimeter")),
                    ),
                    "/api/edge/apply": lambda: outer._controller.apply_edge(
                        bool(body.get("confirmed", False)),
                        str(body.get("board_name", "")),
                    ),
                    "/api/report/export": lambda: outer._controller.export_report(
                        str(body.get("output_directory", ""))
                    ),
                    "/api/solver/export": lambda: outer._controller.export_solver(
                        str(body.get("output_directory", ""))
                    ),
                    "/api/shutdown": lambda: _shutdown_response(outer),
                }
                callback = routes.get(path)
                if callback is None:
                    self._json_error(HTTPStatus.NOT_FOUND, "Unknown API endpoint.")
                    return
                self._invoke(callback)

            def _invoke(self, callback: Callable[[], Any]) -> None:
                """Invoke a controller operation and normalize errors."""

                try:
                    result = callback()
                except EmiGuardianError as exc:
                    self._json_error(HTTPStatus.BAD_REQUEST, str(exc), type(exc).__name__)
                except ValueError as exc:
                    self._json_error(HTTPStatus.BAD_REQUEST, str(exc), type(exc).__name__)
                except Exception as exc:  # pragma: no cover - runtime safety net
                    LOGGER.exception("Unhandled dashboard operation failure")
                    self._json_error(
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                        f"Unexpected error: {exc}",
                        type(exc).__name__,
                    )
                else:
                    self._json_response(HTTPStatus.OK, {"ok": True, "data": result})

            def _read_json(self) -> dict[str, Any] | None:
                """Read a bounded JSON object request body."""

                raw_length = self.headers.get("Content-Length", "0")
                try:
                    length = int(raw_length)
                except ValueError:
                    self._json_error(HTTPStatus.BAD_REQUEST, "Invalid Content-Length header.")
                    return None
                if length < 0 or length > MAX_REQUEST_BYTES:
                    self._json_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request body is too large.")
                    return None
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    value = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._json_error(HTTPStatus.BAD_REQUEST, "The request body must be valid UTF-8 JSON.")
                    return None
                if not isinstance(value, dict):
                    self._json_error(HTTPStatus.BAD_REQUEST, "The JSON root must be an object.")
                    return None
                return value

            def _serve_static(self, request_path: str) -> None:
                """Serve a bundled dashboard asset without directory traversal."""

                relative = "index.html" if request_path in {"", "/"} else unquote(request_path.lstrip("/"))
                candidate = (outer._static_root / relative).resolve()
                try:
                    candidate.relative_to(outer._static_root)
                except ValueError:
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return
                if not candidate.is_file():
                    candidate = outer._static_root / "index.html"
                content = candidate.read_bytes()
                content_type, _ = mimetypes.guess_type(candidate.name)
                self.send_response(HTTPStatus.OK)
                self.send_header(
                    "Content-Type",
                    (content_type or "application/octet-stream")
                    + ("; charset=utf-8" if candidate.suffix in {".html", ".css", ".js"} else ""),
                )
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
                )
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(content)

            def _json_response(self, status: HTTPStatus, payload: Any) -> None:
                """Write one JSON response."""

                content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(content)

            def _json_error(self, status: HTTPStatus, message: str, kind: str = "RequestError") -> None:
                """Write a stable JSON error envelope."""

                self._json_response(status, {"ok": False, "error": {"type": kind, "message": message}})

        return Handler


def _browser_url_host(host: str) -> str:
    """Return a browser-safe host, replacing unspecified addresses with loopback."""

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if address.is_unspecified:
        return "127.0.0.1"
    return f"[{address}]" if address.version == 6 else str(address)


def _optional_bool(value: Any) -> bool | None:
    """Validate an optional JSON boolean."""

    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError("Expected a boolean value.")
    return value


def _optional_string_array(value: Any, field_name: str) -> list[str] | None:
    """Validate an optional JSON string array."""

    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array.")
    return [str(item) for item in value]


def _shutdown_response(server: DashboardServer) -> dict[str, bool]:
    """Return a response before asynchronously stopping the HTTP server."""

    server.shutdown()
    return {"shutting_down": True}
