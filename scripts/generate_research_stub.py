#!/usr/bin/env python3
"""Deterministic monthly research-doc STUB generator (#512).

Why this exists: the ``docs/research/`` editions are refreshed monthly by a
human author. The mechanical scaffolding around each edition — the header,
the forward-deadline countdown, and "what changed since last month" relative
to the regulatory calendar — is deterministic and should not be re-typed by
hand. This script generates that scaffolding as a *stub* with explicit
``TODO(human)`` placeholders for the analytical prose. The monthly
``monthly-research-refresh`` GitHub Actions workflow runs it on the 1st of
each month and opens a DRAFT PR; a human completes the prose and the
primary-source citations.

Hard constraints (compliance-sensitive):

* **Deterministic + no network.** Given ``--month YYYY-MM`` the output is a
  pure function of the packaged regulatory calendar. There is NO
  ``datetime.now()``/``date.today()`` in the generation path — the only use
  of today's date is the *argparse default* for ``--month``. All logic uses
  the resolved month string.
* **Single source of truth for the calendar.** The forward deadlines live in
  ``src/aml_framework/dashboard/regulatory_calendar.yaml`` and are loaded by
  the pure ``aml_framework.dashboard.regulatory_calendar`` module (no
  streamlit at module level). This script REUSES that module — it never reads
  the yaml directly.
* **Never fabricate citations.** The stub leaves analytical prose and
  primary-source citations as ``TODO(human)`` placeholders. The only URLs it
  emits are the authoritative ``source_url`` values from the calendar.
* **Never clobber.** If the target edition file already exists the script
  prints a message and exits 0 without overwriting (idempotent).

Usage:
    python scripts/generate_research_stub.py --month 2026-07
    python scripts/generate_research_stub.py --month 2026-07 --out-dir docs/research
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from aml_framework.dashboard.regulatory_calendar import (
    Deadline,
    active_deadlines,
    days_remaining,
    load_calendar,
    urgency_band,
)

# Band ordering, tightest last. "expired" is computed here (days < 0) — the
# calendar module's urgency_band() only classifies non-negative days, so this
# script treats already-passed deadlines as their own tightest band.
_BAND_RANK: dict[str, int] = {"info": 0, "warning": 1, "error": 2, "expired": 3}

DEFAULT_OUT_DIR = "docs/research"
DEFAULT_SLUG = "aml-data-problem"
DEFAULT_TITLE = "Data is the AML problem"
AUDIENCE = "CCO / MLRO / Head of Financial Crime / CRO / 2LoD model-validation"


def _default_month() -> str:
    """argparse default ONLY — the generation path uses the resolved value."""
    return date.today().strftime("%Y-%m")


def month_anchor(month: str) -> date:
    """First day of ``YYYY-MM`` — the as-of anchor for this edition."""
    year, mon = (int(part) for part in month.split("-", 1))
    return date(year, mon, 1)


def prev_month_anchor(month: str) -> date:
    """First day of the month BEFORE ``YYYY-MM`` (stdlib-only rollover)."""
    year, mon = (int(part) for part in month.split("-", 1))
    if mon == 1:
        return date(year - 1, 12, 1)
    return date(year, mon - 1, 1)


def band_for(d: Deadline, *, as_of: date) -> str:
    """Urgency band at ``as_of``; ``"expired"`` once the deadline has passed."""
    days = days_remaining(d, as_of=as_of)
    if days < 0:
        return "expired"
    return urgency_band(days)


def band_transitions(
    calendar: list[Deadline], *, as_of_now: date, as_of_prev: date
) -> list[tuple[Deadline, str, str]]:
    """Deadlines that entered a TIGHTER band between the two anchors.

    Returns ``(deadline, prev_band, now_band)`` for each deadline whose band
    rank strictly increased (info→warning, warning→error, →expired, ...),
    sorted by deadline ascending for determinism.
    """
    out: list[tuple[Deadline, str, str]] = []
    for d in calendar:
        prev_band = band_for(d, as_of=as_of_prev)
        now_band = band_for(d, as_of=as_of_now)
        if _BAND_RANK[now_band] > _BAND_RANK[prev_band]:
            out.append((d, prev_band, now_band))
    return sorted(out, key=lambda row: row[0].deadline)


def _framework_alignment_cell(d: Deadline) -> str:
    """Compact one-cell rendering of the deadline's framework cross-refs."""
    fa = d.framework_alignment
    parts: list[str] = []
    pages = fa.get("pages") or []
    specs = fa.get("example_specs") or []
    fields = fa.get("spec_fields") or []
    if pages:
        parts.append("Pages: " + ", ".join(pages))
    if specs:
        parts.append("Specs: " + ", ".join(specs))
    if fields:
        parts.append("Fields: " + ", ".join(fields))
    return "<br>".join(parts) if parts else "—"


def _what_changed_section(transitions: list[tuple[Deadline, str, str]], *, as_of_now: date) -> str:
    """Markdown for the pre-populated "What changed since last month" block."""
    lines = ["## What changed since last month", ""]
    if not transitions:
        lines.append("No deadline band changes this month.")
        lines.append("")
        return "\n".join(lines)
    lines.append(
        "These regulatory deadlines entered a tighter urgency band this "
        "month (computed from the bundled regulatory calendar):"
    )
    lines.append("")
    lines.append("| Deadline | Date | Days remaining | Band transition | Source |")
    lines.append("|---|---|---|---|---|")
    for d, prev_band, now_band in transitions:
        days = days_remaining(d, as_of=as_of_now)
        lines.append(
            f"| {d.description} | {d.deadline.isoformat()} | {days} "
            f"| {prev_band} → {now_band} | [source]({d.source_url}) |"
        )
    lines.append("")
    return "\n".join(lines)


