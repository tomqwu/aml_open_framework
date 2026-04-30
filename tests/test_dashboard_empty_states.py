"""Source-level tests for PR-D: empty-state polish.

The `empty_state(message, icon, detail, stop)` helper exists in
``components.py`` but was only used in `5_Rule_Performance.py`. Six
other pages had bare ``st.caption("No data yet")`` / ``st.success(...)``
/ ``st.info(...)`` calls. PR-D replaces those with the styled
empty_state card so analysts see the same shape everywhere.

Run as text-only assertions.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages"


PAGES_WITH_EMPTY_STATE = (
    "14_Data_Quality.py",
    "15_Run_History.py",
    "19_Comparative_Analytics.py",
    "20_Spec_Editor.py",
    "21_My_Queue.py",
    "25_BOI_Workflow.py",
)


class TestPagesUseEmptyState:
    def test_each_page_imports_empty_state(self):
        for page in PAGES_WITH_EMPTY_STATE:
            body = (PAGES_DIR / page).read_text(encoding="utf-8")
            assert "empty_state" in body, f"{page} must import empty_state from components"

    def test_data_quality_guards_no_contracts(self):
        body = (PAGES_DIR / "14_Data_Quality.py").read_text(encoding="utf-8")
        assert "No data contracts defined" in body
        assert "empty_state(" in body

    def test_run_history_no_stored_runs_uses_helper(self):
        body = (PAGES_DIR / "15_Run_History.py").read_text(encoding="utf-8")
        assert "No stored runs yet" in body
        # The empty_state replaces the bare st.caption("...") for the
        # "no stored runs" branch.
        empty_idx = body.find("empty_state(")
        no_runs_idx = body.find("No stored runs yet")
        assert 0 < empty_idx < no_runs_idx, (
            "empty_state(...) must wrap the 'No stored runs yet' branch"
        )

    def test_comparative_analytics_no_history_uses_helper(self):
        body = (PAGES_DIR / "19_Comparative_Analytics.py").read_text(encoding="utf-8")
        assert "No historical runs stored" in body
        assert "empty_state(" in body

    def test_spec_editor_load_failure_uses_helper(self):
        body = (PAGES_DIR / "20_Spec_Editor.py").read_text(encoding="utf-8")
        # Old: `current_yaml = "# Could not load spec file"` (silent)
        # New: empty_state(... stop=True) at load-failure point
        assert "Could not load spec file" in body
        assert "empty_state(" in body
        assert "stop=True" in body, (
            "Spec load failure should halt rendering — there's no usable spec to edit"
        )

    def test_my_queue_clear_state_uses_helper(self):
        body = (PAGES_DIR / "21_My_Queue.py").read_text(encoding="utf-8")
        assert "queue is clear" in body
        assert "empty_state(" in body

    def test_boi_workflow_no_reporting_co_uses_helper(self):
        body = (PAGES_DIR / "25_BOI_Workflow.py").read_text(encoding="utf-8")
        assert "No reporting-company customers in this run" in body
        assert "empty_state(" in body
        assert "stop=True" in body, (
            "Missing reporting-company customers means there's nothing to "
            "drill into — empty_state should halt the page below it"
        )
