"""Pillar-6 SLA-breach + batch-lateness monitor (PR-LF1 / #383).

Backs the Pillar-6 alert-lifecycle gap on the framework's North Star: the
engine evaluates two operational SLAs declared on `program.sla` and emits
a structured `sla_report.json` artifact in the run directory.

Two monitors, both pure functions of the spec + run inputs:

- **Alert SLA breach**: every `case_opened` decision in the audit ledger
  whose timestamp is older than `program.sla.alert_disposition_days` from
  `as_of` and which has no terminal decision (`closed` /
  `escalated_to_str`) for the same `case_id`. Returns per-rule breach
  counts so a 1LoD lead can prioritise the queue.
- **Batch lateness**: compare `as_of` to the most-recent transaction
  timestamp across every data contract in the run. If the gap exceeds
  `batch_cadence_days + batch_lateness_grace_days`, the run is flagged
  with the observed lateness in days.

The evaluator is **pure** and **engine-time** — it never mutates the
ledger and emits no events itself. The runner writes the report to
`run_dir/sla_report.json`; the audit bundle picks it up via `rglob`.
Absent `program.sla` block disables the monitor; the artifact is still
written (empty / zero values) so downstream surfaces can rely on its
presence — same posture as `dq_exceptions.jsonl` and
`field_lineage.jsonl`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aml_framework.engine.constants import Event
from aml_framework.spec.models import AMLSpec, ProgramSLA


# Terminal-decision events that close out a case for SLA purposes. Anything
# else (manual_review, escalated within the workflow, narrative_review, etc.)
# leaves the case open — those events still represent in-flight work.
_TERMINAL_EVENTS = frozenset({Event.CLOSED, Event.ESCALATED_TO_STR})


class _SLABase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AlertSLABreach(_SLABase):
    """One alert that breached `alert_disposition_days`."""

    case_id: str
    rule_id: str
    opened_at: datetime
    age_days: int


class SLAReport(_SLABase):
    """Run-level Pillar-6 SLA-monitor report.

    Always emitted in the run dir (possibly empty). Fields are stable
    across runs so dashboards can render a consistent shape.
    """

    enabled: bool = False
    alert_disposition_days: int | None = None
    batch_cadence_days: int | None = None
    batch_lateness_grace_days: int | None = None

    total_breaches: int = 0
    breaches_by_rule: dict[str, int] = Field(default_factory=dict)
    breaches: list[AlertSLABreach] = Field(default_factory=list)

    batch_lateness_days: int = 0
    batch_late: bool = False
    latest_transaction_at: datetime | None = None


def _coerce_datetime(value: Any) -> datetime | None:
    """Best-effort parse for an audit-ledger `ts` value or row timestamp.

    Mirrors `freshness._coerce_datetime` — same input shapes (datetime,
    date, ISO 8601 string), same fall-through behaviour. Returns None if
    the value is unparseable rather than raising; the caller skips
    unparseable rows (a malformed timestamp surfaces as a DQ event
    elsewhere, not as an SLA breach here).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        from datetime import date as _date

        if isinstance(value, _date):
            return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    except Exception:  # pragma: no cover - defensive
        pass
    # Python 3.10's `datetime.fromisoformat` rejects the `Z` UTC suffix
    # (3.11+ accepts it). The framework supports 3.10, and ISO 8601
    # timestamps from external sources (warehouse exports, JSON ingest)
    # commonly carry `Z` — normalise to `+00:00` so they parse on every
    # supported runtime. Codex P2 finding on PR-LF1.
    raw = str(value).replace(" ", "T", 1)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _naive(dt: datetime) -> datetime:
    """Drop tzinfo so two timestamps can be subtracted without mixing
    aware/naive. The runner stamps `as_of` in UTC; row timestamps may be
    naive or aware depending on the loader, so we normalise to naive
    comparison space (consistent with `engine/freshness.py`)."""
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _max_transaction_timestamp(
    data: dict[str, list[dict[str, Any]]],
) -> datetime | None:
    """Return the most-recent transaction timestamp across all contracts.

    Scans well-known timestamp column names (`booked_at`,
    `transaction_date`, `event_time`) — the framework's example specs
    consistently use `booked_at`; the other two names are accepted so
    operators with a different convention don't silently get a
    no-lateness signal. Returns None when no contract surfaces any of
    these columns (e.g. customer-only fixtures in unit tests).
    """
    candidates = ("booked_at", "transaction_date", "event_time")
    best: datetime | None = None
    for rows in data.values():
        for row in rows:
            for key in candidates:
                if key not in row:
                    continue
                ts = _coerce_datetime(row[key])
                if ts is None:
                    continue
                ts_naive = _naive(ts)
                if best is None or ts_naive > best:
                    best = ts_naive
    return best


