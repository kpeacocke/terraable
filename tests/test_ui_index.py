"""UI contract tests for the control-plane frontend."""

from pathlib import Path


def _read_ui_index() -> str:
    root = Path(__file__).resolve().parents[1]
    return (root / "ui" / "index.html").read_text(encoding="utf-8")


def test_demo_configuration_panel_is_present() -> None:
    html = _read_ui_index()

    assert "Demo Configuration" in html
    assert 'id="demo-profile-buttons"' in html
    assert 'id="demo-apply"' in html
    assert 'id="demo-start-terraform"' in html
    assert 'id="demo-start-ansible"' in html


def test_demo_api_routes_are_wired_in_frontend() -> None:
    html = _read_ui_index()

    assert 'api("/api/demo/status")' in html
    assert 'api("/api/demo/configure", { profile })' in html
    assert "api(`/api/demo/start-service/${service}`, {})" in html
    assert 'api("/api/demo/service-ready/terraform", {})' in html
    assert 'api("/api/demo/service-ready/ansible", {})' in html
