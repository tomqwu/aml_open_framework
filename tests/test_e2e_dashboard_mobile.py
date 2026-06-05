"""End-to-end mobile-viewport tests for the Streamlit dashboard.

Issue #66 mobile-responsive overlay verification, expanded by
**PR-M1 of the responsive-redesign epic** into a tiered 8-archetype
regression net.

The dashboard's mobile support is currently a *thin CSS overlay*
(`components.py` injects column-stacking + a 44px touch-target rule
behind `@media (max-width: 768px)`). PR-M1 lands the regression net
*first* so the real responsive work in PR-M2..M6 is measured against
an objective bar. Several archetype pages FAIL the per-page net under
today's overlay — that is the point. Those pages are marked
`@pytest.mark.xfail(strict=True)` so this PR is green now (they XFAIL)
while making the net an enforceable per-page gate: once PR-M2..M6
*fixes* a page it XPASSes, and under `strict=True` an unexpected pass
is a hard FAILURE — forcing that PR to delete the mark in the same
change. A later regression then fails loudly instead of silently
re-XFAILing. The xfail can never be relaxed away to keep CI green.

Tier structure (highest mobile-risk page archetypes):

  - 375x667 (iPhone SE) — FLOOR net, all 8 pages
    (`test_full_net_iphone_se`). The 5 PR-M1 structural assertions:
      * no page-level horizontal scroll (scrollWidth <= clientWidth+2)
      * zero `[data-testid="stException"]`
      * zero error `stAlert`
      * a page-specific content token is present (proves the page
        rendered real content, not a blank shell)
      * primary (first stMain) `button` / `[data-baseweb="select"]`
        bounding-box height >= 44 (Apple HIG / Material tap target)
    EMPIRICALLY all 8 pages already CLEAR this floor under the thin
    overlay (column-stacking + dataframe `overflow-x:auto` already
    contain wide content so the *document* never scrolls). Nothing
    here is xfail'd — it is a hard-pass regression net that fails if
    a later CSS PR *breaks* page-level layout.

  - 375x667 (iPhone SE) — STRICT net, 7 pages (Today excluded)
    (`test_responsive_quality_iphone_se`). Two DEEPER ergonomics
    assertions the thin overlay does NOT satisfy today:
      * no `stMain` descendant spills past the viewport edge
        (Streamlit *clips* inner overflow, so a 1010px YAML block /
        427px chart stack hides off-screen WITHOUT a document
        scrollbar — the floor tier cannot see this)
      * EVERY visible stMain control >= 44px (not just the first;
        probed controls render as small as 22px)
    Every case is `xfail(strict=True)` — the real "bar PR-M2..M6
    must hit". The strict mark makes a fixed page XPASS into a hard
    failure, so PR-M2..M6 must delete the mark when it fixes the page;
    it can never be relaxed away to keep CI green.

  - 414x896 + 768x1024  — SMOKE, 2 pages (Today + Executive
    Dashboard): no-horizontal-scroll + no-error only.

Plus the original issue #66 guards (kept verbatim in spirit):
  - sidebar auto-collapses on a phone viewport
  - the mobile CSS media query is actually injected into the DOM

Runtime budget: ONE browser context per viewport tier, navigated
page-to-page inside that context. The suite is Playwright-heavy
(~12 min) so added cold-starts are kept minimal: a single
module-scoped Streamlit server, one chromium launch per tier.

NAVIGATION (see `_nav_to`): URL-slug routing, NOT sidebar clicks.
The responsive plan asked for sidebar-link nav on the premise "URL
slugs bounce to main", but that premise was probed empirically on a
375x667 phone viewport against this app + Streamlit 1.57 and is
false — slugs reach their route cleanly. Sidebar-click nav is the
one that is actually broken on a phone here (the fixed `.dna-topbar`
overlay intercepts the collapsed-sidebar expand control), which is
also why the desktop e2e suite uses URL nav. The per-page content
token assertion is the bounce-to-main guard regardless of route.
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


# ---------------------------------------------------------------------------
# The 8 highest-mobile-risk page archetypes + a content token proving
# the page rendered real content (not a blank shell). Tokens are stable
# strings each page emits via `page_header()` (`st.markdown(f"# {t}")`
# → an <h1>) or, for Today, its bespoke landing hero.
#
# TWO TIERS — designed from an empirical 375x667 probe of the current
# thin overlay (PR-M1 build notes), not from assumption:
#
#   FLOOR tier (`test_full_net_iphone_se`) — the 5 PR-M1 structural
#   assertions exactly as specified: no page-level horizontal scroll,
#   no stException, no error stAlert, content token present, primary
#   (first stMain) control >= 44px. EMPIRICALLY all 8 archetypes
#   already CLEAR this floor under the thin overlay (column-stacking +
#   `overflow-x:auto` on dataframes + `max-width:100vw` already
#   contain the wide content so the *document* never scrolls
#   horizontally). So the floor is a hard PASS for every page — a true
#   regression net: a later CSS PR that *breaks* page-level layout
#   fails here. Nothing in the floor tier is xfail'd.
#
#   STRICT tier (`test_responsive_quality_iphone_se`) — two DEEPER
#   ergonomics assertions the thin overlay genuinely does NOT satisfy
#   today (probed: Executive Dashboard has a `.dvn-stack` overflowing
#   its container by ~427px and four 22px tap targets; Audit has a
#   ~1010px-wide YAML code block; every page's fixed `.dna-topbar`
#   wordmark overflows 375px by ~110px): (i) no `stMain` descendant
#   spills past the viewport edge, (ii) EVERY visible stMain
#   button/select >= 44px. These FAIL today on the 7 chart/grid pages
#   — that is the real "bar PR-M2..M6 must hit", so each is
#   `xfail(strict=True)`. Strict makes a fixed page's XPASS a hard
#   failure, so PR-M2..M6 must FIX the page CSS (responsive code block
#   / chart / stack widths + uniform 44px controls) and delete the
#   mark in the same PR — it can never be relaxed away. Today is a pure
#   hero/text page (zero stMain controls, no inner overflow) so it is
#   NOT in the strict tier — it would vacuously pass and add noise.
# ---------------------------------------------------------------------------
PageSpec = tuple[str, str]  # (nav title, content token)

FULL_NET_PAGES: list[PageSpec] = [
    ("Today", "An AML program you can"),
    ("Executive Dashboard", "Executive Dashboard"),
    ("Alert Queue", "Alert Queue"),
    ("Audit & Evidence", "Audit & Evidence"),
    ("Sanctions Screening", "Sanctions Screening"),
    ("Customer 360", "Customer 360"),
    ("Data Integration", "Data Integration"),
    ("Network Explorer", "Network Explorer"),
]

# Strict-tier pages — every archetype EXCEPT Today (the hero page has
# no in-content controls / inner overflow to grade). These are the
# explicit known-bad set PR-M2..M6 must fix.
STRICT_PAGES: list[PageSpec] = [p for p in FULL_NET_PAGES if p[0] != "Today"]

# Pages still under the thin overlay (strict checks genuinely FAIL → the
# remaining xfail backlog). The Direction-C mobile redesign (persistent
# bottom tab bar + full-bleed `@media (max-width:640px)` layout + uniform
# 44px controls) is exactly the "PR that flips a page to a hard pass" the
# strict-xfail contract demands: once a page passes both ergonomics
# assertions it MUST drop its xfail mark in the same change (strict=True
# turns an XPASS into a hard CI failure precisely to force that).
#
# As of the mobile-exec-polish PR this set is EMPTY: the last three
# archetypes (Executive Dashboard, Alert Queue, Audit & Evidence) now
# clear both the inner-overflow and uniform-44px-tap-target bars. The
# DEFECT-2 fix (code/YAML/hash blocks wrap so the laid-out box never
# exceeds the column) closed Audit & Evidence; the DEFECT-4 fix (44px
# floor extended to input/toolbar/inline-link variants) and the
# glide-data-grid containment (its internal `.dvn-stack` canvas reflows
# to the column width instead of laying out 793px off-screen) closed
# Alert Queue + Executive Dashboard. Every strict-tier page is now a
# hard pass; a future regression on any of them fails CI loudly.
STRICT_STILL_FAILING: frozenset[str] = frozenset()

# The 2-page smoke set for the larger viewport tiers.
SMOKE_PAGES: list[PageSpec] = [
    ("Today", "An AML program you can"),
    ("Executive Dashboard", "Executive Dashboard"),
]

XFAIL_REASON = "responsive PR-M2..M6 not yet landed"


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
    # `domcontentloaded` + shell-selector wait, NOT `networkidle`: the
    # section-explanation poller runs an `st.fragment(run_every=...)`
    # while LLM calls are in flight, so the page is never network-idle
    # until every AI box resolves. The page hero `<h1>` paints before
    # any section_explainer call and is the stable readiness anchor.
    page.goto(dashboard_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("[data-testid='stHeading'], h1", state="visible", timeout=60000)
    page.wait_for_timeout(10000)  # Engine warm-up on first load.
    return browser, page


def _nav_to(page, title: str) -> None:
    """Navigate to a page via its Streamlit multi-page URL slug.

    EMPIRICAL NOTE (PR-M1): the responsive plan flagged sidebar-link
    nav as the route to use because "URL slugs bounce to main". That
    was probed on a 375x667 phone viewport against this exact app +
    Streamlit 1.57 and is NOT true: every archetype slug reaches its
    route and renders its page-specific content token (no bounce).

    Sidebar-click nav, conversely, is genuinely broken on a phone
    viewport here: the fixed `.dna-topbar` brand bar (a `position`
    overlay injected by `app.py`) sits on top of Streamlit's
    collapsed-sidebar expand control, so Playwright's click is
    "intercepted by <div class='dna-topbar-brand'>" and times out.
    This is the same failure mode that drove the *desktop* e2e suite
    (`test_e2e_dashboard.py:_navigate`, documented v3–v5 history) to
    abandon sidebar clicks for direct URL navigation.

    So this net uses URL-slug nav (mirroring the proven desktop
    `_navigate`). The per-page *content-token* assertion is the real
    guard against a silent bounce-to-main: a blank shell or the main
    route would not contain the destination page's token, so the
    assertion would fail loudly rather than pass on the wrong page.

    Slug rule (Streamlit multi-page route): the page's display title
    with " & " → "_" and remaining spaces → "_".
    """
    slug = title.replace(" & ", "_").replace(" ", "_")
    page.goto(
        f"http://localhost:{PORT}/{slug}",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    page.wait_for_selector("[data-testid='stHeading'], h1", state="visible", timeout=60000)
    page.wait_for_timeout(3500)


# ---------------------------------------------------------------------------
# Tier 1 — FULL net, all 8 archetype pages @ 375x667 (iPhone SE).
# One browser context; navigate page-to-page inside it.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _playwright():
    """The SINGLE sync Playwright instance for this module.

    Playwright's sync API allows only one active `sync_playwright()`
    per thread: opening a second while one is live raises
    "It looks like you are using Playwright Sync API inside the
    asyncio loop". The module-scoped `iphone_se_page` fixture holds
    its instance open for the whole module, so the standalone tests
    that used to open their *own* `sync_playwright()` collided with it
    and failed deterministically on `main`. Every fixture/test here
    now draws its browser from this one instance via
    `_open_mobile_page` — many browsers/contexts from one Playwright
    is fully supported and is the canonical sync pattern.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed")

    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="module")
