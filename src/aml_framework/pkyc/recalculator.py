"""Risk recalculator — turn a customer's triggers into a new rating.

Pure function: same triggers in → same rating out. The escalation
ladder (low → medium → high → critical) is a one-step bump per
qualifying group of triggers, never a teleport. That keeps the rating
movement auditable: every increase has a documented trigger trail.
"""

from __future__ import annotations

from typing import Any

from aml_framework.pkyc.triggers import Trigger

_LADDER = ("low", "medium", "high", "critical")


def _bump(current: str, steps: int) -> str:
    """Move `steps` rungs up the ladder, clamped at 'critical'."""
    cur = current.lower() if current else "low"
    try:
        idx = _LADDER.index(cur)
    except ValueError:
        idx = 0  # unknown rating → treat as low
    new_idx = max(0, min(len(_LADDER) - 1, idx + steps))
    return _LADDER[new_idx]


def recompute_rating(customer: dict[str, Any], triggers: list[Trigger]) -> str:
    """Return a new risk_rating for `customer` given its triggers.

    Rules
        critical trigger          → "critical"
        ≥1 high triggers          → bump current up one (capped at high)
        ≥2 medium triggers        → bump current up one
        else                      → no change

    The caller decides whether to write the new rating back to source.
    """
    current = str(customer.get("risk_rating") or "low").lower()
    if current not in _LADDER:
        current = "low"

    if not triggers:
        return current

    if any(t.severity == "critical" for t in triggers):
        return "critical"

    high_count = sum(1 for t in triggers if t.severity == "high")
    if high_count >= 1:
        bumped = _bump(current, 1)
        # Cap at "high" — only critical-severity triggers reach critical.
        return "high" if bumped == "critical" else bumped

    medium_count = sum(1 for t in triggers if t.severity == "medium")
    if medium_count >= 2:
        bumped = _bump(current, 1)
        return "high" if bumped == "critical" else bumped

    return current


class RiskRecalculator:
    """Object form for callers that want to inject custom ladder rules later."""

    def __init__(self, *, ladder: tuple[str, ...] = _LADDER) -> None:
        self.ladder = ladder

    def recompute(self, customer: dict[str, Any], triggers: list[Trigger]) -> str:
        return recompute_rating(customer, triggers)
