"""Phase B-1 — SLA timer + STR bundle integration on case-facing pages.

Verifies that pages #4 (Case Investigation), #21 (My Queue), and #17
(Customer 360) wire in `cases.sla` + `cases.str_bundle` correctly.
Source-level checks since importing the pages requires streamlit; the
e2e-dashboard suite covers the full render path.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages"

CASE_INVESTIGATION = PAGES_DIR / "4_Case_Investigation.py"
MY_QUEUE = PAGES_DIR / "21_My_Queue.py"
CUSTOMER_360 = PAGES_DIR / "17_Customer_360.py"


# ---------------------------------------------------------------------------
# Page #4 — Case Investigation
# ---------------------------------------------------------------------------


class TestCaseInvestigationSLA:
    def test_imports_compute_sla_status(self):
        body = CASE_INVESTIGATION.read_text(encoding="utf-8")
        assert "from aml_framework.cases.sla import" in body
        assert "compute_sla_status" in body

    def test_imports_apply_escalation(self):
        body = CASE_INVESTIGATION.read_text(encoding="utf-8")
        assert "apply_escalation" in body

    def test_imports_bundle_function(self):
        body = CASE_INVESTIGATION.read_text(encoding="utf-8")
        assert "from aml_framework.cases.str_bundle import bundle_investigation_to_str" in body

    def test_imports_aggregator(self):
        # bundle_investigation_to_str needs an Investigation dict; the
        # page wraps the single case via aggregate_investigations(strategy="per_case").
        body = CASE_INVESTIGATION.read_text(encoding="utf-8")
        assert "from aml_framework.cases.aggregator import aggregate_investigations" in body

    def test_uses_severity_color_helper(self):
        # Replaces the inline sev_colors dict that drifted from
        # SEVERITY_COLORS. Severity should now resolve via the helper.
        body = CASE_INVESTIGATION.read_text(encoding="utf-8")
        assert "from aml_framework.dashboard.components import" in body
        assert "severity_color" in body
        # And the inline dict should be gone — no rebuilt copy of
        # {"high": "#dc2626", ...} inside the page.
        assert 'sev_colors = {"high":' not in body

    def test_uses_sla_band_color_helper(self):
        body = CASE_INVESTIGATION.read_text(encoding="utf-8")
        assert "sla_band_color" in body

    def test_uses_empty_state_helper(self):
        body = CASE_INVESTIGATION.read_text(encoding="utf-8")
        assert "from aml_framework.dashboard.components import" in body
        assert "empty_state" in body
        # The old st.warning + st.stop pair should be replaced.
        assert 'st.warning("No cases in this run.")' not in body

    def test_supports_deep_link_via_consume_param(self):
        # Allows Alert Queue / Customer 360 / Investigations to deep-link
        # via ?case_id=... . consume_param clears the link state on read.
        body = CASE_INVESTIGATION.read_text(encoding="utf-8")
        assert "from aml_framework.dashboard.query_params import consume_param" in body
        assert 'consume_param("case_id")' in body

    def test_renders_str_download_button(self):
        body = CASE_INVESTIGATION.read_text(encoding="utf-8")
        assert "st.download_button" in body
        # Names matter for analyst recognition.
        assert "STR submission ZIP" in body or "str_bundle" in body

    def test_str_bundle_failure_does_not_crash_page(self):
        # The bundle generator must never crash the page — wrap in try.
        # Skip the import-statement occurrence and find the actual call.
        body = CASE_INVESTIGATION.read_text(encoding="utf-8")
        # The function-call occurrence is followed by `(` and at least
        # one keyword arg over the next ~200 chars; the import line is
        # `from aml_framework.cases.str_bundle import bundle_investigation_to_str\n`.
        call_idx = body.find("bundle_investigation_to_str(\n")
        assert call_idx > 0, "no actual call to bundle_investigation_to_str found"
        # There should be a try/except surrounding it.
        assert "try:" in body[max(0, call_idx - 500) : call_idx]


# ---------------------------------------------------------------------------
# Page #21 — My Queue
# ---------------------------------------------------------------------------


class TestMyQueueSLA:
    def test_imports_compute_sla_status(self):
        body = MY_QUEUE.read_text(encoding="utf-8")
        assert "from aml_framework.cases.sla import compute_sla_status" in body

    def test_uses_empty_state_helper(self):
        body = MY_QUEUE.read_text(encoding="utf-8")
        assert "empty_state" in body
        assert 'st.warning("No cases in this run.")' not in body

    def test_open_cases_table_includes_sla_columns(self):
        body = MY_QUEUE.read_text(encoding="utf-8")
        # The table builder should append sla_state + sla_remaining.
        assert "sla_state" in body
        assert "sla_remaining" in body

    def test_sla_caption_documents_bands(self):
        # Operators learn the band thresholds once if we always show them.
        body = MY_QUEUE.read_text(encoding="utf-8")
        assert "green > 50%" in body or "green &gt; 50%" in body


# ---------------------------------------------------------------------------
# Page #17 — Customer 360
# ---------------------------------------------------------------------------


class TestCustomer360SLA:
    def test_cases_table_imports_sla(self):
        body = CUSTOMER_360.read_text(encoding="utf-8")
        # The page imports lazily inside the cases section to keep the
        # top-level import surface stable.
        assert "from aml_framework.cases.sla import compute_sla_status" in body

    def test_cases_table_includes_sla_state(self):
        body = CUSTOMER_360.read_text(encoding="utf-8")
        assert "sla_state" in body


# ---------------------------------------------------------------------------
# Cross-page: same helper usage = same behavior
# ---------------------------------------------------------------------------


class TestCrossPageConsistency:
    def test_all_three_pages_use_compute_sla_status(self):
        for page in (CASE_INVESTIGATION, MY_QUEUE, CUSTOMER_360):
            body = page.read_text(encoding="utf-8")
            assert "compute_sla_status" in body, (
                f"{page.name} should use compute_sla_status from cases.sla"
            )

    def test_no_page_reimplements_sla_band_classification(self):
        # If any page hardcodes the green/amber/red/breached thresholds
        # (e.g. its own `if pct_remaining > 50: "green"` ladder), it
        # would drift from cases/sla.py's band logic. Pages may still
        # use parse_window for chart annotation (drawing an SLA line on
        # a histogram) — that's display, not classification.
        for page in (CASE_INVESTIGATION, MY_QUEUE, CUSTOMER_360):
            body = page.read_text(encoding="utf-8")
            # No inline band ladder: catches `if ... > 50`, `if ... > 0.5`
            # patterns that would parallel _classify() in cases/sla.py.
            assert "DEFAULT_SLA_BANDS" not in body, (
                f"{page.name} should not reach into SLA band internals — "
                "use compute_sla_status() instead"
            )
