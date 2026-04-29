"""Daily/hourly alert digest for Slack + Teams.

Process problem this solves
---------------------------
Today, when an analyst escalates a case to L2 — or when an SLA timer
breaches — the only way the supervisor finds out is by opening the
dashboard. So they don't, until end-of-day. Cases drift past SLA;
critical alerts sit unread. The fix is a push: a digest into the
team's Slack / Teams channel showing what crossed the line in the
last N hours.

Existing `integrations/notifications.py` already has per-event
hooks (notify_alert, notify_sla_breach) — useful when you want a
ping per event but noisy at scale. This module adds the **digest**
mode: aggregate everything in a window, format one rich message, post
once. Run via cron or ad-hoc from the CLI.

Design notes
------------
- Pure-function aggregator (`build_digest`) so tests don't need a
  webhook server. Renderer + sender are split so a future operator
  can pipe to email or PagerDuty without touching the rollup logic.
- Window is computed against the engine's `as_of`, not wall clock —
  digests are reproducible like the rest of the framework. Rerunning
  `aml notify-digest` over the same run dir + same window produces
  the same message.
- Quiet defaults: when nothing crossed the line in the window, the
  digest is a one-line "all clear" rather than empty. Cron jobs that
  page on missing output break less.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Literal

DigestPlatform = Literal["slack", "teams"]


@dataclass(frozen=True)
class DigestEntry:
    """One row in the digest — an escalation, breach, or notable alert."""

    kind: Literal["alert", "escalation", "sla_breach"]
    severity: str
    case_id: str
    customer_id: str
    rule_id: str
    occurred_at: str  # ISO 8601
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "case_id": self.case_id,
            "customer_id": self.customer_id,
            "rule_id": self.rule_id,
            "occurred_at": self.occurred_at,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class DigestPayload:
    """Rolled-up summary for a single window."""

    program_name: str
    window_hours: int
    window_end: str  # ISO 8601
    entries: list[DigestEntry] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.entries)

    @property
    def by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.entries:
            counts[e.severity] = counts.get(e.severity, 0) + 1
        return counts

    @property
    def critical_entries(self) -> list[DigestEntry]:
        return [e for e in self.entries if e.severity == "critical"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_name": self.program_name,
            "window_hours": self.window_hours,
            "window_end": self.window_end,
            "total": self.total,
            "by_severity": self.by_severity,
            "entries": [e.to_dict() for e in self.entries],
        }


# ---------------------------------------------------------------------------
# Building the digest
# ---------------------------------------------------------------------------


# Map decision-event names → DigestEntry.kind. Anything not mapped here
# is ignored — keeps the digest focused on what a supervisor cares
# about (escalations, SLA breaches), not noise (case_opened on every
# alert).
_EVENT_KIND_MAP: dict[str, str] = {
    "escalated": "escalation",
    "escalated_to_str": "escalation",
    "sla_breach": "sla_breach",
}


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00").replace("+00:00", ""))
    except ValueError:
        return None


def build_digest(
    run_dir: Path,
    *,
    program_name: str,
    window_hours: int = 24,
    as_of: datetime | None = None,
) -> DigestPayload:
    """Aggregate notable events from `run_dir/decisions.jsonl` in the window.

    Window is `[as_of - window_hours, as_of]`. When `as_of` is None,
    falls back to the most recent timestamp in the ledger so a digest
    over a deterministic test run produces deterministic output.

    Returns a `DigestPayload` with one entry per escalation, SLA
    breach, or critical-severity alert that occurred in the window.
    """
    decisions_path = run_dir / "decisions.jsonl"
    if not decisions_path.exists():
        return DigestPayload(
            program_name=program_name,
            window_hours=window_hours,
            window_end=(as_of or datetime.utcnow()).isoformat(),
        )

    rows: list[dict[str, Any]] = []
    for line in decisions_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))

    if as_of is None:
        ts = [_parse_iso(r.get("ts")) for r in rows]
        valid = [t for t in ts if t is not None]
        as_of = max(valid) if valid else datetime.utcnow()

    window_start = as_of - timedelta(hours=window_hours)
    entries: list[DigestEntry] = []

    for row in rows:
        occurred = _parse_iso(row.get("ts"))
        if occurred is None or occurred < window_start or occurred > as_of:
            continue
        event = row.get("event", "")
        kind = _EVENT_KIND_MAP.get(event)
        # Critical-severity alerts get included as kind="alert" even if
        # the event isn't escalation — supervisors want to see them.
        if kind is None and row.get("severity") != "critical":
            continue
        if kind is None:
            kind = "alert"
        entries.append(
            DigestEntry(
                kind=kind,  # type: ignore[arg-type]
                severity=row.get("severity") or "unknown",
                case_id=row.get("case_id", ""),
                customer_id=row.get("customer_id", ""),
                rule_id=row.get("rule_id", ""),
                occurred_at=row.get("ts", ""),
                detail=row.get("note") or row.get("detail", ""),
            )
        )

    return DigestPayload(
        program_name=program_name,
        window_hours=window_hours,
        window_end=as_of.isoformat(),
        entries=entries,
    )


# ---------------------------------------------------------------------------
# Rendering for Slack / Teams
# ---------------------------------------------------------------------------


_SEVERITY_EMOJI = {
    "critical": "🚨",
    "high": "🔴",
    "medium": "🟠",
    "low": "🟢",
}


def render_slack_text(payload: DigestPayload) -> str:
    """Render a Slack-flavoured markdown message. Designed for a single
    `chat.postMessage` block — supervisors read these on phones."""
    if payload.total == 0:
        return (
            f"*AML Digest · {payload.program_name}* "
            f"({payload.window_hours}h ending {payload.window_end[:16]})\n"
            "✅ All clear — no escalations, breaches, or critical alerts."
        )

    lines = [
        f"*AML Digest · {payload.program_name}* "
        f"({payload.window_hours}h ending {payload.window_end[:16]})",
        f"Total events: *{payload.total}*",
    ]
    counts = payload.by_severity
    severity_line = " · ".join(
        f"{_SEVERITY_EMOJI.get(s, '·')} {s}: {n}"
        for s, n in sorted(
            counts.items(),
            key=lambda kv: (
                ["critical", "high", "medium", "low"].index(kv[0])
                if kv[0] in ["critical", "high", "medium", "low"]
                else 99
            ),
        )
    )
    lines.append(severity_line)
    lines.append("")

    # Show critical first, then up to 10 of the rest. More than that
    # belongs in the dashboard; Slack messages get truncated past ~3KB.
    for e in payload.critical_entries[:10]:
        lines.append(_format_entry_line(e))
    non_critical = [e for e in payload.entries if e.severity != "critical"]
    for e in non_critical[: max(0, 10 - len(payload.critical_entries))]:
        lines.append(_format_entry_line(e))
    if payload.total > 10:
        lines.append(f"…and {payload.total - 10} more — see dashboard.")
    return "\n".join(lines)


def _format_entry_line(e: DigestEntry) -> str:
    emoji = _SEVERITY_EMOJI.get(e.severity, "·")
    kind_label = {
        "alert": "alert",
        "escalation": "escalated",
        "sla_breach": "SLA breach",
    }.get(e.kind, e.kind)
    return (
        f"{emoji} *{kind_label}* · `{e.rule_id or '?'}` "
        f"· customer `{e.customer_id or '?'}` "
        f"· case `{e.case_id or '?'}`"
    )


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------


def post_digest(
    payload: DigestPayload,
    *,
    platforms: Iterable[DigestPlatform] = ("slack", "teams"),
    suppress_when_empty: bool = False,
) -> dict[str, bool]:
    """Post the digest to configured webhooks. Returns per-platform send result.

    `suppress_when_empty=True` skips the send when the digest is empty —
    useful for quiet hours where supervisors don't want a "no news"
    ping. Default False because a periodic digest is also a heartbeat:
    the absence of one is its own signal.
    """
    if suppress_when_empty and payload.total == 0:
        return {p: False for p in platforms}

    text = render_slack_text(payload)
    sent: dict[str, bool] = {}
    for platform in platforms:
        try:
            if platform == "slack":
                from aml_framework.integrations.notifications import _send_slack

                _send_slack(text)
                sent["slack"] = True
            elif platform == "teams":
                from aml_framework.integrations.notifications import _send_teams

                _send_teams(text)
                sent["teams"] = True
        except Exception:
            sent[platform] = False
    return sent
