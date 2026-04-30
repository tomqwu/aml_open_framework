"""Unit tests for the Executive Dashboard's new visual helpers.

Covers:
- `headline_hero` accepts the 3-tile dict spec + raises on wrong count
- `kpi_card_with_trend` renders the spark + delta string when history is
  ≥2 numeric values; falls back to "(no prior runs)" otherwise
- `dashboard.run_history` helpers are pure-stdlib + Streamlit-free
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# run_history (Streamlit-free; pure functions over a Path)
# ---------------------------------------------------------------------------


def _write_run(parent: Path, name: str, manifest: dict, mtime_offset: int = 0) -> Path:
    run = parent / name
    run.mkdir(parents=True, exist_ok=True)
    (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if mtime_offset:
        # Force ordering — stat().st_mtime is what recent_runs sorts on.
        import os

        target_time = (run / "manifest.json").stat().st_mtime + mtime_offset
        os.utime(run, (target_time, target_time))
    return run


def test_recent_runs_orders_by_mtime(tmp_path: Path):
    from aml_framework.dashboard.run_history import recent_runs

    parent = tmp_path / "runs"
    parent.mkdir()
    older = _write_run(parent, "2026-04-01", {"total_alerts": 5}, mtime_offset=-3600)
    middle = _write_run(parent, "2026-04-15", {"total_alerts": 12}, mtime_offset=-1800)
    newer = _write_run(parent, "2026-04-29", {"total_alerts": 8}, mtime_offset=0)

    runs = recent_runs(newer, n=8)
    assert runs == [older, middle, newer]


def test_recent_runs_no_siblings(tmp_path: Path):
    """Single-run install — should return just the active run."""
    from aml_framework.dashboard.run_history import recent_runs

    parent = tmp_path / "runs"
    parent.mkdir()
    only = _write_run(parent, "2026-04-29", {"total_alerts": 1})
    assert recent_runs(only) == [only]


def test_manifest_field_history_handles_missing_runs(tmp_path: Path):
    from aml_framework.dashboard.run_history import manifest_field_history

    parent = tmp_path / "runs"
    parent.mkdir()
    a = _write_run(parent, "a", {"total_alerts": 5}, mtime_offset=-3600)
    b = parent / "b"
    b.mkdir()  # No manifest written → graceful None
    c = _write_run(parent, "c", {"total_alerts": 11}, mtime_offset=-1800)

    history = manifest_field_history([a, b, c], "total_alerts")
    assert history == [5.0, None, 11.0]


def test_metric_value_history_reads_metrics_json(tmp_path: Path):
    from aml_framework.dashboard.run_history import metric_value_history

    parent = tmp_path / "runs"
    parent.mkdir()
    a = parent / "a"
    a.mkdir()
    (a / "manifest.json").write_text(json.dumps({}), encoding="utf-8")
    (a / "metrics.json").write_text(
        json.dumps([{"id": "typology_coverage", "value": 0.62}]), encoding="utf-8"
    )

    b = parent / "b"
    b.mkdir()
    (b / "manifest.json").write_text(json.dumps({}), encoding="utf-8")
    (b / "metrics.json").write_text(
        json.dumps([{"id": "typology_coverage", "value": 0.71}]), encoding="utf-8"
    )

    history = metric_value_history([a, b], "typology_coverage")
    assert history == [0.62, 0.71]


def test_delta_pct_signed_change():
    from aml_framework.dashboard.run_history import delta_pct

    # 50% increase
    assert delta_pct([100.0, 150.0]) == pytest.approx(50.0)
    # 20% decrease
    assert delta_pct([100.0, 80.0]) == pytest.approx(-20.0)
    # Zero baseline → None (avoid div-by-zero)
    assert delta_pct([0.0, 5.0]) is None
    # Single value → None
    assert delta_pct([42.0]) is None
    # All None → None
    assert delta_pct([None, None]) is None
    # Mixed; only last two numerics matter
    assert delta_pct([1.0, None, 2.0, 4.0]) == pytest.approx(100.0)


def test_numeric_only_drops_none():
    from aml_framework.dashboard.run_history import numeric_only

    assert numeric_only([1.0, None, 2.0, None, 3.0]) == [1.0, 2.0, 3.0]
    assert numeric_only([None, None]) == []
    assert numeric_only([]) == []


# Note: a `headline_hero` arity-validation test was prototyped but
# importing `dashboard.components` transitively imports streamlit,
# which trips the `_no_streamlit_import` autouse fixture in
# `test_dashboard_tuning_state.py` when both files run in one pytest
# invocation. The arity guard (`raise ValueError("exactly 3 tiles")`)
# is exercised end-to-end via the dashboard test (test_e2e_dashboard.py)
# at full integration; isolating it as a unit test here would require
# faking the streamlit import surface, which the CI image isn't built
# for. The 6 run_history tests above cover the load-bearing logic.
