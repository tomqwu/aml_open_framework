"""Tests for engine/tuning.py — sweep grid, dot-path patching, sweep_rule."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from aml_framework.data import generate_dataset
from aml_framework.engine.constants import Event
from aml_framework.engine.tuning import (
    ScenarioResult,
    TuningRun,
    _f1,
    _grid_combinations,
    _precision,
    _recall,
    _set_by_path,
    sweep_rule,
)
from aml_framework.spec import load_spec

EXAMPLE_CA = (
    Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
)
EXAMPLE_US = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"


# ---------------------------------------------------------------------------
# Grid expansion
# ---------------------------------------------------------------------------


class TestGridCombinations:
    def test_single_param(self):
        out = _grid_combinations({"logic.having.count": [3, 4, 5]})
        assert out == [
            {"logic.having.count": 3},
            {"logic.having.count": 4},
            {"logic.having.count": 5},
        ]

    def test_cartesian_product(self):
        out = _grid_combinations(
            {
                "logic.having.count": [3, 4],
                "logic.having.sum_amount": [1000, 2000],
            }
        )
        assert len(out) == 4

    def test_empty_grid(self):
        assert _grid_combinations({}) == [{}]


# ---------------------------------------------------------------------------
# Dot-path patching of frozen Pydantic Rule
# ---------------------------------------------------------------------------


class TestSetByPath:
    def test_patches_having_count(self):
        spec = load_spec(EXAMPLE_US)
        rule = next(r for r in spec.rules if r.logic.type == "aggregation_window")
        original_count = rule.logic.having.get("count")
        new_rule = _set_by_path(rule, "logic.having.count", {"gte": 99})
        assert new_rule.logic.having["count"] == {"gte": 99}
        # Original rule unchanged (frozen).
        assert rule.logic.having.get("count") == original_count
        # ID unchanged (we only patched the leaf).
        assert new_rule.id == rule.id

    def test_patches_top_level_logic_field(self):
        spec = load_spec(EXAMPLE_US)
        rule = next(r for r in spec.rules if r.logic.type == "aggregation_window")
        new_rule = _set_by_path(rule, "logic.window", "60d")
        assert new_rule.logic.window == "60d"

    def test_nested_non_logic_path_rejected(self):
        # Nested paths must go through `logic.…`. Top-level scalar
        # patches are allowed (e.g. `name`), but `severity.x.y` would
        # try to descend into a non-existent dict and that's invalid.
        spec = load_spec(EXAMPLE_US)
        rule = spec.rules[0]
        with pytest.raises(ValueError, match=r"must start with"):
            _set_by_path(rule, "severity.x.y", "high")

    def test_top_level_rule_field_allowed(self):
        spec = load_spec(EXAMPLE_US)
        rule = spec.rules[0]
        new_rule = _set_by_path(rule, "name", "Renamed Rule")
        assert new_rule.name == "Renamed Rule"

    def test_dict_path_not_dict_raises(self):
        spec = load_spec(EXAMPLE_US)
        rule = next(r for r in spec.rules if r.logic.type == "aggregation_window")
        with pytest.raises(ValueError, match="not a dict"):
            _set_by_path(rule, "logic.window.bogus", "x")


# ---------------------------------------------------------------------------
# Precision / recall / F1
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_precision_with_labels(self):
        labels = {"C1": True, "C2": False, "C3": True, "C4": False}
        # Predicted {C1, C2, C3}: 2 TP, 1 FP → precision = 2/3
        assert _precision(frozenset({"C1", "C2", "C3"}), labels) == pytest.approx(2 / 3)

    def test_recall_with_labels(self):
        labels = {"C1": True, "C2": False, "C3": True, "C4": False}
        # Positives = {C1, C3}; predicted {C1} → recall 1/2
        assert _recall(frozenset({"C1"}), labels) == 0.5

    def test_no_labels_returns_none(self):
        assert _precision(frozenset({"C1"}), None) is None
        assert _recall(frozenset({"C1"}), None) is None
        assert _f1(frozenset({"C1"}), None) is None

    def test_f1_combines_p_and_r(self):
        labels = {"C1": True, "C2": True}
        f1 = _f1(frozenset({"C1"}), labels)  # p=1, r=0.5 → f1 = 2*1*0.5/1.5 = 0.666...
        assert f1 == pytest.approx(2 / 3)

    def test_no_predictions_undefined_precision(self):
        labels = {"C1": True}
        assert _precision(frozenset(), labels) is None

    def test_recall_no_positives_undefined(self):
        labels = {"C1": False, "C2": False}
        assert _recall(frozenset({"C1"}), labels) is None


# ---------------------------------------------------------------------------
# sweep_rule end-to-end
# ---------------------------------------------------------------------------


class TestSweepRule:
    def test_sweep_with_explicit_grid(self):
        spec = load_spec(EXAMPLE_US)
        rule = next(r for r in spec.rules if r.id == "structuring_cash_deposits")
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        run = sweep_rule(
            spec,
            rule.id,
            data,
            as_of=as_of,
            grid={
                "logic.having.count": [{"gte": 2}, {"gte": 3}, {"gte": 5}],
            },
        )
        assert run.rule_id == "structuring_cash_deposits"
        assert run.grid_size == 3
        assert len(run.scenarios) == 3
        # Lower threshold should yield ≥ alerts compared to higher threshold.
        sorted_scenarios = sorted(
            run.scenarios, key=lambda s: s.parameters["logic.having.count"]["gte"]
        )
        assert sorted_scenarios[0].alert_count >= sorted_scenarios[-1].alert_count, (
            "Lower threshold should fire at least as many alerts"
        )

    def test_baseline_alerts_match_run_spec(self):
        from aml_framework.engine.runner import run_spec as runner_run_spec

        spec = load_spec(EXAMPLE_US)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        # Get production alert count for the rule via the full runner.
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            full = runner_run_spec(
                spec=spec,
                spec_path=EXAMPLE_US,
                data=data,
                as_of=as_of,
                artifacts_root=Path(td),
            )
        prod_alerts = full.alerts.get("structuring_cash_deposits", [])
        prod_ids = {a.get("customer_id") for a in prod_alerts if a.get("customer_id")}

        run = sweep_rule(
            spec,
            "structuring_cash_deposits",
            data,
            as_of=as_of,
            grid={"logic.having.count": [{"gte": 99}]},  # one no-op scenario
        )
        # Baseline must mirror production thresholds.
        assert run.baseline.alert_customer_ids == frozenset(prod_ids)

    def test_diff_added_and_removed(self):
        spec = load_spec(EXAMPLE_US)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        run = sweep_rule(
            spec,
            "structuring_cash_deposits",
            data,
            as_of=as_of,
            grid={
                "logic.having.count": [{"gte": 2}],  # looser → should add some
            },
        )
        assert run.scenarios[0].added_vs_baseline >= 0
        assert run.scenarios[0].removed_vs_baseline == 0  # looser can't remove

    def test_unknown_rule_raises(self):
        spec = load_spec(EXAMPLE_US)
        with pytest.raises(ValueError, match="No rule with id"):
            sweep_rule(spec, "nope", {}, as_of=datetime(2026, 4, 23), grid={"logic.window": ["7d"]})

    def test_no_grid_no_override_raises(self):
        spec = load_spec(EXAMPLE_US)
        with pytest.raises(ValueError, match="no tuning_grid"):
            sweep_rule(
                spec,
                "structuring_cash_deposits",
                {},
                as_of=datetime(2026, 4, 23),
            )

    def test_labels_drive_precision_recall(self):
        spec = load_spec(EXAMPLE_US)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)

        # First, get the baseline alert customer ids so we can build labels.
        bootstrap = sweep_rule(
            spec,
            "structuring_cash_deposits",
            data,
            as_of=as_of,
            grid={"logic.having.count": [{"gte": 3}]},
        )
        # Mark all baseline-alerted customers as true positives.
        labels = {cid: True for cid in bootstrap.baseline.alert_customer_ids}

        run = sweep_rule(
            spec,
            "structuring_cash_deposits",
            data,
            as_of=as_of,
            grid={"logic.having.count": [{"gte": 3}]},
            labels=labels,
        )
        # With every alert == true positive, precision must be 1.0.
        assert run.scenarios[0].precision == 1.0


# ---------------------------------------------------------------------------
# Audit ledger integration
# ---------------------------------------------------------------------------


class TestAuditIntegration:
    def test_tuning_run_event_appended(self, tmp_path):
        spec = load_spec(EXAMPLE_US)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)

        # Pre-create an empty decisions.jsonl in a tmp run dir.
        run_dir = tmp_path / "run-test"
        run_dir.mkdir()
        (run_dir / "decisions.jsonl").touch()

        sweep_rule(
            spec,
            "structuring_cash_deposits",
            data,
            as_of=as_of,
            grid={"logic.having.count": [{"gte": 3}, {"gte": 5}]},
            audit_run_dir=run_dir,
        )

        lines = [
            json.loads(line)
            for line in (run_dir / "decisions.jsonl").read_text().splitlines()
            if line.strip()
        ]
        assert len(lines) == 1
        rec = lines[0]
        assert rec["event"] == Event.TUNING_RUN
        assert rec["rule_id"] == "structuring_cash_deposits"
        assert rec["grid_size"] == 2
        assert "baseline_alerts" in rec


# ---------------------------------------------------------------------------
# TuningRun helpers
# ---------------------------------------------------------------------------


class TestTuningRun:
    def test_best_by_returns_none_without_labels(self):
        run = TuningRun(
            rule_id="r",
            grid_size=1,
            baseline=ScenarioResult(parameters={}, alert_count=0, alert_customer_ids=frozenset()),
            scenarios=[
                ScenarioResult(parameters={}, alert_count=0, alert_customer_ids=frozenset())
            ],
        )
        assert run.best_by("f1") is None

    def test_best_by_picks_highest(self):
        scenarios = [
            ScenarioResult(
                parameters={"a": 1}, alert_count=1, alert_customer_ids=frozenset(), f1=0.3
            ),
            ScenarioResult(
                parameters={"a": 2}, alert_count=1, alert_customer_ids=frozenset(), f1=0.7
            ),
            ScenarioResult(
                parameters={"a": 3}, alert_count=1, alert_customer_ids=frozenset(), f1=0.5
            ),
        ]
        run = TuningRun(
            rule_id="r",
            grid_size=3,
            baseline=ScenarioResult(parameters={}, alert_count=0, alert_customer_ids=frozenset()),
            scenarios=scenarios,
        )
        best = run.best_by("f1")
        assert best is not None
        assert best.parameters == {"a": 2}

    def test_to_dict_round_trip(self):
        scenario = ScenarioResult(
            parameters={"logic.having.count": {"gte": 3}},
            alert_count=2,
            alert_customer_ids=frozenset({"C1", "C2"}),
            added_vs_baseline=1,
            removed_vs_baseline=0,
            precision=0.9,
            recall=0.8,
            f1=0.84,
        )
        run = TuningRun(
            rule_id="r1",
            grid_size=1,
            baseline=ScenarioResult(
                parameters={"_baseline": True}, alert_count=1, alert_customer_ids=frozenset({"C1"})
            ),
            scenarios=[scenario],
        )
        d = run.to_dict()
        assert d["rule_id"] == "r1"
        assert d["scenarios"][0]["precision"] == 0.9
        # JSON-serialisable
        json.dumps(d, default=str)


# ---------------------------------------------------------------------------
# Spec-declared tuning_grid path
# ---------------------------------------------------------------------------


class TestSpecDeclaredGrid:
    def test_rule_tuning_grid_consumed(self, tmp_path):
        # Build a spec on the fly with a tuning_grid declared on the rule.
        from aml_framework.spec.models import (
            AggregationWindowLogic,
            AMLSpec,
            DataContract,
            Column,
            Program,
            Queue,
            RegulationRef,
            Rule,
            Workflow,
        )

        spec = AMLSpec(
            version=1,
            program=Program(
                name="Test",
                jurisdiction="US",
                regulator="FinCEN",
                owner="x",
                effective_date="2026-01-01",
            ),
            data_contracts=[
                DataContract(
                    id="txn",
                    source="synthetic://txn",
                    columns=[
                        Column(name="customer_id", type="string"),
                        Column(name="amount", type="decimal"),
                        Column(name="booked_at", type="timestamp"),
                    ],
                )
            ],
            rules=[
                Rule(
                    id="big_amount",
                    name="Big amount",
                    severity="high",
                    regulation_refs=[RegulationRef(citation="X", description="X")],
                    escalate_to="q1",
                    logic=AggregationWindowLogic(
                        type="aggregation_window",
                        source="txn",
                        group_by=["customer_id"],
                        window="30d",
                        having={"sum_amount": {"gte": 50000}},
                    ),
                    tuning_grid={"logic.having.sum_amount": [{"gte": 25000}, {"gte": 100000}]},
                )
            ],
            workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
        )

        from datetime import datetime as _dt
        from decimal import Decimal

        data = {
            "txn": [
                {"customer_id": "C1", "amount": Decimal("60000"), "booked_at": _dt(2026, 4, 20)},
                {"customer_id": "C2", "amount": Decimal("30000"), "booked_at": _dt(2026, 4, 20)},
            ]
        }
        run = sweep_rule(spec, "big_amount", data, as_of=_dt(2026, 4, 23, 12))
        assert run.grid_size == 2
        # Lower threshold (25k) should match both customers; higher (100k) neither.
        looser = next(
            s for s in run.scenarios if s.parameters["logic.having.sum_amount"] == {"gte": 25000}
        )
        tighter = next(
            s for s in run.scenarios if s.parameters["logic.having.sum_amount"] == {"gte": 100000}
        )
        assert looser.alert_count >= tighter.alert_count
        assert tighter.alert_count == 0
