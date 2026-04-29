"""Tests for the per-persona Today landing (PR 3 of design review).

Covers two layers:

  1. Pure-python card builder (`dashboard/today.py`) — runs on the
     unit-test image; verifies each persona returns exactly 3 cards
     pulling from the live spec/result/dataframe state.
  2. Source-level wiring (`app.py` registers Today first; audience
     filter exposes it universally) — file-as-text assertions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

# pandas is in `dashboard` extras, not `dev`. The unit-tests CI image
# only installs `.[dev]`, so skip the whole module gracefully there.
pd = pytest.importorskip("pandas")

from aml_framework.dashboard.today import (  # noqa: E402
    TodayCard,
    build_cards_for_audience,
)


# ---------------------------------------------------------------------------
# Fakes — minimal stand-ins for Spec, RunResult, dataframes
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


def _fake_spec(rule_severities: list[tuple[str, str]] | None = None) -> Any:
    rules = [
        _FakeRule(id=rid, severity=sev)
        for rid, sev in (
            rule_severities
            or [
                ("structuring_cash_deposits", "high"),
                ("rapid_pass_through", "critical"),
                ("sanctions_screening", "critical"),
                ("ml_risk_scorer", "medium"),
            ]
        )
    ]
    return SimpleNamespace(rules=rules, open_findings=[])


def _fake_result(
    metrics: list[_FakeMetric] | None = None,
    case_count: int = 5,
    total_alerts: int = 17,
) -> Any:
    metrics = metrics or [
        _FakeMetric("typology_coverage", "Typology Coverage", 0.86, "green", target=0.80),
        _FakeMetric("repeat_alert_rate", "Repeat alerts", 0.05, "green"),
        _FakeMetric("channel_coverage", "Channel coverage", 0.6, "amber"),
    ]
    return SimpleNamespace(
        metrics=metrics,
        case_ids=[f"C{i:04d}" for i in range(case_count)],
        total_alerts=total_alerts,
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


def _fake_cases(sla_states: list[str] | None = None) -> pd.DataFrame:
    sla_states = sla_states or ["green", "amber", "breached"]
    return pd.DataFrame(
        [{"case_id": f"C{i:04d}", "sla_state": s} for i, s in enumerate(sla_states)]
    )


# ---------------------------------------------------------------------------
# Card-count + structural invariants — must hold for every persona
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "audience",
    [
        "svp",
        "cco",
        "vp",
        "director",
        "cto",
        "business",
        "manager",
        "analyst",
        "auditor",
        "developer",
        "pm",
        None,
        "all",
        "unknown_persona",
    ],
)
def test_returns_exactly_three_cards(audience: str | None):
    cards = build_cards_for_audience(
        audience, _fake_spec(), _fake_result(), _fake_alerts(), _fake_cases()
    )
    assert len(cards) == 3, f"audience {audience!r} returned {len(cards)} cards (expected 3)"


@pytest.mark.parametrize(
    "audience",
    ["svp", "cco", "manager", "analyst", "auditor", "developer", "pm", "all"],
)
def test_every_card_is_a_today_card_dataclass(audience: str | None):
    cards = build_cards_for_audience(
        audience, _fake_spec(), _fake_result(), _fake_alerts(), _fake_cases()
    )
    for c in cards:
        assert isinstance(c, TodayCard)
        # All required fields populated.
        assert c.label and isinstance(c.label, str)
        assert c.value and isinstance(c.value, str)
        assert c.cta and isinstance(c.cta, str)
        # target_page must point at a real page file in the dashboard.
        assert c.target_page.startswith("pages/")
        page_file = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "aml_framework"
            / "dashboard"
            / c.target_page
        )
        assert page_file.exists(), f"Card targets non-existent page: {c.target_page}"


@pytest.mark.parametrize(
    "audience",
    ["svp", "cco", "manager", "analyst", "auditor", "developer", "pm", "all"],
)
def test_rag_values_are_valid(audience: str | None):
    cards = build_cards_for_audience(
        audience, _fake_spec(), _fake_result(), _fake_alerts(), _fake_cases()
    )
    valid = {None, "green", "amber", "red", "breached", "unset"}
    for c in cards:
        assert c.rag in valid, f"Invalid rag value {c.rag!r} on card {c.label!r}"


# ---------------------------------------------------------------------------
# Persona-specific signal correctness
# ---------------------------------------------------------------------------


class TestExecutivePersonas:
    def test_program_rag_card_reflects_metric_bands(self):
        # 1 red + 1 amber + 2 green (one of which is typology_coverage).
        result = _fake_result(
            metrics=[
                _FakeMetric("a", "A", 1, "red"),
                _FakeMetric("b", "B", 1, "amber"),
                _FakeMetric("c", "C", 1, "green"),
                _FakeMetric("typology_coverage", "Typology", 0.9, "green", target=0.8),
            ]
        )
        cards = build_cards_for_audience("cco", _fake_spec(), result, _fake_alerts())
        program_rag_card = next(c for c in cards if "RAG" in c.label)
        assert "2G" in program_rag_card.value
        assert "1A" in program_rag_card.value
        assert "1R" in program_rag_card.value
        # Any red present → card itself is red.
        assert program_rag_card.rag == "red"

    def test_typology_card_carries_metric_rag(self):
        result = _fake_result(
            metrics=[
                _FakeMetric("typology_coverage", "Typology", 0.55, "amber", target=0.80),
            ]
        )
        cards = build_cards_for_audience("svp", _fake_spec(), result, _fake_alerts())
        typ_card = next(c for c in cards if "Typology" in c.label)
        assert typ_card.rag == "amber"
        assert "55%" in typ_card.value


class TestManagerCards:
    def test_sla_breach_card_red_when_breaches_present(self):
        cards = build_cards_for_audience(
            "manager",
            _fake_spec(),
            _fake_result(),
            _fake_alerts(),
            _fake_cases(sla_states=["green", "breached", "breached"]),
        )
        breach_card = next(c for c in cards if "SLA" in c.label)
        assert breach_card.value == "2"
        assert breach_card.rag == "red"

    def test_sla_breach_card_green_when_clean(self):
        cards = build_cards_for_audience(
            "manager",
            _fake_spec(),
            _fake_result(),
            _fake_alerts(),
            _fake_cases(sla_states=["green", "green"]),
        )
        breach_card = next(c for c in cards if "SLA" in c.label)
        assert breach_card.value == "0"
        assert breach_card.rag == "green"

    def test_high_severity_count_uses_rule_severities(self):
        spec = _fake_spec(
            rule_severities=[
                ("rule_a", "high"),
                ("rule_b", "low"),
                ("rule_c", "critical"),
            ]
        )
        df = pd.DataFrame(
            [
                {"rule_id": "rule_a", "customer_id": "C1"},  # high
                {"rule_id": "rule_b", "customer_id": "C2"},  # low — not counted
                {"rule_id": "rule_c", "customer_id": "C3"},  # critical
            ]
        )
        cards = build_cards_for_audience("manager", spec, _fake_result(), df, _fake_cases())
        sev_card = next(c for c in cards if "High" in c.label or "critical" in c.label)
        assert sev_card.value == "2", "should count high+critical, not low"


class TestAnalystCards:
    def test_sanctions_card_counts_only_sanctions_alerts(self):
        df = pd.DataFrame(
            [
                {"rule_id": "structuring_cash_deposits", "customer_id": "C1"},
                {"rule_id": "sanctions_screening", "customer_id": "C2"},
                {"rule_id": "sanctions_screening", "customer_id": "C3"},
            ]
        )
        cards = build_cards_for_audience("analyst", _fake_spec(), _fake_result(), df, _fake_cases())
        sanctions_card = next(c for c in cards if "Sanctions" in c.label)
        assert sanctions_card.value == "2"
        assert sanctions_card.rag == "red"


# ---------------------------------------------------------------------------
# Empty-state safety — no card builder may crash on empty inputs
# ---------------------------------------------------------------------------


class TestEmptyStateSafety:
    @pytest.mark.parametrize(
        "audience",
        ["svp", "manager", "analyst", "auditor", "developer", "pm", "all"],
    )
    def test_empty_alerts_dataframe(self, audience: str | None):
        # Empty dataframe shouldn't blow up — first run of the day,
        # nothing has fired yet.
        empty_df = pd.DataFrame(columns=["rule_id", "customer_id"])
        cards = build_cards_for_audience(
            audience,
            _fake_spec(),
            _fake_result(total_alerts=0),
            empty_df,
        )
        assert len(cards) == 3

    @pytest.mark.parametrize("audience", ["analyst", "manager"])
    def test_no_cases_dataframe(self, audience: str):
        # df_cases may be None if the case-loading hook hasn't run.
        cards = build_cards_for_audience(
            audience, _fake_spec(), _fake_result(case_count=0), _fake_alerts(), None
        )
        assert len(cards) == 3


# ---------------------------------------------------------------------------
# Source-level wiring — Today must be registered + universally visible
# ---------------------------------------------------------------------------


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "app.py"
TODAY_PAGE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages" / "0_Today.py"


class TestTodayPageWired:
    def test_today_page_file_exists(self):
        assert TODAY_PAGE.exists(), "pages/0_Today.py must exist"

    def test_app_registers_today_first(self):
        body = APP_FILE.read_text(encoding="utf-8")
        # Today must come before Executive Dashboard in ALL_PAGES so it
        # becomes the default landing.
        today_idx = body.index('title="Today"')
        exec_idx = body.index('title="Executive Dashboard"')
        assert today_idx < exec_idx, (
            "Today must register before Executive Dashboard in ALL_PAGES "
            "to become the default landing"
        )

    def test_today_universally_visible_under_audience_filter(self):
        body = APP_FILE.read_text(encoding="utf-8")
        # The audience filter has to add Today to relevant_titles for
        # every persona — otherwise selecting an audience hides it.
        assert 'relevant_titles.add("Today")' in body, (
            "Audience filter must always include Today; otherwise "
            "selecting a persona hides the personalised landing"
        )