def iphone_se_page(_playwright, dashboard_server):
    """One chromium context at 375x667 reused across the full net so
    we pay a single cold-start, not one per page (runtime budget)."""
    browser, page = _open_mobile_page(_playwright, dashboard_server, {"width": 375, "height": 667})
    try:
        yield page
    finally:
        browser.close()


def _assert_full_net(page, title: str, token: str, viewport: dict[str, int]) -> None:
    """The five PR-M1 per-page assertions for the full net tier."""
    # (a) No horizontal scroll. 2px slop for sub-pixel / scrollbar gutter.
    scroll_width = page.evaluate("document.documentElement.scrollWidth")
    client_width = page.evaluate("document.documentElement.clientWidth")
    assert scroll_width <= client_width + 2, (
        f"[{title}] horizontal scroll at {viewport}: "
        f"scrollWidth={scroll_width} > clientWidth={client_width}"
    )

    # (b) No Streamlit exception element.
    exceptions = page.locator("[data-testid='stException']")
    assert exceptions.count() == 0, (
        f"[{title}] {exceptions.count()} stException element(s) at {viewport}"
    )

    # (c) No error-kind stAlert banner.
    error_alerts = page.locator("[data-testid='stAlert'][kind='error']")
    assert error_alerts.count() == 0, (
        f"[{title}] {error_alerts.count()} error stAlert(s) at {viewport}"
    )

    # (d) Page-specific content token present — proves a real render,
    #     not a blank shell / bounced-to-main route. Scope to `stMain`,
    #     NOT the whole body: the sidebar nav lists every page title, so
    #     a body-wide search would pass on nav chrome even on the wrong
    #     page / when main content failed to render.
    main_text = page.inner_text("[data-testid='stMain']")
    assert token in main_text, (
        f"[{title}] content token {token!r} missing — page did not render its content"
    )

    # (e) Primary interactive control meets the 44px tap-target floor.
    #     Scope to the MAIN content area (`stMain`), NOT the whole page:
    #     the first visible `button` page-wide is Streamlit's sidebar
    #     collapse chevron (a ~28px framework-chrome handle the mobile
    #     CSS intentionally keeps small) — measuring it would falsely
    #     fail every page including text-only ones. The 44px floor is a
    #     statement about *page action controls*, so we measure the
    #     first visible button / selectbox inside `stMain`.
    #
    #     A page with NO in-content control (Today is a pure hero/text
    #     landing — zero stMain buttons or selects) has no primary
    #     control to mis-size, so the floor is vacuously met. Every
    #     page that DOES render an action control gets measured.
    main_control = page.locator(
        "[data-testid='stMain'] button:visible, "
        "[data-testid='stMain'] [data-baseweb='select']:visible"
    )
    if main_control.count() > 0:
        box = main_control.first.bounding_box()
        assert box is not None, f"[{title}] primary control has no measurable bounding box"
        assert box["height"] >= 44, (
            f"[{title}] primary control height {box['height']}px < 44px "
            f"tap-target floor at {viewport}"
        )


