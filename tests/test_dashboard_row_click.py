"""Source-level tests for the PR-A row-click drill-through migration.

Guards the design decision that the redundant "selectbox-below-the-
table" pattern has been replaced with `st.dataframe(on_select="rerun",
selection_mode="single-row")` via the shared `selectable_dataframe`
helper. Run as text-only assertions so they pass on the lint-only CI
image without streamlit installed.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENTS_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "components.py"
PAGES_DIR = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages"


# ---------------------------------------------------------------------------
# Helper exists with the right contract
# ---------------------------------------------------------------------------


class TestSelectableDataframeHelper:
    def test_function_defined(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "def selectable_dataframe(" in body, "selectable_dataframe helper missing"

    def test_signature_takes_drill_kwargs(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        sig = re.search(r"def selectable_dataframe\([^)]*\)", body, flags=re.DOTALL)
        assert sig, "selectable_dataframe signature not found"
        sig_text = sig.group(0)
        for kw in ("key", "drill_target", "drill_param", "drill_column"):
            assert kw in sig_text, f"selectable_dataframe must accept '{kw}' kwarg"

    def test_uses_streamlit_on_select_api(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        body_after_def = body.split("def selectable_dataframe(", 1)[1]
        body_func = body_after_def.split("\ndef ", 1)[0]
        assert 'on_select="rerun"' in body_func, (
            "selectable_dataframe must use Streamlit's on_select='rerun' contract — "
            "without it the dataframe stays read-only"
        )
        assert 'selection_mode="single-row"' in body_func, (
            "row drill-through requires single-row selection mode"
        )
        assert "switch_page" in body_func, (
            "drill_target navigation needs st.switch_page on selection event"
        )


# ---------------------------------------------------------------------------
# Pages migrated to the helper
# ---------------------------------------------------------------------------


class TestPagesMigrated:
    def test_alert_queue_has_row_click_drill(self):
        # PR-A introduced selectable_dataframe; PR-CHART-2 replaced it
        # with the AG-Grid-backed data_grid (same drill_target /
        # drill_param / drill_column contract). Either is acceptable —
        # the invariant is that the table itself is the drill, not a
        # selectbox below.
        body = (PAGES_DIR / "3_Alert_Queue.py").read_text(encoding="utf-8")
        assert ("selectable_dataframe(" in body) or ("data_grid(" in body), (
            "Alert Queue must use selectable_dataframe or data_grid for row-click drill"
        )
        # Old selectbox-below pattern should be gone for the customer + case drills.
        assert "alertqueue_customer_drill" not in body, (
            "Old customer-drill selectbox should be removed; row-click replaces it"
        )
        assert "alertqueue_case_drill" not in body, (
            "Old case-drill selectbox should be removed; row-click replaces it"
        )

    def test_customer_360_cases_table_drills(self):
        body = (PAGES_DIR / "17_Customer_360.py").read_text(encoding="utf-8")
        assert "selectable_dataframe(" in body
        assert "customer360_case_drill" not in body, "Old case-drill selectbox should be removed"
        assert "customer360_cases_table" in body, (
            "Customer 360 cases table must use the named selectable_dataframe key"
        )

    def test_my_queue_open_cases_drills(self):
        body = (PAGES_DIR / "21_My_Queue.py").read_text(encoding="utf-8")
        assert "selectable_dataframe(" in body
        assert "myqueue_open_cases_table" in body
        # Drill target must be Case Investigation
        assert 'drill_target="pages/4_Case_Investigation.py"' in body

    def test_investigations_three_tables_drill(self):
        body = (PAGES_DIR / "24_Investigations.py").read_text(encoding="utf-8")
        assert body.count("selectable_dataframe(") >= 3, (
            "Investigations page has 3 drillable tables: investigation list "
            "(→ Customer 360), constituent cases (→ Case Investigation), and "
            "linked-across-domains (→ Customer 360)"
        )
        assert "investigations_list_table" in body
        assert "investigations_constituent_cases" in body
        assert "investigations_linked_table" in body

    def test_boi_workflow_records_table_drills(self):
        body = (PAGES_DIR / "25_BOI_Workflow.py").read_text(encoding="utf-8")
        assert "selectable_dataframe(" in body
        assert "boi_records_table" in body
        assert 'drill_target="pages/17_Customer_360.py"' in body
