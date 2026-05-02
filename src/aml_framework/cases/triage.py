"""Composite triage ranking for the AML analyst's morning queue (PR-PROC-2).

Backs PROC-1 in the "Process & Ingestion" research doc: operators face
a wall of alerts every morning and don't know which one to open first.
The framework already knows severity, SLA band, and customer
risk_rating per case; this module composes them into a single
deterministic score so an analyst can answer "which one first?" in
one glance instead of a spreadsheet sweep.

Composite score (0-100, higher = more urgent):
- 40% SLA breach window remaining (breached → 100, red → 75, amber → 50, green → 25)
- 30% Severity (critical → 100, high → 75, medium → 50, low → 25)
- 20% Customer risk_rating (critical → 100, high → 75, medium → 50, low → 25)
- 10% Rule precision proxy (defaults to 0.5; tuneable from recent runs)

The weighting is institution-tuneable in a future PR via
`spec.program.triage_weights`; for now it's a sensible default informed
by FCA Mar 2026 SAR-backlog supervisory framing (SLA breach is the
loudest signal in regulator language) and TD 2024 enforcement (severity
+ customer risk are the load-bearing inputs the consent order called
out).

Pure module — no streamlit, no IO. Same inputs → same output ranking.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aml_framework.cases.sla import compute_sla_status
from aml_framework.spec.models import AMLSpec

# Score buckets — kept as constants so they're easy to override in tests
# and for future spec-side tuning.
_SEVERITY_SCORE = {"critical": 100, "high": 75, "medium": 50, "low": 25}
_RISK_SCORE = {"critical": 100, "high": 75, "medium": 50, "low": 25}

_WEIGHT_SLA = 0.40
_WEIGHT_SEV = 0.30
_WEIGHT_RISK = 0.20
_WEIGHT_PRECISION = 0.10


@dataclass(frozen=True)
class RankedCase:
    """One case + its composite triage score, ready to render."""

    case_id: str
    score: float  # 0-100, higher = open this first
    severity: str
    queue: str
    sla_state: str  # "green" | "amber" | "red" | "breached" | "unknown"
    pct_remaining: float
    customer_id: str
    customer_risk_rating: str
    rule_id: str
    why: str  # one-line "why this case first" justification

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "score": round(self.score, 1),
            "severity": self.severity,
            "queue": self.queue,
            "sla_state": self.sla_state,
            "pct_remaining": round(self.pct_remaining, 1),
            "customer_id": self.customer_id,
            "customer_risk_rating": self.customer_risk_rating,
            "rule_id": self.rule_id,
            "why": self.why,
        }


def _sla_score(sla_state: str, pct_remaining: float) -> float:
    """Map SLA position to a 0-100 urgency component.

    `pct_remaining` is the canonical input; `sla_state` is a fallback
    for cases where the case has no resolvable open time (compute_sla_status
    returned None — surface those as `state="unknown"` and treat as
    medium urgency rather than silently zero).
    """
    if sla_state == "unknown":
        return 50.0
    if pct_remaining <= 0:
        return 100.0  # breached
    if pct_remaining <= 10:
        return 75.0  # red
    if pct_remaining <= 50:
        return 50.0  # amber
    return 25.0  # green


def triage_score(
    *,
    severity: str,
    sla_state: str,
    sla_pct_remaining: float,
    customer_risk: str,
    rule_precision: float = 0.5,
) -> float:
    """Composite triage score 0-100, higher = open this case first.

    All weights documented at module top. Same inputs always produce
    the same score (no randomness, no clock).
    """
    sev = _SEVERITY_SCORE.get((severity or "low").lower(), 25)
    risk = _RISK_SCORE.get((customer_risk or "low").lower(), 25)
    sla = _sla_score(sla_state, sla_pct_remaining)
    precision = max(0.0, min(1.0, rule_precision)) * 100
    return (
        _WEIGHT_SLA * sla + _WEIGHT_SEV * sev + _WEIGHT_RISK * risk + _WEIGHT_PRECISION * precision
    )


def _build_justification(
    severity: str,
    sla_state: str,
    pct_remaining: float,
    customer_risk: str,
) -> str:
    """One-line 'why this case first' string analysts can scan in 1s."""
    parts: list[str] = []
    if sla_state == "breached":
        parts.append("SLA breached")
    elif sla_state == "red":
        parts.append(f"SLA {pct_remaining:.0f}% left")
    elif sla_state == "amber":
        parts.append(f"SLA {pct_remaining:.0f}% left")
    sev_lower = (severity or "low").lower()
    if sev_lower in ("high", "critical"):
        parts.append(f"{sev_lower} severity")
    risk_lower = (customer_risk or "low").lower()
    if risk_lower in ("high", "critical"):
        parts.append(f"{risk_lower}-risk customer")
    if not parts:
        parts.append("standard priority")
    return " · ".join(parts)


def rank_queue(
    cases: list[dict[str, Any]],
    spec: AMLSpec,
    customers: list[dict[str, Any]],
    *,
    as_of: datetime,
    top_n: int | None = None,
) -> list[RankedCase]:
    """Rank open cases by composite triage score, descending.

    Args:
        cases: list of CaseDict-shaped dicts from the engine run dir.
        spec: the AMLSpec — used to resolve queue SLAs.
        customers: customer table — used to look up risk_rating per case.
        as_of: the moment to evaluate SLA against (typically `datetime.now()`
            in the dashboard, or the engine's `as_of` for backtests).
        top_n: if set, return only the top N cases.

    Returns: cases sorted by `score` descending, ties broken by case_id
    (deterministic). Cases with no resolvable queue or no severity field
    are still ranked (treated as low/unknown) — silent drops would hide
    operator-blocking data-quality issues.
    """
    customers_by_id = {c.get("customer_id"): c for c in customers if c.get("customer_id")}
    queues_by_id = {q.id: q for q in spec.workflow.queues}

    ranked: list[RankedCase] = []
    for case in cases:
        queue_id = case.get("queue") or ""
        queue = queues_by_id.get(queue_id)

        if queue is not None:
            sla_status = compute_sla_status(case, queue, as_of=as_of)
        else:
            sla_status = None

        if sla_status is None:
            sla_state = "unknown"
            pct_remaining = 100.0
        else:
            sla_state = sla_status.get("state", "unknown")
            pct_remaining = float(sla_status.get("pct_remaining", 100.0))

        cust_id = (case.get("alert") or {}).get("customer_id", "") or ""
        customer = customers_by_id.get(cust_id, {})
        customer_risk = str(customer.get("risk_rating") or "low")
        severity = case.get("severity", "low")

        score = triage_score(
            severity=severity,
            sla_state=sla_state,
            sla_pct_remaining=pct_remaining,
            customer_risk=customer_risk,
        )
        why = _build_justification(severity, sla_state, pct_remaining, customer_risk)

        ranked.append(
            RankedCase(
                case_id=str(case.get("case_id", "")),
                score=score,
                severity=str(severity),
                queue=queue_id,
                sla_state=sla_state,
                pct_remaining=pct_remaining,
                customer_id=str(cust_id),
                customer_risk_rating=customer_risk,
                rule_id=str(case.get("rule_id", "")),
                why=why,
            )
        )

    # Stable sort: score desc, case_id asc as tiebreaker for determinism.
    ranked.sort(key=lambda r: (-r.score, r.case_id))
    if top_n is not None:
        return ranked[: max(0, top_n)]
    return ranked
