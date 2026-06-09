"""PR-LIN-8: Lineage Explorer page #32.

Source-level checks that the new page exists, is registered in
app.py + e2e PAGES + audience.py, and renders the expected sections
(Mermaid graph, run anchors, source provenance, rendered SQL,
matched rows, decision timeline, JSON download).

Avoids importing Streamlit (not on the unit-test CI image).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages" / "32_Lineage_Explorer.py"
APP = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "app.py"
AUDIENCE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "audience.py"
E2E = PROJECT_ROOT / "tests" / "test_e2e_dashboard.py"


class TestLineageExplorerPage:
    def test_page_file_exists(self):
        assert PAGE.exists(), "32_Lineage_Explorer.py must exist"

    def test_uses_walk_lineage(self):
        body = PAGE.read_text(encoding="utf-8")
        assert "from aml_framework.engine.audit import walk_lineage" in body
        assert "walk_lineage(run_dir, " in body

    def test_reads_case_id_from_deep_link(self):
        body = PAGE.read_text(encoding="utf-8")
        assert "consume_param(" in body, "must accept deep-link from Audit/Case pages"
        assert '"case_id"' in body

    def test_case_id_is_a_dropdown_over_run_cases(self):
        body = PAGE.read_text(encoding="utf-8")
        # The case_id input must be a searchable selectbox built from the
        # current run's cases — not a free-text paste box that forces the
        # analyst to type an exact, run-stamped case_id by hand.
        assert "st.selectbox(" in body, "case_id input must be a dropdown"
        assert 'sorted(df_cases["case_id"].tolist())' in body, (
            "dropdown options must be the run's sorted case_ids"
        )
        assert "st.text_input(" not in body, "case_id paste box must be removed"

    def test_deep_link_preselects_dropdown_default(self):
        body = PAGE.read_text(encoding="utf-8")
        # A "Why this fired" deep-link must still pre-select the matching
        # case via the selectbox `index`, not lose the inbound case_id.
        assert "default_idx" in body and "index=default_idx" in body, (
            "deep-link / session case must drive the selectbox default index"
        )
        assert "if deep_link in case_ids:" in body

    def test_invalid_deep_link_warns_instead_of_silent_swap(self):
        body = PAGE.read_text(encoding="utf-8")
        # A deep-link naming a case absent from the current run (stale
        # bookmark after the loaded run changed) must surface a warning,
        # not silently resolve to a different case.
        assert "deep_link and deep_link not in case_ids" in body, (
            "must detect a deep-link case_id missing from the current run"
        )
        assert "st.warning(" in body

    def test_session_case_captured_before_consume_param(self):
        body = PAGE.read_text(encoding="utf-8")
        # consume_param('case_id') pops the `selected_case_id` mirror, so the
        # cross-page session fallback must be read BEFORE it — else a stale
        # deep-link bounces an analyst off their selected case to the first.
        sess_idx = body.index('_session_case = st.session_state.get("selected_case_id")')
        consume_idx = body.index('deep_link = consume_param("case_id")')
        assert sess_idx < consume_idx, "_session_case must be captured before consume_param pops it"

    def test_renders_all_seven_sections(self):
        body = PAGE.read_text(encoding="utf-8")
        for header in (
            "### Lineage graph",
            "### Run anchors",
            "### Source provenance",
            "### Rule SQL",
            "### Matched source rows",
            "### Decision timeline",
            "### Export",
        ):
            assert header in body, f"section header '{header}' missing from page"

    def test_mermaid_graph_includes_source_to_str_chain(self):
        body = PAGE.read_text(encoding="utf-8")
        # The Mermaid graph must wire source → contract → table → rule
        # → alert → case (and conditionally → investigation → STR).
        assert "graph LR" in body
        assert "DuckDB table" in body
        assert "matched rows" in body

    def test_sql_block_uses_st_code_with_language(self):
        body = PAGE.read_text(encoding="utf-8")
        assert 'st.code(chain["rule_sql"], language="sql")' in body

    def test_json_download_button(self):
        body = PAGE.read_text(encoding="utf-8")
        assert "st.download_button(" in body
        assert "lineage_" in body and ".json" in body


class TestLineageExplorerWiredIntoApp:
    def test_registered_in_app(self):
        body = APP.read_text(encoding="utf-8")
        assert 'st.Page(\n            "pages/32_Lineage_Explorer.py"' in body or (
            'st.Page("pages/32_Lineage_Explorer.py"' in body
        ), "Lineage Explorer must be registered in app.py"
        assert 'title="Lineage Explorer"' in body

    def test_in_e2e_pages_list(self):
        body = E2E.read_text(encoding="utf-8")
        assert '"Lineage Explorer"' in body, "e2e PAGES list must include Lineage Explorer"

    def test_assigned_to_analyst_persona(self):
        body = AUDIENCE.read_text(encoding="utf-8")
        # Find the analyst block and assert Lineage Explorer is in it.
        # Cheap check: both strings appear close together.
        analyst_idx = body.index('"analyst": [')
        next_persona_idx = body.index('"pm": [', analyst_idx)
        analyst_block = body[analyst_idx:next_persona_idx]
        assert '"Lineage Explorer"' in analyst_block, (
            "Lineage Explorer must be in the analyst persona's page list"
        )
