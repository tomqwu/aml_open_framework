"""Smoke tests for the Round-6 Investigations dashboard page (#24).

The dashboard module imports streamlit at module-level which the unit-
test CI image doesn't have, so this file uses pytest.importorskip to
skip cleanly on minimal environments. The actual page-render flow is
exercised by the e2e-dashboard CI job.

What we cover here without needing a Streamlit runtime:
  - Page file exists at the expected path
  - audience.py wires "Investigations" into manager + analyst views
  - app.py registers the page in ALL_PAGES
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages" / "24_Investigations.py"


class TestPageFile:
    def test_page_file_exists(self):
        assert PAGE_FILE.exists(), f"page file missing at {PAGE_FILE}"

    def test_page_imports_aggregator_and_sla(self):
        # Sanity-check that the page sources the right composable modules.
        body = PAGE_FILE.read_text(encoding="utf-8")
        assert "from aml_framework.cases import" in body
        assert "aggregate_investigations" in body
        assert "summarise_backlog" in body
        assert "compute_sla_status" in body

    def test_page_offers_all_three_strategies(self):
        body = PAGE_FILE.read_text(encoding="utf-8")
        assert "per_customer_window" in body
        assert "per_customer_per_run" in body
        assert "per_case" in body

    def test_page_handles_no_cases_gracefully(self):
        body = PAGE_FILE.read_text(encoding="utf-8")
        # Page bails out on empty case set rather than crashing.
        assert "df_cases.empty" in body
        assert "st.stop()" in body


# ---------------------------------------------------------------------------
# audience.py wiring
# ---------------------------------------------------------------------------


class TestAudienceWiring:
    def test_audience_module_is_importable_without_streamlit(self):
        # The audience module is import-safe without streamlit (the
        # AUDIENCE_PAGES dict is module-level, no st imports at top).
        from aml_framework.dashboard.audience import AUDIENCE_PAGES

        assert isinstance(AUDIENCE_PAGES, dict)

    def test_investigations_in_manager_view(self):
        from aml_framework.dashboard.audience import AUDIENCE_PAGES

        assert "Investigations" in AUDIENCE_PAGES["manager"]

    def test_investigations_in_analyst_view(self):
        from aml_framework.dashboard.audience import AUDIENCE_PAGES

        assert "Investigations" in AUDIENCE_PAGES["analyst"]


# ---------------------------------------------------------------------------
# app.py registration
# ---------------------------------------------------------------------------


class TestAppRegistration:
    def test_app_module_registers_page_24(self):
        # We don't import dashboard.app (it imports streamlit at module
        # level); instead grep the source for the page registration.
        app_file = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "app.py"
        body = app_file.read_text(encoding="utf-8")
        assert "24_Investigations.py" in body
        assert 'title="Investigations"' in body


# ---------------------------------------------------------------------------
# End-to-end functional check (skipped without streamlit / engine deps)
# ---------------------------------------------------------------------------


class TestEndToEndComputables:
    def test_page_modules_compose_real_engine_output(self, tmp_path):
        """Smoke-test that the modules the page uses actually work together
        on a real engine run — independent of Streamlit rendering."""
        import json
        from datetime import datetime, timedelta

        from aml_framework.cases import (
            aggregate_investigations,
            apply_escalation,
            compute_sla_status,
            summarise_backlog,
        )
        from aml_framework.data import generate_dataset
        from aml_framework.engine import run_spec
        from aml_framework.spec import load_spec

        spec_path = PROJECT_ROOT / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
        spec = load_spec(spec_path)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=generate_dataset(as_of=as_of, seed=42),
            as_of=as_of,
            artifacts_root=tmp_path,
        )
        cases_dirs = list(tmp_path.glob("**/cases"))
        cases = [json.loads(f.read_text()) for f in sorted(cases_dirs[0].glob("*.json"))]

        # The three computations the page does — none should raise.
        invs = aggregate_investigations(cases, strategy="per_customer_window")
        backlog = summarise_backlog(cases, spec, as_of=as_of + timedelta(days=1))
        # Per-case SLA + escalation drill-down on the first investigation.
        if invs:
            first = invs[0]
            queue_map = {q.id: q for q in spec.workflow.queues}
            for case in cases:
                if case.get("case_id") not in first["case_ids"]:
                    continue
                queue = queue_map.get(case.get("queue", ""))
                if queue is None:
                    continue
                status = compute_sla_status(case, queue, as_of=as_of + timedelta(days=1))
                # apply_escalation must accept whatever compute returns.
                if status is not None:
                    apply_escalation(case, status, queue)

        assert isinstance(invs, list)
        assert isinstance(backlog, list)
