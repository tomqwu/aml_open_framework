"""Investigation aggregator — group per-alert cases into investigations.

Round-6 PR #1. The framework's engine emits one case per alert
(`case_id = "{rule_id}__{customer_id}__{window_end}"`), so a single
customer hit by 3 different rules in one run produces 3 separate cases.
**FinCEN's 2024 effectiveness rule (and its 2026 supervisory
guidance) measures AML program effectiveness in terms of
*investigations*, not alerts** — an investigation is one subject
reviewed once with all related signals together. Without an
investigation entity the framework can't compute the alert →
investigation → SAR funnel that FinCEN now treats as the canonical
program metric.

This module is the foundation for Round-6 features 3-5 (SLA timer,
case-to-STR auto-bundling, case dashboard page) and Round-7 #1
(outcome metrics).

Design
- Pure function — no IO. The engine already persists raw cases to
  the audit ledger; aggregation runs over the in-memory case list.
- Deterministic: same case set + same strategy → same investigation
  IDs. `investigation_id` is a SHA-256 prefix over the sorted list
  of constituent case_ids.
- Three strategies in v1:
    * `per_customer_window` (default) — group by (customer_id, 30-day
      bucket). Two cases for the same customer 25 days apart land in
      the same investigation; 35 days apart land in different ones.
    * `per_customer_per_run` — every case for a customer in this run
      becomes one investigation regardless of timing.
    * `per_case` — singleton investigations (legacy compat for tests
      and operators who don't want grouping).
- Severity escalation: investigation severity = max(case severities)
  using the standard ordering low < medium < high < critical.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, TypedDict

# 30-day bucketing epoch — fixed so investigation IDs don't drift across runs.
_BUCKET_EPOCH = datetime(2020, 1, 1)
_BUCKET_DAYS = 30

_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class Investigation(TypedDict, total=False):
    """Aggregated unit of analyst work — one subject, one review."""

    investigation_id: str
    customer_id: str
    case_ids: list[str]
    rule_ids: list[str]
    severity: str
    queues: list[str]
    tags: list[str]
    total_amount: Decimal
    window_start: datetime | None
    window_end: datetime | None
    case_count: int
    rule_count: int
    evidence_requested: list[str]
    strategy: str


# ---------------------------------------------------------------------------
# Bucketing helpers
# ---------------------------------------------------------------------------


def _alert_dt(case: dict[str, Any]) -> datetime | None:
    """Return the alert's representative timestamp (window_end fallback)."""
    alert = case.get("alert") or {}
    for key in ("window_end", "booked_at", "window_start"):
        v = alert.get(key)
        if isinstance(v, datetime):
            return v
        if isinstance(v, str) and v:
            try:
                # Engine writes ISO format; tolerate Z suffix.
                return datetime.fromisoformat(v.replace("Z", "+00:00").replace("+00:00", ""))
            except ValueError:
                continue
    return None


def _bucket_index(dt: datetime | None) -> int:
    if dt is None:
        return -1
    delta = dt - _BUCKET_EPOCH
    return delta.days // _BUCKET_DAYS


def _customer_id(case: dict[str, Any]) -> str:
    """Resolve the subject — case-level customer_id wins, alert is fallback."""
    alert = case.get("alert") or {}
    return case.get("customer_id") or alert.get("customer_id") or ""


# ---------------------------------------------------------------------------
# Strategy implementations
# ---------------------------------------------------------------------------


def _group_per_customer_window(
    cases: list[dict[str, Any]],
) -> dict[tuple[str, int], list[dict[str, Any]]]:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for case in cases:
        cid = _customer_id(case)
        if not cid:
            continue
        bucket = _bucket_index(_alert_dt(case))
        groups.setdefault((cid, bucket), []).append(case)
    return groups


def _group_per_customer_per_run(
    cases: list[dict[str, Any]],
) -> dict[tuple[str, int], list[dict[str, Any]]]:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for case in cases:
        cid = _customer_id(case)
        if not cid:
            continue
        groups.setdefault((cid, 0), []).append(case)
    return groups


def _group_per_case(
    cases: list[dict[str, Any]],
) -> dict[tuple[str, int], list[dict[str, Any]]]:
    return {(case.get("case_id", f"_{i}"), 0): [case] for i, case in enumerate(cases)}


_STRATEGIES = {
    "per_customer_window": _group_per_customer_window,
    "per_customer_per_run": _group_per_customer_per_run,
    "per_case": _group_per_case,
}


# ---------------------------------------------------------------------------
# Investigation construction
# ---------------------------------------------------------------------------


def _max_severity(cases: Iterable[dict[str, Any]]) -> str:
    best_rank = -1
    best = "low"
    for case in cases:
        sev = (case.get("severity") or "low").lower()
        rank = _SEVERITY_ORDER.get(sev, 0)
        if rank > best_rank:
            best_rank = rank
            best = sev
    return best


