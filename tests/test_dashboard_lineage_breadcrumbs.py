"""PR-LIN-12+: lineage breadcrumbs across the daily triage path.

Source-level checks that the dashboard pages pull lineage info into
their tables and link out to Lineage Explorer (#32) for the full
walk-back. Verifies the chain shipped in Round 12 (rule_version,
matched_row_ids, rule_sql) is now reachable from every analyst-facing
surface, not just Audit & Evidence + Lineage Explorer.

Avoids importing Streamlit (not on the unit-test CI image).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGES = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages"

ALERT_QUEUE = PAGES / "3_Alert_Queue.py"
MY_QUEUE = PAGES / "21_My_Queue.py"
ANALYST_REVIEW = PAGES / "22_Analyst_Review_Queue.py"
CASE_INV = PAGES / "4_Case_Investigation.py"


class TestAlertQueueBreadcrumbs:
    def test_matched_rows_column_added(self):
        body = ALERT_QUEUE.read_text(encoding="utf-8")
        assert '"Matched rows"' in body, "Matched rows column missing from Alert Queue"
        assert "matched_row_ids" in body, "Alert Queue must read matched_row_ids from alert"

    def test_rule_version_column_added(self):
        body = ALERT_QUEUE.read_text(encoding="utf-8")
        assert '"Rule version"' in body, "Rule version column missing from Alert Queue"
        assert "rule_version" in body, "Alert Queue must read rule_version from alert"


class TestMyQueueBreadcrumbs:
    def test_matched_rows_column_added(self):
        body = MY_QUEUE.read_text(encoding="utf-8")
        assert '"Matched rows"' in body
        assert "matched_row_ids" in body

    def test_rule_version_column_added(self):
        body = MY_QUEUE.read_text(encoding="utf-8")
        assert '"Rule version"' in body
        assert "rule_version" in body


class TestAnalystReviewLineageExpander:
    def test_lineage_expander_present(self):
        body = ANALYST_REVIEW.read_text(encoding="utf-8")
        assert "Source lineage" in body, "Analyst Review Queue missing lineage expander"
        assert "walk_lineage" in body, "Lineage expander must call walk_lineage()"

    def test_links_to_lineage_explorer(self):
        body = ANALYST_REVIEW.read_text(encoding="utf-8")
        assert "32_Lineage_Explorer.py" in body, (
            "Analyst Review Queue must deep-link to Lineage Explorer"
        )
        assert "case_id=row.case_id" in body or "case_id=row.case_id," in body, (
            "Lineage Explorer link must pass case_id"
        )


class TestCaseInvestigationDeepLink:
    def test_links_to_lineage_explorer(self):
        body = CASE_INV.read_text(encoding="utf-8")
        # PR-LIN-12 wires the path from Case Investigation's "Why this
        # fired" panel to the dedicated Lineage Explorer page so the
        # analyst can drill from in-workflow context into the full
        # walk-back.
        assert "32_Lineage_Explorer.py" in body, (
            "Case Investigation must link to Lineage Explorer from the Why-this-fired panel"
        )
        assert 'case_id=case["case_id"]' in body or "case_id=case['case_id']" in body, (
            "deep-link must pass case_id"
        )