@pytest.mark.parametrize(
    "title,token",
    [
        pytest.param(t, tok, id=t.replace(" ", "_").replace("&", "and").replace("__", "_"))
        for (t, tok) in FULL_NET_PAGES
    ],
)
def test_full_net_iphone_se(iphone_se_page, title, token):
    """FLOOR tier: every archetype page must clear all five PR-M1
    structural mobile assertions at 375x667. Empirically every page
    (Today included) passes today — this is the regression net that
    fails loudly if a later CSS PR *breaks* page-level layout."""
    _nav_to(iphone_se_page, title)
    _assert_full_net(iphone_se_page, title, token, {"width": 375, "height": 667})


def _assert_responsive_quality(page, title: str, viewport: dict[str, int]) -> None:
    """The two DEEPER ergonomics assertions PR-M2..M6 must satisfy.

    These are stricter than the floor tier and FAIL on the thin
    overlay today (that is the point — they are xfail scaffolding).
    """
    # (i) No `stMain` descendant spills past the viewport's right
    #     edge. The floor tier's `documentElement.scrollWidth` check
    #     only catches *page-level* scroll; Streamlit clips inner
    #     overflow so a 1010px-wide YAML block or a 427px chart stack
    #     hides off-screen content WITHOUT moving the document scroll
    #     bar. This DOM walk is the assertion that actually grades
    #     "does every element fit the phone".
    worst = page.evaluate(
        """() => {
            const vw = document.documentElement.clientWidth;
            let worst = 0, tag = '';
            const root = document.querySelector('[data-testid=\"stMain\"]');
            if (!root) return [0, ''];
            for (const el of root.querySelectorAll('*')) {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.right > vw + 2 && (r.right - vw) > worst) {
                    worst = r.right - vw;
                    tag = el.tagName + '.' + (el.className || '').toString().slice(0, 50);
                }
            }
            return [Math.round(worst), tag];
        }"""
    )
    assert worst[0] == 0, (
        f"[{title}] stMain content overflows the {viewport['width']}px viewport by "
        f"{worst[0]}px (worst element: {worst[1]}) — clipped off-screen, not responsive"
    )

    # (ii) EVERY visible stMain button / selectbox meets the 44px
    #      tap-target floor (not just the first, as the floor tier
    #      checks). The thin overlay's `min-height:44px` rule does not
    #      reach all control variants — probed Executive Dashboard
    #      controls render as small as 22px.
    controls = page.locator(
        "[data-testid='stMain'] button:visible, "
        "[data-testid='stMain'] [data-baseweb='select']:visible"
    )
    n = controls.count()
    undersized: list[float] = []
    for i in range(n):
        box = controls.nth(i).bounding_box()
        if box is not None and box["height"] < 44:
            undersized.append(round(box["height"], 1))
    assert not undersized, (
        f"[{title}] {len(undersized)}/{n} stMain controls below the 44px "
        f"tap-target floor at {viewport}: heights={undersized}"
    )


