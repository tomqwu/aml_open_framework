"""Governed alert-prioritization: an explainable, deterministic, ADVISORY
0-1 risk score per alert.

Thesis (ML as governed augmentation): this never changes an alert's
disposition — it only lets investigators sort a triage queue by risk. The
MVP scorer is a transparent weighted model whose every contribution is
echoed in `priority_explanation`; `score_alert()` is the seam a trained ML
model can later swap behind without changing the governance contract.

Pure functions, stdlib-only — deterministic so same spec+data+seed yields
identical scores (and therefore identical hashes).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Ordinal severity -> [0, 1]. Unknown severities map to the lowest band so a
# typo can never silently inflate priority.
_SEVERITY_RANK = {"low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0}
# Risk tier (PR-RISK-1) -> [0, 1]; None/unknown -> 0 (no contribution).
_RISK_TIER_RANK = {"low": 0.33, "medium": 0.66, "high": 1.0}
# Amount is log-scaled then capped so a $10M alert doesn't dwarf everything.
_AMOUNT_CAP = 100_000.0
# Volume (txn count behind the alert) capped likewise.
_VOLUME_CAP = 50.0


@dataclass(frozen=True)
class PriorityResult:
    score: float  # 0-1
    explanation: list[dict[str, Any]]  # [{feature, value, contribution}]


def _coerce_float(value: Any) -> float:
    """Best-effort finite float for an optional scoring feature. Prioritization
    is ADVISORY — a custom_sql/python_ref alert may carry a formatted, redacted,
    or non-finite (`"NaN"`/`"inf"`) `sum_amount`/`count`, and such a value must
    NEVER abort the run or produce a NaN/inf score (which would break the 0-1
    contract and emit non-standard JSON). Treat anything unparseable OR
    non-finite as 0 (no contribution from that feature)."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def _feature_value(alert: dict[str, Any], rule: Any) -> dict[str, float]:
    """Extract the normalised [0,1] feature values used by the scorer."""
    severity = _SEVERITY_RANK.get(str(getattr(rule, "severity", "") or "").lower(), 0.25)
    risk_tier = _RISK_TIER_RANK.get(str(getattr(rule, "risk_tier", "") or "").lower(), 0.0)
    # Prefer `sum_amount` by KEY PRESENCE, not truthiness — a legitimate
    # `sum_amount: 0` must not silently fall through to `amount` (which would
    # inflate the amount feature). Only when `sum_amount` is absent do we fall
    # back to a projected `amount`.
    amount_raw = alert.get("sum_amount")
    if amount_raw is None:
        amount_raw = alert.get("amount")
    amount = _coerce_float(amount_raw if amount_raw is not None else 0.0)
    amount_n = min(math.log1p(max(amount, 0.0)) / math.log1p(_AMOUNT_CAP), 1.0)
    # Volume = txns behind the alert. Prefer the projected `count`; when a rule
    # doesn't project one (e.g. a sum_amount-only CTR aggregation_window rule),
    # fall back to the already-stamped `matched_row_ids` so high- and low-volume
    # alerts still rank differently instead of both scoring volume 0.
    count_raw = alert.get("count")
    if count_raw is None:
        matched = alert.get("matched_row_ids")
        count_raw = len(matched) if isinstance(matched, list) else 0
    # Clamp at 0 — a malformed negative `count` must not yield a negative
    # normalised volume (which would violate the documented [0, 1] feature
    # contract and subtract from the score).
    count = max(_coerce_float(count_raw), 0.0)
    volume_n = min(count / _VOLUME_CAP, 1.0)
    return {"severity": severity, "risk_tier": risk_tier, "amount": amount_n, "volume": volume_n}


def score_alert(alert: dict[str, Any], rule: Any, config: Any) -> PriorityResult:
    """Return an advisory 0-1 priority score + per-feature explanation."""
    w = config.weights
    feats = _feature_value(alert, rule)
    weights = {
        "severity": w.severity,
        "risk_tier": w.risk_tier,
        "amount": w.amount,
        "volume": w.volume,
    }
    bias = -1.0
    explanation: list[dict[str, Any]] = [{"feature": "bias", "value": 1.0, "contribution": bias}]
    for name in ("severity", "risk_tier", "amount", "volume"):
        contribution = round(weights[name] * feats[name], 6)
        explanation.append(
            {
                "feature": name,
                "value": round(feats[name], 6),
                "contribution": contribution,
            }
        )
    # Reconstruct logit from the stored (rounded) contributions so the
    # round-trip identity score == sigmoid(sum(contributions)) holds exactly
    # (within float64 precision — no further rounding that would break it).
    logit = sum(c["contribution"] for c in explanation)
    score = 1.0 / (1.0 + math.exp(-logit))
    return PriorityResult(score=score, explanation=explanation)


def stamp_priority(rule: Any, alerts: list[dict[str, Any]], config: Any) -> None:
    """Mutate each alert in place, adding `priority_score` +
    `priority_explanation`. No-op when config is None or disabled. ADVISORY:
    only ADDS fields — never removes or alters existing keys, never touches
    disposition/queue/state.
    """
    if config is None or not getattr(config, "enabled", False):
        return
    for alert in alerts:
        result = score_alert(alert, rule, config)
        alert["priority_score"] = result.score
        alert["priority_explanation"] = result.explanation


class PriorityReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    scored_alerts: int
    by_rule: dict[str, int] = Field(default_factory=dict)  # rule_id -> count scored
    top_alerts: list[dict[str, Any]] = Field(
        default_factory=list
    )  # [{customer_id, rule_id, priority_score}]


def build_priority_report(
    alerts_by_rule: dict[str, list[dict[str, Any]]],
    *,
    enabled: bool,
    top_n: int = 20,
    mask_customer_id: Callable[[str], str] | None = None,
) -> PriorityReport:
    """Deterministic distribution summary for the run's priority scores.

    `alerts_by_rule` holds the in-memory (UN-masked) alert dicts, so when PII
    masking is active the caller must pass `mask_customer_id` — the same
    masking function the audit ledger applies to `alerts/*.jsonl` — so this
    frozen, regulator-facing artifact never persists a plaintext customer_id.
    """
    scored: list[dict[str, Any]] = []
    by_rule: dict[str, int] = {}
    for rule_id in sorted(alerts_by_rule):
        rows = [a for a in alerts_by_rule[rule_id] if "priority_score" in a]
        if rows:
            by_rule[rule_id] = len(rows)
        for a in rows:
            cid = a.get("customer_id")
            if mask_customer_id is not None and cid is not None:
                cid = mask_customer_id(cid)
            scored.append(
                {
                    "customer_id": cid,
                    "rule_id": rule_id,
                    "priority_score": a["priority_score"],
                }
            )
    # Sort by score desc, then (rule_id, customer_id) for a stable tiebreak —
    # determinism contract: no dependence on dict iteration order.
    scored.sort(key=lambda r: (-r["priority_score"], str(r["rule_id"]), str(r["customer_id"])))
    return PriorityReport(
        enabled=enabled,
        scored_alerts=len(scored),
        by_rule=by_rule,
        top_alerts=scored[:top_n],
    )
