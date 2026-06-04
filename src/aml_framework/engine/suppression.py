"""Governed advisory alert suppression — risk-segment de-prioritization (#495).

Post-scoring pass over the alert list. For each declared low-risk segment,
an alert whose customer falls in the segment AND whose advisory
``priority_score`` is below the segment's ``deprioritize_below`` threshold is
flagged ``suppression.applied = True``. This is ADVISORY — it NEVER removes
the alert, changes disposition/queue/open-close state, or deletes keys. The
rule alert still lands in the ledger; suppression is a triage lens an
investigator can override.

Design rules (mirror ``engine/prioritization.py``): pure / deterministic
(no clock, no random, no I/O), stdlib only, only ADDS the ``suppression``
key. Precondition: ``priority_score`` must be present (prioritization
enabled); otherwise the pass records ``applied=False`` with an explicit
reason and suppresses nothing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SuppressionResult:
    applied: bool
    segment_id: str | None
    reason: str
    threshold: float | None
    score: float | None
    reversible: bool = True


def score_suppression(
    alert: dict[str, Any], cfg, customer_risk: dict[str, str]
) -> SuppressionResult:
    """Pure: decide whether one alert is advisory-suppressed. No mutation."""
    score = alert.get("priority_score")
    if score is None:
        return SuppressionResult(
            False, None, "prioritization disabled — no priority_score", None, None
        )
    risk = customer_risk.get(alert.get("customer_id", ""))
    for seg in cfg.segments:
        if risk is not None and risk in seg.values:
            if score < seg.deprioritize_below:
                return SuppressionResult(
                    True,
                    seg.id,
                    f"score {score} < {seg.deprioritize_below} for segment '{seg.id}'",
                    seg.deprioritize_below,
                    score,
                )
            return SuppressionResult(
                False,
                seg.id,
                f"score {score} >= {seg.deprioritize_below} for segment '{seg.id}'",
                seg.deprioritize_below,
                score,
            )
    return SuppressionResult(False, None, "customer not in any declared segment", None, score)


def stamp_suppression(rule, alerts, cfg, customer_risk: dict[str, str]) -> None:
    """Add an advisory ``suppression`` dict to each alert. No-op when cfg is
    None or disabled. Never removes keys, never auto-closes."""
    if cfg is None or not getattr(cfg, "enabled", False):
        return
    for alert in alerts:
        alert["suppression"] = asdict(score_suppression(alert, cfg, customer_risk))
