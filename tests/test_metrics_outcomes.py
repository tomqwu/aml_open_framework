"""Outcome-funnel tests — Round-7 PR #2.

Pure-function tests over case + decision dicts. No engine needed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from aml_framework.metrics.outcomes import (
    AMLA_RTS_VERSION,
    compute_outcomes,
    format_amla_rts_json,
    funnel_ratios,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _case(case_id: str, rule_id: str, customer_id: str = "C001") -> dict[str, Any]:
    return {
        "case_id": case_id,
        "rule_id": rule_id,
        "rule_name": rule_id.replace("_", " ").title(),
        "severity": "high",
        "queue": "l1_analyst",
        "alert": {"customer_id": customer_id, "sum_amount": 10000},
        "evidence_requested": [],
        "spec_program": "test_program",
        "input_hash": {},
        "status": "open",
    }


def _decision(case_id: str, event: str, **extras: Any) -> dict[str, Any]:
    d = {"case_id": case_id, "event": event}
    d.update(extras)
    return d


# ---------------------------------------------------------------------------
# compute_outcomes — happy paths
# ---------------------------------------------------------------------------


class TestComputeOutcomes:
    def test_empty_inputs_yields_zeros(self):
        report = compute_outcomes(cases=[], decisions=[])
        assert report.total_alerts == 0
        assert report.total_cases == 0
        assert report.alert_to_case_pct == 0
        assert report.case_to_str_pct == 0
        assert not report.rules

    def test_single_case_no_decision_pending(self):
        cases = [_case("c1", "structuring")]
        report = compute_outcomes(cases=cases, decisions=[])
        assert report.total_alerts == 1
        assert report.total_cases == 1
        assert report.total_str_filed == 0
        assert report.rules[0].pending == 1

    def test_str_filed_counted(self):
        cases = [_case("c1", "structuring")]
        decisions = [_decision("c1", "str_filed")]
        report = compute_outcomes(cases=cases, decisions=decisions)
        assert report.total_str_filed == 1
        assert report.rules[0].str_filed == 1
        assert report.alert_to_str_pct == 100.0

    def test_closed_no_action_counted(self):
        cases = [_case("c1", "structuring")]
        decisions = [_decision("c1", "closed_no_action")]
        report = compute_outcomes(cases=cases, decisions=decisions)
        assert report.total_closed_no_action == 1
        assert report.rules[0].closed_no_action == 1

    def test_str_filed_via_disposition_field(self):
        # Some specs only emit disposition strings, not normalized event names.
        cases = [_case("c1", "structuring")]
        decisions = [_decision("c1", "case_decision", disposition="str_filing")]
        report = compute_outcomes(cases=cases, decisions=decisions)
        assert report.total_str_filed == 1

    def test_per_rule_breakdown(self):
        cases = [
            _case("c1", "structuring"),
            _case("c2", "structuring"),
            _case("c3", "rapid_movement"),
        ]
        decisions = [
            _decision("c1", "str_filed"),
            _decision("c3", "closed_no_action"),
        ]
        report = compute_outcomes(cases=cases, decisions=decisions)
        rules_by_id = {r.rule_id: r for r in report.rules}
        assert rules_by_id["structuring"].alerts == 2
        assert rules_by_id["structuring"].str_filed == 1
        assert rules_by_id["structuring"].pending == 1
        assert rules_by_id["rapid_movement"].alerts == 1
        assert rules_by_id["rapid_movement"].closed_no_action == 1

    def test_funnel_ratios(self):
        cases = [_case(f"c{i}", "structuring") for i in range(10)]
        decisions = [
            _decision("c0", "str_filed"),
            _decision("c1", "str_filed"),
            _decision("c2", "closed_no_action"),
            _decision("c3", "closed_no_action"),
        ]
        report = compute_outcomes(cases=cases, decisions=decisions)
        assert report.alert_to_case_pct == 100.0  # every alert opened a case
        assert report.case_to_str_pct == 20.0  # 2/10 → STR
        assert report.alert_to_str_pct == 20.0
        ratios = funnel_ratios(report)
        assert ratios["alert_to_str_pct"] == 20.0


# ---------------------------------------------------------------------------
# SLA breach handling
# ---------------------------------------------------------------------------


class TestSLABreaches:
    def test_within_sla_false_counts_as_breach(self):
        cases = [_case("c1", "structuring"), _case("c2", "structuring")]
        decisions = [
            _decision("c1", "case_resolved", within_sla=False),
            _decision("c2", "case_resolved", within_sla=True),
        ]
        report = compute_outcomes(cases=cases, decisions=decisions)
        assert report.rules[0].sla_breaches == 1
        assert report.rules[0].sla_breach_rate_pct == 50.0
        assert report.sla_breach_rate_pct == 50.0

    def test_no_within_sla_field_no_breach(self):
        cases = [_case("c1", "structuring")]
        decisions = [_decision("c1", "str_filed")]
        report = compute_outcomes(cases=cases, decisions=decisions)
        assert report.rules[0].sla_breaches == 0


# ---------------------------------------------------------------------------
# Precision/recall via labels
# ---------------------------------------------------------------------------


class TestLabelledPrecision:
    def test_no_labels_yields_none(self):
        cases = [_case("c1", "structuring")]
        report = compute_outcomes(cases=cases, decisions=[])
        assert report.rules[0].precision is None
        assert report.rules[0].recall is None
        assert report.rules[0].true_positives is None

    def test_perfect_precision(self):
        cases = [_case("c1", "structuring"), _case("c2", "structuring")]
        labels = {"c1": True, "c2": True}
        report = compute_outcomes(cases=cases, decisions=[], labels=labels)
        assert report.rules[0].precision == 1.0
        assert report.rules[0].true_positives == 2
        assert report.rules[0].false_positives == 0

    def test_half_precision(self):
        cases = [_case(f"c{i}", "structuring") for i in range(4)]
        labels = {"c0": True, "c1": True, "c2": False, "c3": False}
        report = compute_outcomes(cases=cases, decisions=[], labels=labels)
        assert report.rules[0].precision == 0.5
        assert report.rules[0].true_positives == 2
        assert report.rules[0].false_positives == 2

    def test_unlabelled_cases_excluded_from_precision(self):
        cases = [_case(f"c{i}", "structuring") for i in range(4)]
        labels = {"c0": True}  # only 1 of 4 labelled
        report = compute_outcomes(cases=cases, decisions=[], labels=labels)
        # precision = 1/(1+0) = 1.0; the 3 unlabelled don't penalise.
        assert report.rules[0].precision == 1.0


# ---------------------------------------------------------------------------
# AMLA RTS JSON renderer
# ---------------------------------------------------------------------------


class TestAMLARTSRenderer:
    def _sample_report(self) -> dict[str, Any]:
        cases = [_case("c1", "structuring"), _case("c2", "structuring")]
        decisions = [_decision("c1", "str_filed")]
        report = compute_outcomes(
            cases=cases,
            decisions=decisions,
            spec_program="eu_bank_aml",
            as_of=datetime(2026, 4, 27, tzinfo=timezone.utc),
        )
        metadata = {
            "lei": "529900T8BM49AURSDO55",
            "obliged_entity_type": "credit_institution",
            "home_member_state": "DE",
            "reporting_period_start": "2026-01-01",
            "reporting_period_end": "2026-03-31",
        }
        return json.loads(format_amla_rts_json(report, program_metadata=metadata))

    def test_renders_required_top_level_keys(self):
        payload = self._sample_report()
        for key in (
            "rts_version",
            "submission_id",
            "obliged_entity",
            "reporting_period",
            "program",
            "effectiveness",
        ):
            assert key in payload, f"missing top-level key {key!r}"

    def test_rts_version_pinned(self):
        payload = self._sample_report()
        assert payload["rts_version"] == AMLA_RTS_VERSION

    def test_submission_id_format(self):
        payload = self._sample_report()
        sid = payload["submission_id"]
        assert sid.startswith("AMLA-")
        assert len(sid) == 5 + 16  # "AMLA-" + 16 hex chars

    def test_submission_id_deterministic(self):
        a = self._sample_report()
        b = self._sample_report()
        assert a["submission_id"] == b["submission_id"]

    def test_effectiveness_carries_per_rule(self):
        payload = self._sample_report()
        assert "per_rule" in payload["effectiveness"]
        assert payload["effectiveness"]["per_rule"][0]["rule_id"] == "structuring"

    def test_obliged_entity_metadata_propagated(self):
        payload = self._sample_report()
        assert payload["obliged_entity"]["lei"] == "529900T8BM49AURSDO55"
        assert payload["obliged_entity"]["home_member_state"] == "DE"

    def test_byte_output_deterministic(self):
        cases = [_case("c1", "structuring")]
        decisions = [_decision("c1", "str_filed")]
        report = compute_outcomes(
            cases=cases,
            decisions=decisions,
            spec_program="x",
            as_of=datetime(2026, 4, 27, tzinfo=timezone.utc),
        )
        meta = {"lei": "X", "reporting_period_start": "2026-01-01"}
        a = format_amla_rts_json(report, program_metadata=meta)
        b = format_amla_rts_json(report, program_metadata=meta)
        assert a == b


# ---------------------------------------------------------------------------
# End-to-end with engine output
# ---------------------------------------------------------------------------


class TestEndToEndWithEngine:
    def test_runs_against_real_engine_output(self, tmp_path):
        from aml_framework.data import generate_dataset
        from aml_framework.engine import run_spec
        from aml_framework.spec import load_spec
        from pathlib import Path

        spec_path = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "canadian_schedule_i_bank"
            / "aml.yaml"
        )
        spec = load_spec(spec_path)
        as_of = datetime(2026, 4, 23)
        result = run_spec(
            spec=spec,
            spec_path=spec_path,
            data=generate_dataset(as_of=as_of, seed=42),
            as_of=as_of,
            artifacts_root=tmp_path,
        )
        # Load the cases + decisions from the run dir.
        cases_dirs = list(tmp_path.glob("**/cases"))
        cases = [json.loads(f.read_text()) for f in sorted(cases_dirs[0].glob("*.json"))]
        decisions_path = next(tmp_path.glob("**/decisions.jsonl"))
        decisions = [json.loads(line) for line in decisions_path.read_text().splitlines() if line]

        report = compute_outcomes(
            cases=cases,
            decisions=decisions,
            spec_program=spec.program.name,
        )
        # Sanity: at least one rule fired, ratios are within bounds.
        assert report.total_alerts == len(result.case_ids)
        assert 0.0 <= report.alert_to_case_pct <= 100.0
        assert 0.0 <= report.case_to_str_pct <= 100.0
        # AMLA JSON renders without error.
        payload = format_amla_rts_json(
            report,
            program_metadata={
                "lei": "529900T8BM49AURSDO55",
                "obliged_entity_type": "credit_institution",
                "home_member_state": "CA",
                "reporting_period_start": "2026-01-01",
                "reporting_period_end": "2026-03-31",
            },
        )
        assert b"AMLA-" in payload
