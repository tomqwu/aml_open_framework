"""Threshold tuning lab — sweep rule parameters over a fixed dataset.

Operators tune AML rule thresholds today by guesswork plus quarterly
reviews. The Tuning Lab makes it cheap and defensible: declare a
`tuning_grid` on a rule, run `aml tune SPEC --rule RULE_ID`, and get
back a per-scenario report (alert-count delta, shadow diff vs the
production thresholds, optional precision/recall when labels are
provided). Same dataset, same seed across the grid, so every scenario
is apples-to-apples — `test_run_is_reproducible` extends to the sweep.

The audit ledger records each `aml tune` invocation as a `tuning_run`
event so any threshold change has a documented decision trail.

Architecture
    The tuner clones the rule with each parameter combination (deep
    copy via Pydantic `model_copy(update=...)`), runs **only that
    rule** against the in-memory DuckDB warehouse, and collects the
    alert customer_ids. It does NOT spin up a full `run_spec`; that
    would re-execute every other rule on every iteration and explode
    cost. Net cost: O(grid_size) rule executions, dominated by the
    rule's own SQL.

    The engine's existing `_execute_*` helpers do the heavy lifting,
    so adding a new rule logic type means it works in the tuner with
    no change here.
"""

from __future__ import annotations

import itertools
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from aml_framework.engine.audit import AuditLedger
from aml_framework.engine.constants import Event
from aml_framework.engine.entity_resolution import resolve_entities
from aml_framework.engine.runner import (
    _build_warehouse,
    _execute_list_match,
    _execute_network_pattern,
)
from aml_framework.generators.sql import compile_rule_sql
from aml_framework.spec.models import AMLSpec, Rule


@dataclass(frozen=True)
class ScenarioResult:
    """One point in the tuning grid: parameter combination + alert outcome."""

    parameters: dict[str, Any]  # dot-path → value
    alert_count: int
    alert_customer_ids: frozenset[str]  # used for diff math
    added_vs_baseline: int = 0  # alerts that appeared but weren't in baseline
    removed_vs_baseline: int = 0  # baseline alerts that disappeared
    precision: float | None = None  # only when labels provided
    recall: float | None = None
    f1: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "parameters": self.parameters,
            "alert_count": self.alert_count,
            "added_vs_baseline": self.added_vs_baseline,
            "removed_vs_baseline": self.removed_vs_baseline,
        }
        if self.precision is not None:
            d["precision"] = round(self.precision, 4)
            d["recall"] = round(self.recall or 0.0, 4)
            d["f1"] = round(self.f1 or 0.0, 4)
        return d


@dataclass(frozen=True)
class TuningRun:
    """Output of `sweep_rule`: baseline + every scenario in the grid."""

    rule_id: str
    grid_size: int
    baseline: ScenarioResult
    scenarios: list[ScenarioResult] = field(default_factory=list)

    def best_by(self, metric: str) -> ScenarioResult | None:
        """Pick the highest scoring scenario for `metric` ∈ {precision,
        recall, f1}. Returns None when labels weren't provided."""
        candidates = [s for s in self.scenarios if getattr(s, metric, None) is not None]
        if not candidates:
            return None
        return max(candidates, key=lambda s: getattr(s, metric))

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "grid_size": self.grid_size,
            "baseline": self.baseline.to_dict(),
            "scenarios": [s.to_dict() for s in self.scenarios],
        }


# ---------------------------------------------------------------------------
# Dot-path patching on a frozen Pydantic Rule
# ---------------------------------------------------------------------------


def _set_by_path(rule: Rule, path: str, value: Any) -> Rule:
    """Return a new Rule with `path` (dot-separated) replaced by `value`.

    Pydantic v2 frozen models can't be mutated; we rebuild the affected
    branch using `model_copy(update=...)` and dict deep-copy for the
    nested `having`/`filter` blocks.
    """
    head, _, tail = path.partition(".")
    if not tail:
        # Top-level rule field (rare; mostly we patch into logic).
        return rule.model_copy(update={head: value})

    if head == "logic":
        new_logic = _set_by_path_logic(rule.logic, tail, value)
        return rule.model_copy(update={"logic": new_logic})

    raise ValueError(
        f"Tuning path must start with 'logic.' (got {path!r}); only "
        "logic-internal parameters are sweep-safe in v1."
    )


