"""End-to-end mobile-viewport tests for the Streamlit dashboard.

Issue #66 mobile-responsive overlay verification. Re-uses the
existing `dashboard_server` fixture pattern from
`test_e2e_dashboard.py` but launches a separate Playwright browser
with a phone-sized viewport per test class.

Acceptance criteria from issue #66:
  - Dashboard renders without horizontal scroll on 375px viewport
  - Sidebar auto-collapses on first load when viewport < 768px
  - At least 3 e2e tests run at mobile viewport (375x667, 414x896,
    768x1024)
  - No regression in desktop e2e suite (separate file; this one
    runs additionally)
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

SPEC = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
APP = Path(__file__).resolve().parents[1] / "src" / "aml_framework" / "dashboard" / "app.py"
PORT = 8600  # Different from the desktop e2e port so they can run in parallel.


# Three viewports matching the issue #66 acceptance criteria.
MOBILE_VIEWPORTS = [
    pytest.param({"width": 375, "height": 667}, id="iphone_se"),
    pytest.param({"width": 414, "height": 896}, id="iphone_xr"),
    pytest.param({"width": 768, "height": 1024}, id="ipad_portrait"),
]


@pytest.fixture(scope="module")
def dashboard_server():
    """Start the Streamlit dashboard once for the module."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(APP),
            "--server.port",
            str(PORT),
            "--server.headless",
            "true",
            "--",
            str(SPEC),
            "42",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    for _ in range(30):
        time.sleep(1)
        try:
            import urllib.request

            urllib.request.urlopen(f"http://localhost:{PORT}").read()
            break
        except Exception:
            continue
    else:
        proc.kill()
        pytest.fail("Dashboard did not start within 30 seconds")

    yield f"http://localhost:{PORT}"
    proc.terminate()
    proc.wait(timeout=5)


def _open_mobile_page(playwright, dashboard_url: str, viewport: dict[str, int]):
    """Helper: launch chromium with the given viewport, navigate, settle."""
    try:
        browser = playwright.chromium.launch(headless=True)
    except Exception:
        pytest.skip("Chromium not installed — run: python -m playwright install chromium")
    page = browser.new_page(viewport=viewport)
    page.goto(dashboard_url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(10000)  # Engine warm-up on first load.
    return browser, page


# ---------------------------------------------------------------------------
# Acceptance: no horizontal scroll on phone viewports
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("viewport", MOBILE_VIEWPORTS)
def test_no_horizontal_scroll_on_landing(dashboard_server, viewport):
    """Per issue #66: at every mobile viewport, the page body must
    fit within the viewport width — no horizontal scroll bar."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed")

    with sync_playwright() as p:
        browser, page = _open_mobile_page(p, dashboard_server, viewport)
        try:
            scroll_width = page.evaluate("document.documentElement.scrollWidth")
            client_width = page.evaluate("document.documentElement.clientWidth")
            # Allow 2px slop for sub-pixel rendering / scrollbar gutters.
            assert scroll_width <= client_width + 2, (
                f"Horizontal scroll detected at {viewport}: "
                f"scrollWidth={scroll_width} > clientWidth={client_width}"
            )
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Acceptance: sidebar auto-collapses on phone viewports
# ---------------------------------------------------------------------------


def test_sidebar_collapsed_on_phone_viewport(dashboard_server):
    """Streamlit's `initial_sidebar_state="auto"` should leave the
    sidebar collapsed on viewports < 768px wide. We verify by
    measuring the rendered sidebar width — collapsed sidebars
    render at near-zero width with just a hamburger toggle."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed")

    with sync_playwright() as p:
        # 375px width = iPhone SE.
        browser, page = _open_mobile_page(p, dashboard_server, {"width": 375, "height": 667})
        try:
            sidebar = page.locator("[data-testid='stSidebar']")
            if sidebar.count() == 0:
                # Sidebar might not be in DOM at all when fully collapsed —
                # that's acceptable too.
                return
            box = sidebar.bounding_box()
            # Collapsed sidebar in Streamlit is either offscreen
            # (negative x) or has near-zero rendered width.
            collapsed = (
                box is None
                or box["width"] < 50  # collapsed handle only
                or box["x"] < 0  # offscreen
            )
            assert collapsed, f"Sidebar not collapsed at 375px viewport: bounding box={box}"
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Acceptance: mobile CSS media-query rule actually injected
# ---------------------------------------------------------------------------


def test_mobile_css_present_in_dom(dashboard_server):
    """Verify the responsive CSS overlay is in the page — defends
    against a refactor accidentally dropping the mobile media query
    (would silently return us to desktop-only behavior)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed")

    with sync_playwright() as p:
        browser, page = _open_mobile_page(p, dashboard_server, {"width": 375, "height": 667})
        try:
            # The mobile breakpoint string is a stable marker for the
            # overlay rule injected by `apply_theme()`.
            html = page.content()
            assert "@media (max-width: 768px)" in html, (
                "Mobile responsive CSS overlay missing from injected theme"
            )
            assert "@media (max-width: 480px)" in html, (
                "Phone-specific CSS overlay missing from injected theme"
            )
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Acceptance: page renders without a Streamlit error banner on mobile
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("viewport", MOBILE_VIEWPORTS)
def test_landing_page_renders_without_error(dashboard_server, viewport):
    """The Executive Dashboard page (default landing) renders without
    Streamlit's red error banner at every mobile viewport. Regression
    guard for any layout that crashes when columns stack."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed")

    with sync_playwright() as p:
        browser, page = _open_mobile_page(p, dashboard_server, viewport)
        try:
            error_alerts = page.locator("[data-testid='stAlert'][kind='error']")
            assert error_alerts.count() == 0, (
                f"Streamlit error banner present at viewport {viewport}: "
                f"{error_alerts.count()} alert(s)"
            )
        finally:
            browser.close()