def _sum_amount(cases: Iterable[dict[str, Any]]) -> Decimal:
    total = Decimal("0")
    for case in cases:
        alert = case.get("alert") or {}
        v = alert.get("sum_amount")
        if v is None:
            continue
        try:
            total += Decimal(str(v))
        except (ArithmeticError, ValueError):
            continue
    return total


def _window_bounds(cases: Iterable[dict[str, Any]]) -> tuple[datetime | None, datetime | None]:
    starts: list[datetime] = []
    ends: list[datetime] = []
    for case in cases:
        alert = case.get("alert") or {}
        for key, target in (("window_start", starts), ("window_end", ends)):
            v = alert.get(key)
            if isinstance(v, datetime):
                target.append(v)
            elif isinstance(v, str) and v:
                try:
                    target.append(
                        datetime.fromisoformat(v.replace("Z", "+00:00").replace("+00:00", ""))
                    )
                except ValueError:
                    pass
    return (min(starts) if starts else None, max(ends) if ends else None)


def _distinct_sorted(cases: Iterable[dict[str, Any]], key: str) -> list[str]:
    seen: set[str] = set()
    for case in cases:
        v = case.get(key)
        if isinstance(v, str) and v:
            seen.add(v)
    return sorted(seen)


def _union_evidence(cases: Iterable[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    for case in cases:
        for ev in case.get("evidence_requested") or []:
            if isinstance(ev, str) and ev:
                seen.add(ev)
    return sorted(seen)


def _investigation_id(case_ids: list[str]) -> str:
    """Deterministic 16-hex-char ID over sorted constituent case IDs."""
    payload = "\n".join(sorted(case_ids)).encode("utf-8")
    return "INV-" + hashlib.sha256(payload).hexdigest()[:16]


def _build_investigation(
    cases: list[dict[str, Any]],
    *,
    customer_id: str,
    strategy: str,
) -> Investigation:
    case_ids = sorted(c.get("case_id", "") for c in cases if c.get("case_id"))
    rule_ids = _distinct_sorted(cases, "rule_id")
    queues = _distinct_sorted(cases, "queue")
    # Tag union — tags live on the underlying alert if the rule populated them.
    tag_set: set[str] = set()
    for case in cases:
        alert = case.get("alert") or {}
        for tag in alert.get("tags") or []:
            if isinstance(tag, str) and tag:
                tag_set.add(tag)
    window_start, window_end = _window_bounds(cases)
    return {
        "investigation_id": _investigation_id(case_ids),
        "customer_id": customer_id,
        "case_ids": case_ids,
        "rule_ids": rule_ids,
        "severity": _max_severity(cases),
        "queues": queues,
        "tags": sorted(tag_set),
        "total_amount": _sum_amount(cases),
        "window_start": window_start,
        "window_end": window_end,
        "case_count": len(case_ids),
        "rule_count": len(rule_ids),
        "evidence_requested": _union_evidence(cases),
        "strategy": strategy,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def aggregate_investigations(
    cases: list[dict[str, Any]],
    *,
    strategy: str = "per_customer_window",
) -> list[Investigation]:
    """Group raw per-alert cases into investigation units.

    Args:
        cases: list of CaseDict-shaped dicts as emitted by the engine.
        strategy: one of "per_customer_window" (default), "per_customer_per_run",
            or "per_case". See module docstring for semantics.

    Returns:
        Sorted list of Investigation dicts, ordered by investigation_id for
        deterministic output. Cases with no resolvable customer_id are
        silently dropped (they aren't actionable as investigations).
    """
    if strategy not in _STRATEGIES:
        raise ValueError(f"unknown aggregation strategy {strategy!r}; valid: {sorted(_STRATEGIES)}")
    grouper = _STRATEGIES[strategy]
    groups = grouper(cases)
    out: list[Investigation] = []
    for (customer_id, _bucket), group_cases in groups.items():
        if not group_cases:
            continue
        # For per_case strategy, customer_id key is actually the case_id —
        # re-resolve from the underlying case so the field is meaningful.
        if strategy == "per_case":
            customer_id = _customer_id(group_cases[0])
            if not customer_id:
                continue
        out.append(_build_investigation(group_cases, customer_id=customer_id, strategy=strategy))
    out.sort(key=lambda inv: inv["investigation_id"])
    return out


def bucket_window_for(dt: datetime) -> tuple[datetime, datetime]:
    """Return the [start, end) of the 30-day bucket containing `dt`.

    Useful for dashboard queries that want to show "all cases in this
    investigation's window" without recomputing the bucket math.
    """
    idx = _bucket_index(dt)
    start = _BUCKET_EPOCH + timedelta(days=idx * _BUCKET_DAYS)
    return start, start + timedelta(days=_BUCKET_DAYS)
