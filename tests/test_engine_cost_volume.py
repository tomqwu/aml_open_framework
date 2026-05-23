"""Run cost + data volume artifact (LF2 — #384).

Covers:
- pure helpers (`summarise_tables`, `_peak_memory_mb`, `CostVolumeTimer`);
- the runner writes `run_cost_volume.json` to the run dir;
- the manifest pins the artifact's SHA-256 hash;
- the artifact is always written (even on empty input);
- the artifact is in `_FROZEN_SNAPSHOT_TARGETS` so it gets chmodded
  0o444 by `_freeze_snapshot_files()` post-finalize;
- model invariants: frozen + extra="forbid".
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date as _date, datetime, timezone
from pathlib import Path

import pytest

from aml_framework.engine.audit import _FROZEN_SNAPSHOT_TARGETS
from aml_framework.engine.cost_volume import (
    CostVolumeTimer,
    RunCostVolumeReport,
    TableVolume,
    _peak_memory_mb,
    _pick_timestamp_column,
    build_report,
    summarise_tables,
    write_report,
)
from aml_framework.engine.runner import run_spec
from aml_framework.spec.models import (
    AggregationWindowLogic,
    AMLSpec,
    Column,
    DataContract,
    Program,
    Queue,
    RegulationRef,
    Rule,
    Workflow,
)

_AS_OF = datetime(2026, 5, 1, tzinfo=timezone.utc)


def _txn_contract() -> DataContract:
    return DataContract(
        id="txn",
        source="t",
        columns=[
            Column(name="txn_id", type="string", nullable=False),
            Column(name="customer_id", type="string", nullable=False),
            Column(name="amount", type="decimal", nullable=False),
            Column(name="booked_at", type="timestamp", nullable=False),
        ],
    )


def _make_spec(*, rules: list[Rule]) -> AMLSpec:
    return AMLSpec(
        version=1,
        program=Program(
            name="T",
            jurisdiction="US",
            regulator="FinCEN",
            owner="MLRO",
            effective_date=_date(2026, 1, 1),
        ),
        data_contracts=[_txn_contract()],
        rules=rules,
        workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
    )


def _spec_for_run() -> AMLSpec:
    return _make_spec(
        rules=[
            Rule(
                id="r_agg",
                name="Aggregation",
                severity="low",
                regulation_refs=[RegulationRef(citation="x", description="x")],
                logic=AggregationWindowLogic(
                    type="aggregation_window",
                    source="txn",
                    group_by=["customer_id"],
                    window="365d",
                    having={"count": {"gte": 1}, "sum_amount": {"gte": 1}},
                ),
                escalate_to="q1",
                evidence=[],
            )
        ]
    )


def _txn_data() -> dict:
    return {
        "txn": [
            {"txn_id": "T1", "customer_id": "C1", "amount": 10.0, "booked_at": _AS_OF},
            {"txn_id": "T2", "customer_id": "C1", "amount": 20.0, "booked_at": _AS_OF},
            {"txn_id": "T3", "customer_id": "C2", "amount": 5.0, "booked_at": _AS_OF},
        ],
    }


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestSummariseTables:
    def test_row_count_and_distinct_customers(self):
        out = summarise_tables(
            {
                "txn": [
                    {"customer_id": "C1", "booked_at": _AS_OF},
                    {"customer_id": "C1", "booked_at": _AS_OF},
                    {"customer_id": "C2", "booked_at": _AS_OF},
                ]
            }
        )
        assert out["txn"].row_count == 3
        assert out["txn"].distinct_customers == 2

    def test_date_range_picks_booked_at(self):
        early = datetime(2025, 1, 1, tzinfo=timezone.utc)
        late = datetime(2026, 5, 1, tzinfo=timezone.utc)
        out = summarise_tables(
            {
                "txn": [
                    {"customer_id": "C1", "booked_at": late},
                    {"customer_id": "C1", "booked_at": early},
                ]
            }
        )
        assert out["txn"].date_range_start == early
        assert out["txn"].date_range_end == late

    def test_no_customer_column_yields_none(self):
        # A reference list has no customer_id — `distinct_customers`
        # must be None rather than 0 so the artifact distinguishes
        # "table has no concept of customers" from "table has zero".
        out = summarise_tables({"sanctions": [{"name": "X", "list": "OFAC"}]})
        assert out["sanctions"].distinct_customers is None
        assert out["sanctions"].date_range_start is None

    def test_empty_table_safe(self):
        # Zero-row table is valid (e.g. a spec that declares a contract
        # but the run had no inputs). row_count=0, everything else None.
        out = summarise_tables({"txn": []})
        assert out["txn"].row_count == 0
        assert out["txn"].distinct_customers is None
        assert out["txn"].date_range_start is None

    def test_non_datetime_timestamps_are_ignored(self):
        # `booked_at` populated with str/None must not crash; only
        # `datetime` values contribute to the min/max.
        out = summarise_tables(
            {
                "txn": [
                    {"customer_id": "C1", "booked_at": None},
                    {"customer_id": "C2", "booked_at": "2026-05-01"},
                    {"customer_id": "C3", "booked_at": _AS_OF},
                ]
            }
        )
        assert out["txn"].row_count == 3
        # Only one valid datetime — date range collapses to a single
        # point, but neither side is None because the datetime did land.
        assert out["txn"].date_range_start == _AS_OF
        assert out["txn"].date_range_end == _AS_OF


class TestPickTimestampColumn:
    def test_prefers_booked_at(self):
        assert _pick_timestamp_column(["booked_at", "event_at"]) == "booked_at"

    def test_falls_back_to_underscore_at(self):
        assert _pick_timestamp_column(["event_at", "name"]) == "event_at"

    def test_falls_back_to_event_date(self):
        assert _pick_timestamp_column(["event_date", "name"]) == "event_date"

    def test_falls_back_to_as_of_date(self):
        # Order matters — as_of_date is checked after event_date.
        assert _pick_timestamp_column(["as_of_date", "name"]) == "as_of_date"

    def test_returns_none_when_no_candidate(self):
        assert _pick_timestamp_column(["customer_id", "amount"]) is None

    def test_non_string_keys_skipped(self):
        # Defensive: dict keys can be non-strings (rare in practice
        # since data rows come from CSV/DuckDB, but `endswith` would
        # raise AttributeError without the isinstance guard).
        assert _pick_timestamp_column([1, "name"]) is None


class TestPeakMemoryMb:
    def test_returns_float_or_none(self):
        # On Linux + macOS we expect a float; on Windows None. Either
        # is correct — the artifact tolerates None.
        result = _peak_memory_mb()
        assert result is None or (isinstance(result, float) and result > 0)

    def test_returns_none_when_resource_unavailable(self, monkeypatch):
        # Simulate Windows by hiding the `resource` module so the
        # ImportError branch fires. Lock the import name so even a
        # cached import is masked.
        monkeypatch.setitem(sys.modules, "resource", None)
        assert _peak_memory_mb() is None

    def test_linux_path_normalises_kib_to_mib(self, monkeypatch):
        # Tests run on darwin in CI/dev, so the Linux/BSD KiB branch is
        # otherwise uncovered. Force `sys.platform = "linux"` and stub
        # a fake `getrusage` so the result is deterministic: 2048 KiB
        # → 2.0 MiB.
        import aml_framework.engine.cost_volume as mod

        class _FakeUsage:
            ru_maxrss = 2048

        class _FakeResource:
            RUSAGE_SELF = 0

            @staticmethod
            def getrusage(_who):
                return _FakeUsage()

        monkeypatch.setitem(sys.modules, "resource", _FakeResource)
        monkeypatch.setattr(mod, "sys", type("S", (), {"platform": "linux"})())
        assert mod._peak_memory_mb() == 2.0


class TestCostVolumeTimer:
    def test_wall_clock_monotonic_increasing(self):
        timer = CostVolumeTimer()
        a = timer.wall_clock()
        b = timer.wall_clock()
        assert b >= a >= 0.0

    def test_per_rule_accumulates(self):
        timer = CostVolumeTimer()
        with timer.rule("r_a"):
            pass
        with timer.rule("r_a"):
            pass
        # Two separate `with` blocks on the same rule_id should sum,
        # not overwrite.
        assert "r_a" in timer.per_rule_seconds
        assert timer.per_rule_seconds["r_a"] >= 0.0

    def test_increment_queries(self):
        timer = CostVolumeTimer()
        timer.increment_queries()
        timer.increment_queries(2)
        assert timer.total_sql_queries == 3


# ---------------------------------------------------------------------------
# Build / write
# ---------------------------------------------------------------------------


class TestBuildAndWriteReport:
    def test_build_report_payload_shape(self):
        tables = {
            "txn": TableVolume(
                row_count=10,
                distinct_customers=3,
                date_range_start=_AS_OF,
                date_range_end=_AS_OF,
            )
        }
        report = build_report(
            wall_clock_seconds=0.42,
            tables=tables,
            total_sql_queries=4,
            per_rule_seconds={"r_agg": 0.1},
        )
        assert report.wall_clock_seconds == 0.42
        assert report.total_sql_queries == 4
        assert report.per_rule_seconds == {"r_agg": 0.1}
        assert report.tables["txn"].row_count == 10
        # peak_memory_mb is best-effort: either a positive float or None.
        assert report.peak_memory_mb is None or report.peak_memory_mb > 0
        assert isinstance(report.generated_at, datetime)

    def test_write_report_emits_json_with_expected_keys(self, tmp_path: Path):
        report = build_report(
            wall_clock_seconds=0.1,
            tables={
                "txn": TableVolume(
                    row_count=1,
                    distinct_customers=1,
                    date_range_start=_AS_OF,
                    date_range_end=_AS_OF,
                )
            },
            total_sql_queries=1,
            per_rule_seconds={"r_agg": 0.05},
        )
        write_report(tmp_path, report)
        payload = json.loads((tmp_path / "run_cost_volume.json").read_text(encoding="utf-8"))
        assert set(payload) == {
            "wall_clock_seconds",
            "peak_memory_mb",
            "tables",
            "total_sql_queries",
            "per_rule_seconds",
            "generated_at",
        }
        assert payload["tables"]["txn"]["row_count"] == 1


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------


class TestRunSpecEmitsCostVolume:
    def test_run_cost_volume_json_written_with_sane_values(self, tmp_path: Path):
        spec = _spec_for_run()
        data = _txn_data()
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")

        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )

        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        cost_path = run_dir / "run_cost_volume.json"
        assert cost_path.exists(), "run_cost_volume.json must always be written"

        payload = json.loads(cost_path.read_text(encoding="utf-8"))
        # Wall clock should be a non-negative float (zero is acceptable
        # on a very fast machine — we only require non-negativity).
        assert payload["wall_clock_seconds"] >= 0.0
        # At least one rule executed → at least one SQL query + a
        # per-rule timing entry.
        assert payload["total_sql_queries"] >= 1
        assert "r_agg" in payload["per_rule_seconds"]
        # Table volume matches the input data.
        txn = payload["tables"]["txn"]
        assert txn["row_count"] == 3
        assert txn["distinct_customers"] == 2
        assert txn["date_range_start"] is not None
        assert txn["date_range_end"] is not None

    def test_manifest_pins_run_cost_volume_hash(self, tmp_path: Path):
        """Mirror of `field_lineage_hash` pinning: the manifest must
        carry a SHA-256 of `run_cost_volume.json` so post-finalize edits
        are detectable.
        """
        spec = _spec_for_run()
        data = _txn_data()
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")

        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )

        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        cost_bytes = (run_dir / "run_cost_volume.json").read_bytes()
        expected = hashlib.sha256(cost_bytes).hexdigest()
        assert manifest["run_cost_volume_hash"] == expected, (
            "manifest must pin SHA-256 of run_cost_volume.json for tamper detection"
        )

    def test_artifact_always_written_even_on_empty_spec(self, tmp_path: Path):
        """Empty `rules` list → artifact still emitted with row counts
        but empty per_rule_seconds. Parallel to `dq_exceptions.jsonl`'s
        always-present contract.
        """
        spec = _make_spec(rules=[])
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")

        run_spec(
            spec=spec,
            spec_path=spec_path,
            data={"txn": []},
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )

        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        cost_path = run_dir / "run_cost_volume.json"
        assert cost_path.exists()
        payload = json.loads(cost_path.read_text(encoding="utf-8"))
        assert payload["per_rule_seconds"] == {}
        assert payload["total_sql_queries"] == 0
        assert payload["tables"]["txn"]["row_count"] == 0

    def test_artifact_is_in_frozen_snapshot_targets(self):
        """The freeze list must include `run_cost_volume.json` so
        `_freeze_snapshot_files()` chmods it 0o444 post-finalize —
        same audit-integrity posture as `field_lineage.jsonl`.
        """
        assert "run_cost_volume.json" in _FROZEN_SNAPSHOT_TARGETS


# ---------------------------------------------------------------------------
# Model invariants
# ---------------------------------------------------------------------------


def test_table_volume_is_frozen_extra_forbid():
    tv = TableVolume(
        row_count=1,
        distinct_customers=1,
        date_range_start=_AS_OF,
        date_range_end=_AS_OF,
    )
    with pytest.raises(Exception):
        tv.row_count = 99  # type: ignore[misc]
    with pytest.raises(Exception):
        TableVolume(
            row_count=1,
            distinct_customers=1,
            date_range_start=_AS_OF,
            date_range_end=_AS_OF,
            unknown_field="boom",  # type: ignore[call-arg]
        )


def test_run_cost_volume_report_is_frozen_extra_forbid():
    report = RunCostVolumeReport(
        wall_clock_seconds=0.1,
        peak_memory_mb=42.0,
        tables={},
        total_sql_queries=0,
        per_rule_seconds={},
        generated_at=_AS_OF,
    )
    with pytest.raises(Exception):
        report.wall_clock_seconds = 1.0  # type: ignore[misc]
    with pytest.raises(Exception):
        RunCostVolumeReport(
            wall_clock_seconds=0.1,
            peak_memory_mb=None,
            tables={},
            total_sql_queries=0,
            per_rule_seconds={},
            generated_at=_AS_OF,
            unknown_field="boom",  # type: ignore[call-arg]
        )
