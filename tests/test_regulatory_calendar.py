from __future__ import annotations

from datetime import date

import pytest

from aml_framework.dashboard.regulatory_calendar import (
    Deadline,
    active_deadlines,
    banner_items,
    days_remaining,
    load_calendar,
    urgency_band,
)


def _dl(id_: str, deadline: date) -> Deadline:
    return Deadline(
        id=id_,
        description=f"{id_} deadline",
        deadline=deadline,
        urgency_days=14,
        source_url="http://example.test/" + id_,
        framework_alignment={},
    )


def test_load_calendar_nonempty():
    cal = load_calendar()
    assert len(cal) >= 4
    assert all(isinstance(d, Deadline) for d in cal)
    d0 = cal[0]
    assert d0.id and d0.description and d0.deadline and d0.source_url


def test_days_remaining():
    d = Deadline(
        id="x",
        description="d",
        deadline=date(2026, 6, 9),
        urgency_days=14,
        source_url="http://e",
        framework_alignment={},
    )
    assert days_remaining(d, as_of=date(2026, 6, 5)) == 4
    assert days_remaining(d, as_of=date(2026, 6, 9)) == 0
    assert days_remaining(d, as_of=date(2026, 6, 12)) == -3


@pytest.mark.parametrize(
    "days,band",
    [(3, "error"), (7, "error"), (8, "warning"), (30, "warning"), (31, "info"), (200, "info")],
)
def test_urgency_band(days, band):
    assert urgency_band(days) == band


def test_active_deadlines_hides_expired_sorted():
    cal = [
        Deadline(
            id="past",
            description="p",
            deadline=date(2026, 6, 1),
            urgency_days=14,
            source_url="http://e",
            framework_alignment={},
        ),
        Deadline(
            id="soon",
            description="s",
            deadline=date(2026, 6, 9),
            urgency_days=14,
            source_url="http://e",
            framework_alignment={},
        ),
        Deadline(
            id="later",
            description="l",
            deadline=date(2026, 7, 10),
            urgency_days=30,
            source_url="http://e",
            framework_alignment={},
        ),
    ]
    active = active_deadlines(cal, as_of=date(2026, 6, 5))
    assert [d.id for d in active] == ["soon", "later"]  # past hidden, sorted by deadline asc


def test_active_deadlines_empty_when_all_past():
    cal = [
        Deadline(
            id="past",
            description="p",
            deadline=date(2026, 1, 1),
            urgency_days=14,
            source_url="http://e",
            framework_alignment={},
        )
    ]
    assert active_deadlines(cal, as_of=date(2026, 6, 5)) == []


def test_loaded_calendar_entries_are_well_formed():
    for d in load_calendar():
        assert d.deadline.year >= 2026
        assert d.urgency_days > 0
        assert d.source_url.startswith("http")


def test_banner_items_bands_and_messages():
    cal = [
        _dl("today", date(2026, 6, 5)),  # 0 days  → error, "due today"
        _dl("soon", date(2026, 6, 9)),  # 4 days  → error
        _dl("mid", date(2026, 6, 25)),  # 20 days → warning
        _dl("far", date(2026, 9, 1)),  # 88 days → info
        _dl("past", date(2026, 1, 1)),  # expired → excluded
    ]
    items = banner_items(as_of=date(2026, 6, 5), calendar=cal)
    bands = [band for band, _ in items]
    assert bands == ["error", "error", "warning", "info"]  # expired dropped, sorted asc
    assert "**due today**" in items[0][1]
    assert "**4 days** remaining" in items[1][1]
    assert "[source](http://example.test/soon)" in items[1][1]


def test_banner_items_truncates_to_max_items():
    cal = [_dl(f"d{i}", date(2026, 6, 10 + i)) for i in range(6)]
    items = banner_items(as_of=date(2026, 6, 5), calendar=cal, max_items=3)
    assert len(items) == 3


def test_banner_items_empty_when_nothing_upcoming():
    cal = [_dl("past", date(2026, 1, 1))]
    assert banner_items(as_of=date(2026, 6, 5), calendar=cal) == []


def test_banner_items_against_packaged_calendar_is_deterministic():
    a = banner_items(as_of=date(2026, 6, 5))
    b = banner_items(as_of=date(2026, 6, 5))
    assert a == b
    assert all(band in {"error", "warning", "info"} for band, _ in a)
