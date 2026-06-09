"""FinCEN Whistleblower internal-channel audit report (#531).

OFFLINE, post-run compliance-readiness lens. Reads a finalized run
directory (manifest + decisions.jsonl + cases/) and rolls five
governance signals into a frozen `WhistleblowerAuditReport`:

  * `sar_backlog_exposure`  — open alerts older than 30 days that were
    never resolved to a SAR or a documented non-suspicious disposition.
  * `escalation_coverage_pct` — share of human-disposition decisions that
    carry a documented reviewer AND rationale (vs system-auto).
  * `triage_time` — alert-to-decision distribution (median + p95, days).
  * `board_documented_decisions` — alert decisions tied to a board-report
    event in the ledger.
  * `ledger_integrity` — "verified" / "broken" from the hash chain.

Source / motivation: FinCEN's proposed Whistleblower Incentives and
Protections rule (Federal Register 2026-06271,
https://www.federalregister.gov/documents/2026/04/01/2026-06271/whistleblower-incentives-and-protections),
which presses institutions to demonstrate that an internal reporting
channel exists, that triage is timely, and that escalations reach the
board. This report is the readiness mirror of that ask, computed only
from artifacts a run already produced.

Governance: ADVISORY ONLY. Never blocks or changes a run, never
auto-dispositions an alert. Pure + deterministic — `as_of` is anchored
to the run's `manifest.json`; there is no `datetime.now()` on the report
path. Stdlib + pydantic, never imported by the engine run path.

A signal that a run simply does not record (e.g. board-report events,
or human reviewer metadata in a synthetic run) is reported as 0 /
not-tracked — it is NEVER fabricated.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from aml_framework.engine.audit import AuditLedger
from aml_framework.engine.constants import Event

# An alert open longer than this (days, measured from the run's `as_of`)
# without a resolving disposition is "stale backlog". 30 days mirrors the
# SAR filing clock investigators work against.
STALE_BACKLOG_DAYS = 30

# Decision events that represent a *human disposition* of an alert — the
# population escalation-coverage and triage-time are computed over.
# `case_opened` (engine bookkeeping) and `environment_gate_check`
# (promotion gate) are excluded.
_DISPOSITION_EVENTS = frozenset(
    {Event.ESCALATED, Event.ESCALATED_TO_STR, Event.CLOSED, Event.MANUAL_REVIEW}
)

# Field names that, when present + non-empty on a decision event, count as
# a documented human reviewer (an identity that took the decision).
_REVIEWER_FIELDS = ("reviewer", "reviewed_by", "analyst", "override_by", "decided_by")

# Field names that, when present + non-empty, count as a documented
# rationale for the decision.
_RATIONALE_FIELDS = ("rationale", "override_reason", "narrative", "reason", "justification")

# `source` values that denote a human-driven decision (vs the engine
# auto-simulating a disposition). The dashboard stamps `dashboard_ui`.
_HUMAN_SOURCES = frozenset({"dashboard_ui", "analyst", "investigator"})

# Event names (or `source` markers) that denote a board-level escalation /
# board-report being recorded against an alert decision.
_BOARD_MARKERS = ("board_report", "board_review", "board_escalation")


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SarBacklogExposure(_Base):
    open_stale_alerts: int
    oldest_days: int  # 0 when there is no stale backlog


class TriageTime(_Base):
    median_days: float | None  # None when no disposition decisions exist
    p95_days: float | None
    n_decisions: int


class WhistleblowerAuditReport(_Base):
    enabled: bool
    sar_backlog_exposure: SarBacklogExposure
    escalation_coverage_pct: float  # 0.0–100.0
    n_disposition_decisions: int
    triage_time: TriageTime
    board_documented_decisions: int
    board_reporting_tracked: bool  # False => 0 is "not-tracked", not "zero board reports"
    ledger_integrity: str  # "verified" | "broken"
    ledger_integrity_detail: str
    generated_at: datetime


def _read_decisions(run_dir: Path) -> list[dict[str, Any]]:
    """Load decisions.jsonl as a list of events, skipping blank/malformed lines.

    Malformed lines are skipped rather than raised on — the report is a
    read-only lens and a single bad line must not crash it (the ledger
    hash-chain check is the authoritative tamper signal).
    """
    path = run_dir / "decisions.jsonl"
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            out.append(event)
    return out


def _parse_ts(value: Any) -> datetime | None:
    """Parse an ISO-8601 `ts` into a naive UTC datetime (matching `as_of`)."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _has_reviewer_and_rationale(event: dict[str, Any]) -> bool:
    """True when the decision carries BOTH a documented reviewer identity and
    a documented rationale. A `source` in `_HUMAN_SOURCES` satisfies the
    reviewer half (the dashboard stamps the actor as `source`)."""
    has_reviewer = (
        any(str(event.get(f, "")).strip() for f in _REVIEWER_FIELDS)
        or str(event.get("source", "")).strip() in _HUMAN_SOURCES
    )
    has_rationale = any(str(event.get(f, "")).strip() for f in _RATIONALE_FIELDS)
    return has_reviewer and has_rationale


