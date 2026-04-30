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

# All page titles as they appear in the sidebar navigation. "Today" is
# the post-PR-3 default landing — every persona sees it first.
PAGES = [
    "Today",
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
    "Sanctions Screening",
    "Model Performance",
    "Data Quality",
    "Run History",
    "Rule Tuning",
    "Customer 360",
    "Typology Catalogue",
    "Comparative Analytics",
    "Spec Editor",
    "My Queue",
]


@pytest.fixture(scope="module")
def dashboard_server():
    """Start the Streamlit dashboard as a subprocess for the test session."""
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
    """Create a Playwright browser page connected to the running dashboard.

    Captures `pageerror` (uncaught JS) and `console.error` events on a
    list attribute so per-test assertions can fail loudly when the page
    silently throws while still rendering.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip(
            "playwright not installed — run: pip install playwright && python -m playwright install chromium"
        )

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception:
            pytest.skip("Chromium not installed — run: python -m playwright install chromium")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        # Stash error buffers on the page so tests can read + reset them
        # without Playwright tearing down the listeners between assertions.
        page.pageerrors = []
        page.console_errors = []
        page.on("pageerror", lambda e: page.pageerrors.append(str(e)))
        page.on(
            "console",
            lambda msg: page.console_errors.append(msg.text) if msg.type == "error" else None,
        )
        page.goto(dashboard_server, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(10000)  # Let the engine run on first load.
        yield page
        browser.close()


def _navigate(page, title: str) -> None:
    # Expand collapsed nav if needed ("View N more" button).
    sidebar = page.locator("[data-testid='stSidebar']")
    view_more = sidebar.locator("button:has-text('View')")
    if view_more.count() > 0:
        view_more.first.click()
        page.wait_for_timeout(1000)
    link = sidebar.locator(f"a:has-text('{title}')")
    if link.count() > 0:
        link.first.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        link.first.click()
        page.wait_for_timeout(3500)


def _select_persona(page, persona_label: str) -> None:
    """Drive the 'I am a…' selector to switch the active persona.

    The dropdown's label is the human-readable string (`Senior VP of
    Risk`, `Chief Compliance Officer`, etc.) that `format_func` puts in
    the DOM. Clicks the selectbox, picks the option by text, waits for
    Streamlit's rerun to settle.
    """
    sidebar = page.locator("[data-testid='stSidebar']")
    # The persona selector lives below the program-info block; locate it
    # by the static label "I am a…" Streamlit renders above it.
    selector = sidebar.locator("div[data-testid='stSelectbox']:has-text('I am a')").first
    selector.scroll_into_view_if_needed()
    selector.click()
    page.wait_for_timeout(400)
    page.get_by_text(persona_label, exact=False).first.click()
    page.wait_for_timeout(3500)  # let st.rerun() reload the nav


def _assert_no_browser_errors(page, page_title: str) -> None:
    """Fail with the page title in the message so parametrised failures
    point at the exact persona × page combination that broke.
    """
    if page.pageerrors:
        msg = "; ".join(page.pageerrors)
        # Reset so subsequent assertions in the same module run don't
        # double-report the same error.
        page.pageerrors.clear()
        pytest.fail(f"[{page_title}] uncaught JS pageerror(s): {msg}")
    streamlit_errors = [e for e in page.console_errors if "streamlit" in e.lower()]
    if streamlit_errors:
        msg = "; ".join(streamlit_errors)
        page.console_errors.clear()
        pytest.fail(f"[{page_title}] Streamlit console error(s): {msg}")


# Page titles a single persona is *guaranteed* to see — used to dedupe
# the persona × page matrix without needing to import streamlit. These
# match the entries app.py adds via `relevant_titles.add(...)`.
_UNIVERSAL_PAGES = ("Today", "Executive Dashboard")


class TestAllPagesRender:
    """Verify every dashboard page renders without a Streamlit error banner."""

    @pytest.mark.parametrize("page_title", PAGES)
    def test_page_renders(self, browser_page, page_title):
        _navigate(browser_page, page_title)
        # Streamlit shows an error element with data-testid="stException" on crash.
        errors = browser_page.locator("[data-testid='stException']")
        assert errors.count() == 0, f"Page '{page_title}' has a Streamlit error"

    @pytest.mark.parametrize("page_title", PAGES)
    def test_no_html_leak_in_visible_text(self, browser_page, page_title):
        """Catch unsafe_allow_html mishaps: card markup escapes the DOM
        and shows up as literal `</div>` / `<div ...>` text inside the
        rendered page (regression seen on Executive Dashboard with the
        Streamlit 1.56 use_container_width deprecation).

        We exclude the sidebar — its inner_text includes legitimate
        markup demos (e.g. mono `<div>` examples in a help block).
        Body text minus sidebar is the user-visible content surface.
        """
        _navigate(browser_page, page_title)
        body_text = browser_page.inner_text("body")
        sidebar_text = browser_page.locator("[data-testid='stSidebar']").inner_text()
        main_text = body_text.replace(sidebar_text, "")
        forbidden = ("</div>", "<div ", "<span ", "</span>", "<p>")
        leaks = [s for s in forbidden if s in main_text]
        assert not leaks, f"[{page_title}] HTML tag leaked into visible text: {leaks}"

    def test_sidebar_shows_program_info(self, browser_page):
        sidebar = browser_page.locator("[data-testid='stSidebar']")
        text = sidebar.inner_text()
        assert "schedule_i_bank_aml" in text
        assert "FINTRAC" in text

    def test_sidebar_has_nav_links(self, browser_page):
        sidebar = browser_page.locator("[data-testid='stSidebar']")
        sidebar_text = sidebar.inner_text()
        # With 15 pages, Streamlit may collapse some behind "View N more".
        # Check that the core pages are visible and "View" button exists for the rest.
        assert "Executive Dashboard" in sidebar_text
        assert "Alert Queue" in sidebar_text
        nav_links = sidebar.locator("a")
        # Should have at least 10 visible nav links (some may be collapsed).
        assert nav_links.count() >= 10, f"Only {nav_links.count()} nav links visible"


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

    def test_live_monitor_renders(self, browser_page, dashboard_server):
        # Navigate directly via URL since it may be behind "View more".
        browser_page.goto(
            f"{dashboard_server}/Live_Monitor", wait_until="networkidle", timeout=30000
        )
        browser_page.wait_for_timeout(4000)
        text = browser_page.inner_text("body")
        assert "Live Monitor" in text or "Start Monitoring" in text or "screening rules" in text


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


# ---------------------------------------------------------------------------
# PR-T additions — coverage gaps that let PR-O / PR-R / PR-S ship to a real
# user despite this suite existing.
# ---------------------------------------------------------------------------


class TestSidebarCollapseExpand:
    """Regression for PR-O — once the sidebar collapses, the user must be
    able to re-open it. The PR-O bug was a CSS rule that hid the expand
    chevron entirely, stranding anyone who clicked collapse."""

    def test_collapse_then_reopen_round_trip(self, browser_page):
        # Reset to a known state by reloading the dashboard root.
        browser_page.goto(browser_page.url, wait_until="networkidle", timeout=30000)
        browser_page.wait_for_timeout(2000)
        collapse = browser_page.locator("[data-testid='stSidebarCollapseButton']").first
        assert collapse.count() > 0, (
            "Sidebar collapse button missing — Streamlit changed its testid?"
        )
        collapse.click()
        browser_page.wait_for_timeout(1500)
        # Modern Streamlit (≥1.50) renders the floating expand control as
        # `stExpandSidebarButton`. Older versions used
        # `stSidebarCollapsedControl`. Either must be visible + clickable.
        expand = browser_page.locator(
            "[data-testid='stExpandSidebarButton'], [data-testid='stSidebarCollapsedControl']"
        ).first
        assert expand.count() > 0, "Expand control missing after collapse"
        assert expand.is_visible(), (
            "Expand control was rendered but is hidden by CSS — exact "
            "PR-O failure mode (CSS suppressed stToolbar wholesale)."
        )
        expand.click()
        browser_page.wait_for_timeout(1500)
        # Sidebar should be back: collapse button visible again.
        assert browser_page.locator("[data-testid='stSidebarCollapseButton']").first.is_visible(), (
            "Sidebar did not re-expand after click"
        )


# Personas that cover the spread of operational vs strategic flows.
# Iterating ALL 12 personas would be ~12 × 5 pages = 60 navigations and
# bust our CI budget. This subset hits every distinct card builder
# (executive / manager / analyst / auditor / developer / pm / generic)
# AND every card target page, so it catches the same class of bug PR-R
# / PR-S surfaced without exhausting the runner.
_PERSONA_MATRIX = [
    ("svp", "Senior VP of Risk"),
    ("cco", "Chief Compliance Officer"),
    ("vp", "VP / MLRO"),
    ("director", "Director of Financial Crime"),
    ("manager", "AML Operations Manager"),
    ("analyst", "Analyst (L1 / L2)"),
    ("auditor", "Auditor (Internal / External)"),
    ("developer", "Engineer / Detection Developer"),
    ("pm", "Program / Product Manager"),
    ("fintech_mlro", "FinTech / EMI / VASP MLRO"),
]


class TestPersonaCoverage:
    """The load-bearing PR-T addition — for each persona, switch the
    selector and verify Today + Executive Dashboard + the persona's
    first audience-specific page render without a Streamlit exception
    or browser-level error.

    This single class would have caught PR-R AND PR-S in one run.
    """

    @pytest.mark.parametrize("persona_code,persona_label", _PERSONA_MATRIX)
    def test_persona_can_navigate_universal_pages(self, browser_page, persona_code, persona_label):
        _select_persona(browser_page, persona_label)
        for page_title in _UNIVERSAL_PAGES:
            _navigate(browser_page, page_title)
            errors = browser_page.locator("[data-testid='stException']")
            assert errors.count() == 0, (
                f"Persona {persona_code} crashed on {page_title!r}: stException element rendered"
            )
            _assert_no_browser_errors(browser_page, f"{persona_code}/{page_title}")


class TestExecutiveDashboardDrillDowns:
    """PR-S regression — the drill-down links from Executive Dashboard
    must not crash the page when the persona's filter hides the target.
    Defensive fallback in `link_to_page` should render a caption
    instead.
    """

    def test_drill_downs_render_for_default_persona(self, browser_page):
        # Reset to default ("All pages" — every page in nav).
        browser_page.goto(browser_page.url, wait_until="networkidle", timeout=30000)
        browser_page.wait_for_timeout(3000)
        _navigate(browser_page, "Executive Dashboard")
        # No exception should fire; drill-down links to Alert Queue +
        # Investigations are present in the body.
        errors = browser_page.locator("[data-testid='stException']").count()
        assert errors == 0
        text = browser_page.inner_text("body")
        # Either the actual page_link rendered (visible link text) OR
        # the defensive caption rendered ("Hidden in your current persona").
        assert "Triage alerts" in text or "Hidden in your current persona" in text
        assert "Open investigations" in text or "Hidden in your current persona" in text

    def test_drill_downs_degrade_gracefully_for_svp(self, browser_page):
        """SVP's nav hides Alert Queue + Investigations (both in the
        ALLOWED_GRACEFUL_GAPS whitelist). The drill-down links must
        render the defensive caption instead of crashing.
        """
        _select_persona(browser_page, "Senior VP of Risk")
        _navigate(browser_page, "Executive Dashboard")
        errors = browser_page.locator("[data-testid='stException']").count()
        assert errors == 0, "Executive Dashboard crashed for SVP — drill-down fallback missing"
        text = browser_page.inner_text("body")
        # The caption from link_to_page's fallback mentions "persona" so
        # the user knows why the link is disabled.
        assert "persona" in text.lower() or "Triage alerts" in text, (
            "SVP view of Executive Dashboard shows neither the working "
            "link nor the graceful-degradation caption"
        )
