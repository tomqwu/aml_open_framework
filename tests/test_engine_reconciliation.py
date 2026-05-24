"""Pillar-4 reconciliation stage tracker (PR-B3 — #368).

Covers:
- pure helpers (`_rule_source_to_contract`, `_stage_counts_for_contract`,
  `_drop_breakdown_for_contract`);
- `build_reconciliation_report` happy path / no-DQ-drops / severe drop /
  missing layer / unattributed rule sources;
- the runner writes `reconciliation_report.json` to the run dir;
- the manifest pins the artifact's SHA-256 hash;
- the artifact is always written (even on empty input);
- `reconciliation_report.json` is in `_FROZEN_SNAPSHOT_TARGETS` so
  `_freeze_snapshot_files()` chmods it 0o444 post-finalize;
- model invariants: frozen + extra="forbid".
"""

from __future__ import annotations

import hashlib
import json
from datetime import date as _date, datetime, timezone
from pathlib import Path

import pytest

from aml_framework.engine.audit import _FROZEN_SNAPSHOT_TARGETS
from aml_framework.engine.dq import DQException
from aml_framework.engine.reconciliation import (
    ContractReconciliation,
    ReconciliationReport,
    ReconciliationStage,
    StageDrop,
    _drop_breakdown_for_contract,
    _rule_source_to_contract,
    _stage_counts_for_contract,
    build_reconciliation_report,
    write_reconciliation_report,
)
from aml_framework.engine.runner import run_spec
from aml_framework.spec.models import (
    AggregationWindowLogic,
    AMLSpec,
    Column,
    CustomSQLLogic,
    DataContract,
    Program,
    Queue,
    RegulationRef,
    Rule,
    Workflow,
)

_AS_OF = datetime(2026, 5, 1, tzinfo=timezone.utc)


def _txn_contract(layer: str | None = "bronze") -> DataContract:
    return DataContract(
        id="txn",
        source="t",
        layer=layer,
        columns=[
            Column(name="txn_id", type="string", nullable=False),
            Column(name="customer_id", type="string", nullable=False),
            Column(name="amount", type="decimal", nullable=False),
            Column(name="booked_at", type="timestamp", nullable=False),
        ],
    )