def _set_by_path_logic(logic: Any, path: str, value: Any) -> Any:
    """Patch `path` on a logic union member. Returns a new frozen logic."""
    head, _, tail = path.partition(".")
    if not tail:
        # Direct field on logic (e.g. `having`, `window`, `threshold`).
        return logic.model_copy(update={head: value})

    # Two-deep: head is a dict-typed field on logic (typically `having`,
    # `filter`); tail names a key inside it. We deep-copy to avoid
    # mutating the original.
    current = getattr(logic, head, None)
    if not isinstance(current, dict):
        raise ValueError(
            f"Tuning path component {head!r} is not a dict on the rule's logic; "
            f"can't apply nested patch {path!r}={value!r}"
        )
    new_dict = deepcopy(current)
    _set_in_dict(new_dict, tail.split("."), value)
    return logic.model_copy(update={head: new_dict})


def _set_in_dict(d: dict[str, Any], path_parts: list[str], value: Any) -> None:
    """Mutate `d` in place — set d[k1][k2]…[kN] = value."""
    head = path_parts[0]
    if len(path_parts) == 1:
        d[head] = value
        return
    if head not in d or not isinstance(d[head], dict):
        d[head] = {}
    _set_in_dict(d[head], path_parts[1:], value)


def _grid_combinations(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Cartesian product of grid values, yielding dot-path → value dicts."""
    keys = list(grid.keys())
    value_lists = [grid[k] for k in keys]
    out: list[dict[str, Any]] = []
    for combo in itertools.product(*value_lists):
        out.append(dict(zip(keys, combo)))
    return out


# ---------------------------------------------------------------------------
# Per-rule execution (single-rule re-run, no full run_spec)
# ---------------------------------------------------------------------------


def _execute_rule_only(
    rule: Rule, con: duckdb.DuckDBPyConnection, as_of: datetime
) -> list[dict[str, Any]]:
    """Run one rule against the prepared warehouse.

    Mirrors the dispatch in `runner.run_spec` for the supported logic
    types. Skips python_ref (those are scorers — the tuner doesn't
    sweep model versions; that's a separate concern).
    """
    logic_type = rule.logic.type
    if logic_type == "list_match":
        return _execute_list_match(rule, con, as_of)
    if logic_type == "network_pattern":
        return _execute_network_pattern(rule, con, as_of)
    if logic_type in ("aggregation_window", "custom_sql"):
        # Source table = the data_contract id (engine convention).
        source_table = getattr(rule.logic, "source", None) or "txn"
        sql = compile_rule_sql(rule, as_of=as_of, source_table=source_table)
        try:
            rows = con.execute(sql).fetchall()
            cols = [d[0] for d in con.description] if con.description else []
        except Exception:
            return []
        return [dict(zip(cols, r)) for r in rows]
    if logic_type == "python_ref":
        # Out of scope: scorer thresholds are model-internal; tuning
        # those belongs in the model package, not the rule sweep.
        return []
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def sweep_rule(
    spec: AMLSpec,
    rule_id: str,
    data: dict[str, list[dict[str, Any]]],
    *,
    as_of: datetime,
    labels: dict[str, bool] | None = None,
    grid: dict[str, list[Any]] | None = None,
    audit_run_dir: Path | None = None,
) -> TuningRun:
    """Sweep `tuning_grid` for `rule_id` over `data`. Returns TuningRun.

    `labels` (optional) is `customer_id → is_true_positive`. When
    provided each scenario gets precision/recall/F1 computed against
    those labels. Without labels, scenarios are still ranked by
    alert-count delta.

    `grid` overrides the rule's declared `tuning_grid`. Useful for ad-hoc
    sweeps without editing the spec.

    `audit_run_dir` (optional) — when provided, a `tuning_run` event is
    appended to that run's `decisions.jsonl` so the sweep is part of
    the audit trail.
    """
    rule = next((r for r in spec.rules if r.id == rule_id), None)
    if rule is None:
        raise ValueError(f"No rule with id {rule_id!r} in spec")

    sweep_grid = grid if grid is not None else (rule.tuning_grid or {})
    if not sweep_grid:
        raise ValueError(
            f"Rule {rule_id!r} has no tuning_grid declared and no override grid passed."
        )

    # Build the warehouse once; every scenario reads from the same DB.
    con = duckdb.connect(":memory:")
    _build_warehouse(con, spec, data)
    resolve_entities(con, spec)

    # Baseline: production thresholds (the rule as declared in the spec).
    baseline_alerts = _execute_rule_only(rule, con, as_of)
    baseline_ids = frozenset(a["customer_id"] for a in baseline_alerts if "customer_id" in a)
    baseline = ScenarioResult(
        parameters={"_baseline": True},
        alert_count=len(baseline_alerts),
        alert_customer_ids=baseline_ids,
        precision=_precision(baseline_ids, labels),
        recall=_recall(baseline_ids, labels),
        f1=_f1(baseline_ids, labels),
    )

    combos = _grid_combinations(sweep_grid)
    scenarios: list[ScenarioResult] = []
    for params in combos:
        scenario_rule = rule
        for path, value in params.items():
            scenario_rule = _set_by_path(scenario_rule, path, value)
        alerts = _execute_rule_only(scenario_rule, con, as_of)
        ids = frozenset(a["customer_id"] for a in alerts if "customer_id" in a)
        scenarios.append(
            ScenarioResult(
                parameters=params,
                alert_count=len(alerts),
                alert_customer_ids=ids,
                added_vs_baseline=len(ids - baseline_ids),
                removed_vs_baseline=len(baseline_ids - ids),
                precision=_precision(ids, labels),
                recall=_recall(ids, labels),
                f1=_f1(ids, labels),
            )
        )

    run = TuningRun(
        rule_id=rule_id,
        grid_size=len(combos),
        baseline=baseline,
        scenarios=scenarios,
    )

    if audit_run_dir is not None:
        AuditLedger.append_to_run_dir(
            audit_run_dir,
            {
                "event": Event.TUNING_RUN,
                "rule_id": rule_id,
                "grid_size": len(combos),
                "baseline_alerts": baseline.alert_count,
                "scenarios_with_more_alerts": sum(
                    1 for s in scenarios if s.alert_count > baseline.alert_count
                ),
                "scenarios_with_fewer_alerts": sum(
                    1 for s in scenarios if s.alert_count < baseline.alert_count
                ),
                "best_f1": run.best_by("f1").to_dict() if run.best_by("f1") else None,
            },
        )

    return run


# ---------------------------------------------------------------------------
# Precision / recall / F1 helpers
# ---------------------------------------------------------------------------


def _precision(predicted: frozenset[str], labels: dict[str, bool] | None) -> float | None:
    """TP / (TP + FP). None when no labels."""
    if labels is None:
        return None
    if not predicted:
        return None  # undefined when no predictions
    tp = sum(1 for cid in predicted if labels.get(cid))
    return tp / len(predicted)


def _recall(predicted: frozenset[str], labels: dict[str, bool] | None) -> float | None:
    """TP / (TP + FN). None when no labels or no positives in label set."""
    if labels is None:
        return None
    positives = {cid for cid, is_tp in labels.items() if is_tp}
    if not positives:
        return None
    tp = len(predicted & positives)
    return tp / len(positives)


def _f1(predicted: frozenset[str], labels: dict[str, bool] | None) -> float | None:
    if labels is None:
        return None
    p = _precision(predicted, labels)
    r = _recall(predicted, labels)
    if p is None or r is None or (p + r) == 0:
        return None
    return 2 * p * r / (p + r)
