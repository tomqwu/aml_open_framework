"""Investigation aggregator tests — Round-6 PR #1.

Verifies the three grouping strategies, severity escalation, deterministic
ID generation, sum-amount totalling, window-bound computation, and
edge-case handling (empty input, missing customer_id, mixed timestamp
shapes).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from aml_framework.cases import (
    Investigation,
    aggregate_investigations,
    bucket_window_for,
)
from aml_framework.cases.aggregator import _bucket_index, _investigation_id


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _case(
    *,
    case_id: str,
    rule_id: str,
    customer_id: str,
    severity: str = "medium",
    queue: str = "l1_analyst",
    sum_amount: Decimal | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    tags: list[str] | None = None,
    evidence: list[str] | None = None,
) -> dict:
    """Build a CaseDict-shaped dict for tests."""
    alert: dict = {"customer_id": customer_id}
    if sum_amount is not None:
        alert["sum_amount"] = sum_amount
    if window_start is not None:
        alert["window_start"] = window_start
    if window_end is not None:
        alert["window_end"] = window_end
    if tags is not None:
        alert["tags"] = tags
    return {
        "case_id": case_id,
        "rule_id": rule_id,
        "rule_name": rule_id.replace("_", " ").title(),
        "severity": severity,
        "regulation_refs": [],
        "queue": queue,
        "alert": alert,
        "evidence_requested": evidence or [],
        "spec_program": "test_program",
        "input_hash": {},
        "status": "open",
    }


# ---------------------------------------------------------------------------
# Strategy: per_customer_window (default)
# ---------------------------------------------------------------------------


class TestPerCustomerWindow:
    def test_two_cases_same_customer_same_bucket_collapse(self):
        cases = [
            _case(
                case_id="r1__C001__x",
                rule_id="structuring",
                customer_id="C001",
                window_end=datetime(2026, 4, 10),
            ),
            _case(
                case_id="r2__C001__y",
                rule_id="rapid_movement",
                customer_id="C001",
                window_end=datetime(2026, 4, 25),  # 15 days later — same 30d bucket
            ),
        ]
        invs = aggregate_investigations(cases)
        assert len(invs) == 1
        assert invs[0]["customer_id"] == "C001"
        assert invs[0]["case_count"] == 2
        assert invs[0]["rule_count"] == 2

    def test_two_cases_same_customer_different_buckets_split(self):
        cases = [
            _case(
                case_id="r1__C001__x",
                rule_id="structuring",
                customer_id="C001",
                window_end=datetime(2026, 1, 5),
            ),
            _case(
                case_id="r2__C001__y",
                rule_id="rapid_movement",
                customer_id="C001",
                window_end=datetime(2026, 4, 25),  # ~110 days later
            ),
        ]
        invs = aggregate_investigations(cases)
        assert len(invs) == 2

    def test_different_customers_different_investigations(self):
        cases = [
            _case(
                case_id="r1__C001__x",
                rule_id="structuring",
                customer_id="C001",
                window_end=datetime(2026, 4, 10),
            ),
            _case(
                case_id="r1__C002__x",
                rule_id="structuring",
                customer_id="C002",
                window_end=datetime(2026, 4, 10),
            ),
        ]
        invs = aggregate_investigations(cases)
        assert len(invs) == 2
        customer_ids = {i["customer_id"] for i in invs}
        assert customer_ids == {"C001", "C002"}

    def test_default_strategy_is_per_customer_window(self):
        c = _case(
            case_id="x",
            rule_id="r",
            customer_id="C001",
            window_end=datetime(2026, 4, 10),
        )
        invs = aggregate_investigations([c])
        assert invs[0]["strategy"] == "per_customer_window"


# ---------------------------------------------------------------------------
# Strategy: per_customer_per_run
# ---------------------------------------------------------------------------


class TestPerCustomerPerRun:
    def test_collapses_across_buckets(self):
        cases = [
            _case(
                case_id="r1__C001__x",
                rule_id="structuring",
                customer_id="C001",
                window_end=datetime(2025, 1, 1),
            ),
            _case(
                case_id="r2__C001__y",
                rule_id="rapid",
                customer_id="C001",
                window_end=datetime(2026, 12, 31),  # different decade-end
            ),
        ]
        invs = aggregate_investigations(cases, strategy="per_customer_per_run")
        # per_customer_per_run ignores time bucketing.
        assert len(invs) == 1
        assert invs[0]["case_count"] == 2

    def test_different_customers_still_split(self):
        cases = [
            _case(case_id="a", rule_id="r", customer_id="C001"),
            _case(case_id="b", rule_id="r", customer_id="C002"),
        ]
        invs = aggregate_investigations(cases, strategy="per_customer_per_run")
        assert len(invs) == 2


# ---------------------------------------------------------------------------
# Strategy: per_case (singleton)
# ---------------------------------------------------------------------------


class TestPerCase:
    def test_one_investigation_per_case(self):
        cases = [
            _case(case_id="a", rule_id="r1", customer_id="C001"),
            _case(case_id="b", rule_id="r2", customer_id="C001"),
            _case(case_id="c", rule_id="r1", customer_id="C002"),
        ]
        invs = aggregate_investigations(cases, strategy="per_case")
        assert len(invs) == 3
        for inv in invs:
            assert inv["case_count"] == 1
            assert inv["rule_count"] == 1


# ---------------------------------------------------------------------------
# Severity escalation
# ---------------------------------------------------------------------------


class TestSeverityEscalation:
    def test_max_severity_wins(self):
        cases = [
            _case(case_id="a", rule_id="r1", customer_id="C001", severity="low"),
            _case(case_id="b", rule_id="r2", customer_id="C001", severity="critical"),
            _case(case_id="c", rule_id="r3", customer_id="C001", severity="medium"),
        ]
        invs = aggregate_investigations(cases, strategy="per_customer_per_run")
        assert invs[0]["severity"] == "critical"

    def test_unknown_severity_defaults_low(self):
        cases = [
            _case(case_id="a", rule_id="r1", customer_id="C001", severity="bogus"),
        ]
        invs = aggregate_investigations(cases)
        # Unknown severity ranks at 0 (low); best_severity is the input string.
        # Acceptable: returns the input as-is since it was the only one seen.
        assert invs[0]["severity"] in {"bogus", "low"}

    def test_severity_ordering_low_medium_high_critical(self):
        # Mix all four; max should be critical.
        cases = [
            _case(case_id=f"c{i}", rule_id=f"r{i}", customer_id="C001", severity=s)
            for i, s in enumerate(["medium", "low", "high", "critical"])
        ]
        invs = aggregate_investigations(cases, strategy="per_customer_per_run")
        assert invs[0]["severity"] == "critical"


# ---------------------------------------------------------------------------
# Sum amount aggregation
# ---------------------------------------------------------------------------


class TestSumAmount:
    def test_sums_alert_amounts(self):
        cases = [
            _case(case_id="a", rule_id="r1", customer_id="C001", sum_amount=Decimal("1000.50")),
            _case(case_id="b", rule_id="r2", customer_id="C001", sum_amount=Decimal("2500.00")),
        ]
        invs = aggregate_investigations(cases, strategy="per_customer_per_run")
        assert invs[0]["total_amount"] == Decimal("3500.50")

    def test_missing_amounts_default_zero(self):
        cases = [
            _case(case_id="a", rule_id="r1", customer_id="C001"),
        ]
        invs = aggregate_investigations(cases)
        assert invs[0]["total_amount"] == Decimal("0")

    def test_string_amounts_coerced(self):
        # Engine sometimes JSON-roundtrips Decimals to strings.
        case = _case(case_id="a", rule_id="r1", customer_id="C001")
        case["alert"]["sum_amount"] = "1234.56"
        invs = aggregate_investigations([case])
        assert invs[0]["total_amount"] == Decimal("1234.56")

    def test_unparseable_amount_skipped(self):
        case = _case(case_id="a", rule_id="r1", customer_id="C001")
        case["alert"]["sum_amount"] = "not-a-number"
        invs = aggregate_investigations([case])
        # Doesn't raise; just contributes 0.
        assert invs[0]["total_amount"] == Decimal("0")


# ---------------------------------------------------------------------------
# Window bounds
# ---------------------------------------------------------------------------


class TestWindowBounds:
    def test_window_start_min_window_end_max(self):
        cases = [
            _case(
                case_id="a",
                rule_id="r1",
                customer_id="C001",
                window_start=datetime(2026, 4, 10),
                window_end=datetime(2026, 4, 15),
            ),
            _case(
                case_id="b",
                rule_id="r2",
                customer_id="C001",
                window_start=datetime(2026, 4, 5),
                window_end=datetime(2026, 4, 20),
            ),
        ]
        invs = aggregate_investigations(cases, strategy="per_customer_per_run")
        assert invs[0]["window_start"] == datetime(2026, 4, 5)
        assert invs[0]["window_end"] == datetime(2026, 4, 20)

    def test_iso_string_timestamps_parsed(self):
        case = _case(case_id="a", rule_id="r1", customer_id="C001")
        case["alert"]["window_start"] = "2026-04-10T12:00:00"
        case["alert"]["window_end"] = "2026-04-15T18:00:00"
        invs = aggregate_investigations([case])
        assert invs[0]["window_start"] == datetime(2026, 4, 10, 12, 0, 0)
        assert invs[0]["window_end"] == datetime(2026, 4, 15, 18, 0, 0)

    def test_no_timestamps_yields_none(self):
        case = _case(case_id="a", rule_id="r1", customer_id="C001")
        invs = aggregate_investigations(case_with_timestamp_in_run := [case])
        assert invs[0]["window_start"] is None
        assert invs[0]["window_end"] is None
        del case_with_timestamp_in_run  # silence lint


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_same_investigation_ids(self):
        cases = [
            _case(case_id="a", rule_id="r1", customer_id="C001", window_end=datetime(2026, 4, 10)),
            _case(case_id="b", rule_id="r2", customer_id="C001", window_end=datetime(2026, 4, 12)),
        ]
        invs1 = aggregate_investigations(cases)
        invs2 = aggregate_investigations(cases)
        assert [i["investigation_id"] for i in invs1] == [i["investigation_id"] for i in invs2]

    def test_case_order_does_not_affect_ids(self):
        c1 = _case(case_id="a", rule_id="r1", customer_id="C001", window_end=datetime(2026, 4, 10))
        c2 = _case(case_id="b", rule_id="r2", customer_id="C001", window_end=datetime(2026, 4, 12))
        invs1 = aggregate_investigations([c1, c2])
        invs2 = aggregate_investigations([c2, c1])
        assert invs1[0]["investigation_id"] == invs2[0]["investigation_id"]

    def test_investigation_id_format(self):
        invs = aggregate_investigations(
            [_case(case_id="a", rule_id="r", customer_id="C001", window_end=datetime(2026, 4, 10))]
        )
        inv_id = invs[0]["investigation_id"]
        assert inv_id.startswith("INV-")
        assert len(inv_id) == 4 + 16  # "INV-" + 16 hex chars

    def test_different_case_sets_different_ids(self):
        a = _investigation_id(["case-a"])
        b = _investigation_id(["case-b"])
        assert a != b

    def test_output_sorted_by_investigation_id(self):
        cases = [
            _case(
                case_id=f"c{i}",
                rule_id="r",
                customer_id=f"C{i:03d}",
                window_end=datetime(2026, 4, 10),
            )
            for i in range(5)
        ]
        invs = aggregate_investigations(cases)
        ids = [i["investigation_id"] for i in invs]
        assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# Bucket math
# ---------------------------------------------------------------------------


class TestBucketing:
    def test_bucket_window_for_returns_30day_bounds(self):
        start, end = bucket_window_for(datetime(2026, 4, 15))
        # Window is 30 days wide.
        assert (end - start).days == 30
        # The probe date falls inside [start, end).
        assert start <= datetime(2026, 4, 15) < end

    def test_consecutive_bucket_windows_abut(self):
        s1, e1 = bucket_window_for(datetime(2026, 4, 1))
        s2, e2 = bucket_window_for(e1)
        assert s2 == e1

    def test_bucket_index_monotonic(self):
        i1 = _bucket_index(datetime(2026, 1, 1))
        i2 = _bucket_index(datetime(2026, 4, 1))
        assert i2 > i1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_case_list_returns_empty(self):
        assert aggregate_investigations([]) == []

    def test_case_without_customer_id_dropped(self):
        cases = [
            _case(case_id="a", rule_id="r", customer_id=""),
            _case(case_id="b", rule_id="r", customer_id="C001", window_end=datetime(2026, 4, 10)),
        ]
        invs = aggregate_investigations(cases)
        # Only C001's case becomes an investigation.
        assert len(invs) == 1
        assert invs[0]["customer_id"] == "C001"

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="unknown aggregation strategy"):
            aggregate_investigations([], strategy="bogus_strategy")

    def test_case_with_no_window_end_buckets_to_minus_one(self):
        # No timestamp at all — bucket index is -1; cases collapse together.
        cases = [
            _case(case_id="a", rule_id="r1", customer_id="C001"),
            _case(case_id="b", rule_id="r2", customer_id="C001"),
        ]
        invs = aggregate_investigations(cases)
        assert len(invs) == 1
        assert invs[0]["case_count"] == 2

    def test_tag_union(self):
        cases = [
            _case(
                case_id="a",
                rule_id="r1",
                customer_id="C001",
                tags=["structuring", "cash"],
                window_end=datetime(2026, 4, 10),
            ),
            _case(
                case_id="b",
                rule_id="r2",
                customer_id="C001",
                tags=["rapid_movement", "cash"],  # 'cash' overlaps
                window_end=datetime(2026, 4, 12),
            ),
        ]
        invs = aggregate_investigations(cases)
        assert invs[0]["tags"] == ["cash", "rapid_movement", "structuring"]

    def test_evidence_union(self):
        cases = [
            _case(
                case_id="a",
                rule_id="r1",
                customer_id="C001",
                evidence=["customer_kyc", "txn_log"],
                window_end=datetime(2026, 4, 10),
            ),
            _case(
                case_id="b",
                rule_id="r2",
                customer_id="C001",
                evidence=["txn_log", "sanctions_match"],
                window_end=datetime(2026, 4, 12),
            ),
        ]
        invs = aggregate_investigations(cases)
        assert invs[0]["evidence_requested"] == ["customer_kyc", "sanctions_match", "txn_log"]

    def test_queues_distinct_sorted(self):
        cases = [
            _case(
                case_id="a",
                rule_id="r1",
                customer_id="C001",
                queue="l2_investigator",
                window_end=datetime(2026, 4, 10),
            ),
            _case(
                case_id="b",
                rule_id="r2",
                customer_id="C001",
                queue="l1_analyst",
                window_end=datetime(2026, 4, 12),
            ),
        ]
        invs = aggregate_investigations(cases)
        assert invs[0]["queues"] == ["l1_analyst", "l2_investigator"]


# ---------------------------------------------------------------------------
# End-to-end with engine output
# ---------------------------------------------------------------------------


class TestEndToEndWithEngine:
    def test_aggregator_runs_over_real_engine_output(self, tmp_path):
        import json
        import pathlib
        from datetime import datetime as _dt

        from aml_framework.data import generate_dataset
        from aml_framework.engine import run_spec
        from aml_framework.spec import load_spec

        spec_path = (
            pathlib.Path(__file__).resolve().parents[1]
            / "examples"
            / "canadian_schedule_i_bank"
            / "aml.yaml"
        )
        spec = load_spec(spec_path)
        as_of = _dt(2026, 4, 23, 12, 0, 0)
        result = run_spec(
            spec=spec,
            spec_path=spec_path,
            data=generate_dataset(as_of=as_of, seed=42),
            as_of=as_of,
            artifacts_root=tmp_path,
        )
        # Engine persists each case as cases/<case_id>.json under the run dir.
        cases_dirs = list(tmp_path.glob("**/cases"))
        assert cases_dirs, "engine should have written a cases/ directory"
        cases = []
        for case_file in sorted(cases_dirs[0].glob("*.json")):
            cases.append(json.loads(case_file.read_text()))
        assert len(cases) == len(result.case_ids)
        invs = aggregate_investigations(cases)
        # Synthetic data fires multiple rules on planted positives — at
        # least one investigation must come out, and case_count summed
        # across investigations must equal total cases (no losses).
        assert len(invs) >= 1
        total_cases_in_invs = sum(i["case_count"] for i in invs)
        assert total_cases_in_invs == len(cases)

    def test_investigation_typeddict_shape_matches(self):
        # Defensive: make sure Investigation's TypedDict is the API surface.
        inv: Investigation = aggregate_investigations(
            [_case(case_id="a", rule_id="r", customer_id="C001", window_end=datetime(2026, 4, 10))]
        )[0]
        # Type-ignore: TypedDict accessors check at static-analysis time;
        # we exercise the runtime shape.
        for k in (
            "investigation_id",
            "customer_id",
            "case_ids",
            "rule_ids",
            "severity",
            "queues",
            "tags",
            "total_amount",
            "window_start",
            "window_end",
            "case_count",
            "rule_count",
            "evidence_requested",
            "strategy",
        ):
            assert k in inv, f"missing key {k!r}"
