"""Source-level tests for PR-I: Metrics Taxonomy dashboard page.

The new page (28_Metrics_Taxonomy.py) is a read-only catalogue
browser for the spec's `metrics:` block, sister to the Typology
Catalogue. Tests verify the page exists, has the documented
sections (KPI strip, filters, accordion, see-also), and that
the audience routing exposes it to the 7 senior personas.

Text-only assertions — no Streamlit needed.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages" / "28_Metrics_Taxonomy.py"
AUDIENCE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "audience.py"


class TestPageExists:
    def test_page_file_exists(self):
        assert PAGE.exists(), f"Metrics Taxonomy page must exist at {PAGE}"


class TestPageStructure:
    def test_page_header_renders_title(self):
        body = PAGE.read_text(encoding="utf-8")
        assert "page_header(" in body
        assert '"Metrics Taxonomy"' in body or "PAGE_TITLE" in body

    def test_kpi_strip_uses_kpi_card_rag(self):
        body = PAGE.read_text(encoding="utf-8")
        # 4 KPI cards: total / categories used / with targets / owners assigned
        assert body.count("kpi_card_rag(") >= 4, "KPI strip must render 4 cards via kpi_card_rag()"

    def test_kpi_completeness_carries_rag(self):
        body = PAGE.read_text(encoding="utf-8")
        # RAG: green when fully populated, amber partial, red none.
        # The helper that computes this branching must exist.
        assert "_completeness_rag" in body, (
            "KPI completeness should branch green/amber/red, not always neutral"
        )

    def test_filters_present(self):
        body = PAGE.read_text(encoding="utf-8")
        # 3 multiselects + 1 toggle (only with targets)
        assert body.count("st.multiselect(") >= 3, (
            "Page needs 3 multiselect filters: category, audience, formula"
        )
        assert "st.toggle(" in body, "Page needs the 'Only with targets' toggle"
        assert "selected_categories" in body
        assert "selected_audiences" in body
        assert "selected_formulas" in body

    def test_audience_filter_defaults_to_active_persona(self):
        body = PAGE.read_text(encoding="utf-8")
        assert "selected_audience" in body, (
            "Audience filter must default to the persona picked in the sidebar"
        )

    def test_iterates_metrics_by_category(self):
        body = PAGE.read_text(encoding="utf-8")
        # Per-category accordion structure
        assert "ALL_CATEGORIES" in body
        assert "operational" in body
        assert "effectiveness" in body
        assert "regulatory" in body
        assert "delivery" in body
        assert "st.expander(" in body

    def test_metric_card_shows_live_value_when_present(self):
        body = PAGE.read_text(encoding="utf-8")
        # The card must consult result.metrics for the current run's RAG
        assert "metrics_by_id" in body
        assert "result.metrics" in body
        assert "live.rag" in body or "live_html" in body

    def test_uses_rag_colors_token(self):
        body = PAGE.read_text(encoding="utf-8")
        # Colour discipline — no inline hex codes for RAG bands; pulls
        # from the centralised RAG_COLORS / KPI_NEUTRAL_BORDER.
        assert "RAG_COLORS" in body
        assert "KPI_NEUTRAL_BORDER" in body

    def test_formula_definition_in_yaml_expander(self):
        body = PAGE.read_text(encoding="utf-8")
        # Each card has a YAML-formatted formula expander so spec
        # readers recognise the shape.
        assert "import yaml" in body
        assert 'language="yaml"' in body
        assert "Formula definition" in body


class TestEmptyState:
    def test_zero_metrics_uses_empty_state(self):
        body = PAGE.read_text(encoding="utf-8")
        assert "empty_state(" in body
        assert "stop=True" in body, "Zero-metrics path must halt the page (no usable content)"
        assert "zero metrics" in body.lower()


class TestSeeAlsoFooter:
    def test_renders_see_also_footer(self):
        body = PAGE.read_text(encoding="utf-8")
        assert "see_also_footer(" in body

    def test_links_to_executive_dashboard_and_comparative(self):
        body = PAGE.read_text(encoding="utf-8")
        assert "1_Executive_Dashboard" in body, (
            "See-also footer must cross-link to Executive Dashboard"
        )
        assert "19_Comparative_Analytics" in body
        assert "20_Spec_Editor" in body

    def test_links_to_research_doc(self):
        body = PAGE.read_text(encoding="utf-8")
        assert "research_link(" in body
        assert "FinCEN AML Effectiveness" in body


class TestAudienceRouting:
    SENIOR_PERSONAS = ("cco", "vp", "director", "manager", "pm", "auditor", "fintech_mlro")
    EXCLUDED = ("analyst",)

    def test_metrics_taxonomy_in_senior_persona_page_lists(self):
        body = AUDIENCE.read_text(encoding="utf-8")
        # Each senior persona must have "Metrics Taxonomy" in their
        # AUDIENCE_PAGES list. We do per-persona substring checks
        # against the dict literal.
        for persona in self.SENIOR_PERSONAS:
            persona_block_start = body.find(f'"{persona}": [')
            assert persona_block_start > 0, f"persona {persona} missing from AUDIENCE_PAGES"
            # Look at the next ~700 chars for that persona's list.
            persona_block = body[persona_block_start : persona_block_start + 700]
            assert "Metrics Taxonomy" in persona_block, (
                f"persona '{persona}' must include 'Metrics Taxonomy' in their pages"
            )

    def test_metrics_taxonomy_excluded_from_analyst(self):
        body = AUDIENCE.read_text(encoding="utf-8")
        analyst_start = body.find('"analyst": [')
        assert analyst_start > 0
        analyst_block = body[analyst_start : analyst_start + 500]
        assert "Metrics Taxonomy" not in analyst_block, (
            "Analyst should NOT see Metrics Taxonomy — it's a senior-persona reference"
        )
