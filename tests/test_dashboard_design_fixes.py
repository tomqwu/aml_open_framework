"""Source-level tests for the PR-1 design fixes.

These guard against regressions of the four visible bugs called out in
the design review:

  1. Streamlit Cloud chrome (Deploy button + 3-dot toolbar) leaking through
  2. KPI metric values wrapping mid-number (e.g. "$843,3<br>88")
  3. Framework Alignment status column rendering as ☐ glyph boxes
  4. Aggregation-window rules emitting `count=NaN` rendered as "None"

Plus the persona-coverage fixes:

  5. Typology Catalogue is now reachable from at least one persona
  6. The `business` persona has been expanded beyond its 2-page stub

All checks are source-level (file-as-text assertions) so they run on the
minimal unit-test CI image without streamlit / pandas / pytest plugins.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = PROJECT_ROOT / "src" / "aml_framework" / "dashboard"
COMPONENTS_FILE = DASHBOARD / "components.py"
AUDIENCE_FILE = DASHBOARD / "audience.py"
ALERT_QUEUE_FILE = DASHBOARD / "pages" / "3_Alert_Queue.py"
FRAMEWORK_FILE = DASHBOARD / "pages" / "8_Framework_Alignment.py"


# ---------------------------------------------------------------------------
# Fix 1 — Streamlit Cloud chrome hidden
# ---------------------------------------------------------------------------


class TestStreamlitChromeHidden:
    def test_deploy_button_hidden(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # Modern Streamlit (≥1.50) uses [data-testid="stAppDeployButton"];
        # older versions used .stDeployButton. Both must be in the rule
        # so the button stays hidden across Streamlit upgrades.
        assert '[data-testid="stAppDeployButton"]' in body, (
            "stAppDeployButton (modern Streamlit) must be hidden — "
            "looks unprofessional in compliance UIs"
        )
        assert ".stDeployButton" in body, (
            "Legacy stDeployButton selector must remain for older Streamlit"
        )

    def test_toolbar_hidden(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # The 3-dot menu in Streamlit's top-right header uses stMainMenu in
        # current releases. We do NOT suppress the whole stToolbar wrapper
        # any more — that selector also wraps the sidebar collapse/expand
        # control and stranded users who collapsed the sidebar (issue #69).
        assert '[data-testid="stMainMenu"]' in body, (
            "Streamlit 3-dot menu (stMainMenu) must be hidden — but suppress "
            "it directly, not via the wider stToolbar wrapper"
        )
        assert '[data-testid="stToolbar"]' not in body, (
            "stToolbar must NOT be hidden wholesale — it contains the sidebar "
            "collapse/expand control. Use stMainMenu + stDeployButton instead."
        )

    def test_chrome_uses_display_none(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # The chrome-hide rule has to be `display: none` — `visibility: hidden`
        # leaves the layout slot reserved.
        chrome_block = re.search(
            r"\.stDeployButton[^{]*\{[^}]*display:\s*none",
            body,
            flags=re.DOTALL,
        )
        assert chrome_block, "Chrome rule must use display: none, not visibility: hidden"


# ---------------------------------------------------------------------------
# Fix 2 — KPI values nowrap + responsive size
# ---------------------------------------------------------------------------


class TestKPINowrap:
    def test_streamlit_metric_value_has_nowrap(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        block = re.search(
            r'\[data-testid="stMetricValue"\]\s*\{[^}]+\}',
            body,
            flags=re.DOTALL,
        )
        assert block, "stMetricValue style block missing"
        assert "white-space: nowrap" in block.group(0), (
            "KPI metric values must use white-space: nowrap to prevent mid-number wraps"
        )

    def test_html_metric_card_value_has_nowrap(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # The custom-HTML KPI card (kpi_card helper) uses .metric-card .value
        block = re.search(r"\.metric-card \.value\s*\{[^}]+\}", body, flags=re.DOTALL)
        assert block, ".metric-card .value rule missing"
        assert "white-space: nowrap" in block.group(0)

    def test_metric_value_uses_clamp_for_responsive_sizing(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # clamp() is what lets the font shrink rather than wrap when the
        # column is narrow but not narrow enough to trigger the mobile
        # breakpoint.
        assert "clamp(" in body, "KPI font-size should use clamp() for responsive sizing"


# ---------------------------------------------------------------------------
# Fix 3 — Framework Alignment status labels (no emoji-font dependency)
# ---------------------------------------------------------------------------


class TestFrameworkStatusLabels:
    def test_status_labels_dict_present(self):
        body = FRAMEWORK_FILE.read_text(encoding="utf-8")
        assert "STATUS_LABELS" in body, "STATUS_LABELS dict missing"

    def test_status_labels_use_text_not_emoji_circles(self):
        body = FRAMEWORK_FILE.read_text(encoding="utf-8")
        # The old version used U+1F7E2 (green circle), U+1F7E1 (yellow), U+1F534
        # (red). These render as ☐ on systems without an emoji font (most CI
        # runners + many corporate browsers). The fix replaces them with text.
        for bad in ("\U0001f7e2", "\U0001f7e1", "\U0001f534"):
            assert bad not in body, (
                f"Emoji circle {bad!r} still in Framework Alignment — depends on emoji font"
            )

    def test_status_labels_have_human_readable_text(self):
        body = FRAMEWORK_FILE.read_text(encoding="utf-8")
        assert "Mapped" in body
        assert "Partial" in body
        assert "Gap" in body

    def test_status_labels_carry_color_via_styler(self):
        body = FRAMEWORK_FILE.read_text(encoding="utf-8")
        # Color is preserved via a Styler (so the table is still scannable).
        assert "_status_style" in body or "_STATUS_TEXT_COLORS" in body, (
            "Status column should still be color-coded via Styler.map"
        )


# ---------------------------------------------------------------------------
# Fix 4 — Alert Queue NaN → em-dash
# ---------------------------------------------------------------------------


class TestAlertQueueNanRendering:
    def test_styler_uses_na_rep(self):
        body = ALERT_QUEUE_FILE.read_text(encoding="utf-8")
        assert "na_rep" in body, (
            "Alert Queue Styler must set na_rep to render NaN as something "
            "other than the literal string 'None'"
        )

    def test_em_dash_used_for_na(self):
        body = ALERT_QUEUE_FILE.read_text(encoding="utf-8")
        # em-dash (U+2014) is the standard typographic placeholder for
        # "no value" in financial reports.
        assert "—" in body, "em-dash (—) should be the NaN placeholder"


# ---------------------------------------------------------------------------
# Fix 5 — Typology Catalogue assigned to at least one persona
# ---------------------------------------------------------------------------


def _audience_pages() -> dict[str, list[str]]:
    """Parse AUDIENCE_PAGES via AST so we don't need to import streamlit."""
    import ast

    tree = ast.parse(AUDIENCE_FILE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "AUDIENCE_PAGES":
                    return ast.literal_eval(node.value)
    raise AssertionError("AUDIENCE_PAGES not found in audience.py")


class TestTypologyCatalogueOwned:
    def test_typology_catalogue_in_at_least_one_persona(self):
        pages = _audience_pages()
        owners = [p for p, titles in pages.items() if "Typology Catalogue" in titles]
        assert owners, (
            "Typology Catalogue is orphan — no persona has it in their primary "
            "workflow. Strategic/educational page with no owner."
        )

    def test_typology_catalogue_in_manager_workflow(self):
        # Per the PR-1 design review: managers calibrate detection
        # thresholds against the typology library — Typology Catalogue
        # belongs in their tuning loop.
        pages = _audience_pages()
        assert "Typology Catalogue" in pages["manager"]

    def test_typology_catalogue_in_pm_workflow(self):
        # PM uses typology research to drive roadmap priorities.
        pages = _audience_pages()
        assert "Typology Catalogue" in pages["pm"]


# ---------------------------------------------------------------------------
# Fix 6 — Business persona expanded beyond stub
# ---------------------------------------------------------------------------


class TestBusinessPersonaExpanded:
    def test_business_has_more_than_two_pages(self):
        pages = _audience_pages()
        # Pre-fix the business persona only had Executive Dashboard +
        # Risk Assessment which felt token. docs/personas.md describes
        # the business owner reading the control matrix and evidence
        # bundle — both must be reachable.
        assert len(pages["business"]) > 2, (
            f"business persona still stubbed at {len(pages['business'])} page(s)"
        )

    def test_business_includes_framework_alignment(self):
        pages = _audience_pages()
        assert "Framework Alignment" in pages["business"], (
            "Business owner reads the control matrix per docs/personas.md"
        )

    def test_business_includes_audit_evidence(self):
        pages = _audience_pages()
        assert "Audit & Evidence" in pages["business"], (
            "Business owner reviews the evidence bundle when audits are scheduled"
        )


# ---------------------------------------------------------------------------
# Cap invariant — no persona exceeds the 8-page cognitive load cap
# (defined in audience.MAX_PAGES_PER_PERSONA)
# ---------------------------------------------------------------------------


class TestPersonaCapInvariant:
    def test_no_persona_exceeds_page_cap(self):
        # PR-I bumped the cap 8 → 9 so the Metrics Taxonomy reference
        # page could join senior personas without forcing a Phase-D
        # commitment to be dropped. Stays in lock-step with
        # audience.MAX_PAGES_PER_PERSONA — that's the canonical knob.
        from aml_framework.dashboard.audience import MAX_PAGES_PER_PERSONA

        pages = _audience_pages()
        offenders = {p: len(t) for p, t in pages.items() if len(t) > MAX_PAGES_PER_PERSONA}
        assert not offenders, (
            f"Personas exceeding the {MAX_PAGES_PER_PERSONA}-page cognitive cap: "
            f"{offenders}. Either drop a page or raise MAX_PAGES_PER_PERSONA "
            "in audience.py."
        )
