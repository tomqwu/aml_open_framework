"""End-to-end Playwright tests for the Streamlit dashboard.

Launches the dashboard, navigates every page, and verifies key elements
render without errors. Requires: pip install playwright && python -m
playwright install chromium.

Run with: pytest tests/test_e2e_dashboard.py -v
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

SPEC = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
APP = Path(__file__).resolve().parents[1] / "src" / "aml_framework" / "dashboard" / "app.py"
PORT = 8599  # Use a non-standard port to avoid conflicts.

# All 11 page titles as they appear in the sidebar navigation.
PAGES = [
    "Executive Dashboard",
    "Program Maturity",
    "Alert Queue",
    "Case Investigation",
    "Rule Performance",
    "Risk Assessment",
    "Audit & Evidence",
    "Framework Alignment",
    "Transformation Roadmap",
    "Network Explorer",
    "Live Monitor",
]


@pytest.fixture(scope="module")
def dashboard_server():
    """Start the Streamlit dashboard as a subprocess for the test session."""
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", str(APP),
            "--server.port", str(PORT),
            "--server.headless", "true",
            "--", str(SPEC), "42",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    # Wait for the server to be ready.
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


@pytest.fixture(scope="module")
def browser_page(dashboard_server):
    """Create a Playwright browser page connected to the running dashboard."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed — run: pip install playwright && python -m playwright install chromium")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception:
            pytest.skip("Chromium not installed — run: python -m playwright install chromium")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(dashboard_server, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(10000)  # Let the engine run on first load.
        yield page
        browser.close()


def _navigate(page, title: str) -> None:
    link = page.locator(f"a:has-text('{title}')")
    if link.count() > 0:
        link.first.click()
        page.wait_for_timeout(3000)


class TestAllPagesRender:
    """Verify every dashboard page renders without a Streamlit error banner."""

    @pytest.mark.parametrize("page_title", PAGES)
    def test_page_renders(self, browser_page, page_title):
        _navigate(browser_page, page_title)
        # Streamlit shows an error element with data-testid="stException" on crash.
        errors = browser_page.locator("[data-testid='stException']")
        assert errors.count() == 0, f"Page '{page_title}' has a Streamlit error"

    def test_sidebar_shows_program_info(self, browser_page):
        sidebar = browser_page.locator("[data-testid='stSidebar']")
        text = sidebar.inner_text()
        assert "schedule_i_bank_aml" in text
        assert "FINTRAC" in text

    def test_sidebar_has_all_nav_links(self, browser_page):
        for title in PAGES:
            link = browser_page.locator(f"a:has-text('{title}')")
            assert link.count() >= 1, f"Missing nav link: {title}"


class TestExecutiveDashboard:
    """Verify key content on the Executive Dashboard."""

    def test_kpi_cards_present(self, browser_page):
        _navigate(browser_page, "Executive Dashboard")
        text = browser_page.inner_text("body")
        assert "TOTAL ALERTS" in text
        assert "OPEN CASES" in text
        assert "ACTIVE RULES" in text

    def test_alerts_by_rule_chart(self, browser_page):
        _navigate(browser_page, "Executive Dashboard")
        # Plotly charts render as SVG or canvas inside a div.
        charts = browser_page.locator(".js-plotly-plot")
        assert charts.count() >= 1, "No Plotly chart found on Executive Dashboard"


class TestNetworkExplorer:
    """Verify the Network Explorer page renders a graph."""

    def test_graph_renders(self, browser_page):
        _navigate(browser_page, "Network Explorer")
        text = browser_page.inner_text("body")
        assert "NODES" in text
        assert "EDGES" in text
        assert "ALERTED NODES" in text

    def test_graph_has_nodes(self, browser_page):
        _navigate(browser_page, "Network Explorer")
        # The agraph component renders inside an iframe or a div with canvas.
        text = browser_page.inner_text("body")
        # KPI should show 25 nodes (one per customer).
        assert "25" in text


class TestLiveMonitor:
    """Verify the Live Monitor page has controls."""

    def test_start_button_present(self, browser_page):
        _navigate(browser_page, "Live Monitor")
        start_btn = browser_page.locator("button:has-text('Start Monitoring')")
        assert start_btn.count() >= 1

    def test_transaction_count_shown(self, browser_page):
        _navigate(browser_page, "Live Monitor")
        text = browser_page.inner_text("body")
        assert "transactions" in text
        assert "screening rules from spec" in text


class TestAuditEvidence:
    """Verify the Audit & Evidence page shows hash data."""

    def test_hash_table_present(self, browser_page):
        _navigate(browser_page, "Audit & Evidence")
        text = browser_page.inner_text("body")
        assert "Rule Output Hashes" in text
        # The table has a "SHA-256" column but it may be truncated in rendering.
        assert "structuring_cash_deposits" in text

    def test_ml_risk_scorer_in_hash_table(self, browser_page):
        _navigate(browser_page, "Audit & Evidence")
        text = browser_page.inner_text("body")
        assert "ml_risk_scorer" in text
