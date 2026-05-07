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
