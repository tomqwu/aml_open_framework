"""Source-level tests for PR-C: cross-page navigation + research-link sweep.

Six pages were islands — no cross-link to the related dashboard
page that owns the next workflow step, no link to the research doc
that informed them. PR-C adds a standardised `see_also_footer(...)`
block to each, reusing the `research_link()` helper added in PR #148.

Run as text-only assertions (no Streamlit needed).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENTS_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "components.py"
PAGES_DIR = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages"


class TestSeeAlsoFooterHelper:
    def test_function_defined(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "def see_also_footer(" in body, "see_also_footer helper missing"

    def test_renders_divider_then_caption(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        func = body.split("def see_also_footer(", 1)[1].split("\ndef ", 1)[0]
        assert 'st.markdown("---")' in func, "see_also_footer must render a divider"
        assert "**See also**" in func, "footer text must read 'See also'"


class TestPagesUseSeeAlsoFooter:
    PAGES_WITH_FOOTER = (
        "2_Program_Maturity.py",
        "6_Risk_Assessment.py",
        "8_Framework_Alignment.py",
        "9_Transformation_Roadmap.py",
        "15_Run_History.py",
        "24_Investigations.py",
    )

    def test_each_page_calls_see_also_footer(self):
        for page in self.PAGES_WITH_FOOTER:
            body = (PAGES_DIR / page).read_text(encoding="utf-8")
            assert "see_also_footer(" in body, f"{page} must invoke see_also_footer()"

    def test_program_maturity_links_pain4(self):
        body = (PAGES_DIR / "2_Program_Maturity.py").read_text(encoding="utf-8")
        assert "PAIN-4" in body
        assert "research_link(" in body

    def test_risk_assessment_links_customer360_and_pulse(self):
        body = (PAGES_DIR / "6_Risk_Assessment.py").read_text(encoding="utf-8")
        assert "17_Customer_360" in body
        assert "27_Regulator_Pulse" in body

    def test_framework_alignment_links_spec_editor(self):
        body = (PAGES_DIR / "8_Framework_Alignment.py").read_text(encoding="utf-8")
        assert "20_Spec_Editor" in body
        assert "research_link(" in body

    def test_transformation_roadmap_links_program_maturity(self):
        body = (PAGES_DIR / "9_Transformation_Roadmap.py").read_text(encoding="utf-8")
        assert "2_Program_Maturity" in body
        assert "7_Audit_Evidence" in body

    def test_run_history_links_comparative_analytics_and_audit(self):
        body = (PAGES_DIR / "15_Run_History.py").read_text(encoding="utf-8")
        assert "19_Comparative_Analytics" in body
        assert "7_Audit_Evidence" in body

    def test_investigations_links_fintech4(self):
        body = (PAGES_DIR / "24_Investigations.py").read_text(encoding="utf-8")
        assert "FINTECH-4" in body
        assert "research_link(" in body
