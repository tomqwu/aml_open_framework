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


class TestInvestigationsBreadcrumbs:
    """PR-LIN-13: Investigations page constituent-cases grid carries
    rule_version + matched-row count alongside SLA state."""

    def test_columns_added_to_constituent_cases(self):
        body = (PAGES / "24_Investigations.py").read_text(encoding="utf-8")
        assert '"Matched rows"' in body
        assert '"Rule version"' in body
        assert "matched_row_ids" in body
        assert "rule_version" in body


class TestNetworkExplorerLineage:
    """PR-LIN-13: Network Explorer surfaces per-customer lineage walk-back
    deep-links so an auditor working a cluster can follow each alert
    back to its source rows."""

    def test_walk_back_section_present(self):
        body = (PAGES / "10_Network_Explorer.py").read_text(encoding="utf-8")
        assert "Lineage walk-back per alerted customer" in body
        assert "32_Lineage_Explorer.py" in body
        assert "case_id=_case_id" in body


class TestCustomer360Lineage:
    """PR-LIN-13: Customer 360 cases table gains rule_version +
    matched-row count plus a deep-link to Lineage Explorer."""

    def test_lineage_columns_on_cases_table(self):
        body = (PAGES / "17_Customer_360.py").read_text(encoding="utf-8")
        assert '"Matched rows"' in body
        assert '"Rule version"' in body

    def test_deep_link_present(self):
        body = (PAGES / "17_Customer_360.py").read_text(encoding="utf-8")
        assert "32_Lineage_Explorer.py" in body
        assert "Walk lineage chain" in body


class TestRulePerformanceVersion:
    """PR-LIN-14: Rule Performance analytics table stamps rule_version
    so MRM dossiers can be cross-checked against the version that fired."""

    def test_rule_version_column_added(self):
        body = (PAGES / "5_Rule_Performance.py").read_text(encoding="utf-8")
        assert '"Rule version"' in body
        assert "rule_version_hash(rule)" in body


class TestRunHistoryLineageLinks:
    """PR-LIN-14: Run History points users to the lineage walk-back
    surfaces (Audit & Evidence + Lineage Explorer)."""

    def test_audit_evidence_link_present(self):
        body = (PAGES / "15_Run_History.py").read_text(encoding="utf-8")
        assert "7_Audit_Evidence.py" in body

    def test_lineage_explorer_link_present(self):
        body = (PAGES / "15_Run_History.py").read_text(encoding="utf-8")
        assert "32_Lineage_Explorer.py" in body


class TestSanctionsScreeningRowid:
    """PR-LIN-14: list_match alerts carry matched_row_ids per PR-LIN-4
    and Sanctions Screening surfaces them as a Source rowid column."""

    def test_source_rowid_column_added(self):
        body = (PAGES / "12_Sanctions_Screening.py").read_text(encoding="utf-8")
        assert '"Source rowid"' in body
        assert "matched_row_ids" in body


class TestTuningLabLineagePointer:
    """PR-LIN-14: Tuning Lab points to Lineage Explorer for case-level
    walk-back; per-scenario row tracing is deferred."""

    def test_lineage_explorer_link_present(self):
        body = (PAGES / "23_Tuning_Lab.py").read_text(encoding="utf-8")
        assert "32_Lineage_Explorer.py" in body


class TestTodayLineageLink:
    """PR-LIN-15: Today's 'Next 5 to triage' section deep-links to
    Lineage Explorer for the top-ranked case."""

    def test_lineage_explorer_link_present(self):
        body = (PAGES / "0_Today.py").read_text(encoding="utf-8")
        assert "32_Lineage_Explorer.py" in body
        assert "case_id=_ranked[0].case_id" in body


class TestExecutiveDashboardLineagePointer:
    """PR-LIN-15: Executive Dashboard surfaces the lineage entry-point
    on the headline page so board readers can ask 'why this number?'"""

    def test_lineage_explorer_link_present(self):
        body = (PAGES / "1_Executive_Dashboard.py").read_text(encoding="utf-8")
        assert "32_Lineage_Explorer.py" in body
        assert "matched_row_ids" in body


class TestAIAssistantVerifyLink:
    """PR-LIN-15: AI Assistant citations link to Lineage Explorer for
    the first referenced_case_id — closes the 'AI claim → audit chain'
    gap."""

    def test_verify_against_audit_trail_link_present(self):
        body = (PAGES / "29_AI_Assistant.py").read_text(encoding="utf-8")
        assert "Verify against audit trail" in body
        assert "32_Lineage_Explorer.py" in body
        assert "reply.referenced_case_ids[0]" in body


class TestRiskAssessmentDrill:
    """PR-LIN-23: Risk Assessment alerted-customers grid drills to
    Alert Queue (which carries Round 12 lineage breadcrumbs)."""

    def test_drill_target_is_alert_queue(self):
        body = (PAGES / "6_Risk_Assessment.py").read_text(encoding="utf-8")
        assert 'drill_target="pages/3_Alert_Queue.py"' in body
        assert 'drill_param="customer_id"' in body


class TestModelPerformanceLineagePointer:
    """PR-LIN-23: Model Performance gains a Lineage Explorer pointer
    so MRM reviewers can validate alert scoring against the chain."""

    def test_lineage_explorer_link_present(self):
        body = (PAGES / "13_Model_Performance.py").read_text(encoding="utf-8")
        assert "32_Lineage_Explorer.py" in body
        assert "Lineage Explorer" in body


class TestComparativeAnalyticsLineagePointer:
    """PR-LIN-23: Comparative Analytics gains a Lineage Explorer
    pointer (same Run History pattern from PR-LIN-14)."""

    def test_lineage_explorer_link_present(self):
        body = (PAGES / "19_Comparative_Analytics.py").read_text(encoding="utf-8")
        assert "32_Lineage_Explorer.py" in body


class TestFinTechCockpitLineagePointer:
    """PR-LIN-23: FinTech Cockpit gains a 'walk a case from this pack'
    Lineage Explorer pointer right after the evidence-pack download."""

    def test_lineage_explorer_link_present(self):
        body = (PAGES / "26_FinTech_Cockpit.py").read_text(encoding="utf-8")
        assert "32_Lineage_Explorer.py" in body
        assert "Walk a case from this pack" in body


class TestMetricsTaxonomyLineagePointer:
    """PR-LIN-23: Metrics Taxonomy gains a footer pointer to Lineage
    Explorer for per-metric case-evidence walk-back."""

    def test_lineage_explorer_link_present(self):
        body = (PAGES / "28_Metrics_Taxonomy.py").read_text(encoding="utf-8")
        assert "32_Lineage_Explorer.py" in body


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
