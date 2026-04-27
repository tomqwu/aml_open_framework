"""Tests for `dashboard/tuning_state.py` — pure helpers, no streamlit.

Streamlit is NOT imported here; the page glue lives in tuning_state.py
and gets exercised end-to-end. CI's unit-tests job stays slim.
"""

from __future__ import annotations

import pytest
import yaml

from aml_framework.dashboard.tuning_state import (
    best_scenario,
    parse_labels_csv,
    render_spec_patch,
    rules_with_tuning_grid,
    scenarios_to_table,
)
from aml_framework.engine.tuning import ScenarioResult, TuningRun


def _scenario(params, alerts, p=None, r=None, f1=None, added=0, removed=0):
    return ScenarioResult(
        parameters=params,
        alert_count=alerts,
        alert_customer_ids=frozenset(),
        added_vs_baseline=added,
        removed_vs_baseline=removed,
        precision=p,
        recall=r,
        f1=f1,
    )


def _baseline(alerts=5):
    return ScenarioResult(
        parameters={"_baseline": True},
        alert_count=alerts,
        alert_customer_ids=frozenset(),
    )


# ---------------------------------------------------------------------------
# parse_labels_csv
# ---------------------------------------------------------------------------


class TestParseLabelsCSV:
    def test_basic_parse(self):
        csv_text = "customer_id,is_true_positive\nC001,1\nC002,0\nC003,true\nC004,false"
        labels = parse_labels_csv(csv_text)
        assert labels == {"C001": True, "C002": False, "C003": True, "C004": False}

    def test_alternative_truthy_values(self):
        csv_text = "customer_id,is_true_positive\nA,yes\nB,no\nC,Y\nD,t"
        labels = parse_labels_csv(csv_text)
        assert labels == {"A": True, "B": False, "C": True, "D": True}

    def test_empty_rows_skipped(self):
        csv_text = "customer_id,is_true_positive\n,1\nC1,1"
        assert parse_labels_csv(csv_text) == {"C1": True}

    def test_missing_flag_column_defaults_false(self):
        csv_text = "customer_id\nC1\nC2"
        labels = parse_labels_csv(csv_text)
        assert labels == {"C1": False, "C2": False}


# ---------------------------------------------------------------------------
# rules_with_tuning_grid
# ---------------------------------------------------------------------------


class TestRulesWithTuningGrid:
    def test_only_returns_tunable_rules(self):
        from pathlib import Path

        from aml_framework.spec import load_spec

        spec_path = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "canadian_schedule_i_bank"
            / "aml.yaml"
        )
        spec = load_spec(spec_path)
        ids = rules_with_tuning_grid(spec)
        # The CA spec ships with one tunable rule (added in PR #50).
        assert "structuring_cash_deposits" in ids


# ---------------------------------------------------------------------------
# scenarios_to_table
# ---------------------------------------------------------------------------


class TestScenariosToTable:
    def test_omits_metric_columns_when_no_labels(self):
        run = TuningRun(
            rule_id="r1",
            grid_size=2,
            baseline=_baseline(),
            scenarios=[
                _scenario({"logic.having.count": {"gte": 3}}, alerts=4, added=1, removed=2),
                _scenario({"logic.having.count": {"gte": 5}}, alerts=2),
            ],
        )
        rows = scenarios_to_table(run)
        assert len(rows) == 2
        assert "precision" not in rows[0]
        assert rows[0]["alerts"] == 4
        assert rows[0]["delta_alerts"] == -1  # 4 - 5
        assert rows[0]["added_vs_baseline"] == 1
        assert rows[0]["removed_vs_baseline"] == 2

    def test_includes_metric_columns_when_labels(self):
        run = TuningRun(
            rule_id="r1",
            grid_size=1,
            baseline=_baseline(),
            scenarios=[
                _scenario({"logic.having.count": {"gte": 3}}, alerts=4, p=0.8, r=0.6, f1=0.686)
            ],
        )
        rows = scenarios_to_table(run)
        assert rows[0]["precision"] == 0.8
        assert rows[0]["recall"] == 0.6
        assert rows[0]["f1"] == 0.686

    def test_params_formatted_compactly(self):
        run = TuningRun(
            rule_id="r1",
            grid_size=1,
            baseline=_baseline(),
            scenarios=[
                _scenario(
                    {"logic.having.count": {"gte": 3}, "logic.having.sum_amount": {"gte": 25000}},
                    alerts=4,
                )
            ],
        )
        params_str = scenarios_to_table(run)[0]["params"]
        assert "count gte=3" in params_str
        assert "sum_amount gte=25000" in params_str


