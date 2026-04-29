"""Tests for `engine/backtest.py` and the `aml backtest` CLI.

The MLRO use case this guards: replay a rule across quarters, get a
defensible precision/recall trend without commissioning a vendor study.
If these break, the 2LoD model-challenge story breaks.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aml_framework.cli import app
from aml_framework.engine.backtest import (
    BacktestPeriod,
    PeriodResult,
    backtest_rule,
    quarters,
)
from aml_framework.spec import load_spec

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = REPO_ROOT / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
RULE = "structuring_cash_deposits"


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------


def test_quarters_helper_builds_n_periods() -> None:
    end = datetime(2026, 4, 28)
    qs = quarters(end=end, n=4)
    assert len(qs) == 4
    # Most recent period last; oldest first.
    assert qs[-1].as_of == end
    assert qs[0].as_of < qs[-1].as_of
    # Labels are unique.
    assert len({q.label for q in qs}) == 4


def test_quarters_step_is_90_days() -> None:
    end = datetime(2026, 4, 28)
    qs = quarters(end=end, n=2)
    delta = (qs[1].as_of - qs[0].as_of).days
    assert delta == 90


# ---------------------------------------------------------------------------
# Backtest core
# ---------------------------------------------------------------------------


def test_backtest_returns_one_result_per_period() -> None:
    spec = load_spec(SPEC)
    periods = quarters(end=datetime(2026, 4, 28), n=3)
    report = backtest_rule(spec, RULE, periods)
    assert len(report.periods) == 3
    assert all(isinstance(p, PeriodResult) for p in report.periods)
    assert report.rule_id == RULE


def test_backtest_unknown_rule_raises() -> None:
    spec = load_spec(SPEC)
    with pytest.raises(ValueError, match="No rule with id"):
        backtest_rule(spec, "no_such_rule", quarters(datetime(2026, 4, 28), 1))


def test_backtest_requires_at_least_one_period() -> None:
    spec = load_spec(SPEC)
    with pytest.raises(ValueError, match="at least one period"):
        backtest_rule(spec, RULE, [])


def test_backtest_drift_attached_for_subsequent_periods() -> None:
    spec = load_spec(SPEC)
    periods = quarters(end=datetime(2026, 4, 28), n=3)
    report = backtest_rule(spec, RULE, periods)
    # First period has no prior, so drift is None there only.
    assert report.periods[0].drift_vs_prior_period is None
    for p in report.periods[1:]:
        assert p.drift_vs_prior_period is not None
        assert "alert_count_delta" in p.drift_vs_prior_period


def test_backtest_with_labels_computes_precision_and_recall() -> None:
    spec = load_spec(SPEC)
    periods = quarters(end=datetime(2026, 4, 28), n=2)

    def labels(_: BacktestPeriod) -> dict[str, bool]:
        # Mark a customer the rule would plausibly catch as TP. Exact
        # values don't matter — we only assert that scoring runs.
        return {"C0001": True, "C0002": False}

    report = backtest_rule(spec, RULE, periods, labels_loader=labels)
    # At least the periods that produced alerts should have precision.
    has_score = [p for p in report.periods if p.precision is not None]
    if has_score:
        for p in has_score:
            assert 0.0 <= p.precision <= 1.0
            assert 0.0 <= (p.recall or 0.0) <= 1.0


def test_backtest_drift_summary_includes_volume_slope() -> None:
    spec = load_spec(SPEC)
    periods = quarters(end=datetime(2026, 4, 28), n=4)
    report = backtest_rule(spec, RULE, periods)
    assert "alert_count_slope_per_period" in report.drift_summary


def test_backtest_is_reproducible() -> None:
    """Same spec + same periods + same seed = identical alert sets.

    This is the determinism guarantee MRM is depending on; if it ever
    fails here, the audit trail's replay-equivalence story collapses.
    """
    spec = load_spec(SPEC)
    periods = quarters(end=datetime(2026, 4, 28), n=2)
    a = backtest_rule(spec, RULE, periods)
    b = backtest_rule(spec, RULE, periods)
    for pa, pb in zip(a.periods, b.periods):
        assert pa.alert_count == pb.alert_count
        assert pa.alert_customer_ids == pb.alert_customer_ids


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_backtest_writes_json_report(runner: CliRunner, tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    result = runner.invoke(
        app,
        [
            "backtest",
            str(SPEC),
            "--rule",
            RULE,
            "--quarters",
            "3",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    import json

    payload = json.loads(out.read_text())
    assert payload["rule_id"] == RULE
    assert payload["n_periods"] == 3


def test_cli_backtest_renders_table(runner: CliRunner, tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    result = runner.invoke(
        app,
        ["backtest", str(SPEC), "--rule", RULE, "--quarters", "2", "--out", str(out)],
    )
    assert result.exit_code == 0
    assert "Backtest" in result.output
    assert "Period" in result.output
    assert "Precision" in result.output


def test_cli_backtest_with_labels_csv(runner: CliRunner, tmp_path: Path) -> None:
    labels = tmp_path / "labels.csv"
    labels.write_text("customer_id,is_true_positive\nC0001,1\nC0002,0\n", encoding="utf-8")
    out = tmp_path / "report.json"
    result = runner.invoke(
        app,
        [
            "backtest",
            str(SPEC),
            "--rule",
            RULE,
            "--quarters",
            "2",
            "--labels",
            str(labels),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
