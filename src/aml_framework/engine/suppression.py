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
key. Precondition: the caller must pass an explicit
``prioritization_enabled`` flag reflecting ``program.prioritization.enabled``;
when it is False the pass records ``applied=False`` with an explicit reason
and suppresses nothing — it never infers the precondition from the mere
presence of a stray ``priority_score`` on an alert.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class SuppressionResult:
    applied: bool
    segment_id: str | None
    reason: str
    threshold: float | None
    score: float | None
    reversible: bool = True


def score_suppression(
    alert: dict[str, Any], cfg, customer_risk: dict[str, str], prioritization_enabled: bool
) -> SuppressionResult:
    """Pure: decide whether one alert is advisory-suppressed. No mutation.

    Precondition is the explicit ``prioritization_enabled`` flag (from
    ``program.prioritization.enabled``), NOT the presence of a
    ``priority_score`` on the alert: a stray score on a disabled run must
    never trigger suppression.
    """
    if not prioritization_enabled:
        # Short-circuit BEFORE reading priority_score — the precondition is
        # the explicit flag, never the presence of a (possibly stray) score.
        return SuppressionResult(False, None, "prioritization disabled", None, None)
    score = alert.get("priority_score")
    if score is None:
        return SuppressionResult(
            False, None, "prioritization enabled but no priority_score on this alert", None, None
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


def stamp_suppression(
    rule, alerts, cfg, customer_risk: dict[str, str], prioritization_enabled: bool
) -> None:
    """Add an advisory ``suppression`` dict to each alert. No-op when cfg is
    None or disabled. Never removes keys, never auto-closes.

    The suppression precondition is the explicit ``prioritization_enabled``
    flag (``program.prioritization.enabled``), threaded through to
    ``score_suppression`` — suppression is never inferred from a stray
    ``priority_score`` on an alert."""
    if cfg is None or not getattr(cfg, "enabled", False):
        return
    for alert in alerts:
        alert["suppression"] = asdict(
            score_suppression(alert, cfg, customer_risk, prioritization_enabled)
        )


class SuppressionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    scored_alerts: int  # alerts that went through the suppression pass
    suppressed: int  # subset flagged suppression.applied = True
    by_segment: dict[str, int] = Field(default_factory=dict)  # segment_id -> suppressed count
    by_rule: dict[str, int] = Field(default_factory=dict)  # rule_id -> suppressed count
    sample: list[dict[str, Any]] = Field(
        default_factory=list
    )  # [{customer_id, rule_id, segment_id, priority_score}]


def build_suppression_report(
    alerts_by_rule: dict[str, list[dict[str, Any]]],
    *,
    enabled: bool,
    top_n: int = 20,
    mask_customer_id: Callable[[str], str] | None = None,
) -> SuppressionReport:
    """Deterministic summary of the run's advisory suppression pass.

    Mirrors ``prioritization.build_priority_report``: ``alerts_by_rule`` holds
    the in-memory (UN-masked) alert dicts, so when PII masking is active the
    caller must pass ``mask_customer_id`` — the same masking function the audit
    ledger applies to ``alerts/*.jsonl`` — so this frozen, regulator-facing
    artifact never persists a plaintext customer_id.

    Only alerts that actually carry a ``suppression`` dict (i.e. the pass ran)
    are counted as scored; a never-stamped alert is ignored.
    """
    scored = 0
    by_segment: dict[str, int] = {}
    by_rule: dict[str, int] = {}
    sample: list[dict[str, Any]] = []
    for rule_id in sorted(alerts_by_rule):
        for a in alerts_by_rule[rule_id]:
            supp = a.get("suppression")
            if not isinstance(supp, dict):
                continue
            scored += 1
            if not supp.get("applied"):
                continue
            seg_id = supp.get("segment_id")
            if seg_id is not None:
                by_segment[seg_id] = by_segment.get(seg_id, 0) + 1
            by_rule[rule_id] = by_rule.get(rule_id, 0) + 1
            cid = a.get("customer_id")
            if mask_customer_id is not None and cid is not None:
                cid = mask_customer_id(cid)
            sample.append(
                {
                    "customer_id": cid,
                    "rule_id": rule_id,
                    "segment_id": seg_id,
                    "priority_score": supp.get("score"),
                }
            )
    # Stable order: lowest score first (most-confidently suppressed), then
    # (rule_id, customer_id) — no dependence on dict iteration order.
    sample.sort(
        key=lambda r: (
            r["priority_score"] if r["priority_score"] is not None else 0.0,
            str(r["rule_id"]),
            str(r["customer_id"]),
        )
    )
    return SuppressionReport(
        enabled=enabled,
        scored_alerts=scored,
        suppressed=sum(by_rule.values()),
        by_segment=dict(sorted(by_segment.items())),
        by_rule=dict(sorted(by_rule.items())),
        sample=sample[:top_n],
    )
