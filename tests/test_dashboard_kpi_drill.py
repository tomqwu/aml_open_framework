"""Source-level tests for PR-G: KPI card drill-through.

KPI cards on operational pages (My Queue, BOI Workflow, Alert Queue)
showed counts that should drill into a filtered list. PR-G:
- My Queue + BOI Workflow: cross-page drill via `link_to_page` with
  query params (`queue_filter`, `boi_status_filter`)
- Alert Queue: in-page severity drill via session-state-driven
  multiselect default
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages"


class TestMyQueueKpiDrill:
    def test_imports_link_to_page(self):
        body = (PAGES_DIR / "21_My_Queue.py").read_text(encoding="utf-8")
        assert "link_to_page" in body, "My Queue must use link_to_page for KPI drill"

    def test_assigned_kpi_drills_to_case_investigation(self):
        body = (PAGES_DIR / "21_My_Queue.py").read_text(encoding="utf-8")
        assert "queue_filter=selected_queue" in body, (
            "Assigned/Open/Resolved KPIs must forward the queue filter"
        )

    def test_open_kpi_carries_status_filter(self):
        body = (PAGES_DIR / "21_My_Queue.py").read_text(encoding="utf-8")
        assert 'status_filter="open"' in body

    def test_sla_kpi_drills_to_breaches_when_below_100(self):
        body = (PAGES_DIR / "21_My_Queue.py").read_text(encoding="utf-8")
        assert 'sla_filter="breached"' in body


class TestBoiWorkflowKpiDrill:
    def test_filter_buttons_present(self):
        body = (PAGES_DIR / "25_BOI_Workflow.py").read_text(encoding="utf-8")
        assert "Show missing" in body
        assert "Show stale" in body
        assert "Show all" in body
        assert "boi_status_filter" in body

    def test_table_reads_filter_from_session_state(self):
        body = (PAGES_DIR / "25_BOI_Workflow.py").read_text(encoding="utf-8")
        # The filter must be applied before the dataframe render —
        # otherwise the buttons drill to nothing.
        filter_idx = body.find("boi_status_filter")
        df_idx = body.find("df_records = pd.DataFrame")
        assert filter_idx > 0 and df_idx > 0
        # at least one filter read happens before the dataframe is built
        assert body.find('st.session_state.get("boi_status_filter")') < df_idx


class TestAlertQueueKpiDrill:
    def test_kpi_filter_buttons_added(self):
        body = (PAGES_DIR / "3_Alert_Queue.py").read_text(encoding="utf-8")
        assert "kpi_filter_high" in body
        assert "alertqueue_severity_filter" in body

    def test_severity_multiselect_reads_filter(self):
        body = (PAGES_DIR / "3_Alert_Queue.py").read_text(encoding="utf-8")
        assert "severity_default" in body, (
            "Severity multiselect must read the KPI-filter session state for its default"
        )