def _agg_rule() -> Rule:
    return Rule(
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


def _make_spec(*, contracts: list[DataContract], rules: list[Rule]) -> AMLSpec:
    return AMLSpec(
        version=1,
        program=Program(
            name="T",
            jurisdiction="US",
            regulator="FinCEN",
            owner="MLRO",
            effective_date=_date(2026, 1, 1),
        ),
        data_contracts=contracts,
        rules=rules,
        workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
    )


def _dq_exception(
    contract_id: str = "txn",
    check_id: str = "not_null:amount",
    *,
    row_index: int | None = 0,
) -> DQException:
    return DQException(
        contract_id=contract_id,
        check_id=check_id,
        check_type="not_null",
        column="amount",
        failing_value=None,
        row_index=row_index,
        reason="amount is null",
        at=_AS_OF,
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestRuleSourceToContract:
    def test_aggregation_rule_maps_to_source_contract(self):
        spec = _make_spec(contracts=[_txn_contract()], rules=[_agg_rule()])
        assert _rule_source_to_contract(spec) == {"r_agg": "txn"}

    def test_custom_sql_rule_has_no_attribution(self):
        # custom_sql logic carries no `source` field; the helper drops it.
        rule = Rule(
            id="r_custom",
            name="Custom",
            severity="low",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=CustomSQLLogic(type="custom_sql", sql="SELECT 1"),
            escalate_to="q1",
            evidence=[],
        )
        spec = _make_spec(contracts=[_txn_contract()], rules=[rule])
        assert _rule_source_to_contract(spec) == {}

    def test_inactive_rule_excluded(self):
        # Non-active rules (experimental / deprecated / inactive) must be
        # skipped — the runner doesn't execute them, so attributing a
        # zero-alert count to their source contract would falsely claim
        # the contract reached the alert surface this run.
        rule = _agg_rule()
        inactive = rule.model_copy(update={"status": "experimental"})
        spec = _make_spec(contracts=[_txn_contract()], rules=[inactive])
        assert _rule_source_to_contract(spec) == {}


class TestStageCountsForContract:
    def test_bronze_layer_propagates_with_dq_drop(self):
        counts = _stage_counts_for_contract(
            contract_id="txn",
            layer="bronze",
            input_row_count=100,
            dq_drops=3,
            alert_count=5,
        )
        assert counts[ReconciliationStage.BRONZE] == 100
        assert counts[ReconciliationStage.SILVER] == 97
        assert counts[ReconciliationStage.GOLD] == 97
        assert counts[ReconciliationStage.ALERT] == 5

    def test_silver_layer_skips_bronze(self):
        counts = _stage_counts_for_contract(
            contract_id="txn",
            layer="silver",
            input_row_count=50,
            dq_drops=2,
            alert_count=0,
        )
        assert counts[ReconciliationStage.BRONZE] is None
        assert counts[ReconciliationStage.SILVER] == 50
        assert counts[ReconciliationStage.GOLD] == 48
        assert counts[ReconciliationStage.ALERT] == 0

    def test_gold_layer_starts_at_gold(self):
        counts = _stage_counts_for_contract(
            contract_id="txn",
            layer="gold",
            input_row_count=10,
            dq_drops=0,
            alert_count=1,
        )
        assert counts[ReconciliationStage.BRONZE] is None
        assert counts[ReconciliationStage.SILVER] is None
        assert counts[ReconciliationStage.GOLD] == 10
        assert counts[ReconciliationStage.ALERT] == 1

    def test_no_layer_keeps_only_alert_known(self):
        counts = _stage_counts_for_contract(
            contract_id="ref",
            layer=None,
            input_row_count=5,
            dq_drops=0,
            alert_count=None,
        )
        assert counts[ReconciliationStage.BRONZE] is None
        assert counts[ReconciliationStage.SILVER] is None
        assert counts[ReconciliationStage.GOLD] is None
        assert counts[ReconciliationStage.ALERT] is None

    def test_dq_drops_floored_at_zero(self):
        # Defensive: DQ drops can't exceed input rows under a well-formed
        # run, but the helper must not produce negative survival counts.
        counts = _stage_counts_for_contract(
            contract_id="txn",
            layer="bronze",
            input_row_count=2,
            dq_drops=5,
            alert_count=0,
        )
        assert counts[ReconciliationStage.SILVER] == 0
        assert counts[ReconciliationStage.GOLD] == 0


class TestDropBreakdownForContract:
    def test_bronze_to_alert_with_dq_and_alert_surface(self):
        counts = _stage_counts_for_contract(
            contract_id="txn",
            layer="bronze",
            input_row_count=100,
            dq_drops=3,
            alert_count=2,
        )
        drops = _drop_breakdown_for_contract(counts, dq_drops=3)
        # Three legs: bronze→silver, silver→gold, gold→alert.
        assert [d.from_stage for d in drops] == [
            ReconciliationStage.BRONZE,
            ReconciliationStage.SILVER,
            ReconciliationStage.GOLD,
        ]
        assert drops[0].attribution == "dq_exceptions"
        assert drops[0].delta == -3
        # bronze→silver already absorbed the DQ delta, so silver→gold is a
        # no_drop.
        assert drops[1].attribution == "no_drop"
        assert drops[1].delta == 0
        # gold→alert is the rule-fire surface (100-3=97 → 2 alerts).
        assert drops[2].attribution == "alert_surface"
        assert drops[2].delta == 2 - 97

    def test_missing_upstream_layer_surfaces_attribution(self):
        # A silver-anchored contract has no bronze count; the bronze→
        # silver leg records that explicitly.
        counts = _stage_counts_for_contract(
            contract_id="txn",
            layer="silver",
            input_row_count=10,
            dq_drops=0,
            alert_count=1,
        )
        drops = _drop_breakdown_for_contract(counts, dq_drops=0)
        assert drops[0].attribution == "missing_layer"
        assert drops[0].delta == 0

    def test_gold_to_alert_emitted_when_no_alerts(self):
        # alert_count=0 is NOT None — the leg is emitted with delta=-N.
        counts = _stage_counts_for_contract(
            contract_id="txn",
            layer="gold",
            input_row_count=5,
            dq_drops=0,
            alert_count=0,
        )
        drops = _drop_breakdown_for_contract(counts, dq_drops=0)
        # Filter to the gold→alert leg.
        leg = next(d for d in drops if d.from_stage == ReconciliationStage.GOLD)
        assert leg.attribution == "alert_surface"
        assert leg.delta == -5

    def test_silver_anchored_dq_drop_attributes_dq_on_silver_to_gold(self):
        # Silver-anchored contract w/ DQ drops: the bronze→silver leg
        # is missing_layer (no bronze count), and the dq attribution
        # lands on silver→gold instead. Exercises the dq_exceptions
        # branch of the silver→gold leg.
        counts = _stage_counts_for_contract(
            contract_id="txn",
            layer="silver",
            input_row_count=10,
            dq_drops=4,
            alert_count=1,
        )
        drops = _drop_breakdown_for_contract(counts, dq_drops=4)
        silver_to_gold = next(d for d in drops if d.from_stage == ReconciliationStage.SILVER)
        assert silver_to_gold.attribution == "dq_exceptions"
        assert silver_to_gold.delta == -4

    def test_unconsumed_contract_drops_gold_to_alert_as_no_drop(self):
        # alert_count=None (no rule sources this contract) → gold→alert
        # leg records `no_drop` so the row shape is stable.
        counts = _stage_counts_for_contract(
            contract_id="ref",
            layer="gold",
            input_row_count=3,
            dq_drops=0,
            alert_count=None,
        )
        drops = _drop_breakdown_for_contract(counts, dq_drops=0)
        leg = next(d for d in drops if d.from_stage == ReconciliationStage.GOLD)
        assert leg.attribution == "no_drop"
        assert leg.delta == 0


# ---------------------------------------------------------------------------
# build_reconciliation_report
# ---------------------------------------------------------------------------


class TestBuildReconciliationReport:
    def test_happy_path_one_bronze_contract(self):
        spec = _make_spec(contracts=[_txn_contract("bronze")], rules=[_agg_rule()])
        data = {
            "txn": [
                {"txn_id": "T1", "customer_id": "C1", "amount": 10.0, "booked_at": _AS_OF},
                {"txn_id": "T2", "customer_id": "C1", "amount": 20.0, "booked_at": _AS_OF},
            ]
        }
        report = build_reconciliation_report(spec, data, [], {"r_agg": [{"customer_id": "C1"}]})
        assert report.total_contracts == 1
        assert report.total_input_rows == 2
        assert report.total_alerts == 1
        contract = report.contracts[0]
        assert contract.contract_id == "txn"
        assert contract.layer == "bronze"
        assert contract.stage_counts[ReconciliationStage.BRONZE] == 2
        assert contract.stage_counts[ReconciliationStage.ALERT] == 1

    def test_no_dq_drops_keeps_full_survival(self):
        spec = _make_spec(contracts=[_txn_contract("bronze")], rules=[_agg_rule()])
        data = {"txn": [{"txn_id": f"T{i}", "customer_id": "C1"} for i in range(5)]}
        report = build_reconciliation_report(spec, data, [], {})
        contract = report.contracts[0]
        assert contract.stage_counts[ReconciliationStage.SILVER] == 5
        assert contract.stage_counts[ReconciliationStage.GOLD] == 5
        # No alerts fired; r_agg is the only rule that sources `txn`, so
        # the alert_count is 0 (not None).
        assert contract.stage_counts[ReconciliationStage.ALERT] == 0

    def test_severe_drop_recorded_in_breakdown(self):
        # 100 rows in, 80 distinct rows fail DQ → 20 survive; one alert.
        spec = _make_spec(contracts=[_txn_contract("bronze")], rules=[_agg_rule()])
        data = {"txn": [{"txn_id": f"T{i}", "customer_id": "C1"} for i in range(100)]}
        # Use distinct row_index values so unique-row-index semantics
        # match the "80 distinct rows failed" intent.
        dq = [_dq_exception(row_index=i) for i in range(80)]
        report = build_reconciliation_report(spec, data, dq, {"r_agg": [{"customer_id": "C1"}]})
        contract = report.contracts[0]
        assert contract.stage_counts[ReconciliationStage.SILVER] == 20
        # First leg is the dq_exceptions drop.
        first = contract.drop_breakdown[0]
        assert first.attribution == "dq_exceptions"
        assert first.delta == -80

    def test_multiple_exceptions_per_row_dedup(self):
        # Same row failing two checks must count as ONE removed row.
        # Exception-count inflation would understate survival.
        spec = _make_spec(contracts=[_txn_contract("bronze")], rules=[_agg_rule()])
        data = {"txn": [{"txn_id": f"T{i}", "customer_id": "C1"} for i in range(10)]}
        dq = [
            _dq_exception(check_id="not_null:amount", row_index=0),
            _dq_exception(check_id="range:amount", row_index=0),
            _dq_exception(check_id="not_null:amount", row_index=1),
        ]
        report = build_reconciliation_report(spec, data, dq, {})
        contract = report.contracts[0]
        # Two distinct rows failed — silver count is 10 - 2 = 8.
        assert contract.stage_counts[ReconciliationStage.SILVER] == 8

    def test_row_index_none_does_not_drop_rows(self):
        # `malformed_check` DQ events carry row_index=None — they
        # surface a control gap but can't reduce a row count.
        spec = _make_spec(contracts=[_txn_contract("bronze")], rules=[_agg_rule()])
        data = {"txn": [{"txn_id": "T1", "customer_id": "C1"}]}
        dq = [_dq_exception(row_index=None)]
        report = build_reconciliation_report(spec, data, dq, {})
        contract = report.contracts[0]
        # Row count survives — silver still 1, no DQ drop applied.
        assert contract.stage_counts[ReconciliationStage.SILVER] == 1

    def test_missing_layer_records_no_medallion_signal(self):
        spec = _make_spec(contracts=[_txn_contract(layer=None)], rules=[])
        data = {"txn": [{"txn_id": "T1"}]}
        report = build_reconciliation_report(spec, data, [], {})
        contract = report.contracts[0]
        assert contract.layer is None
        assert all(contract.stage_counts[stage] is None for stage in ReconciliationStage)
        # All adjacent-pair legs surface as "missing_layer" since both
        # endpoints are unknown — drop_breakdown drops those rows
        # entirely, so the list is empty.
        assert contract.drop_breakdown == []

    def test_custom_sql_alerts_count_in_total_not_per_contract(self):
        # A custom_sql rule has no source attribution; its alerts swell
        # the run-wide total but don't land on any contract's alert
        # stage.
        rule = Rule(
            id="r_custom",
            name="Custom",
            severity="low",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=CustomSQLLogic(type="custom_sql", sql="SELECT 1"),
            escalate_to="q1",
            evidence=[],
        )
        spec = _make_spec(contracts=[_txn_contract("bronze")], rules=[rule])
        data = {"txn": [{"txn_id": "T1"}]}
        report = build_reconciliation_report(spec, data, [], {"r_custom": [{"customer_id": "C1"}]})
        assert report.total_alerts == 1
        # No rule references `txn` via its source, so alert_count is None.
        assert report.contracts[0].stage_counts[ReconciliationStage.ALERT] is None


# ---------------------------------------------------------------------------
# write_reconciliation_report
# ---------------------------------------------------------------------------


class TestWriteReconciliationReport:
    def test_writes_byte_stable_json(self, tmp_path: Path):
        report = ReconciliationReport(
            total_contracts=0,
            total_input_rows=0,
            total_alerts=0,
            contracts=[],
        )
        path = write_reconciliation_report(tmp_path, report)
        assert path.exists()
        assert path.name == "reconciliation_report.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload == {
            "total_contracts": 0,
            "total_input_rows": 0,
            "total_alerts": 0,
            "contracts": [],
        }

    def test_two_writes_produce_identical_bytes(self, tmp_path: Path):
        # Determinism contract: same input → same bytes. The manifest
        # SHA-256 pin would otherwise drift on every re-run.
        spec = _make_spec(contracts=[_txn_contract("bronze")], rules=[_agg_rule()])
        data = {"txn": [{"txn_id": "T1", "customer_id": "C1"}]}
        report_a = build_reconciliation_report(spec, data, [], {})
        report_b = build_reconciliation_report(spec, data, [], {})
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        a_path = write_reconciliation_report(dir_a, report_a)
        b_path = write_reconciliation_report(dir_b, report_b)
        assert a_path.read_bytes() == b_path.read_bytes()


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------


class TestRunSpecEmitsReconciliationReport:
    def test_runner_writes_reconciliation_report(self, tmp_path: Path):
        spec = _make_spec(contracts=[_txn_contract("bronze")], rules=[_agg_rule()])
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")
        data = {
            "txn": [
                {"txn_id": "T1", "customer_id": "C1", "amount": 10.0, "booked_at": _AS_OF},
            ]
        }

        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        path = run_dir / "reconciliation_report.json"
        assert path.exists(), "reconciliation_report.json must always be written"
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["total_contracts"] == 1
        assert payload["total_input_rows"] == 1

    def test_manifest_pins_reconciliation_hash(self, tmp_path: Path):
        spec = _make_spec(contracts=[_txn_contract("bronze")], rules=[_agg_rule()])
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")
        data = {"txn": [{"txn_id": "T1", "customer_id": "C1", "amount": 10.0, "booked_at": _AS_OF}]}

        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        expected = hashlib.sha256((run_dir / "reconciliation_report.json").read_bytes()).hexdigest()
        assert manifest["reconciliation_report_hash"] == expected

    def test_artifact_always_written_on_empty_spec(self, tmp_path: Path):
        spec = _make_spec(contracts=[_txn_contract("bronze")], rules=[])
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
        payload = json.loads((run_dir / "reconciliation_report.json").read_text(encoding="utf-8"))
        assert payload["total_contracts"] == 1
        assert payload["total_alerts"] == 0
        assert payload["total_input_rows"] == 0

    def test_artifact_is_in_frozen_snapshot_targets(self):
        assert "reconciliation_report.json" in _FROZEN_SNAPSHOT_TARGETS


# ---------------------------------------------------------------------------
# Model invariants
# ---------------------------------------------------------------------------


def test_stage_drop_is_frozen_extra_forbid():
    drop = StageDrop(
        from_stage=ReconciliationStage.BRONZE,
        to_stage=ReconciliationStage.SILVER,
        delta=-1,
        attribution="dq_exceptions",
    )
    with pytest.raises(Exception):
        drop.delta = 0  # type: ignore[misc]
    with pytest.raises(Exception):
        StageDrop(
            from_stage=ReconciliationStage.BRONZE,
            to_stage=ReconciliationStage.SILVER,
            delta=0,
            attribution="x",
            unknown="boom",  # type: ignore[call-arg]
        )


def test_contract_reconciliation_is_frozen_extra_forbid():
    cr = ContractReconciliation(
        contract_id="txn",
        layer="bronze",
        stage_counts={
            ReconciliationStage.BRONZE: 1,
            ReconciliationStage.SILVER: 1,
            ReconciliationStage.GOLD: 1,
            ReconciliationStage.ALERT: 0,
        },
        drop_breakdown=[],
    )
    with pytest.raises(Exception):
        cr.layer = "silver"  # type: ignore[misc]
    with pytest.raises(Exception):
        ContractReconciliation(
            contract_id="x",
            layer=None,
            stage_counts={
                ReconciliationStage.BRONZE: None,
                ReconciliationStage.SILVER: None,
                ReconciliationStage.GOLD: None,
                ReconciliationStage.ALERT: None,
            },
            drop_breakdown=[],
            unknown="boom",  # type: ignore[call-arg]
        )


def test_reconciliation_report_is_frozen_extra_forbid():
    rep = ReconciliationReport()
    with pytest.raises(Exception):
        rep.total_contracts = 99  # type: ignore[misc]
    with pytest.raises(Exception):
        ReconciliationReport(unknown="boom")  # type: ignore[call-arg]
