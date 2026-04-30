"""Regression guard for issue #69 — Today cards must link only to pages
that the active persona can navigate to.

The bug: Streamlit's modern API refuses ``st.page_link("pages/X.py")``
unless ``pages/X.py`` was registered with ``st.navigation([...])`` for
the current run. The dashboard filters ``ALL_PAGES`` per-persona via
``AUDIENCE_PAGES``, so if a Today card targets a page that the persona's
list omits, the page link raises ``StreamlitPageNotFoundError`` and the
whole Today render crashes.

Caught in production by a VP-mode user — VP's Today cards link to
``Audit & Evidence`` but ``AUDIENCE_PAGES["vp"]`` did not include it.
PR-R closes the gap.

This test walks **every** persona, builds their Today cards, resolves
each ``target_page`` file path to a page title, and asserts that the
title is in the persona's filtered nav set. If any persona regresses,
the test fails with the exact missing page so the fix is mechanical.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pd = pytest.importorskip("pandas")

from aml_framework.dashboard.audience import AUDIENCE_PAGES, PERSONA_LABELS  # noqa: E402
from aml_framework.dashboard.today import build_cards_for_audience  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "app.py"


# ---------------------------------------------------------------------------
# Harvest the path→title mapping straight out of app.py — that's the
# source of truth for what `st.navigation()` will accept.
# ---------------------------------------------------------------------------


def _path_to_title_map() -> dict[str, str]:
    """Parse `st.Page("pages/X.py", title="Title", ...)` calls in app.py."""
    body = APP_FILE.read_text(encoding="utf-8")
    pattern = re.compile(
        r"st\.Page\(\s*[\"'](pages/[^\"']+)[\"']\s*,\s*title=[\"']([^\"']+)[\"']",
        flags=re.DOTALL,
    )
    mapping = dict(pattern.findall(body))
    assert mapping, "Failed to parse st.Page() declarations from app.py"
    return mapping


PATH_TO_TITLE = _path_to_title_map()


# Pages every persona can always reach, regardless of their AUDIENCE_PAGES
# entry. These are added in app.py: `relevant_titles.add("Today")`,
# `relevant_titles.add("Executive Dashboard")`.
UNIVERSAL_TITLES = {"Today", "Executive Dashboard"}


# ---------------------------------------------------------------------------
# Lightweight fakes — same shape today.py expects (mirrors fixtures in
# test_dashboard_today.py but kept self-contained so this file doesn't
# import from another test module).
# ---------------------------------------------------------------------------


@dataclass
class _FakeRule:
    id: str
    severity: str
    status: str = "active"


@dataclass
class _FakeMetric:
    id: str
    name: str
    value: float
    rag: str
    target: float | None = None


def _fake_spec() -> Any:
    return SimpleNamespace(
        rules=[
            _FakeRule(id="structuring_cash_deposits", severity="high"),
            _FakeRule(id="rapid_pass_through", severity="critical"),
            _FakeRule(id="sanctions_screening", severity="critical"),
            _FakeRule(id="ml_risk_scorer", severity="medium"),
        ],
        open_findings=[],
    )


def _fake_result() -> Any:
    return SimpleNamespace(
        metrics=[
            _FakeMetric("typology_coverage", "Typology Coverage", 0.86, "green", target=0.80),
            _FakeMetric("repeat_alert_rate", "Repeat alerts", 0.05, "green"),
            _FakeMetric("channel_coverage", "Channel coverage", 0.6, "amber"),
        ],
        case_ids=[f"C{i:04d}" for i in range(5)],
        total_alerts=17,
        rule_alerts={"structuring_cash_deposits"},
    )


def _fake_alerts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"rule_id": "structuring_cash_deposits", "customer_id": "C0001"},
            {"rule_id": "rapid_pass_through", "customer_id": "C0002"},
            {"rule_id": "sanctions_screening", "customer_id": "C0003"},
        ]
    )


def _fake_cases() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"case_id": "C0000", "sla_state": "green"},
            {"case_id": "C0001", "sla_state": "amber"},
            {"case_id": "C0002", "sla_state": "breached"},
        ]
    )


# ---------------------------------------------------------------------------
# The load-bearing test — every persona, every card, must be navigable.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("persona", sorted(PERSONA_LABELS.keys()))
def test_today_cards_are_in_persona_navigation(persona: str):
    cards = build_cards_for_audience(
        persona, _fake_spec(), _fake_result(), _fake_alerts(), _fake_cases()
    )
    persona_titles = set(AUDIENCE_PAGES.get(persona, [])) | UNIVERSAL_TITLES

    missing: list[str] = []
    for card in cards:
        # Skip cards that point at pages app.py doesn't know about — the
        # path-existence test in test_dashboard_today.py already catches
        # that class of bug. Here we only care about the persona-filter
        # interaction.
        title = PATH_TO_TITLE.get(card.target_page)
        if title is None:
            pytest.fail(
                f"Today card for persona {persona!r} targets {card.target_page!r}, "
                f"which is not registered in app.py's ALL_PAGES list"
            )
        if title not in persona_titles:
            missing.append(f"  - {title!r} (card.cta={card.cta!r})")

    assert not missing, (
        f"Persona {persona!r} has Today cards linking to pages that the "
        f"persona-filtered navigation hides. Streamlit will raise "
        f"StreamlitPageNotFoundError on render. "
        f"Add these page titles to AUDIENCE_PAGES[{persona!r}]:\n" + "\n".join(missing)
    )


def test_no_persona_falls_through_to_unguarded_default():
    """Catch the case where a new persona is added to PERSONA_LABELS but
    not to AUDIENCE_PAGES — its cards would silently get the generic
    fallback, which may target pages that aren't in the (empty) audience
    list.
    """
    missing_audience: list[str] = []
    for persona in PERSONA_LABELS:
        if persona not in AUDIENCE_PAGES:
            missing_audience.append(persona)
    assert not missing_audience, (
        "PERSONA_LABELS keys missing from AUDIENCE_PAGES:\n  " + "\n  ".join(missing_audience)
    )
