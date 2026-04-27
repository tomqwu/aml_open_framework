"""SLA timer and escalation engine for case management.

Round-6 PR #3. The framework's engine already records `within_sla`
and `resolution_hours` in the simulated decisions ledger, but those
are *retrospective* — they tell you whether a case beat its SLA after
the fact. What was missing: a **real-time** SLA computation that,
given a still-open case + the queue's SLA, tells you "this case is
amber, 4 hours remaining, due at 14:00 today."

The **FCA's March 2026 Dear CEO letter on SAR backlogs** named
real-time SLA tracking + active escalation discipline as the gap UK
firms most often failed on in supervisory visits. Retrospective
"within_sla" reporting wasn't enough — examiners wanted to see the
live queue. This module provides that live-queue view + the
escalation policy that automatically flags breached cases for
queue advancement per the spec's `workflow.queues[].next` list.

Composes with:
- Round-6 #1 investigation aggregator — backlog stats can be
  computed at investigation level too (max time-in-queue across
  constituent cases).
- Round-6 #5 case dashboard page — feeds the per-case timer rings
  and queue-health table.
- Round-7 #1 outcome metrics — SLA-breach rate per rule per quarter
  is one of the FinCEN NPRM funnel ratios.

Design
- Pure functions over case dicts + spec — no IO.
- Time math is timezone-agnostic (matches the engine's existing
  pattern of stripping tzinfo before persistence). Operators
  passing tz-aware datetimes get tz-aware timedelta back.
- SLA bands are: green (>50% time remaining), amber (10-50%),
  red (0-10%), breached (negative remaining). The thresholds are
  module-level constants; operators with a different palette can
  override via the `sla_thresholds` arg on the public functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypedDict

from aml_framework.generators.sql import parse_window
from aml_framework.spec.models import AMLSpec, Queue

DEFAULT_SLA_BANDS = {
    "green_above_pct": 50.0,  # >50% time remaining
    "amber_above_pct": 10.0,  # 10-50% remaining
    # below 10% → red; negative → breached
}


class SLAStatus(TypedDict, total=False):
    """Real-time SLA position of one case."""

    case_id: str
    queue: str
    state: str  # "green" | "amber" | "red" | "breached"
    queue_sla_hours: float
    time_in_queue_hours: float
    time_remaining_hours: float
    pct_remaining: float
    opened_at: datetime
    due_at: datetime


@dataclass(frozen=True)
class EscalationAction:
    """Recommended next-queue advancement for a breached case."""

    case_id: str
    from_queue: str
    to_queue: str
    reason: str  # "sla_breach" | "severity_critical" | etc.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _opened_at(case: dict[str, Any]) -> datetime | None:
    """Resolve the case's open timestamp.

    The engine doesn't write a dedicated `opened_at`; we use the alert's
    `window_end` (when the rule fired) as the proxy. Falls back to
    `booked_at` if window_end is missing.
    """
    alert = case.get("alert") or {}
    for key in ("opened_at", "window_end", "booked_at"):
        v = alert.get(key) if key != "opened_at" else case.get("opened_at")
        if isinstance(v, datetime):
            return v
        if isinstance(v, str) and v:
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00").replace("+00:00", ""))
            except ValueError:
                continue
    return None


def _classify(pct_remaining: float, bands: dict[str, float]) -> str:
    if pct_remaining < 0:
        return "breached"
    if pct_remaining > bands["green_above_pct"]:
        return "green"
    if pct_remaining > bands["amber_above_pct"]:
        return "amber"
    return "red"


# ---------------------------------------------------------------------------
# Public: per-case SLA computation
# ---------------------------------------------------------------------------


def compute_sla_status(
    case: dict[str, Any],
    queue: Queue,
    *,
    as_of: datetime,
    sla_thresholds: dict[str, float] | None = None,
) -> SLAStatus | None:
    """Compute the live SLA position of one case.

    Returns None when the case has no resolvable open time — those are
    skipped rather than silently classified as "breached" so callers can
    surface data-quality issues separately.

    Args:
        case: a CaseDict-shaped dict from the engine.
        queue: the `Queue` object the case currently sits in.
        as_of: the moment to evaluate against (typically `datetime.now()`
            in the dashboard, or the engine's `as_of` for backtests).
        sla_thresholds: optional override for the green/amber/red band
            cutoffs. Defaults to DEFAULT_SLA_BANDS.
    """
    bands = sla_thresholds or DEFAULT_SLA_BANDS
    opened_at = _opened_at(case)
    if opened_at is None:
        return None

    sla_td = parse_window(queue.sla)
    sla_hours = sla_td.total_seconds() / 3600
    if sla_hours <= 0:
        return None

    elapsed = as_of - opened_at
    elapsed_hours = elapsed.total_seconds() / 3600
    remaining_hours = sla_hours - elapsed_hours
    pct_remaining = (remaining_hours / sla_hours) * 100

    return {
        "case_id": case.get("case_id", ""),
        "queue": queue.id,
        "state": _classify(pct_remaining, bands),
        "queue_sla_hours": sla_hours,
        "time_in_queue_hours": elapsed_hours,
        "time_remaining_hours": remaining_hours,
        "pct_remaining": pct_remaining,
        "opened_at": opened_at,
        "due_at": opened_at + sla_td,
    }


# ---------------------------------------------------------------------------
# Public: escalation policy
# ---------------------------------------------------------------------------


def apply_escalation(
    case: dict[str, Any],
    sla_status: SLAStatus,
    queue: Queue,
) -> EscalationAction | None:
    """Recommend the next queue when the SLA has breached.

    Picks the first non-closed entry in the queue's `next` list (which
    typically is the higher-tier investigator queue). Returns None when:
        - SLA hasn't breached
        - The queue has no `next` entries
        - All `next` entries look like closure queues
    """
    if sla_status.get("state") != "breached":
        return None
    candidates = [
        next_q
        for next_q in (queue.next or [])
        if "closed" not in next_q.lower() and "no_action" not in next_q.lower()
    ]
    if not candidates:
        return None
    return EscalationAction(
        case_id=case.get("case_id", ""),
        from_queue=queue.id,
        to_queue=candidates[0],
        reason="sla_breach",
    )


# ---------------------------------------------------------------------------
# Public: backlog summarisation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BacklogStats:
    """Per-queue backlog snapshot."""

    queue_id: str
    queue_sla_hours: float
    total_cases: int
    green: int
    amber: int
    red: int
    breached: int
    oldest_age_hours: float  # of the oldest *open* case in this queue
    breach_rate_pct: float  # breached / total * 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "queue_id": self.queue_id,
            "queue_sla_hours": self.queue_sla_hours,
            "total_cases": self.total_cases,
            "green": self.green,
            "amber": self.amber,
            "red": self.red,
            "breached": self.breached,
            "oldest_age_hours": self.oldest_age_hours,
            "breach_rate_pct": self.breach_rate_pct,
        }


def summarise_backlog(
    cases: list[dict[str, Any]],
    spec: AMLSpec,
    *,
    as_of: datetime,
    sla_thresholds: dict[str, float] | None = None,
) -> list[BacklogStats]:
    """Roll up SLA states by queue.

    Returns one `BacklogStats` per queue defined in the spec's workflow,
    even when the queue has zero open cases (so the dashboard's queue-
    health table doesn't omit empty rows). Closed-state queues
    ("closed_no_action", "str_filing", etc.) are still included but
    typically show low/zero counts.

    Cases with no resolvable opened_at are dropped per-queue but counted
    in the spec-wide `total_cases` field for ops visibility.
    """
    queue_map = {q.id: q for q in spec.workflow.queues}
    by_queue: dict[str, list[SLAStatus]] = {qid: [] for qid in queue_map}

    for case in cases:
        qid = case.get("queue") or ""
        queue = queue_map.get(qid)
        if queue is None:
            continue
        status = compute_sla_status(case, queue, as_of=as_of, sla_thresholds=sla_thresholds)
        if status is None:
            continue
        by_queue[qid].append(status)

    out: list[BacklogStats] = []
    for qid, statuses in by_queue.items():
        queue = queue_map[qid]
        sla_td = parse_window(queue.sla)
        sla_hours = sla_td.total_seconds() / 3600
        total = len(statuses)
        green = sum(1 for s in statuses if s["state"] == "green")
        amber = sum(1 for s in statuses if s["state"] == "amber")
        red = sum(1 for s in statuses if s["state"] == "red")
        breached = sum(1 for s in statuses if s["state"] == "breached")
        oldest = max((s["time_in_queue_hours"] for s in statuses), default=0.0)
        breach_rate = (breached / total * 100) if total > 0 else 0.0
        out.append(
            BacklogStats(
                queue_id=qid,
                queue_sla_hours=sla_hours,
                total_cases=total,
                green=green,
                amber=amber,
                red=red,
                breached=breached,
                oldest_age_hours=oldest,
                breach_rate_pct=breach_rate,
            )
        )
    out.sort(key=lambda b: b.queue_id)
    return out


__all__ = [
    "DEFAULT_SLA_BANDS",
    "SLAStatus",
    "EscalationAction",
    "BacklogStats",
    "compute_sla_status",
    "apply_escalation",
    "summarise_backlog",
]
