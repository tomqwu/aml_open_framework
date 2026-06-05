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