@pytest.mark.parametrize(
    "title,token",
    [
        pytest.param(
            t,
            tok,
            id=t.replace(" ", "_").replace("&", "and").replace("__", "_"),
            marks=(
                (pytest.mark.xfail(reason=XFAIL_REASON, strict=True),)
                if t in STRICT_STILL_FAILING
                else ()
            ),
        )
        for (t, tok) in STRICT_PAGES
    ],
)
def test_responsive_quality_iphone_se(iphone_se_page, title, token):
    """STRICT tier: the 7 chart/grid archetypes must have zero
    off-screen inner overflow and uniformly >=44px tap targets at
    375x667. Pages still on the thin overlay (`STRICT_STILL_FAILING`)
    stay `xfail(strict=True)`; pages the Direction-C mobile redesign
    fixed (Sanctions Screening, Customer 360, Data Integration, Network
    Explorer) are promoted to a HARD pass — the strict-xfail contract
    requires dropping the mark the moment a page passes, so an
    accidental future regression fails loudly instead of silently
    re-XFAILing. PR-M2..M6 flips each remaining page to a hard pass by
    FIXING the page CSS (responsive code/chart/stack widths + uniform
    44px controls), NOT by relaxing this assertion. Today is excluded —
    it is a pure hero page with no controls / inner overflow to grade."""
    _nav_to(iphone_se_page, title)
    # Re-assert the token (scoped to stMain, not body — the sidebar nav
    # lists every page title) so a silent bounce-to-main can't make the
    # strict checks vacuously "pass" on the wrong page.
    assert token in iphone_se_page.inner_text("[data-testid='stMain']"), (
        f"[{title}] content token {token!r} missing — wrong page rendered"
    )
    _assert_responsive_quality(iphone_se_page, title, {"width": 375, "height": 667})