# ---------------------------------------------------------------------------
# best_scenario
# ---------------------------------------------------------------------------


class TestBestScenario:
    def test_picks_highest_f1(self):
        run = TuningRun(
            rule_id="r",
            grid_size=3,
            baseline=_baseline(),
            scenarios=[
                _scenario({"a": 1}, 1, p=0.5, r=0.5, f1=0.5),
                _scenario({"a": 2}, 1, p=0.9, r=0.7, f1=0.79),
                _scenario({"a": 3}, 1, p=0.6, r=0.6, f1=0.6),
            ],
        )
        assert best_scenario(run, "f1") == 1

    def test_returns_none_without_metric(self):
        run = TuningRun(
            rule_id="r",
            grid_size=1,
            baseline=_baseline(),
            scenarios=[_scenario({"a": 1}, 1)],
        )
        assert best_scenario(run, "f1") is None

    def test_picks_highest_precision(self):
        run = TuningRun(
            rule_id="r",
            grid_size=2,
            baseline=_baseline(),
            scenarios=[
                _scenario({"a": 1}, 1, p=0.5, r=0.9, f1=0.64),
                _scenario({"a": 2}, 1, p=0.95, r=0.5, f1=0.66),
            ],
        )
        assert best_scenario(run, "precision") == 1


# ---------------------------------------------------------------------------
# render_spec_patch
# ---------------------------------------------------------------------------


class TestRenderSpecPatch:
    def test_round_trip_yaml(self):
        patch = render_spec_patch(
            "structuring_cash_deposits",
            {"logic.having.count": {"gte": 4}, "logic.having.sum_amount": {"gte": 30000}},
        )
        # Strip header comments, parse the YAML.
        lines = [line for line in patch.splitlines() if not line.strip().startswith("#")]
        parsed = yaml.safe_load("\n".join(lines))
        assert parsed["rules"][0]["id"] == "structuring_cash_deposits"
        assert parsed["rules"][0]["logic"]["having"]["count"] == {"gte": 4}
        assert parsed["rules"][0]["logic"]["having"]["sum_amount"] == {"gte": 30000}

    def test_includes_rule_id(self):
        patch = render_spec_patch("my_rule", {"logic.window": "60d"})
        assert "my_rule" in patch
        assert "60d" in patch

    def test_header_comment_present(self):
        patch = render_spec_patch("my_rule", {"logic.window": "60d"})
        assert patch.startswith("# Spec patch produced by the Tuning Lab.")


# ---------------------------------------------------------------------------
# Compose with engine/tuning sweep_rule end-to-end
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_sweep_to_table_to_patch(self):
        from datetime import datetime
        from pathlib import Path

        from aml_framework.data import generate_dataset
        from aml_framework.engine.tuning import sweep_rule
        from aml_framework.spec import load_spec

        spec = load_spec(
            Path(__file__).resolve().parents[1]
            / "examples"
            / "canadian_schedule_i_bank"
            / "aml.yaml"
        )
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)

        run = sweep_rule(spec, "structuring_cash_deposits", data, as_of=as_of)
        rows = scenarios_to_table(run)
        # The CA grid is 4×3 = 12 scenarios.
        assert len(rows) == 12
        # Each row has the core columns.
        for r in rows:
            assert "params" in r
            assert "alerts" in r
            assert "delta_alerts" in r

        # Promote scenario 0 — patch must be valid YAML referencing the rule.
        patch = render_spec_patch("structuring_cash_deposits", run.scenarios[0].parameters)
        parsed = yaml.safe_load(
            "\n".join(line for line in patch.splitlines() if not line.strip().startswith("#"))
        )
        assert parsed["rules"][0]["id"] == "structuring_cash_deposits"


@pytest.fixture(autouse=True)
def _no_streamlit_import(monkeypatch):
    """Helper assertion — streamlit must not be imported transitively."""
    import sys

    assert "streamlit" not in sys.modules, "tuning_state.py must not import streamlit"
    yield
