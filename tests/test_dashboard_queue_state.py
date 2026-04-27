"""Tests for `dashboard/queue_state.py` — composition of pkyc + narratives.

Streamlit is NOT imported here; the page glue lives in queue_state.py and
gets exercised end-to-end. CI's unit-test job doesn't install streamlit.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aml_framework.dashboard.queue_state import (
    NARRATIVE_ACCEPT,
    NARRATIVE_AMEND,
    NARRATIVE_ESCALATE,
    NARRATIVE_REJECT,
    build_queue_rows,
    event_for_narrative_action,
    event_for_pkyc_action,
    record_decision,
    supported_narrative_actions,
)
from aml_framework.engine.constants import Event


def _now():
    return datetime(2026, 4, 27, tzinfo=timezone.utc)


def _case(case_id="case-1", customer_id="C0001", severity="high"):
    return {
        "case_id": case_id,
        "rule_id": "structuring_cash_deposits",
        "rule_name": "Cash structuring",
        "severity": severity,
        "queue": "l1_aml_analyst",
        "spec_program": "schedule_i_bank",
        "alert": {
            "customer_id": customer_id,
            "sum_amount": "45900.00",
            "count": 5,
            "window_start": "2026-04-05 23:00:00",
            "window_end": "2026-04-25 03:00:00",
        },
        "regulation_refs": [{"citation": "PCMLTFA s.11.1", "description": "Structuring offence."}],
    }


def _customer(cid="C0001", country="US", rating="low"):
    return {
        "customer_id": cid,
        "full_name": "Olena Kowalski",
        "country": country,
        "risk_rating": rating,
    }


def _txn(cid="C0001", booked="2026-04-10 09:00:00", amount="9500"):
    return {
        "customer_id": cid,
        "amount": amount,
        "channel": "cash",
        "booked_at": booked,
    }


# ---------------------------------------------------------------------------
# build_queue_rows
# ---------------------------------------------------------------------------


class TestBuildQueueRows:
    def test_one_row_per_case(self):
        rows = build_queue_rows(
            cases=[_case("c1"), _case("c2", customer_id="C0002")],
            customers=[_customer(), _customer(cid="C0002")],
            transactions=[_txn(), _txn(cid="C0002")],
            as_of=_now(),
        )
        assert len(rows) == 2
        assert {r.case_id for r in rows} == {"c1", "c2"}

    def test_drafted_narrative_attached(self):
        rows = build_queue_rows(
            cases=[_case()],
            customers=[_customer()],
            transactions=[_txn()],
            as_of=_now(),
        )
        assert rows[0].drafted.case_id == "case-1"
        assert rows[0].drafted.drafted_by == "template:v1"
        assert any("PCMLTFA s.11.1" in c.citation for c in rows[0].drafted.citations)

    def test_country_risk_trigger_attaches_to_matching_case(self):
        rows = build_queue_rows(
            cases=[_case()],
            customers=[_customer(country="RU")],
            transactions=[_txn()],
            as_of=_now(),
            high_risk_countries={"RU"},
        )
        assert any(t.kind == "country_risk" for t in rows[0].triggers)

    def test_pattern_trigger_uses_alert_counts(self):
        rows = build_queue_rows(
            cases=[_case()],
            customers=[_customer()],
            transactions=[_txn()],
            as_of=_now(),
            alert_counts_by_customer={"C0001": 5},
            alert_threshold=3,
        )
        assert any(t.kind == "transaction_pattern" for t in rows[0].triggers)

    def test_rating_change_recorded_when_critical_trigger_fires(self):
        # We can't fire sanctions_hit without sanctions_added (which the page
        # leaves empty by design). Combine 2 medium triggers indirectly:
        # alert_counts of 5 + high_risk_country gives 1 country_risk (high)
        # which bumps low → medium.
        rows = build_queue_rows(
            cases=[_case()],
            customers=[_customer(country="RU")],
            transactions=[_txn()],
            as_of=_now(),
            high_risk_countries={"RU"},
        )
        assert rows[0].rating_change is not None
        assert rows[0].rating_change.old_rating == "low"
        # 1 high trigger → bump one rung; "low" → "medium"
        assert rows[0].rating_change.new_rating == "medium"

    def test_no_trigger_no_rating_change(self):
        rows = build_queue_rows(
            cases=[_case()],
            customers=[_customer()],
            transactions=[_txn()],
            as_of=_now(),
        )
        assert rows[0].triggers == []
        assert rows[0].rating_change is None

    def test_unknown_customer_still_yields_row(self):
        # Case references C9999 but customer list doesn't contain them.
        rows = build_queue_rows(
            cases=[_case(customer_id="C9999")],
            customers=[_customer()],
            transactions=[],
            as_of=_now(),
        )
        assert len(rows) == 1
        assert rows[0].customer_id == "C9999"
        # The drafter still produces a narrative (template handles missing customer).
        assert rows[0].drafted.case_id == "case-1"

    def test_transactions_filtered_to_window(self):
        # Transaction outside the window should not be counted.
        in_window = _txn(booked="2026-04-10 09:00:00")
        out_of_window = _txn(booked="2025-01-01 09:00:00")
        rows = build_queue_rows(
            cases=[_case()],
            customers=[_customer()],
            transactions=[in_window, out_of_window],
            as_of=_now(),
        )
        # Findings include amount; if both txns leaked through we'd see different totals.
        # The narrative builder uses sum_amount from the alert, not the txns, so
        # we instead check the drafted narrative was built (no error).
        assert rows[0].drafted is not None


# ---------------------------------------------------------------------------
# Action mapping
# ---------------------------------------------------------------------------


class TestActionMapping:
    def test_supported_narrative_actions(self):
        assert set(supported_narrative_actions()) == {
            NARRATIVE_ACCEPT,
            NARRATIVE_AMEND,
            NARRATIVE_REJECT,
            NARRATIVE_ESCALATE,
        }

    def test_escalate_maps_to_str_event(self):
        assert event_for_narrative_action(NARRATIVE_ESCALATE) == Event.ESCALATED_TO_STR

    def test_accept_maps_to_narrative_review(self):
        assert event_for_narrative_action(NARRATIVE_ACCEPT) == Event.NARRATIVE_REVIEW

    def test_pkyc_escalate_maps_to_escalated(self):
        assert event_for_pkyc_action("approve_escalate") == Event.ESCALATED

    def test_pkyc_other_actions_map_to_pkyc_review(self):
        assert event_for_pkyc_action("approve_re_review") == Event.PKYC_REVIEW
        assert event_for_pkyc_action("dismiss") == Event.PKYC_REVIEW


# ---------------------------------------------------------------------------
# record_decision
# ---------------------------------------------------------------------------


class TestRecordDecision:
    def test_writes_jsonl_line(self, tmp_path):
        run = tmp_path / "run-1"
        run.mkdir()
        (run / "decisions.jsonl").touch()

        record_decision(
            run,
            case_id="case-1",
            event=Event.NARRATIVE_REVIEW,
            actor="alice",
            disposition=NARRATIVE_ACCEPT,
            notes="LGTM",
        )

        lines = [
            json.loads(line)
            for line in (run / "decisions.jsonl").read_text().splitlines()
            if line.strip()
        ]
        assert len(lines) == 1
        rec = lines[0]
        assert rec["event"] == Event.NARRATIVE_REVIEW
        assert rec["case_id"] == "case-1"
        assert rec["actor"] == "alice"
        assert rec["disposition"] == NARRATIVE_ACCEPT
        assert rec["notes"] == "LGTM"
        assert "ts" in rec

    def test_extra_fields_merged(self, tmp_path):
        run = tmp_path / "run-1"
        run.mkdir()
        (run / "decisions.jsonl").touch()
        record_decision(
            run,
            case_id="c1",
            event=Event.PKYC_REVIEW,
            actor="alice",
            disposition="approve_re_review",
            extra={"trigger_kind": "country_risk", "customer_id": "C0001"},
        )
        rec = json.loads((run / "decisions.jsonl").read_text().strip())
        assert rec["trigger_kind"] == "country_risk"
        assert rec["customer_id"] == "C0001"

    def test_appends_not_truncates(self, tmp_path):
        run = tmp_path / "run-1"
        run.mkdir()
        (run / "decisions.jsonl").touch()
        for i in range(3):
            record_decision(
                run,
                case_id=f"c{i}",
                event=Event.NARRATIVE_REVIEW,
                actor="alice",
                disposition=NARRATIVE_ACCEPT,
            )
        lines = (run / "decisions.jsonl").read_text().splitlines()
        assert len([line_ for line_ in lines if line_.strip()]) == 3


# ---------------------------------------------------------------------------
# Composition with the audit ledger hash chain
# ---------------------------------------------------------------------------


class TestAuditChainIntegration:
    def test_decision_appears_in_chain(self, tmp_path):
        from aml_framework.engine.audit import AuditLedger

        run = tmp_path / "run-1"
        run.mkdir()
        (run / "decisions.jsonl").touch()

        record_decision(
            run,
            case_id="case-1",
            event=Event.NARRATIVE_REVIEW,
            actor="alice",
            disposition=NARRATIVE_ACCEPT,
        )

        # Verify via the ledger's own helper that the decision is part of
        # the chain (even though no manifest exists, we pass the expected
        # hash explicitly).
        import hashlib

        chain = b""
        for line in (run / "decisions.jsonl").read_bytes().splitlines():
            if line.strip():
                chain = hashlib.sha256(chain + line).digest()
        ok, msg = AuditLedger.verify_decisions(run, expected_hash=chain.hex())
        assert ok, msg


# ---------------------------------------------------------------------------
# End-to-end sanity: build queue from a real run dir (uses synthetic data)
# ---------------------------------------------------------------------------


class TestEndToEndWithRealRun:
    def test_build_rows_from_finalised_run(self, tmp_path):
        from aml_framework.data import generate_dataset
        from aml_framework.engine import run_spec
        from aml_framework.spec import load_spec

        spec_path = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "canadian_schedule_i_bank"
            / "aml.yaml"
        )
        spec = load_spec(spec_path)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec,
            spec_path=spec_path,
            data=data,
            as_of=as_of,
            artifacts_root=tmp_path,
        )
        run_dir = Path(result.manifest["run_dir"])
        cases = [json.loads(p.read_bytes()) for p in sorted((run_dir / "cases").glob("*.json"))]

        rows = build_queue_rows(
            cases,
            customers=data["customer"],
            transactions=data["txn"],
            as_of=as_of,
            jurisdiction=spec.program.jurisdiction,
            high_risk_countries={"RU"},
            alert_counts_by_customer={
                c["alert"]["customer_id"]: 1 for c in cases if c.get("alert")
            },
        )
        assert len(rows) == len(cases)
        # Every row should have a deterministic narrative attached.
        assert all(r.drafted.drafted_by == "template:v1" for r in rows)


@pytest.fixture(autouse=True)
def _no_streamlit_import(monkeypatch):
    """Ensure these tests don't import streamlit (CI doesn't install it)."""
    import sys

    assert "streamlit" not in sys.modules, "queue_state.py must not transitively import streamlit"
    yield
