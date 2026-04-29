"""`aml today` — per-persona morning checklist.

Process problem this solves
---------------------------
A CCO or MLRO walks into Monday with no unified picture of what
needs their attention. They read 4 dashboards, refresh 3 spreadsheets,
ask 2 people for status. Important things slip — not because nobody
saw them, but because nobody saw them *all*.

This module reads the live program state (last run dir + audit
ledger + cases) and produces a one-page checklist tailored to the
asker's persona. CCO sees board-relevant signal; MLRO sees model-
challenge work; Analyst sees their own queue.

Pure-function over the engine output. The CLI command renders the
checklist to the terminal; the same `build_checklist` underwrites a
future dashboard widget or email digest without changing the logic.

Persona checklists
------------------
CCO       — exam readiness, audit chain, drift, board signals
MLRO      — model challenge, threshold proposals, sign-offs pending
Director  — backlog status, breach rate trend, queue health
Manager   — operational triage today
Analyst   — your queue, your aging cases
Auditor   — what's new since last review

Quiet defaults: when the picture is clean, the checklist is a
one-line "all-good" rather than empty.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

Persona = Literal["cco", "mlro", "director", "manager", "analyst", "auditor", "cto", "svp"]

# What kind of attention each item is asking for. Drives the checkbox
# rendering in the terminal output and the priority ordering.
ItemKind = Literal[
    "exam_readiness",
    "queue_health",
    "model_challenge",
    "audit_chain",
    "regulation_drift",
    "queue_backlog",
    "case_drilldown",
    "review_pending",
]


@dataclass(frozen=True)
class ChecklistItem:
    """One actionable line on the checklist."""

    kind: ItemKind
    headline: str  # short summary, e.g. "3 cases breaching SLA"
    detail: str  # 1-2 sentence elaboration the persona reads next
    severity: Literal["critical", "high", "medium", "info"] = "info"
    suggested_action: str = ""  # optional CLI command or page path

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "headline": self.headline,
            "detail": self.detail,
            "severity": self.severity,
            "suggested_action": self.suggested_action,
        }


@dataclass(frozen=True)
class Checklist:
    """A persona's full Today checklist."""

    persona: Persona
    program_name: str
    generated_at: str  # ISO 8601
    items: list[ChecklistItem] = field(default_factory=list)

    @property
    def critical_items(self) -> list[ChecklistItem]:
        return [i for i in self.items if i.severity == "critical"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona": self.persona,
            "program_name": self.program_name,
            "generated_at": self.generated_at,
            "items": [i.to_dict() for i in self.items],
        }


# ---------------------------------------------------------------------------
# Load run state — pure-function readers; no side effects
# ---------------------------------------------------------------------------


