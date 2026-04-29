"""Rule-effectiveness backtester — replay a rule across historical periods.

The 2LoD model-risk problem this solves
---------------------------------------
A second-line MLRO has to challenge first-line detection rules with
evidence: "is rule R still earning its keep, or has it degraded?".
Today, answering that triggers a 4-6 week vendor study or a manual data
pull. This module collapses that into one command.

Conceptually the backtester is the time-axis sister to `engine.tuning`:

- Tuning: same data window, vary thresholds → "best threshold today".
- Backtest: same threshold, vary the time window → "is this rule's
  precision/recall stable over the last N quarters or trending down?".

Both reuse `_execute_rule_only` from `engine.tuning` so a new rule
logic type (e.g. a future `behavioural_segment` rule) works in both
without changes here.

Output is a `BacktestReport` JSON artifact MRM can attach directly to
their per-rule SR 26-2 dossier; no rekeying.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable

import duckdb

from aml_framework.engine.entity_resolution import resolve_entities
from aml_framework.engine.runner import _build_warehouse
from aml_framework.engine.tuning import _execute_rule_only, _f1, _precision, _recall
from aml_framework.spec.models import AMLSpec, Rule


@dataclass(frozen=True)
class BacktestPeriod:
    """One historical window the backtester replays the rule against."""

    label: str  # human-readable, e.g. "2025-Q3"
    as_of: datetime  # the rule's "now" for this period
    seed: int = 42  # data-generation seed (default: same as live runs)


@dataclass(frozen=True)
class PeriodResult:
    """Replay outcome for one period: alert volume + scoring vs labels."""

    period: str
    as_of: str  # ISO 8601
    alert_count: int
    alert_customer_ids: frozenset[str]
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    drift_vs_prior_period: dict[str, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "period": self.period,
            "as_of": self.as_of,
            "alert_count": self.alert_count,
        }
        if self.precision is not None:
            d["precision"] = round(self.precision, 4)
        if self.recall is not None:
            d["recall"] = round(self.recall, 4)
        if self.f1 is not None:
            d["f1"] = round(self.f1, 4)
        if self.drift_vs_prior_period is not None:
            d["drift_vs_prior_period"] = {
                k: round(v, 4) for k, v in self.drift_vs_prior_period.items()
            }
        return d


@dataclass(frozen=True)
class BacktestReport:
    """All-periods backtest output for one rule."""

    rule_id: str
    periods: list[PeriodResult] = field(default_factory=list)
    drift_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "n_periods": len(self.periods),
            "periods": [p.to_dict() for p in self.periods],
            "drift_summary": self.drift_summary,
        }


# ---------------------------------------------------------------------------
# Drift summary: simple linear trend over period scores
# ---------------------------------------------------------------------------


def _linear_slope(values: list[float]) -> float | None:
    """Slope of a least-squares line through `values` indexed 0..n-1.

    Returns None when fewer than two valid points. Used as a cheap
    "is this metric trending up, flat, or down" signal — not a
    statistical model. MRM should treat |slope| ≥ 0.05 per period as
    a flag for human review, not as a hard verdict.
    """
    points = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(points) < 2:
        return None
    n = len(points)
    mean_x = sum(p[0] for p in points) / n
    mean_y = sum(p[1] for p in points) / n
    num = sum((p[0] - mean_x) * (p[1] - mean_y) for p in points)
    denom = sum((p[0] - mean_x) ** 2 for p in points)
    if denom == 0:
        return None
    return num / denom


def _summarise_drift(periods: list[PeriodResult]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for metric in ("precision", "recall", "f1", "alert_count"):
        values: list[float] = []
        for p in periods:
            v = getattr(p, metric, None)
            if v is None:
                continue
            values.append(float(v))
        slope = _linear_slope(values)
        if slope is None:
            continue
        summary[f"{metric}_slope_per_period"] = round(slope, 4)
    if periods:
        first, last = periods[0], periods[-1]
        if first.precision is not None and last.precision is not None:
            summary["precision_first_to_last_delta"] = round(last.precision - first.precision, 4)
        if first.recall is not None and last.recall is not None:
            summary["recall_first_to_last_delta"] = round(last.recall - first.recall, 4)
    return summary


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


DataLoader = Callable[[BacktestPeriod], dict[str, list[dict[str, Any]]]]
LabelLoader = Callable[[BacktestPeriod], dict[str, bool] | None]


def _default_data_loader(period: BacktestPeriod) -> dict[str, list[dict[str, Any]]]:
    """Synthetic-data loader varying `as_of` per period.

    Uses the standard `generate_dataset` so backtested numbers come from
    the same data generator the engine runs against. Importing here
    keeps backtest cheap to import in environments without the data
    extras.
    """
    from aml_framework.data import generate_dataset

    return generate_dataset(as_of=period.as_of, seed=period.seed)


def backtest_rule(
    spec: AMLSpec,
    rule_id: str,
    periods: Iterable[BacktestPeriod],
    *,
    data_loader: DataLoader | None = None,
    labels_loader: LabelLoader | None = None,
) -> BacktestReport:
    """Replay `rule_id` across `periods`. Returns a `BacktestReport`.

    `data_loader(period) -> {table: rows}` lets callers plug in real
    historical data. The default uses the synthetic generator anchored
    at each period's `as_of`.

    `labels_loader(period) -> {customer_id: is_true_positive}` is
    optional. Without labels, the report still carries alert volumes
    and volume-drift, which already answers "is this rule firing
    differently than it used to?". With labels, precision/recall/f1
    drift becomes the headline.
    """
    rule: Rule | None = next((r for r in spec.rules if r.id == rule_id), None)
    if rule is None:
        raise ValueError(f"No rule with id {rule_id!r} in spec")

    data_loader = data_loader or _default_data_loader
    period_list = list(periods)
    if not period_list:
        raise ValueError("backtest_rule requires at least one period")

    results: list[PeriodResult] = []
    prior: PeriodResult | None = None
    for period in period_list:
        data = data_loader(period)
        labels = labels_loader(period) if labels_loader else None

        con = duckdb.connect(":memory:")
        _build_warehouse(con, spec, data)
        resolve_entities(con, spec)

        alerts = _execute_rule_only(rule, con, period.as_of)
        ids = frozenset(a["customer_id"] for a in alerts if "customer_id" in a)
        precision = _precision(ids, labels)
        recall = _recall(ids, labels)
        f1 = _f1(ids, labels)

        drift: dict[str, float] | None = None
        if prior is not None:
            drift = {"alert_count_delta": float(len(ids) - prior.alert_count)}
            if precision is not None and prior.precision is not None:
                drift["precision_delta"] = precision - prior.precision
            if recall is not None and prior.recall is not None:
                drift["recall_delta"] = recall - prior.recall

        result = PeriodResult(
            period=period.label,
            as_of=period.as_of.isoformat(),
            alert_count=len(ids),
            alert_customer_ids=ids,
            precision=precision,
            recall=recall,
            f1=f1,
            drift_vs_prior_period=drift,
        )
        results.append(result)
        prior = result

    return BacktestReport(
        rule_id=rule_id,
        periods=results,
        drift_summary=_summarise_drift(results),
    )


def quarters(end: datetime, n: int) -> list[BacktestPeriod]:
    """Helper: build N quarterly windows ending at `end`.

    The most-recent period is labelled by the end date; older periods
    step back by 90 days each. Caller can override this with an
    explicit list when their fiscal calendar isn't 90-day quarters.
    """
    from datetime import timedelta

    out: list[BacktestPeriod] = []
    for i in range(n - 1, -1, -1):
        as_of = end - timedelta(days=90 * i)
        out.append(BacktestPeriod(label=f"Q-{i}" if i else "Q-current", as_of=as_of))
    return out