# ---------------------------------------------------------------------------
# Tier 2 — SMOKE, 2 pages @ 414x896 + 768x1024.
# no-horizontal-scroll + no-error only. One context per viewport.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "viewport",
    [
        pytest.param({"width": 414, "height": 896}, id="iphone_xr"),
        pytest.param({"width": 768, "height": 1024}, id="ipad_portrait"),
    ],
)
@pytest.mark.parametrize(
    "title,token",
    [pytest.param(t, tok, id=t.replace(" ", "_")) for (t, tok) in SMOKE_PAGES],
)
def test_smoke_larger_viewports(_playwright, dashboard_server, viewport, title, token):
    """Tier 2: Today + Executive Dashboard must have no horizontal
    scroll and no error banner at the two larger viewport tiers. These
    two pages pass today (Executive Dashboard's heavy chart row clears
    at >=414px where the column stack has room), so they are NOT
    xfail'd here."""
    browser, page = _open_mobile_page(_playwright, dashboard_server, viewport)
    try:
        _nav_to(page, title)
        # Same guard as the strict tier (scoped to stMain, not body
        # — the sidebar nav lists every page title): a silent
        # bounce-to-main must not pass the smoke checks vacuously.
        assert token in page.inner_text("[data-testid='stMain']"), (
            f"[{title}] content token {token!r} missing at {viewport} — wrong page rendered"
        )
        scroll_width = page.evaluate("document.documentElement.scrollWidth")
        client_width = page.evaluate("document.documentElement.clientWidth")
        assert scroll_width <= client_width + 2, (
            f"[{title}] horizontal scroll at {viewport}: "
            f"scrollWidth={scroll_width} > clientWidth={client_width}"
        )
        error_alerts = page.locator("[data-testid='stAlert'][kind='error']")
        assert error_alerts.count() == 0, (
            f"[{title}] {error_alerts.count()} error stAlert(s) at {viewport}"
        )
        exceptions = page.locator("[data-testid='stException']")
        assert exceptions.count() == 0, (
            f"[{title}] {exceptions.count()} stException element(s) at {viewport}"
        )
    finally:
        browser.close()


