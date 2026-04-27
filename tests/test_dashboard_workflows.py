"""Workflow + audience-coverage audit for the dashboard.

Verifies that:
  - Every persona in `AUDIENCE_PAGES` maps to pages that actually exist
    in `dashboard/pages/`. A typo in the audience map silently hides
    a page from the user — this catches it.
  - Executive-tier audiences (SVP/CTO/CCO/VP/Director) have an
    `Executive Dashboard` entry — the meeting-room landing.
  - The executive font scale CSS is wired into `apply_theme()`.
  - The audience selectbox in app.py exposes every persona defined
    in `AUDIENCE_PAGES` (selector and map can drift apart silently).
  - Pages that the workflow audit flagged as non-interactive
    (Rule Performance, Risk Assessment, Sanctions Screening,
    Comparative Analytics) now carry filter widgets.
"""

from __future__ import annotations

import re
from pathlib import Path

from aml_framework.dashboard.audience import AUDIENCE_PAGES

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages"
APP_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "app.py"
COMPONENTS_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "components.py"


def _page_titles_on_disk() -> set[str]:
    """Title text mined from each page file's `page_header(...)` call.

    The title argument is the canonical name shown in nav and used as
    the key in AUDIENCE_PAGES — any drift between the two breaks
    audience filtering. Handles three patterns:
      page_header("Title", ...)         positional string
      page_header(title="Title", ...)   keyword string
      page_header(PAGE_TITLE, ...)      constant reference; we then
                                        find PAGE_TITLE = "..." in the file
    """
    titles: set[str] = set()
    for f in sorted(PAGES_DIR.glob("*.py")):
        if f.name == "__init__.py":
            continue
        body = f.read_text(encoding="utf-8")
        # Pattern 1: positional string literal.
        m = re.search(r'page_header\(\s*["\']([^"\']+)["\']', body)
        if m:
            titles.add(m.group(1))
            continue
        # Pattern 2: title= keyword.
        m = re.search(r'page_header\(\s*title=\s*["\']([^"\']+)["\']', body)
        if m:
            titles.add(m.group(1))
            continue
        # Pattern 3: positional identifier — resolve via PAGE_TITLE = "..." in the file.
        m = re.search(r"page_header\(\s*([A-Z_][A-Z0-9_]*)\s*,", body)
        if m:
            const_name = m.group(1)
            const_match = re.search(rf'^{const_name}\s*=\s*["\']([^"\']+)["\']', body, re.MULTILINE)
            if const_match:
                titles.add(const_match.group(1))
    return titles


# ---------------------------------------------------------------------------
# Audience map ↔ pages on disk
# ---------------------------------------------------------------------------


class TestAudienceMapCoverage:
    def test_every_persona_has_at_least_one_page(self):
        for persona, pages in AUDIENCE_PAGES.items():
            assert pages, f"persona {persona!r} has no pages mapped"

    def test_every_mapped_page_exists_on_disk(self):
        on_disk = _page_titles_on_disk()
        # Some entries are aliases — page_header may say "Audit & Evidence"
        # while the file is named differently. We accept any prefix match.
        broken: list[str] = []
        for persona, pages in AUDIENCE_PAGES.items():
            for page in pages:
                # Match either exact title from page_header OR a substring
                # match in the file content (covers rename drift).
                exact = page in on_disk
                substring_hit = any(page in t or t in page for t in on_disk)
                if not (exact or substring_hit):
                    broken.append(f"  {persona}: {page!r}")
        assert not broken, "AUDIENCE_PAGES references pages not on disk:\n" + "\n".join(broken)


# ---------------------------------------------------------------------------
# Executive personas
# ---------------------------------------------------------------------------


class TestExecutivePersonas:
    def test_executive_audiences_set_includes_core_personas(self):
        # Source-level check (avoids importing components.py which pulls
        # streamlit, not available on the unit-test CI image).
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # Find the EXECUTIVE_AUDIENCES literal and verify each persona is present.
        m = re.search(r"EXECUTIVE_AUDIENCES\s*=\s*frozenset\(\{([^}]+)\}\)", body)
        assert m, "EXECUTIVE_AUDIENCES frozenset literal not found in components.py"
        members = m.group(1)
        for persona in ("svp", "vp", "director", "cto", "cco"):
            assert f'"{persona}"' in members, (
                f"{persona} should be in EXECUTIVE_AUDIENCES for font scaling"
            )

    def test_each_executive_persona_has_executive_dashboard(self):
        # The "meeting-room landing" expectation — every exec sees the
        # Executive Dashboard as a recommended page.
        for persona in ("svp", "vp", "director", "cto", "cco"):
            assert persona in AUDIENCE_PAGES, f"persona {persona!r} not in AUDIENCE_PAGES"
            assert "Executive Dashboard" in AUDIENCE_PAGES[persona], (
                f"persona {persona!r} missing Executive Dashboard"
            )


# ---------------------------------------------------------------------------
# CSS + theme injection
# ---------------------------------------------------------------------------