def _is_board_event(event: dict[str, Any]) -> bool:
    event_name = str(event.get("event", ""))
    source = str(event.get("source", ""))
    return any(m in event_name or m in source for m in _BOARD_MARKERS)


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Nearest-rank percentile over a non-empty sorted list. Deterministic
    (no interpolation ambiguity) and stdlib-only."""
    if not sorted_vals:
        raise ValueError("percentile of empty sequence")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    rank = max(1, min(len(sorted_vals), round(pct / 100.0 * len(sorted_vals) + 0.5)))
    return sorted_vals[rank - 1]


def _median(sorted_vals: list[float]) -> float:
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return sorted_vals[mid]
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0


def build_whistleblower_audit_report(
    run_dir: Path,
    *,
    generated_at: datetime,
) -> WhistleblowerAuditReport:
    """Compute the whistleblower-audit report from a run directory.

    Pure + deterministic: every value derives from `run_dir`'s artifacts
    and the supplied `generated_at` (anchor it to `manifest.json`'s
    `as_of`). No clock reads on this path.
    """
    decisions = _read_decisions(run_dir)

    # --- per-case open time + terminal disposition --------------------
    # First `case_opened` ts per case (alert birth), and the EARLIEST
    # terminal disposition ts per case (alert resolution). A case may have
    # several human dispositions; the first terminal one stops the clock.
    # A SAR/STR escalation and a documented non-suspicious close are BOTH
    # terminal dispositions (they're all in `_DISPOSITION_EVENTS`), so a case
    # landing in `resolved_at` is — by definition — no longer SAR backlog.
    opened_at: dict[str, datetime] = {}
    resolved_at: dict[str, datetime] = {}
    resolution_hours: dict[str, float] = {}

    for event in decisions:
        case_id = event.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            continue
        name = event.get("event")
        ts = _parse_ts(event.get("ts"))
        if name == Event.CASE_OPENED:
            if ts is not None and (case_id not in opened_at or ts < opened_at[case_id]):
                opened_at[case_id] = ts
        elif name in _DISPOSITION_EVENTS:
            if ts is not None and (case_id not in resolved_at or ts < resolved_at[case_id]):
                resolved_at[case_id] = ts
                # Capture the engine-stamped resolution_hours alongside the
                # winning (earliest) terminal event for a deterministic
                # triage time even when ts precision differs.
                rh = event.get("resolution_hours")
                if isinstance(rh, (int, float)):
                    resolution_hours[case_id] = float(rh)
                else:
                    resolution_hours.pop(case_id, None)

    # --- SAR backlog exposure -----------------------------------------
    # An alert (case) is stale-backlog when it has NO terminal disposition
    # AND its age from `as_of` exceeds STALE_BACKLOG_DAYS. A case resolved
    # to a SAR or any documented disposition is, by definition, not backlog.
    stale_days: list[int] = []
    for case_id, opened in opened_at.items():
        if case_id in resolved_at:
            continue  # documented disposition (SAR or non-suspicious close)
        age_days = (generated_at - opened).total_seconds() / 86400.0
        if age_days > STALE_BACKLOG_DAYS:
            stale_days.append(int(age_days))
    backlog = SarBacklogExposure(
        open_stale_alerts=len(stale_days),
        oldest_days=max(stale_days) if stale_days else 0,
    )

    # --- escalation coverage ------------------------------------------
    disposition_events = [e for e in decisions if e.get("event") in _DISPOSITION_EVENTS]
    n_disp = len(disposition_events)
    n_documented = sum(1 for e in disposition_events if _has_reviewer_and_rationale(e))
    escalation_coverage_pct = round(100.0 * n_documented / n_disp, 2) if n_disp else 0.0

    # --- triage time ---------------------------------------------------
    # Alert-to-decision per resolved case, in days. Prefer the engine's
    # `resolution_hours` (deterministic, captured at decision time); fall
    # back to the ts delta from case_opened to the terminal decision.
    triage_days: list[float] = []
    for case_id, resolved in resolved_at.items():
        if case_id in resolution_hours:
            triage_days.append(resolution_hours[case_id] / 24.0)
        elif case_id in opened_at:
            delta = (resolved - opened_at[case_id]).total_seconds() / 86400.0
            if delta >= 0:
                triage_days.append(delta)
    triage_days.sort()
    triage = TriageTime(
        median_days=round(_median(triage_days), 3) if triage_days else None,
        p95_days=round(_percentile(triage_days, 95.0), 3) if triage_days else None,
        n_decisions=len(triage_days),
    )

    # --- board-documented decisions -----------------------------------
    # Count disposition decisions whose case also has a board-report event
    # in the ledger. If NO board markers appear anywhere, board reporting
    # is "not tracked" by this run — report 0 honestly, don't fabricate.
    board_events = [e for e in decisions if _is_board_event(e)]
    board_reporting_tracked = bool(board_events)
    board_case_ids = {e.get("case_id") for e in board_events if isinstance(e.get("case_id"), str)}
    board_documented = sum(1 for e in disposition_events if e.get("case_id") in board_case_ids)

    # --- ledger integrity ---------------------------------------------
    ok, detail = AuditLedger.verify_decisions(run_dir)
    integrity = "verified" if ok else "broken"

    return WhistleblowerAuditReport(
        enabled=True,
        sar_backlog_exposure=backlog,
        escalation_coverage_pct=escalation_coverage_pct,
        n_disposition_decisions=n_disp,
        triage_time=triage,
        board_documented_decisions=board_documented,
        board_reporting_tracked=board_reporting_tracked,
        ledger_integrity=integrity,
        ledger_integrity_detail=detail,
        generated_at=generated_at,
    )


def render_whistleblower_markdown(report: WhistleblowerAuditReport) -> str:
    """Pipe-table board-report summary of the audit report. Deterministic."""
    b = report.sar_backlog_exposure
    t = report.triage_time
    median = "n/a" if t.median_days is None else f"{t.median_days:g}"
    p95 = "n/a" if t.p95_days is None else f"{t.p95_days:g}"
    board = (
        str(report.board_documented_decisions) if report.board_reporting_tracked else "not tracked"
    )
    lines = [
        "# Whistleblower internal-channel audit",
        "",
        f"_Generated at {report.generated_at.isoformat()} (anchored to run as_of)._",
        "",
        "| Signal | Value |",
        "| --- | --- |",
        f"| SAR backlog — open stale alerts (>{STALE_BACKLOG_DAYS}d) | {b.open_stale_alerts} |",
        f"| SAR backlog — oldest (days) | {b.oldest_days} |",
        f"| Escalation coverage (documented reviewer + rationale) | "
        f"{report.escalation_coverage_pct:g}% "
        f"({report.n_disposition_decisions} disposition decisions) |",
        f"| Triage time — median (days) | {median} |",
        f"| Triage time — p95 (days) | {p95} |",
        f"| Board-documented decisions | {board} |",
        f"| Ledger integrity | {report.ledger_integrity} |",
        "",
        "_Advisory readiness lens — never blocks or changes a run. "
        "Source: Federal Register 2026-06271._",
        "",
    ]
    return "\n".join(lines)


def render_nprm_gap_markdown(
    report: WhistleblowerAuditReport,
    *,
    backlog_threshold: int = 0,
    median_triage_threshold_days: float = float(STALE_BACKLOG_DAYS),
) -> str:
    """Structured gap table against the NPRM's proposed expectations.

    Each row maps a proposed requirement to ✓ / ⚠ / ✗ with the evidence
    field that decided it. Thresholds are explicit (and overridable) so the
    verdict is auditable, not a black box.
    """
    b = report.sar_backlog_exposure
    t = report.triage_time

    # 1) Internal reporting channels documented => ledger integrity verified
    #    (the immutable, hash-chained channel of record exists + is intact).
    if report.ledger_integrity == "verified":
        chan_mark, chan_ev = "✓", "ledger_integrity=verified"
    else:
        chan_mark, chan_ev = "✗", f"ledger_integrity={report.ledger_integrity}"

    # 2) Median triage < threshold days.
    if t.median_days is None:
        triage_mark = "⚠"
        triage_ev = "triage_time.median_days=n/a (no disposition decisions)"
    elif t.median_days < median_triage_threshold_days:
        triage_mark = "✓"
        triage_ev = f"triage_time.median_days={t.median_days:g}"
    else:
        triage_mark = "✗"
        triage_ev = f"triage_time.median_days={t.median_days:g}"

    # 3) SAR backlog under threshold.
    if b.open_stale_alerts <= backlog_threshold:
        backlog_mark = "✓"
    else:
        backlog_mark = "✗"
    backlog_ev = f"sar_backlog_exposure.open_stale_alerts={b.open_stale_alerts}"

    # 4) Board-level escalation documented.
    if not report.board_reporting_tracked:
        board_mark = "⚠"
        board_ev = "board_documented_decisions=not tracked"
    elif report.board_documented_decisions > 0:
        board_mark = "✓"
        board_ev = f"board_documented_decisions={report.board_documented_decisions}"
    else:
        board_mark = "✗"
        board_ev = "board_documented_decisions=0"

    rows = [
        ("Internal reporting channel documented", chan_mark, chan_ev),
        (
            f"Median triage < {median_triage_threshold_days:g}d",
            triage_mark,
            triage_ev,
        ),
        (f"SAR backlog ≤ {backlog_threshold}", backlog_mark, backlog_ev),
        ("Board-level escalation documented", board_mark, board_ev),
    ]
    lines = [
        "# Whistleblower NPRM readiness gap (FR 2026-06271)",
        "",
        "| Proposed requirement | Status | Evidence |",
        "| --- | :---: | --- |",
    ]
    lines.extend(f"| {req} | {mark} | `{ev}` |" for req, mark, ev in rows)
    lines.append("")
    lines.append("_✓ met · ⚠ not tracked in this run · ✗ gap. Advisory readiness lens only._")
    lines.append("")
    return "\n".join(lines)