# ---------------------------------------------------------------------------
# Acceptance: no horizontal scroll on phone viewports (landing).
# (Original issue #66 guard — kept.)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("viewport", MOBILE_VIEWPORTS)
def test_no_horizontal_scroll_on_landing(_playwright, dashboard_server, viewport):
    """Per issue #66: at every mobile viewport, the landing page body
    must fit within the viewport width — no horizontal scroll bar."""
    browser, page = _open_mobile_page(_playwright, dashboard_server, viewport)
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


def test_sidebar_collapsed_on_phone_viewport(_playwright, dashboard_server):
    """Streamlit's `initial_sidebar_state="auto"` should leave the
    sidebar collapsed on viewports < 768px wide. We verify by
    measuring the rendered sidebar width — collapsed sidebars
    render at near-zero width with just a hamburger toggle."""
    # 375px width = iPhone SE.
    browser, page = _open_mobile_page(_playwright, dashboard_server, {"width": 375, "height": 667})
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


def test_mobile_css_present_in_dom(_playwright, dashboard_server):
    """Verify the responsive CSS overlay is in the page — defends
    against a refactor accidentally dropping the mobile media query
    (would silently return us to desktop-only behavior)."""
    browser, page = _open_mobile_page(_playwright, dashboard_server, {"width": 375, "height": 667})
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
        # The 640px breakpoint carries the mobile-nav carve-out that makes
        # the collapsed-sidebar expand control tappable (the brand bar no
        # longer intercepts the tap). Assert both the breakpoint AND the
        # `.dna-topbar-brand` pointer-events carve-out so a future refactor
        # can't silently drop the headline phone-nav fix.
        assert "640px" in html, "mobile nav carve-out media query missing"
        assert "dna-topbar-brand" in html, "topbar pointer-events carve-out missing"
    finally:
        browser.close()


# ---------------------------------------------------------------------------
# Acceptance: a real user can REACH another page on a phone by TAPPING.
#
# This is the headline mobile-nav fix. Every other test in this file
# navigates by typing URL slugs (`_nav_to`) because the fixed
# `.dna-topbar` brand overlay used to INTERCEPT the tap on Streamlit's
# collapsed-sidebar expand control — a real user with a thumb (no URL
# bar) was stranded on the landing page. This test does ONLY what a
# real user can do: tap the native expand control, then tap a nav link.
# No URL-slug navigation. It must be tappable (no overlay interception).
# ---------------------------------------------------------------------------


