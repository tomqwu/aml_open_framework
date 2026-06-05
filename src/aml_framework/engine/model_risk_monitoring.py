"""Governed model-risk monitoring report (#497).

Pure builder: rolls the model inventory + per-rule count drift (vs the
prior run) + validation cadence into a frozen ModelRiskReport. Advisory
— a monitoring lens, never blocks a run or mutates a model. Deterministic
(no clock/IO); `generated_at` is supplied by the caller. Stdlib + pydantic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelRiskEntry(_Base):
    model_key: str
    kind: str
    tier: str
    owner: str
    current_alerts: int
    prior_alerts: int | None
    drift: str  # "high" | "normal" | "unknown"
    drift_ratio: float | None
    cadence_months: int | None


class ModelRiskReport(_Base):
    enabled: bool
    n_models: int
    n_high_drift: int
    entries: list[ModelRiskEntry]
    generated_at: datetime


def _drift(cur: int, prior: int | None, ratio: float) -> tuple[str, float | None]:
    if prior is None:
        return "unknown", None
    if prior == 0:
        return ("high", None) if cur > 0 else ("normal", 1.0)
    r = cur / prior
    if r >= ratio or r <= 1.0 / ratio:
        return "high", round(r, 3)
    return "normal", round(r, 3)


def build_model_risk_report(
    inventory: dict[str, Any],
    *,
    current_counts: dict[str, int],
    prior_counts: dict[str, int] | None,
    drift_high_ratio: float,
    generated_at: datetime,
) -> ModelRiskReport:
    """Combine the model inventory with per-rule count drift. Pure +
    deterministic; entries sorted high-drift-first, then tier, then key."""
    entries: list[ModelRiskEntry] = []
    for m in inventory.get("models", []):
        key = m["model_key"]
        cur = int(current_counts.get(key, 0))
        prior = None if prior_counts is None else int(prior_counts.get(key, 0))
        drift, ratio = _drift(cur, prior, drift_high_ratio)
        entries.append(
            ModelRiskEntry(
                model_key=key,
                kind=m.get("kind", ""),
                tier=m.get("tier", ""),
                owner=m.get("owner", ""),
                current_alerts=cur,
                prior_alerts=prior,
                drift=drift,
                drift_ratio=ratio,
                cadence_months=m.get("cadence_months"),
            )
        )
    # Sort by tier SEVERITY (high→medium→low), not lexically — a lexical
    # sort on `e.tier` would order "high" < "low" < "medium". Mirrors
    # `_TIER_ORDER` in generators/model_inventory.py.
    entries.sort(
        key=lambda e: (
            e.drift != "high",
            {"high": 0, "medium": 1, "low": 2}.get(e.tier, 9),
            e.model_key,
        )
    )
    return ModelRiskReport(
        enabled=True,
        n_models=len(entries),
        n_high_drift=sum(1 for e in entries if e.drift == "high"),
        entries=entries,
        generated_at=generated_at,
    )
