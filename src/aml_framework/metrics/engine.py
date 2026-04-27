"""Metrics evaluation engine.

Each metric declares a formula (count / sum / ratio / coverage / sql) against
a named source (alerts, cases, decisions, rules, txn, customer). The engine
computes a value, compares it to `target` and `thresholds`, and returns a
`MetricResult` with a RAG band so exec-level reports are trivial to render.

Inputs come from the already-executed rule run — no separate data fetch —
which keeps metric values deterministic and reproducible alongside the
evidence bundle they describe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aml_framework.spec.models import (
    AMLSpec,
    CountFormula,
    CoverageFormula,
    Metric,
    RatioFormula,
    SQLFormula,
    SumFormula,
)


@dataclass
class MetricResult:
    id: str
    name: str
    category: str
    audience: list[str]
    owner: str | None
    unit: str | None
    value: float | int
    rag: str  # "green" | "amber" | "red" | "unset"
    target_met: bool | None
    formula_type: str
    breakdown: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "audience": self.audience,
            "owner": self.owner,
            "unit": self.unit,
            "value": self.value,
            "rag": self.rag,
            "target_met": self.target_met,
            "formula_type": self.formula_type,
            "breakdown": self.breakdown,
        }


def _matches_filter(row: dict[str, Any], filt: dict[str, Any] | None) -> bool:
    if not filt:
        return True
    for field_name, cond in filt.items():
        val = row.get(field_name)
        if not isinstance(cond, dict):
            if val != cond:
                return False
            continue
        for op, arg in cond.items():
            if op == "in" and val not in arg:
                return False
            if op == "eq" and val != arg:
                return False
            if op == "ne" and val == arg:
                return False
            if op == "gte" and not (val is not None and val >= arg):
                return False
            if op == "lte" and not (val is not None and val <= arg):
                return False
            if op == "gt" and not (val is not None and val > arg):
                return False
            if op == "lt" and not (val is not None and val < arg):
                return False
            if op == "between":
                lo, hi = arg
                if val is None or not (lo <= val <= hi):
                    return False
    return True


def _source_rows(source: str, ctx: "MetricContext") -> list[dict[str, Any]]:
    if source == "alerts":
        return [{"rule_id": rid, **a} for rid, alerts in ctx.alerts.items() for a in alerts]
    if source == "cases":
        return list(ctx.cases)
    if source == "decisions":
        return list(ctx.decisions)
    if source == "rules":
        return [r.model_dump() for r in ctx.spec.rules]
    if source == "txn":
        return list(ctx.data.get("txn", []))
    if source == "customer":
        return list(ctx.data.get("customer", []))
    raise ValueError(f"unknown metric source '{source}'")


def _compute(formula: Any, ctx: "MetricContext") -> float:
    if isinstance(formula, CountFormula):
        rows = _source_rows(formula.source, ctx)
        rows = [r for r in rows if _matches_filter(r, formula.filter)]
        if formula.distinct_by:
            return float(len({r.get(formula.distinct_by) for r in rows}))
        return float(len(rows))

    if isinstance(formula, SumFormula):
        rows = _source_rows(formula.source, ctx)
        rows = [r for r in rows if _matches_filter(r, formula.filter)]
        return float(sum(float(r.get(formula.field, 0) or 0) for r in rows))

    if isinstance(formula, RatioFormula):
        denom = _compute(formula.denominator, ctx)
        if denom == 0:
            return 0.0
        return _compute(formula.numerator, ctx) / denom

    if isinstance(formula, CoverageFormula):
        if formula.universe == "typologies":
            # Universe: typologies declared on any rule via its `tags`.
            # Covered_by: distinct tags that actually triggered at least one alert.
            if formula.covered_by == "rule_tags":
                all_tags = {t for r in ctx.spec.rules for t in r.tags}
                fired = {t for r in ctx.spec.rules for t in r.tags if ctx.alerts.get(r.id)}
                return 0.0 if not all_tags else len(fired) / len(all_tags)
        # Other combinations fall back to a neutral 0.0 — a real deployment
        # would extend this; the spec shape is forward-compatible.
        return 0.0

    if isinstance(formula, SQLFormula):
        # SQL formulas can't be executed directly (they reference production
        # tables). Instead, compute best-effort values from the run context.
        return _compute_sql_proxy(formula, ctx)

    raise TypeError(f"unsupported formula: {type(formula).__name__}")


def _rag_band(value: float, metric: Metric) -> tuple[str, bool | None]:
    """Return (rag, target_met). RAG is 'unset' if no thresholds declared."""
    rag = "unset"
    if metric.thresholds:
        for band in ("green", "amber", "red"):
            cond = metric.thresholds.get(band)
            if cond and _cond_holds(value, cond):
                rag = band
                break
    target_met: bool | None = None
    if metric.target:
        target_met = _cond_holds(value, metric.target)
    return rag, target_met


def _cond_holds(value: float, cond: dict[str, Any]) -> bool:
    for op, arg in cond.items():
        if op == "gte" and not value >= arg:
            return False
        if op == "lte" and not value <= arg:
            return False
        if op == "gt" and not value > arg:
            return False
        if op == "lt" and not value < arg:
            return False
        if op == "eq" and value != arg:
            return False
        if op == "between":
            lo, hi = arg
            if not (lo <= value <= hi):
                return False
    return True


def _proxy_repeat_alert(ctx: "MetricContext") -> float:
    """Fraction of closed-no-action customers who were later re-alerted."""
    closed_customers = {
        d.get("case_id", "").split("__")[1]
        for d in ctx.decisions
        if d.get("event") == "case_opened"
        and any(
            c.get("queue") == "closed_no_action"
            for c in ctx.cases
            if c.get("case_id") == d.get("case_id")
        )
    }
    if not closed_customers:
        return 0.0
    all_alerted = [a.get("customer_id") for alerts in ctx.alerts.values() for a in alerts]
    repeat_count = sum(1 for cid in closed_customers if all_alerted.count(cid) > 1)
    return repeat_count / (len(closed_customers) or 1)


def _proxy_filing_latency(ctx: "MetricContext") -> float:
    """p95 STR/SAR filing latency in days (approximate)."""
    filing_hours = sorted(
        d.get("resolution_hours", 0)
        for d in ctx.decisions
        if d.get("disposition", "") in ("str_filing", "sar_filing")
        and d.get("resolution_hours") is not None
    )
    if not filing_hours:
        return 0.0
    p95_idx = min(int(len(filing_hours) * 0.95), len(filing_hours) - 1)
    return round(filing_hours[p95_idx] / 24, 2)  # hours → days


def _proxy_lctr_completeness(ctx: "MetricContext") -> float:
    """Cash-LCTR alert volume divided by reportable cash txn count.
    Reference engine doesn't actually file; alerts stand in for "detected"."""
    txns = ctx.data.get("txn", [])
    reportable = sum(
        1 for t in txns if t.get("channel") == "cash" and float(t.get("amount", 0)) >= 10000
    )
    if reportable == 0:
        return 1.0
    cash_alerts = len(ctx.alerts.get("large_cash_lctr", []) or ctx.alerts.get("large_cash_ctr", []))
    return min(cash_alerts / reportable, 1.0)