def test_mobile_menu_tap_navigates(_playwright, dashboard_server):
    """A phone user lands on the default page, TAPS the real sidebar
    expand control (not a typed URL), then TAPS a nav link to another
    page — and the route actually changes. Guards against the
    `.dna-topbar` overlay re-intercepting the collapsed-sidebar control."""
    browser, page = _open_mobile_page(_playwright, dashboard_server, {"width": 375, "height": 667})
    try:
        before = page.url
        ctrl = page.locator(
            "[data-testid='stSidebarCollapsedControl'], [data-testid='stExpandSidebarButton']"
        ).first
        ctrl.click(timeout=8000)  # must be tappable — no overlay interception
        page.get_by_role("link", name="Today").first.click(timeout=8000)
        page.wait_for_function("u => location.href !== u", arg=before, timeout=8000)
        assert page.url != before, f"phone tap-nav did not change route: stayed on {before}"
    finally:
        browser.close()


def test_mobile_menu_control_visible_on_non_start_page(_playwright, dashboard_server):
    """DISCOVERABILITY: the menu control must be an OBVIOUS, on-screen,
    tappable button on a NON-Start page (the original "where is the
    menu?" complaint was that on every page other than Start the only
    affordance was a faint, top-clipped chevron).

    The restyle in `components.py` turns the live control
    (`stExpandSidebarButton`) into a fixed 44x44 burnt-orange floating
    hamburger just below the topbar. This test lands directly on the
    Today page (NOT Start), then asserts:
      * the control is `is_visible()` (rendered, not display:none);
      * its bounding box is fully inside the 375x667 viewport
        (0 <= x, x+width <= 375, y >= 0) — i.e. NOT half-clipped above
        the top edge the way the default static chevron was;
      * it meets the 44px tap-target floor;
      * a real tap on it followed by a nav-link tap changes the route
        (proves it opens the real sidebar with the full nav).

    Pure user-tap navigation (no URL slugs) — guards both the
    discoverability restyle AND the underlying tappability fix.
    """
    browser, page = _open_mobile_page(_playwright, dashboard_server, {"width": 375, "height": 667})
    try:
        # Land on a NON-Start page via URL, then nav ONLY by tapping.
        page.goto(
            f"http://localhost:{PORT}/Today",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        page.wait_for_selector("[data-testid='stHeading'], h1", state="visible", timeout=60000)
        page.wait_for_timeout(5000)

        before = page.url
        ctrl = page.locator("[data-testid='stExpandSidebarButton']").first
        assert ctrl.is_visible(), "menu control not visible on Today (non-Start) page"

        box = ctrl.bounding_box()
        assert box is not None, "menu control has no measurable bounding box"
        # Fully inside the 375x667 viewport — not the top-clipped (y<0)
        # static chevron the user couldn't find.
        assert box["x"] >= 0, f"menu control off-screen left: x={box['x']}"
        assert box["x"] + box["width"] <= 375, (
            f"menu control overflows right edge: x+w={box['x'] + box['width']}"
        )
        assert box["y"] >= 0, f"menu control clipped above top edge: y={box['y']}"
        # Thumb target floor.
        assert box["height"] >= 44 and box["width"] >= 44, (
            f"menu control below 44px tap-target floor: {box['width']}x{box['height']}"
        )

        # A real tap opens the sidebar; a nav-link tap changes route.
        ctrl.click(timeout=8000)
        page.get_by_role("link", name="Alert Queue").first.click(timeout=8000)
        page.wait_for_function("u => location.href !== u", arg=before, timeout=8000)
        assert page.url != before, (
            f"tapping the visible hamburger did not navigate: stayed on {before}"
        )
    finally:
        browser.close()


# ---------------------------------------------------------------------------
# Acceptance: the Direction-C persistent BOTTOM TAB BAR is the primary
# mobile nav — VISIBLE and in-viewport, and a tab tap actually navigates.
#
# This is the headline of the mobile-redesign ("Direction C"): the real
# answer to "where's the menu?" is a persistent bottom tab bar, always
# on screen, so the primary surfaces (Today / Alerts / Cases / Audit) are
# one thumb-tap away. The bar is injected in `app.py` and revealed only
# inside the ≤640px phone CSS query. This test asserts FINDABILITY (it is
# visible AND pinned to the bottom edge within the viewport width), not
# just presence, then taps "Alerts" and asserts the route changes to the
# Alert Queue slug.
# ---------------------------------------------------------------------------


def test_bottom_tabbar_visible_and_navigates(_playwright, dashboard_server):
    """The bottom tab bar is VISIBLE and in-viewport on the Today page
    (375x667), and tapping the "Alerts" tab navigates to /Alert_Queue."""
    browser, page = _open_mobile_page(_playwright, dashboard_server, {"width": 375, "height": 667})
    try:
        # Land on the Today page (a non-Start surface) and settle.
        page.goto(
            f"http://localhost:{PORT}/Today",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        page.wait_for_selector("[data-testid='stHeading'], h1", state="visible", timeout=60000)
        page.wait_for_timeout(5000)

        tabbar = page.locator(".dna-tabbar").first
        # FINDABILITY, not just presence: the bar must be rendered
        # (not display:none from the desktop fallback) AND on-screen.
        assert tabbar.is_visible(), "bottom tab bar not visible on the Today page at 375x667"

        box = tabbar.bounding_box()
        assert box is not None, "bottom tab bar has no measurable bounding box"
        # Pinned to the bottom edge: its bottom sits at the viewport
        # bottom (667), within a small slop for the fixed-position
        # blur bar. Spans the full width (left at 0, within 375).
        bottom = box["y"] + box["height"]
        assert abs(bottom - 667) <= 2, (
            f"bottom tab bar not pinned to the viewport bottom: bottom={bottom} (want ~667)"
        )
        assert box["x"] <= 1, f"bottom tab bar not flush-left: x={box['x']}"
        assert box["x"] + box["width"] <= 376, (
            f"bottom tab bar overflows the viewport width: right={box['x'] + box['width']}"
        )

        # All five tabs present, and exactly one marked active (.on).
        tabs = page.locator(".dna-tab")
        assert tabs.count() == 5, f"expected 5 tabs, found {tabs.count()}"
        assert page.locator(".dna-tab.on").count() == 1, "expected exactly one active tab"

        # Tap the "Alerts" tab — a real user thumb-tap — and assert the
        # route changed to the Alert Queue slug (proves the anchor's
        # target="_top" full-reload nav works, not just that it's there).
        before = page.url
        page.locator(".dna-tab", has_text="Alerts").first.click(timeout=8000)
        page.wait_for_function("u => location.href !== u", arg=before, timeout=8000)
        assert "/Alert_Queue" in page.url, (
            f"tapping the Alerts tab did not reach the Alert Queue slug: {page.url}"
        )
    finally:
        browser.close()


# ---------------------------------------------------------------------------
# Acceptance: page renders without a Streamlit error banner on mobile
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("viewport", MOBILE_VIEWPORTS)
def test_landing_page_renders_without_error(_playwright, dashboard_server, viewport):
    """The default landing page renders without Streamlit's red error
    banner at every mobile viewport. Regression guard for any layout
    that crashes when columns stack."""
    browser, page = _open_mobile_page(_playwright, dashboard_server, viewport)
    try:
        error_alerts = page.locator("[data-testid='stAlert'][kind='error']")
        assert error_alerts.count() == 0, (
            f"Streamlit error banner present at viewport {viewport}: "
            f"{error_alerts.count()} alert(s)"
        )
    finally:
        browser.close()