def _load_decisions(run_dir: Path) -> list[dict[str, Any]]:
    p = run_dir / "decisions.jsonl"
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _load_cases(run_dir: Path) -> list[dict[str, Any]]:
    cases_dir = run_dir / "cases"
    if not cases_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for f in sorted(cases_dir.glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    p = run_dir / "manifest.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_bytes())
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------------------
# Item generators (one per signal we look at)
# ---------------------------------------------------------------------------


def _critical_alerts_overnight(
    decisions: list[dict[str, Any]], window_hours: int = 24
) -> ChecklistItem | None:
    """Critical-severity alerts in the last `window_hours`."""
    if not decisions:
        return None
    last_ts = max(_parse_iso(d.get("ts")) or datetime.min for d in decisions)
    cutoff = last_ts - timedelta(hours=window_hours)
    crits = [
        d
        for d in decisions
        if (_parse_iso(d.get("ts")) or datetime.min) >= cutoff and d.get("severity") == "critical"
    ]
    if not crits:
        return None
    return ChecklistItem(
        kind="exam_readiness",
        headline=f"{len(crits)} critical alert(s) in the last {window_hours}h",
        detail=(
            "These are the alerts the CCO would not want to read about in an examiner letter first."
        ),
        severity="critical",
        suggested_action="aml dashboard <spec> # → Alert Queue",
    )


def _sla_breaches(decisions: list[dict[str, Any]]) -> ChecklistItem | None:
    """Decisions with event=sla_breach since the last digest cutoff."""
    breaches = [d for d in decisions if d.get("event") == "sla_breach"]
    if not breaches:
        return None
    return ChecklistItem(
        kind="queue_backlog",
        headline=f"{len(breaches)} SLA breach event(s) on the ledger",
        detail=(
            "Cases that aged past their queue's promised time. The FCA "
            "Mar-2026 Dear-CEO letter on SAR backlogs makes this an exam item."
        ),
        severity="high",
        suggested_action="aml dashboard <spec>  # → Investigations → backlog table",
    )


def _aging_cases(cases: list[dict[str, Any]], threshold_days: int = 7) -> ChecklistItem | None:
    """Cases open longer than `threshold_days`."""
    aged = []
    for c in cases:
        opened = _parse_iso(c.get("opened_at") or (c.get("alert") or {}).get("window_end"))
        if opened is None:
            continue
        if (datetime.utcnow() - opened).days >= threshold_days:
            aged.append(c)
    if not aged:
        return None
    return ChecklistItem(
        kind="queue_backlog",
        headline=f"{len(aged)} case(s) older than {threshold_days} days",
        detail=(
            "Cases are aging in the queue. Each one is its own audit question; clear or escalate."
        ),
        severity="high" if len(aged) >= 5 else "medium",
        suggested_action="aml dashboard <spec>  # → Investigations",
    )


def _regulation_drift_hint() -> ChecklistItem:
    """Always-suggested CCO/MLRO item — encourages the weekly cron."""
    return ChecklistItem(
        kind="regulation_drift",
        headline="Re-run regulation-drift watcher",
        detail=(
            "FinCEN BOI was silently narrowed in March 2025; the watcher "
            "catches that pattern. Cron weekly."
        ),
        severity="info",
        suggested_action="aml regwatch <spec>",
    )


def _audit_chain_check() -> ChecklistItem:
    """CCO/Auditor item — verify the chain is intact."""
    return ChecklistItem(
        kind="audit_chain",
        headline="Verify the hash chain on today's run",
        detail=(
            "If the chain breaks, every downstream attestation fails. The "
            "Audit & Evidence page does this in one click."
        ),
        severity="info",
        suggested_action="aml dashboard <spec>  # → Audit & Evidence → 🔒 Re-verify",
    )


def _model_challenge_hint(rules_count: int) -> ChecklistItem | None:
    """MLRO item — back a rule's effectiveness with evidence."""
    if rules_count < 1:
        return None
    return ChecklistItem(
        kind="model_challenge",
        headline=f"Backtest one of your {rules_count} rules this week",
        detail=(
            "Pick the rule whose precision/recall you'd most struggle to "
            "defend at the next exam. The backtester returns the SR-26-2 "
            "evidence in one command."
        ),
        severity="info",
        suggested_action="aml backtest <spec> --rule <id> --quarters 4",
    )


def _exam_readiness_hint() -> ChecklistItem:
    return ChecklistItem(
        kind="exam_readiness",
        headline="Build the auditor pack — pre-empt the next walk-in",
        detail=(
            "One ZIP, chain-verified, jurisdiction-mapped. Keep it on a "
            "shared drive so the auditor downloads it themselves."
        ),
        severity="info",
        suggested_action="aml auditor-pack <spec> --print-link",
    )


def _all_clear(persona: Persona) -> ChecklistItem:
    """Single item shown when nothing notable is happening."""
    return ChecklistItem(
        kind="queue_health",
        headline="✅ All clear",
        detail=(
            f"No critical alerts, breaches, or aging cases in the last 24h. "
            f"Routine {persona.upper()} review pages still apply, but no fires today."
        ),
        severity="info",
    )


# ---------------------------------------------------------------------------
# Composer
# ---------------------------------------------------------------------------


def _parse_iso(s: Any) -> datetime | None:
    if not isinstance(s, str) or not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00").replace("+00:00", ""))
    except ValueError:
        return None


# Per-persona signal mix — defines what each role's checklist focuses on.
# Each entry is a list of "item generator" functions taking the loaded
# state and returning a ChecklistItem or None. `None` items are filtered.
PersonaSignal = Literal["critical", "sla", "aging", "regwatch", "audit", "challenge", "exam"]

PERSONA_SIGNALS: dict[str, list[PersonaSignal]] = {
    "cco": ["critical", "sla", "aging", "regwatch", "audit", "exam"],
    "mlro": ["challenge", "regwatch", "critical", "audit"],
    "director": ["critical", "sla", "aging"],
    "manager": ["sla", "aging", "critical"],
    "analyst": ["aging", "critical"],
    "auditor": ["audit", "regwatch", "exam"],
    "cto": ["audit", "regwatch", "exam"],
    "svp": ["critical", "sla", "aging", "exam"],
}


def build_checklist(
    *,
    persona: Persona,
    spec: Any,
    run_dir: Path | None,
) -> Checklist:
    """Build the persona's checklist from live run state.

    `run_dir=None` produces a checklist of always-applicable hints
    (the operator hasn't run the engine yet), so the new-bank case
    isn't blank.
    """
    decisions = _load_decisions(run_dir) if run_dir else []
    cases = _load_cases(run_dir) if run_dir else []
    rules_count = len(spec.rules) if hasattr(spec, "rules") else 0

    signals = PERSONA_SIGNALS.get(persona, ["critical", "sla", "aging"])
    items: list[ChecklistItem] = []
    seen_kinds: set[str] = set()

    for signal in signals:
        item: ChecklistItem | None = None
        if signal == "critical":
            item = _critical_alerts_overnight(decisions)
        elif signal == "sla":
            item = _sla_breaches(decisions)
        elif signal == "aging":
            item = _aging_cases(cases)
        elif signal == "regwatch":
            item = _regulation_drift_hint()
        elif signal == "audit":
            item = _audit_chain_check()
        elif signal == "challenge":
            item = _model_challenge_hint(rules_count)
        elif signal == "exam":
            item = _exam_readiness_hint()
        if item is None or item.kind in seen_kinds:
            continue
        items.append(item)
        seen_kinds.add(item.kind)

    if not items:
        items.append(_all_clear(persona))

    # Sort by severity rank (critical first), keeping insertion order
    # for ties.
    rank = {"critical": 0, "high": 1, "medium": 2, "info": 3}
    items.sort(key=lambda i: rank.get(i.severity, 99))

    program_name = getattr(getattr(spec, "program", None), "name", "(no program)")
    return Checklist(
        persona=persona,
        program_name=program_name,
        generated_at=datetime.utcnow().isoformat(),
        items=items,
    )


# ---------------------------------------------------------------------------
# Rendering — terminal-friendly checklist
# ---------------------------------------------------------------------------


_SEVERITY_BADGE = {
    "critical": "🚨",
    "high": "🔴",
    "medium": "🟠",
    "info": "ℹ",
}


def render_checklist_text(checklist: Checklist) -> str:
    """Plain-text render — pipes nicely into email or stdout."""
    lines = [
        f"# Today · {checklist.persona.upper()} · {checklist.program_name}",
        f"# Generated {checklist.generated_at}",
        "",
    ]
    for i, item in enumerate(checklist.items, start=1):
        badge = _SEVERITY_BADGE.get(item.severity, "·")
        lines.append(f"[{i}] {badge} {item.headline}")
        lines.append(f"    {item.detail}")
        if item.suggested_action:
            lines.append(f"    → {item.suggested_action}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