def _countdown_section(active: list[Deadline], *, as_of_now: date) -> str:
    """Markdown for the "Deadline countdown" table of active deadlines."""
    lines = ["## Deadline countdown", ""]
    if not active:
        lines.append("No active (non-expired) deadlines on the calendar.")
        lines.append("")
        return "\n".join(lines)
    lines.append(
        f"All non-expired regulatory deadlines as of {as_of_now.isoformat()}, "
        "with the framework surfaces each one maps to:"
    )
    lines.append("")
    lines.append(
        "| Deadline | Date | Days remaining | Urgency band | Framework alignment | Source |"
    )
    lines.append("|---|---|---|---|---|---|")
    for d in active:
        days = days_remaining(d, as_of=as_of_now)
        band = urgency_band(days)
        lines.append(
            f"| {d.description} | {d.deadline.isoformat()} | {days} | {band} "
            f"| {_framework_alignment_cell(d)} | [source]({d.source_url}) |"
        )
    lines.append("")
    return "\n".join(lines)


def render_stub(month: str, calendar: list[Deadline]) -> str:
    """Render the full Markdown stub for ``month`` from ``calendar`` (pure)."""
    as_of_now = month_anchor(month)
    as_of_prev = prev_month_anchor(month)
    transitions = band_transitions(calendar, as_of_now=as_of_now, as_of_prev=as_of_prev)
    active = active_deadlines(calendar, as_of=as_of_now)

    parts = [
        f"# {DEFAULT_TITLE} — {month}",
        "",
        f"*Date: {as_of_now.isoformat()} · Audience: {AUDIENCE}. "
        "Auto-generated STUB (#512) — the sections below marked "
        "`TODO(human)` require a human author before publication.*",
        "",
        "---",
        "",
        _what_changed_section(transitions, as_of_now=as_of_now),
        "---",
        "",
        _countdown_section(active, as_of_now=as_of_now),
        "---",
        "",
        "## The data problem this month",
        "",
        "<!-- TODO(human): write the analytical thesis for this edition. "
        "Anchor it to the deadlines surfaced above; do NOT fabricate "
        "regulatory quotes or citations. -->",
        "",
        "## Primary sources",
        "",
        "<!-- TODO(human): cite the authoritative primary sources for the "
        "claims above. The calendar's source_url links are a starting point; "
        "verify and expand them. Never paste a citation you have not "
        "confirmed. -->",
        "",
        "## Framework response",
        "",
        "<!-- TODO(human): map each deadline / data problem above to the "
        "concrete framework artifact (dashboard page, CLI command, module, "
        "test) that responds to it, in the DATA-N → artifact style of the "
        "prior editions. -->",
        "",
    ]
    return "\n".join(parts) + "\n"


def generate(
    *,
    month: str,
    out_dir: Path,
    slug: str = DEFAULT_SLUG,
    calendar: list[Deadline] | None = None,
) -> tuple[Path, bool]:
    """Write the stub for ``month`` into ``out_dir``.

    Returns ``(path, written)``. ``written`` is ``False`` when the file
    already existed (never overwritten).
    """
    cal = calendar if calendar is not None else load_calendar()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{month}-{slug}.md"
    if target.exists():
        return target, False
    target.write_text(render_stub(month, cal), encoding="utf-8")
    return target, True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--month",
        default=_default_month(),
        help="Edition month as YYYY-MM (default: current month).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(DEFAULT_OUT_DIR),
        help=f"Output directory (default: {DEFAULT_OUT_DIR}).",
    )
    parser.add_argument(
        "--slug",
        default=DEFAULT_SLUG,
        help=f"Filename slug (default: {DEFAULT_SLUG}).",
    )
    parser.add_argument(
        "--calendar",
        type=Path,
        default=None,
        help="Optional override path to a calendar YAML (default: packaged).",
    )
    args = parser.parse_args(argv)

    # Validate the month string early so a bad arg fails loudly, not silently.
    try:
        as_of_now = month_anchor(args.month)
    except (ValueError, IndexError):
        print(f"error: --month must be YYYY-MM, got {args.month!r}", file=sys.stderr)
        return 2

    if args.calendar is not None:
        import yaml

        from aml_framework.dashboard.regulatory_calendar import Deadline as _Deadline

        data = yaml.safe_load(args.calendar.read_text(encoding="utf-8"))
        calendar = [_Deadline(**entry) for entry in data["deadlines"]]
    else:
        calendar = load_calendar()

    target, written = generate(
        month=args.month, out_dir=args.out_dir, slug=args.slug, calendar=calendar
    )

    transitions = band_transitions(
        calendar,
        as_of_now=as_of_now,
        as_of_prev=prev_month_anchor(args.month),
    )
    active = active_deadlines(calendar, as_of=as_of_now)
    if written:
        print(
            f"wrote {target} ({len(transitions)} band change(s), {len(active)} active deadline(s))"
        )
    else:
        print(f"skipped {target} — already exists (not overwritten)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