def _proxy_edd_review(ctx: "MetricContext") -> float:
    """Fraction of high-risk customers whose EDD review is current (within 12 months)."""
    from datetime import datetime as _dt

    customers = ctx.data.get("customer", [])
    high_risk = [c for c in customers if c.get("risk_rating") == "high"]
    if not high_risk:
        return 1.0
    cutoff_days = 365
    current = 0
    for c in high_risk:
        review = c.get("edd_last_review")
        if review is None:
            continue
        if isinstance(review, _dt):
            age_days = max(
                (max(cust.get("onboarded_at", review) for cust in customers) - review).days,
                0,
            )
            if age_days <= cutoff_days:
                current += 1
        else:
            current += 1  # Non-datetime truthy value counts as reviewed.
    return current / len(high_risk)


def _proxy_sla_compliance(ctx: "MetricContext") -> float:
    """Fraction of resolution decisions that met their SLA."""
    resolutions = [
        d for d in ctx.decisions if d.get("event") in ("escalated", "escalated_to_str", "closed")
    ]
    if not resolutions:
        return 0.0
    on_time = sum(1 for d in resolutions if d.get("within_sla", False))
    return on_time / len(resolutions)


def _proxy_avg_resolution(ctx: "MetricContext") -> float:
    """Mean resolution_hours across closed/escalated decisions."""
    hours = [
        d.get("resolution_hours", 0)
        for d in ctx.decisions
        if d.get("resolution_hours") is not None
        and d.get("event") in ("escalated", "escalated_to_str", "closed")
    ]
    return sum(hours) / len(hours) if hours else 0.0


# Token → handler. Order matters: the first match wins, mirroring the
# original cascading if-chain. Keep new tokens specific so they don't shadow
# earlier handlers.
_PROXY_DISPATCH: tuple[tuple[tuple[str, ...], Any], ...] = (
    (("repeat", "closed_cases"), _proxy_repeat_alert),
    (("filing", "percentile", "latency"), _proxy_filing_latency),
    (("reportable", "lctr", "filed"), _proxy_lctr_completeness),
    (("edd", "current_edd", "high_risk"), _proxy_edd_review),
    (("sla", "on_time"), _proxy_sla_compliance),
    (("resolution", "avg"), _proxy_avg_resolution),
)


def _compute_sql_proxy(formula: "SQLFormula", ctx: "MetricContext") -> float:
    """Best-effort computation for SQL-formula metrics from run context.

    Production deployments execute the SQL against their warehouse. The
    reference engine computes proxy values from alerts/cases/decisions
    already in the context so these metrics show real numbers rather than 0.0.
    """
    sql_lower = formula.sql.lower()
    for tokens, handler in _PROXY_DISPATCH:
        if any(tok in sql_lower for tok in tokens):
            return handler(ctx)
    return 0.0  # Unknown SQL formula.


@dataclass
class MetricContext:
    spec: AMLSpec
    alerts: dict[str, list[dict[str, Any]]]
    cases: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    data: dict[str, list[dict[str, Any]]]


def evaluate_metrics(
    spec: AMLSpec,
    alerts: dict[str, list[dict[str, Any]]],
    cases: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    data: dict[str, list[dict[str, Any]]],
) -> list[MetricResult]:
    ctx = MetricContext(spec=spec, alerts=alerts, cases=cases, decisions=decisions, data=data)
    results: list[MetricResult] = []
    for metric in spec.metrics:
        value = _compute(metric.formula, ctx)
        rag, target_met = _rag_band(value, metric)
        results.append(
            MetricResult(
                id=metric.id,
                name=metric.name,
                category=metric.category,
                audience=list(metric.audience),
                owner=metric.owner,
                unit=metric.unit,
                value=round(value, 4),
                rag=rag,
                target_met=target_met,
                formula_type=metric.formula.type,
            )
        )
    return results
