"""SLA timer + escalation engine tests — Round-6 PR #3.

Verifies real-time SLA classification (green/amber/red/breached),
escalation policy on breach, and queue-level backlog summarisation.
The engine's existing `within_sla` field is *retrospective*; this
module gives the live view FCA's March 2026 Dear CEO letter named as
the supervisory gap.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from aml_framework.cases import (
    BacklogStats,
    EscalationAction,
    apply_escalation,
    compute_sla_status,
    summarise_backlog,
)
from aml_framework.spec import load_spec
from aml_framework.spec.models import Queue


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _queue(qid: str = "l1_analyst", sla: str = "24h", next_: list[str] | None = None) -> Queue:
    if next_ is None:
        next_ = ["l2_investigator", "closed_no_action"]
    return Queue(id=qid, sla=sla, next=next_)


def _case(
    *,
    case_id: str = "c1",
    queue: str = "l1_analyst",
    opened_at: datetime | None = None,
    severity: str = "medium",
) -> dict[str, Any]:
    alert: dict[str, Any] = {}
    if opened_at is not None:
        alert["window_end"] = opened_at
    return {
        "case_id": case_id,
        "rule_id": "test_rule",
        "rule_name": "Test Rule",
        "severity": severity,
        "queue": queue,
        "alert": alert,
        "evidence_requested": [],
        "spec_program": "test",
        "input_hash": {},
        "status": "open",
    }


# ---------------------------------------------------------------------------
# Per-case SLA classification
# ---------------------------------------------------------------------------


class TestComputeSLAStatus:
    def test_just_opened_case_is_green(self):
        opened = datetime(2026, 4, 27, 10, 0, 0)
        as_of = opened + timedelta(hours=1)  # 23h remaining of 24h SLA
        case = _case(opened_at=opened)
        status = compute_sla_status(case, _queue(), as_of=as_of)
        assert status is not None
        assert status["state"] == "green"
        assert status["pct_remaining"] > 95

    def test_halfway_through_sla_is_amber(self):
        opened = datetime(2026, 4, 27, 10, 0, 0)
        as_of = opened + timedelta(hours=18)  # 6h of 24h remaining → 25%
        status = compute_sla_status(_case(opened_at=opened), _queue(), as_of=as_of)
        assert status["state"] == "amber"

    def test_almost_due_is_red(self):
        opened = datetime(2026, 4, 27, 10, 0, 0)
        as_of = opened + timedelta(hours=23)  # 1h of 24h → 4%
        status = compute_sla_status(_case(opened_at=opened), _queue(), as_of=as_of)
        assert status["state"] == "red"

    def test_past_due_is_breached(self):
        opened = datetime(2026, 4, 27, 10, 0, 0)
        as_of = opened + timedelta(hours=30)
        status = compute_sla_status(_case(opened_at=opened), _queue(), as_of=as_of)
        assert status["state"] == "breached"
        assert status["time_remaining_hours"] < 0

    def test_due_at_computed_correctly(self):
        opened = datetime(2026, 4, 27, 10, 0, 0)
        as_of = opened + timedelta(hours=2)
        status = compute_sla_status(_case(opened_at=opened), _queue(sla="24h"), as_of=as_of)
        assert status["due_at"] == opened + timedelta(hours=24)

    def test_queue_sla_hours_reported(self):
        opened = datetime(2026, 4, 27, 10, 0, 0)
        status = compute_sla_status(_case(opened_at=opened), _queue(sla="72h"), as_of=opened)
        assert status["queue_sla_hours"] == 72.0

    def test_no_opened_at_returns_none(self):
        # Case with no window_end / booked_at — silently dropped, not
        # misclassified as breached.
        status = compute_sla_status(_case(opened_at=None), _queue(), as_of=datetime(2026, 4, 27))
        assert status is None

    def test_iso_string_opened_at_parsed(self):
        case = _case(opened_at=None)
        case["alert"]["window_end"] = "2026-04-27T10:00:00"
        status = compute_sla_status(case, _queue(), as_of=datetime(2026, 4, 27, 12, 0, 0))
        assert status is not None
        assert status["time_in_queue_hours"] == pytest.approx(2.0)

    def test_custom_thresholds_override(self):
        # Aggressive ops shop wants amber to start at 80% remaining.
        opened = datetime(2026, 4, 27, 10, 0, 0)
        as_of = opened + timedelta(hours=4)  # 20h of 24h → 83%
        status = compute_sla_status(
            _case(opened_at=opened),
            _queue(),
            as_of=as_of,
            sla_thresholds={"green_above_pct": 90, "amber_above_pct": 50},
        )
        # At 83% remaining: not green (>90), but above amber floor (>50) → amber.
        assert status["state"] == "amber"

    def test_supports_minute_sla(self):
        opened = datetime(2026, 4, 27, 10, 0, 0)
        as_of = opened + timedelta(minutes=10)
        # 30m SLA, 10m elapsed → 67% remaining → green.
        status = compute_sla_status(_case(opened_at=opened), _queue(sla="30m"), as_of=as_of)
        assert status["state"] == "green"


# ---------------------------------------------------------------------------
# Escalation policy
# ---------------------------------------------------------------------------


class TestApplyEscalation:
    def test_breached_case_escalates_to_first_non_closed(self):
        opened = datetime(2026, 4, 27, 10, 0, 0)
        as_of = opened + timedelta(hours=30)
        case = _case(opened_at=opened)
        queue = _queue(next_=["l2_investigator", "closed_no_action"])
        status = compute_sla_status(case, queue, as_of=as_of)
        action = apply_escalation(case, status, queue)
        assert action is not None
        assert action.from_queue == "l1_analyst"
        assert action.to_queue == "l2_investigator"
        assert action.reason == "sla_breach"

    def test_green_case_does_not_escalate(self):
        opened = datetime(2026, 4, 27, 10, 0, 0)
        as_of = opened + timedelta(hours=1)
        case = _case(opened_at=opened)
        queue = _queue()
        status = compute_sla_status(case, queue, as_of=as_of)
        assert apply_escalation(case, status, queue) is None

    def test_amber_case_does_not_escalate(self):
        opened = datetime(2026, 4, 27, 10, 0, 0)
        as_of = opened + timedelta(hours=18)
        case = _case(opened_at=opened)
        queue = _queue()
        status = compute_sla_status(case, queue, as_of=as_of)
        assert apply_escalation(case, status, queue) is None

    def test_red_case_does_not_escalate(self):
        opened = datetime(2026, 4, 27, 10, 0, 0)
        as_of = opened + timedelta(hours=23)
        case = _case(opened_at=opened)
        queue = _queue()
        status = compute_sla_status(case, queue, as_of=as_of)
        # Red is "almost due" — escalation only fires on actual breach.
        assert apply_escalation(case, status, queue) is None

    def test_no_next_queue_returns_none(self):
        opened = datetime(2026, 4, 27, 10, 0, 0)
        as_of = opened + timedelta(hours=30)
        case = _case(opened_at=opened)
        queue = _queue(next_=[])  # terminal queue
        status = compute_sla_status(case, queue, as_of=as_of)
        assert apply_escalation(case, status, queue) is None

    def test_only_closed_next_queues_returns_none(self):
        opened = datetime(2026, 4, 27, 10, 0, 0)
        as_of = opened + timedelta(hours=30)
        case = _case(opened_at=opened)
        queue = _queue(next_=["closed_no_action", "closed_str_filed"])
        status = compute_sla_status(case, queue, as_of=as_of)
        # Nothing to escalate to — both are closure queues.
        assert apply_escalation(case, status, queue) is None

    def test_escalation_action_is_frozen(self):
        action = EscalationAction(case_id="c1", from_queue="a", to_queue="b", reason="sla_breach")
        with pytest.raises(Exception):  # FrozenInstanceError
            action.case_id = "c2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Backlog summarisation
# ---------------------------------------------------------------------------


SPEC_CA = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


class TestSummariseBacklog:
    def test_empty_cases_yields_zero_counts_per_queue(self):
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        stats = summarise_backlog([], spec, as_of=as_of)
        # Every queue defined in the spec gets a row, even with zero cases.
        assert len(stats) == len(spec.workflow.queues)
        for s in stats:
            assert s.total_cases == 0
            assert s.breach_rate_pct == 0.0

    def test_mixed_states_counted_correctly(self):
        # Use the CA spec's actual l1 queue id (l1_aml_analyst).
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [
            _case(case_id="g1", queue="l1_aml_analyst", opened_at=as_of - timedelta(hours=1)),
            _case(case_id="a1", queue="l1_aml_analyst", opened_at=as_of - timedelta(hours=18)),
            _case(case_id="r1", queue="l1_aml_analyst", opened_at=as_of - timedelta(hours=23)),
            _case(case_id="b1", queue="l1_aml_analyst", opened_at=as_of - timedelta(hours=30)),
            _case(case_id="b2", queue="l1_aml_analyst", opened_at=as_of - timedelta(hours=48)),
        ]
        stats = summarise_backlog(cases, spec, as_of=as_of)
        l1_stats = next(s for s in stats if s.queue_id == "l1_aml_analyst")
        assert l1_stats.total_cases == 5
        assert l1_stats.green == 1
        assert l1_stats.amber == 1
        assert l1_stats.red == 1
        assert l1_stats.breached == 2
        assert l1_stats.breach_rate_pct == pytest.approx(40.0)

    def test_oldest_age_reflects_oldest_case(self):
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [
            _case(case_id="c1", queue="l1_aml_analyst", opened_at=as_of - timedelta(hours=5)),
            _case(case_id="c2", queue="l1_aml_analyst", opened_at=as_of - timedelta(hours=72)),
            _case(case_id="c3", queue="l1_aml_analyst", opened_at=as_of - timedelta(hours=12)),
        ]
        stats = summarise_backlog(cases, spec, as_of=as_of)
        l1_stats = next(s for s in stats if s.queue_id == "l1_aml_analyst")
        assert l1_stats.oldest_age_hours == pytest.approx(72.0)

    def test_unknown_queue_dropped(self):
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [
            _case(case_id="c1", queue="bogus_queue", opened_at=as_of),
        ]
        stats = summarise_backlog(cases, spec, as_of=as_of)
        # The bogus case is dropped; every defined queue still gets a row.
        for s in stats:
            assert s.total_cases == 0

    def test_case_without_opened_at_dropped(self):
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [
            _case(case_id="c1", queue="l1_aml_analyst", opened_at=None),
            _case(case_id="c2", queue="l1_aml_analyst", opened_at=as_of - timedelta(hours=1)),
        ]
        stats = summarise_backlog(cases, spec, as_of=as_of)
        l1_stats = next(s for s in stats if s.queue_id == "l1_aml_analyst")
        # Only the case with a resolvable opened_at counts.
        assert l1_stats.total_cases == 1

    def test_output_sorted_by_queue_id(self):
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        stats = summarise_backlog([], spec, as_of=as_of)
        ids = [s.queue_id for s in stats]
        assert ids == sorted(ids)

    def test_backlog_stats_to_dict(self):
        bs = BacklogStats(
            queue_id="l1_analyst",
            queue_sla_hours=24.0,
            total_cases=10,
            green=4,
            amber=3,
            red=2,
            breached=1,
            oldest_age_hours=20.0,
            breach_rate_pct=10.0,
        )
        d = bs.to_dict()
        assert d["queue_id"] == "l1_analyst"
        assert d["breach_rate_pct"] == 10.0
        # All 9 keys present.
        assert len(d) == 9


# ---------------------------------------------------------------------------
# End-to-end with engine output
# ---------------------------------------------------------------------------


class TestEndToEndWithEngine:
    def test_summarises_real_engine_run(self, tmp_path):
        import json

        from aml_framework.data import generate_dataset
        from aml_framework.engine import run_spec

        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        result = run_spec(
            spec=spec,
            spec_path=SPEC_CA,
            data=generate_dataset(as_of=as_of, seed=42),
            as_of=as_of,
            artifacts_root=tmp_path,
        )
        cases_dirs = list(tmp_path.glob("**/cases"))
        cases = [json.loads(f.read_text()) for f in sorted(cases_dirs[0].glob("*.json"))]
        # Backlog summary at as_of+0 — every case is green (zero elapsed).
        # Compute one day later instead so we exercise classification
        # against real engine-generated case timestamps.
        stats = summarise_backlog(cases, spec, as_of=as_of + timedelta(days=1))
        total_in_summary = sum(s.total_cases for s in stats)
        # All emitted cases should be reflected in the summary (no losses
        # to the unknown-queue / no-opened-at filter on the synthetic data).
        assert total_in_summary == len(result.case_ids)
        # All queues defined in the CA spec appear, even if empty.
        defined_queues = {q.id for q in spec.workflow.queues}
        summarised_queues = {s.queue_id for s in stats}
        assert defined_queues == summarised_queues
