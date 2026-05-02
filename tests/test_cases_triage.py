"""Composite triage ranking tests — PR-PROC-2.

Backs PROC-1 in the process-and-ingestion research doc: operators staring
at a wall of overnight alerts need to know which case to open first. The
triage_score / rank_queue surface in `aml_framework.cases.triage` answers
that question deterministically — these tests guard the weighting,
the SLA bucket boundaries, the tiebreaker, and end-to-end ordering
against an engine-shaped case list.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from aml_framework.cases.triage import (
    RankedCase,
    rank_queue,
    triage_score,
)
from aml_framework.spec import load_spec
from aml_framework.spec.models import AMLSpec

SPEC_CA = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


@pytest.fixture(scope="module")
def spec() -> AMLSpec:
    return load_spec(SPEC_CA)


def _case(
    *,
    case_id: str,
    queue: str = "l1_aml_analyst",
    severity: str = "medium",
    customer_id: str = "C0001",
    rule_id: str = "test_rule",
    opened_at: datetime | None = None,
) -> dict[str, Any]:
    alert: dict[str, Any] = {"customer_id": customer_id}
    if opened_at is not None:
        alert["window_end"] = opened_at
    return {
        "case_id": case_id,
        "rule_id": rule_id,
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
# triage_score weighting
# ---------------------------------------------------------------------------


class TestTriageScore:
    def test_max_inputs_yield_100(self) -> None:
        # Breached SLA + critical severity + critical customer + perfect precision
        # → all four weighted components hit 100, total 100.
        score = triage_score(
            severity="critical",
            sla_state="breached",
            sla_pct_remaining=0.0,
            customer_risk="critical",
            rule_precision=1.0,
        )
        assert score == pytest.approx(100.0)

    def test_min_inputs_floor_at_25(self) -> None:
        # Low/green/low/0-precision → 25*0.4 + 25*0.3 + 25*0.2 + 0*0.1 = 22.5.
        score = triage_score(
            severity="low",
            sla_state="green",
            sla_pct_remaining=100.0,
            customer_risk="low",
            rule_precision=0.0,
        )
        assert score == pytest.approx(22.5)

    def test_default_precision_is_50pct(self) -> None:
        # rule_precision defaults to 0.5 → contributes 5 points (10% * 50).
        baseline = triage_score(
            severity="medium",
            sla_state="amber",
            sla_pct_remaining=40.0,
            customer_risk="medium",
        )
        explicit = triage_score(
            severity="medium",
            sla_state="amber",
            sla_pct_remaining=40.0,
            customer_risk="medium",
            rule_precision=0.5,
        )
        assert baseline == explicit

    def test_unknown_severity_treated_as_low(self) -> None:
        unknown = triage_score(
            severity="bogus",
            sla_state="green",
            sla_pct_remaining=100.0,
            customer_risk="low",
        )
        low = triage_score(
            severity="low",
            sla_state="green",
            sla_pct_remaining=100.0,
            customer_risk="low",
        )
        assert unknown == low

    def test_severity_weighting_is_30pct(self) -> None:
        # Hold everything else constant; bumping severity from low (25) to
        # critical (100) should add (100-25)*0.3 = 22.5 to the score.
        low_sev = triage_score(
            severity="low",
            sla_state="amber",
            sla_pct_remaining=40.0,
            customer_risk="medium",
        )
        crit_sev = triage_score(
            severity="critical",
            sla_state="amber",
            sla_pct_remaining=40.0,
            customer_risk="medium",
        )
        assert crit_sev - low_sev == pytest.approx(22.5)

    def test_sla_dominates_severity(self) -> None:
        # A breached low-severity case beats a green critical-severity case
        # because SLA is the heaviest weight (40% vs 30%) and breach is the
        # loudest regulator-language signal — FCA Mar 2026 framing.
        breached_low = triage_score(
            severity="low",
            sla_state="breached",
            sla_pct_remaining=0.0,
            customer_risk="low",
        )
        green_critical = triage_score(
            severity="critical",
            sla_state="green",
            sla_pct_remaining=100.0,
            customer_risk="low",
        )
        assert breached_low > green_critical

    def test_precision_clamped_to_unit_interval(self) -> None:
        # Out-of-range precision values get clamped, not crashed.
        assert triage_score(
            severity="low",
            sla_state="green",
            sla_pct_remaining=100.0,
            customer_risk="low",
            rule_precision=2.0,
        ) == triage_score(
            severity="low",
            sla_state="green",
            sla_pct_remaining=100.0,
            customer_risk="low",
            rule_precision=1.0,
        )
        assert triage_score(
            severity="low",
            sla_state="green",
            sla_pct_remaining=100.0,
            customer_risk="low",
            rule_precision=-1.0,
        ) == triage_score(
            severity="low",
            sla_state="green",
            sla_pct_remaining=100.0,
            customer_risk="low",
            rule_precision=0.0,
        )


# ---------------------------------------------------------------------------
# SLA bucket boundaries (via rank_queue, since _sla_score is private)
# ---------------------------------------------------------------------------


class TestSLABuckets:
    def test_breached_outranks_red(self, spec: AMLSpec) -> None:
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [
            _case(
                case_id="breached",
                opened_at=as_of - timedelta(hours=30),
            ),  # past 24h SLA
            _case(
                case_id="red",
                opened_at=as_of - timedelta(hours=23),
            ),  # ~4% remaining
        ]
        ranked = rank_queue(cases, spec, customers=[], as_of=as_of)
        assert ranked[0].case_id == "breached"
        assert ranked[0].sla_state == "breached"
        assert ranked[1].sla_state == "red"

    def test_red_outranks_amber(self, spec: AMLSpec) -> None:
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [
            _case(case_id="amber", opened_at=as_of - timedelta(hours=18)),  # 25% left
            _case(case_id="red", opened_at=as_of - timedelta(hours=23)),  # 4% left
        ]
        ranked = rank_queue(cases, spec, customers=[], as_of=as_of)
        assert ranked[0].case_id == "red"

    def test_amber_outranks_green(self, spec: AMLSpec) -> None:
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [
            _case(case_id="green", opened_at=as_of - timedelta(hours=1)),
            _case(case_id="amber", opened_at=as_of - timedelta(hours=18)),
        ]
        ranked = rank_queue(cases, spec, customers=[], as_of=as_of)
        assert ranked[0].case_id == "amber"

    def test_unknown_sla_treated_as_medium(self, spec: AMLSpec) -> None:
        # A case with no opened_at gets sla_state='unknown' (not silently
        # zero) so operators see the data-quality issue rather than
        # losing the case off the bottom of the queue.
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [_case(case_id="orphan", opened_at=None)]
        ranked = rank_queue(cases, spec, customers=[], as_of=as_of)
        assert len(ranked) == 1
        assert ranked[0].sla_state == "unknown"


# ---------------------------------------------------------------------------
# rank_queue ordering, tiebreaker, lookups
# ---------------------------------------------------------------------------


class TestRankQueue:
    def test_returns_cases_descending_by_score(self, spec: AMLSpec) -> None:
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [
            _case(case_id="a", severity="low", opened_at=as_of - timedelta(hours=1)),
            _case(case_id="b", severity="critical", opened_at=as_of - timedelta(hours=30)),
            _case(case_id="c", severity="medium", opened_at=as_of - timedelta(hours=18)),
        ]
        ranked = rank_queue(cases, spec, customers=[], as_of=as_of)
        scores = [r.score for r in ranked]
        assert scores == sorted(scores, reverse=True)
        assert ranked[0].case_id == "b"  # critical + breached → highest

    def test_ties_broken_by_case_id_ascending(self, spec: AMLSpec) -> None:
        # Two identical cases differ only by case_id — tiebreaker keeps
        # the ranking deterministic so two analysts running the same
        # command see the same queue.
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [
            _case(case_id="z9", opened_at=as_of - timedelta(hours=1)),
            _case(case_id="a1", opened_at=as_of - timedelta(hours=1)),
            _case(case_id="m5", opened_at=as_of - timedelta(hours=1)),
        ]
        ranked = rank_queue(cases, spec, customers=[], as_of=as_of)
        assert [r.case_id for r in ranked] == ["a1", "m5", "z9"]

    def test_top_n_truncates(self, spec: AMLSpec) -> None:
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [_case(case_id=f"c{i}", opened_at=as_of - timedelta(hours=i)) for i in range(1, 11)]
        ranked = rank_queue(cases, spec, customers=[], as_of=as_of, top_n=3)
        assert len(ranked) == 3

    def test_top_n_zero_returns_empty(self, spec: AMLSpec) -> None:
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [_case(case_id="c1", opened_at=as_of)]
        assert rank_queue(cases, spec, customers=[], as_of=as_of, top_n=0) == []

    def test_top_n_none_returns_all(self, spec: AMLSpec) -> None:
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [_case(case_id=f"c{i}", opened_at=as_of) for i in range(5)]
        ranked = rank_queue(cases, spec, customers=[], as_of=as_of, top_n=None)
        assert len(ranked) == 5

    def test_customer_risk_lookup(self, spec: AMLSpec) -> None:
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        customers = [
            {"customer_id": "C0001", "risk_rating": "high"},
            {"customer_id": "C0002", "risk_rating": "low"},
        ]
        # Two equally-aged, equal-severity cases — the high-risk customer
        # wins on the 20% customer-risk weight.
        cases = [
            _case(
                case_id="low_risk",
                customer_id="C0002",
                opened_at=as_of - timedelta(hours=1),
            ),
            _case(
                case_id="high_risk",
                customer_id="C0001",
                opened_at=as_of - timedelta(hours=1),
            ),
        ]
        ranked = rank_queue(cases, spec, customers=customers, as_of=as_of)
        assert ranked[0].case_id == "high_risk"
        assert ranked[0].customer_risk_rating == "high"
        assert ranked[1].customer_risk_rating == "low"

    def test_missing_customer_defaults_to_low_risk(self, spec: AMLSpec) -> None:
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [_case(case_id="c1", customer_id="GHOST", opened_at=as_of)]
        ranked = rank_queue(cases, spec, customers=[], as_of=as_of)
        assert ranked[0].customer_risk_rating == "low"

    def test_unknown_queue_still_ranked(self, spec: AMLSpec) -> None:
        # A case whose queue id isn't defined in the spec is *not* dropped
        # — it surfaces with sla_state='unknown' so operators see the
        # data-quality issue rather than losing the case silently.
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [_case(case_id="c1", queue="bogus_queue", opened_at=as_of)]
        ranked = rank_queue(cases, spec, customers=[], as_of=as_of)
        assert len(ranked) == 1
        assert ranked[0].sla_state == "unknown"

    def test_empty_input_returns_empty_list(self, spec: AMLSpec) -> None:
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        assert rank_queue([], spec, customers=[], as_of=as_of) == []

    def test_deterministic_across_calls(self, spec: AMLSpec) -> None:
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [_case(case_id=f"c{i}", opened_at=as_of - timedelta(hours=i)) for i in range(5)]
        first = [r.case_id for r in rank_queue(cases, spec, customers=[], as_of=as_of)]
        second = [r.case_id for r in rank_queue(cases, spec, customers=[], as_of=as_of)]
        assert first == second


# ---------------------------------------------------------------------------
# RankedCase.to_dict + justification text
# ---------------------------------------------------------------------------


class TestRankedCaseShape:
    def test_to_dict_round_trips_fields(self) -> None:
        rc = RankedCase(
            case_id="c1",
            score=87.5,
            severity="high",
            queue="l1_analyst",
            sla_state="red",
            pct_remaining=4.2,
            customer_id="C0001",
            customer_risk_rating="high",
            rule_id="r1",
            why="SLA 4% left · high severity",
        )
        d = rc.to_dict()
        assert d["case_id"] == "c1"
        assert d["score"] == 87.5
        assert d["severity"] == "high"
        assert d["why"] == "SLA 4% left · high severity"
        assert len(d) == 10

    def test_justification_mentions_breach(self, spec: AMLSpec) -> None:
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [_case(case_id="c1", opened_at=as_of - timedelta(hours=30))]
        ranked = rank_queue(cases, spec, customers=[], as_of=as_of)
        assert "SLA breached" in ranked[0].why

    def test_justification_mentions_severity_only_when_high(self, spec: AMLSpec) -> None:
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [
            _case(
                case_id="medium",
                severity="medium",
                opened_at=as_of - timedelta(hours=1),
            ),
            _case(
                case_id="critical",
                severity="critical",
                opened_at=as_of - timedelta(hours=1),
            ),
        ]
        ranked = {r.case_id: r for r in rank_queue(cases, spec, customers=[], as_of=as_of)}
        assert "severity" not in ranked["medium"].why
        assert "critical severity" in ranked["critical"].why

    def test_justification_falls_back_to_standard_priority(self, spec: AMLSpec) -> None:
        # Green SLA, low severity, low-risk customer — nothing notable to
        # surface, so the justification reads "standard priority" rather
        # than an empty string.
        as_of = datetime(2026, 4, 27, 12, 0, 0)
        cases = [
            _case(
                case_id="boring",
                severity="low",
                opened_at=as_of - timedelta(minutes=5),
            )
        ]
        ranked = rank_queue(cases, spec, customers=[], as_of=as_of)
        assert ranked[0].why == "standard priority"


# ---------------------------------------------------------------------------
# End-to-end against real engine output — same shape the CLI consumes.
# ---------------------------------------------------------------------------


class TestEndToEndWithEngine:
    def test_ranks_real_engine_run(self, tmp_path: Path) -> None:
        from aml_framework.data import generate_dataset
        from aml_framework.engine import run_spec

        spec = load_spec(SPEC_CA)
        # Engine serialises case timestamps as naive ISO strings — keep
        # as_of naive too so SLA arithmetic works (mirrors test_cases_sla).
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        result = run_spec(
            spec=spec,
            spec_path=SPEC_CA,
            data=generate_dataset(as_of=as_of, seed=42),
            as_of=as_of,
            artifacts_root=tmp_path,
        )
        assert result.case_ids, "engine should emit cases for the CA demo spec"

        import json

        cases_dir = next(tmp_path.glob("**/cases"))
        cases = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(cases_dir.glob("*.json"))
            if not p.name.endswith("__filing.json")
        ]
        customers = generate_dataset(as_of=as_of, seed=42)["customer"]
        # Rank one day after as_of so the SLA classification is exercised
        # against non-zero elapsed time.
        ranked = rank_queue(cases, spec, customers, as_of=as_of + timedelta(days=1), top_n=5)
        assert 1 <= len(ranked) <= 5
        assert all(0 <= r.score <= 100 for r in ranked)
