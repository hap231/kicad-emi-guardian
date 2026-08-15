"""Local dashboard HTTP security tests."""

from __future__ import annotations

import json
import threading
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

import pytest

from emi_guardian.config import AppConfig
from emi_guardian.server import DashboardServer, _browser_url_host


class FakeController:
    """Read-only controller surface used by the HTTP test."""

    def __init__(self) -> None:
        self.config = AppConfig()
        self.config.ui.open_browser = False
        self.closed = False
        self.profile_request = None

    def status(self):
        """Return a small status payload."""

        return {"board": {"name": "demo"}, "dry_run": True}

    def manufacturing_catalog(self):
        """Return a compact catalogue payload."""

        return {
            "profiles": [{"profile_id": "jlcpcb_2l_economy"}],
            "track_width_presets_mm": [0.1, 0.2, 5.0],
        }

    def current_manufacturing_report(self):
        """Return no cached report for the initial GET."""

        return None

    def apply_manufacturing_profile(self, body):
        """Record a profile request."""

        self.profile_request = dict(body)
        return {"config": {"manufacturing": dict(body)}}

    def check_manufacturing(self, refresh=True):
        """Return a deterministic DFM result."""

        return {"profile_id": "jlcpcb_2l_economy", "status": "pass", "refresh": refresh}

    def close(self) -> None:
        """Record closure."""

        self.closed = True


@pytest.mark.parametrize(
    ("host", "expected"),
    (
        ("127.0.0.1", "127.0.0.1"),
        ("0.0.0.0", "127.0.0.1"),
        ("::", "127.0.0.1"),
        ("::1", "[::1]"),
    ),
)
def test_browser_url_host_is_loopback_safe_and_ipv6_compatible(host: str, expected: str) -> None:
    """Render valid loopback URLs for IPv4, IPv6, and unspecified server addresses."""

    assert _browser_url_host(host) == expected


def test_static_assets_have_csp_and_api_requires_random_token() -> None:
    """Keep the browser UI local and protect every API operation."""

    controller = FakeController()
    server = DashboardServer(controller)  # type: ignore[arg-type]
    thread = threading.Thread(target=server._httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        parsed = urlparse(server.url)
        base = f"http://{parsed.hostname}:{parsed.port}"
        token = parse_qs(parsed.query)["token"][0]
        with urlopen(base + "/", timeout=3) as response:
            assert response.status == 200
            assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        with pytest.raises(HTTPError) as error:
            urlopen(base + "/api/status", timeout=3)
        assert error.value.code == 403
        request = Request(base + "/api/status", headers={"X-EMI-Guardian-Token": token})
        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["ok"] is True
        assert payload["data"]["board"]["name"] == "demo"
    finally:
        server._httpd.shutdown()
        server._httpd.server_close()
        thread.join(timeout=3)


def test_manufacturing_api_routes_are_authenticated_and_dispatch_json() -> None:
    """Expose the JLCPCB catalogue, profile update, and DFM check through the API."""

    controller = FakeController()
    server = DashboardServer(controller)  # type: ignore[arg-type]
    thread = threading.Thread(target=server._httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        parsed = urlparse(server.url)
        base = f"http://{parsed.hostname}:{parsed.port}"
        token = parse_qs(parsed.query)["token"][0]
        headers = {"X-EMI-Guardian-Token": token, "Content-Type": "application/json"}

        request = Request(base + "/api/manufacturing/catalog", headers=headers)
        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["data"]["profiles"][0]["profile_id"] == "jlcpcb_2l_economy"

        profile_body = {"profile_id": "jlcpcb_2l_economy", "board_thickness_mm": 1.6}
        request = Request(
            base + "/api/manufacturing/profile",
            data=json.dumps(profile_body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["data"]["config"]["manufacturing"]["board_thickness_mm"] == 1.6
        assert controller.profile_request == profile_body

        request = Request(
            base + "/api/manufacturing/check",
            data=b'{"refresh": false}',
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["data"]["status"] == "pass"
        assert payload["data"]["refresh"] is False
    finally:
        server._httpd.shutdown()
        server._httpd.server_close()
        thread.join(timeout=3)
