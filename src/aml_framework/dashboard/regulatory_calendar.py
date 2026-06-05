"""Regulatory deadline calendar — pure loader + deterministic urgency logic.

Loads the packaged ``regulatory_calendar.yaml`` forward calendar and computes
days-remaining / urgency bands against an *explicit* as-of date, plus filters
expired entries. Shared by the Today banner (#510) and the Regulatory Calendar
page (#511).

This module is intentionally pure: NO module-level ``streamlit`` import. The
banner and page surfaces lazy-import streamlit in later tasks. Unit-test CI
installs only ``.[dev]`` (no streamlit), so importing this module must stay on
stdlib + pyyaml + pydantic.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Deadline(_Base):
    id: str
    description: str
    deadline: date
    urgency_days: int = Field(gt=0)
    source_url: str
    framework_alignment: dict[str, Any] = Field(default_factory=dict)


_CALENDAR_PATH = Path(__file__).with_name("regulatory_calendar.yaml")


def load_calendar() -> list[Deadline]:
    """Load the packaged forward calendar in file order."""
    data = yaml.safe_load(_CALENDAR_PATH.read_text(encoding="utf-8"))
    return [Deadline(**entry) for entry in data["deadlines"]]


def days_remaining(d: Deadline, *, as_of: date) -> int:
    """Whole days from ``as_of`` to the deadline (negative once expired)."""
    return (d.deadline - as_of).days


def urgency_band(days: int) -> str:
    """Map days-remaining to a Streamlit-style band.

    ``"error"`` if days <= 7, ``"warning"`` if days <= 30, else ``"info"``.
    Bands apply to non-negative days; callers filter expired entries via
    :func:`active_deadlines`.
    """
    if days <= 7:
        return "error"
    if days <= 30:
        return "warning"
    return "info"


def active_deadlines(calendar: list[Deadline], *, as_of: date) -> list[Deadline]:
    """Non-expired deadlines, sorted by deadline ascending (deterministic)."""
    upcoming = [d for d in calendar if days_remaining(d, as_of=as_of) >= 0]
    return sorted(upcoming, key=lambda d: d.deadline)


def banner_items(
    *, as_of: date, max_items: int = 4, calendar: list[Deadline] | None = None
) -> list[tuple[str, str]]:
    """Pure: the ``(band, markdown_message)`` pairs the banner should render.

    Deterministic given ``as_of`` (and an optional injected ``calendar``,
    defaulting to the packaged one). Returns at most ``max_items`` entries,
    expired deadlines already filtered and sorted by :func:`active_deadlines`.
    Empty list when nothing is upcoming. The streamlit surface
    (:func:`regulatory_alert_banner`) maps each band to the matching
    ``st.error`` / ``st.warning`` / ``st.info`` call — this function carries the
    logic so it stays unit-testable without streamlit.
    """
    cal = calendar if calendar is not None else load_calendar()
    items: list[tuple[str, str]] = []
    for d in active_deadlines(cal, as_of=as_of)[:max_items]:
        days = days_remaining(d, as_of=as_of)
        band = urgency_band(days)
        when = "**due today**" if days == 0 else f"**{days} days** remaining"
        items.append((band, f"{d.description} — {when} · [source]({d.source_url})"))
    return items


def regulatory_alert_banner(
    *, max_items: int = 4
) -> None:  # pragma: no cover - streamlit UI (e2e-covered)
    """Render a sticky band-colored alert banner of upcoming deadlines (#510).

    Streamlit UI surface: lazy-imports streamlit so this module stays
    import-clean for the unit-test image (``.[dev]`` has no streamlit). Uses
    the *live* ``date.today()`` as the countdown anchor — the row-selection
    logic lives in :func:`banner_items` (pure, unit-tested); this wrapper only
    dispatches each band to its ``st.*`` call. Empty calendar → a single muted
    caption. Any failure degrades to a caption note so Today never crashes.
    """
    import streamlit as st
    from datetime import date

    try:
        items = banner_items(as_of=date.today(), max_items=max_items)
        if not items:
            st.caption("No upcoming regulatory deadlines on the calendar.")
            return
        bars = {"error": st.error, "warning": st.warning, "info": st.info}
        for band, msg in items:
            bars.get(band, st.info)(msg)
    except Exception:  # pragma: no cover - defensive UI guard
        st.caption("Regulatory calendar unavailable right now.")
