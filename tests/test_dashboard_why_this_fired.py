"""PR-LIN-6: 'Why this fired' panel on Case Investigation.

Source-level checks that the panel surfaces the lineage primitives
shipped in Phase A:
  - rule_sql block (st.code, language=sql) reading rules/<rule_id>.sql
  - matched_row_ids count metric
  - severity + rule_version metrics
  - panel positioned BEFORE the Transaction Timeline so 'why' answers
    before 'what'

Avoids importing Streamlit (not on the unit-test CI image).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_INV = (
    PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages" / "4_Case_Investigation.py"
)


class TestWhyThisFiredPanel:
    def test_panel_header_present(self):
        body = CASE_INV.read_text(encoding="utf-8")
        assert "### Why this fired" in body, "panel header missing"

    def test_panel_renders_rule_sql_when_available(self):
        body = CASE_INV.read_text(encoding="utf-8")
        assert "rules" in body and ".sql" in body, "must read rules/<rule_id>.sql off disk"
        assert 'st.code(_rule_sql, language="sql")' in body, (
            "rule SQL must render in an st.code(language='sql') block"
        )

    def test_panel_shows_matched_row_count(self):
        body = CASE_INV.read_text(encoding="utf-8")
        assert "matched_row_ids" in body
        assert 'st.metric("Matched source rows"' in body, (
            "matched-rows metric must be visible in the panel header"
        )

    def test_panel_shows_severity_and_rule_version(self):
        body = CASE_INV.read_text(encoding="utf-8")
        assert 'st.metric("Severity"' in body
        assert 'st.metric("Rule version"' in body

    def test_panel_renders_before_transaction_timeline(self):
        body = CASE_INV.read_text(encoding="utf-8")
        why_idx = body.index("### Why this fired")
        timeline_idx = body.index("### Transaction Timeline")
        assert why_idx < timeline_idx, (
            "Why-this-fired must come BEFORE Transaction Timeline so 'why' answers before 'what'"
        )