def evaluate_sla(
    spec: AMLSpec,
    decisions: list[dict[str, Any]],
    data: dict[str, list[dict[str, Any]]],
    as_of: datetime,
) -> SLAReport:
    """Evaluate Pillar-6 SLAs against a run's audit ledger + input data.

    Returns a fully-populated `SLAReport` whether or not `program.sla`
    is set — the absent-block case returns `enabled=False` with zero
    counts so the artifact is always shape-stable. The function is pure
    (no I/O, no ledger writes); `engine/runner.py` is the single caller
    that persists the report.
    """
    sla: ProgramSLA | None = spec.program.sla
    if sla is None:
        return SLAReport()

    as_of_naive = _naive(as_of)

    # ----- Alert SLA: open cases older than `alert_disposition_days` ----
    # Build two indexes from the decisions stream so the breach query is
    # O(n) over events plus O(c) over cases:
    #   - `opened`: case_id -> (opened_at, rule_id) from CASE_OPENED.
    #   - `terminal`: case_ids whose terminal event happened ON OR
    #     BEFORE `as_of`. A close/STR stamped AFTER the report cutoff
    #     (simulation or out-of-order analyst action) means the case
    #     was still open at report time and must remain in the breach
    #     candidate pool. Codex pass-3 P2 on PR-LF1.
    opened: dict[str, tuple[datetime, str]] = {}
    terminal: set[str] = set()
    for event in decisions:
        event_kind = event.get("event")
        case_id = event.get("case_id")
        if not isinstance(case_id, str):
            continue
        if event_kind == Event.CASE_OPENED:
            ts = _coerce_datetime(event.get("ts"))
            if ts is None:
                continue
            # First case_opened wins — the audit ledger appends, but a
            # well-formed run only opens each case once.
            opened.setdefault(case_id, (ts, str(event.get("rule_id", ""))))
        elif event_kind in _TERMINAL_EVENTS:
            terminal_ts = _coerce_datetime(event.get("ts"))
            # Missing or unparseable timestamp → treat as terminal
            # (preserve the original behavior for legacy events that
            # predate the ts field).
            if terminal_ts is None or _naive(terminal_ts) <= as_of_naive:
                terminal.add(case_id)

    # Compare on the full elapsed timedelta, not the floored day count
    # — otherwise a case 10 days + 1 hour old with threshold=10d slips
    # past `.days > 10` (10 > 10 is False). The displayed `age_days` is
    # still the floored integer day count for human-friendly read-out.
    # Codex P2 pass-2 finding on PR-LF1.
    threshold_days = sla.alert_disposition_days
    threshold_td = timedelta(days=threshold_days)
    breaches: list[AlertSLABreach] = []
    breaches_by_rule: dict[str, int] = {}
    for case_id, (opened_at, rule_id) in opened.items():
        if case_id in terminal:
            continue
        elapsed = as_of_naive - _naive(opened_at)
        if elapsed > threshold_td:
            breaches.append(
                AlertSLABreach(
                    case_id=case_id,
                    rule_id=rule_id,
                    opened_at=opened_at,
                    age_days=elapsed.days,
                )
            )
            breaches_by_rule[rule_id] = breaches_by_rule.get(rule_id, 0) + 1

    # Stable ordering: oldest breach first, ties broken by case_id so the
    # JSON diff is byte-stable across re-runs (run reproducibility).
    breaches.sort(key=lambda b: (-b.age_days, b.case_id))

    # ----- Batch lateness: as_of vs latest transaction timestamp --------
    # Same full-timedelta posture as the alert SLA — sub-day overshoots
    # past `cadence + grace` must flag, even though the reported
    # `batch_lateness_days` is still the floored integer day count.
    latest_ts = _max_transaction_timestamp(data)
    lateness_days = 0
    batch_late = False
    lateness_budget_days = sla.batch_cadence_days + sla.batch_lateness_grace_days
    lateness_budget_td = timedelta(days=lateness_budget_days)
    if latest_ts is not None:
        gap = as_of_naive - latest_ts
        if gap.total_seconds() > 0:
            lateness_days = gap.days
        if gap > lateness_budget_td:
            batch_late = True

    return SLAReport(
        enabled=True,
        alert_disposition_days=sla.alert_disposition_days,
        batch_cadence_days=sla.batch_cadence_days,
        batch_lateness_grace_days=sla.batch_lateness_grace_days,
        total_breaches=len(breaches),
        breaches_by_rule=dict(sorted(breaches_by_rule.items())),
        breaches=breaches,
        batch_lateness_days=lateness_days,
        batch_late=batch_late,
        latest_transaction_at=latest_ts,
    )