class TestExecutiveFontScale:
    def test_executive_css_constant_present(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "EXECUTIVE_CSS" in body, "EXECUTIVE_CSS constant missing"

    def test_apply_theme_checks_session_state(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # apply_theme must consult session state to know which audience
        # is active. If this regresses, the executive scale becomes dead code.
        assert 'st.session_state.get("selected_audience")' in body
        assert "EXECUTIVE_AUDIENCES" in body

    def test_executive_css_has_metric_value_scale(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # The KPI value font-size is the most-load-bearing rule —
        # if this gets dropped the exec mode visually does nothing.
        assert "stMetricValue" in body
        # Should be substantially larger than the base 1.8rem.
        assert "2.4rem" in body

    def test_executive_css_scales_headers(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # h1/h2/h3 should all be scaled.
        for tag in ("h1 {", "h2 {", "h3 {"):
            assert tag in body


# ---------------------------------------------------------------------------
# Audience selectbox in app.py
# ---------------------------------------------------------------------------


class TestAudienceSelector:
    def test_selectbox_exposes_every_mapped_persona(self):
        body = APP_FILE.read_text(encoding="utf-8")
        # Every key in AUDIENCE_PAGES should appear in the selectbox
        # options list — otherwise the user can't choose that persona.
        for persona in AUDIENCE_PAGES.keys():
            assert f'"{persona}"' in body, (
                f"persona {persona!r} mapped in audience.py but missing "
                f"from app.py selectbox options"
            )


class TestAllPagesRegistered:
    """Pages exist on disk + are referenced in the audience map but
    silently absent from `ALL_PAGES` in app.py would never appear in
    the sidebar. Caught Round-6 #5 + #2 drift."""

    EXPECTED_PAGE_FILES = {
        "1_Executive_Dashboard.py",
        "2_Program_Maturity.py",
        "3_Alert_Queue.py",
        "4_Case_Investigation.py",
        "5_Rule_Performance.py",
        "6_Risk_Assessment.py",
        "7_Audit_Evidence.py",
        "8_Framework_Alignment.py",
        "9_Transformation_Roadmap.py",
        "10_Network_Explorer.py",
        "11_Live_Monitor.py",
        "12_Sanctions_Screening.py",
        "13_Model_Performance.py",
        "14_Data_Quality.py",
        "15_Run_History.py",
        "16_Rule_Tuning.py",
        "17_Customer_360.py",
        "18_Typology_Catalogue.py",
        "19_Comparative_Analytics.py",
        "20_Spec_Editor.py",
        "21_My_Queue.py",
        "22_Analyst_Review_Queue.py",
        "23_Tuning_Lab.py",
        "24_Investigations.py",
    }

    def test_every_page_file_referenced_in_app(self):
        body = APP_FILE.read_text(encoding="utf-8")
        missing: list[str] = []
        for name in sorted(self.EXPECTED_PAGE_FILES):
            if name not in body:
                missing.append(name)
        assert not missing, (
            "These page files exist but aren't registered in app.py ALL_PAGES "
            "(invisible to the user):\n  " + "\n  ".join(missing)
        )


# ---------------------------------------------------------------------------
# Interactive widgets on previously-static pages
# ---------------------------------------------------------------------------


_INTERACTIVE_WIDGETS_RE = re.compile(
    r"st\.(selectbox|slider|multiselect|toggle|button|radio|"
    r"checkbox|text_input|number_input|date_input|file_uploader)"
)


class TestPagesNowInteractive:
    """The workflow audit (2026-04-27) flagged these pages as having
    no `st.*` interactive widgets. They got filters added in this PR;
    these tests guard against the filters being stripped in future
    refactors."""

    def test_rule_performance_has_widgets(self):
        body = (PAGES_DIR / "5_Rule_Performance.py").read_text(encoding="utf-8")
        assert _INTERACTIVE_WIDGETS_RE.search(body), (
            "Rule Performance page lost its interactive filters"
        )

    def test_risk_assessment_has_widgets(self):
        body = (PAGES_DIR / "6_Risk_Assessment.py").read_text(encoding="utf-8")
        assert _INTERACTIVE_WIDGETS_RE.search(body), (
            "Risk Assessment page lost its interactive filters"
        )

    def test_sanctions_screening_has_widgets(self):
        body = (PAGES_DIR / "12_Sanctions_Screening.py").read_text(encoding="utf-8")
        assert _INTERACTIVE_WIDGETS_RE.search(body), (
            "Sanctions Screening page lost its interactive filters"
        )

    def test_comparative_analytics_has_widgets(self):
        body = (PAGES_DIR / "19_Comparative_Analytics.py").read_text(encoding="utf-8")
        assert _INTERACTIVE_WIDGETS_RE.search(body), (
            "Comparative Analytics page lost its interactive filters"
        )


# ---------------------------------------------------------------------------
# Sample data wiring — every page reads session state OR is documented
# as a static template page
# ---------------------------------------------------------------------------


class TestSampleDataWiring:
    """The dashboard runs the engine on startup (state.py) and caches
    df_alerts/df_customers/df_txns/df_metrics/df_cases/df_decisions in
    session_state. Every operational page should consume one of those
    or read spec/result. Static template pages (Typology Catalogue) are
    the documented exception."""

    STATIC_PAGES = {"18_Typology_Catalogue.py"}

    def test_every_page_reads_session_state_or_is_static(self):
        non_compliant: list[str] = []
        for f in sorted(PAGES_DIR.glob("*.py")):
            if f.name == "__init__.py" or f.name in self.STATIC_PAGES:
                continue
            body = f.read_text(encoding="utf-8")
            if "st.session_state" not in body:
                non_compliant.append(f.name)
        assert not non_compliant, (
            "These pages don't read session state (no sample-data wiring):\n  "
            + "\n  ".join(non_compliant)
        )
