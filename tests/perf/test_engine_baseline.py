"""Perf-regression smoke test — pytest version of the nightly check.

Opt-in: skipped unless `AML_RUN_PERF=1` so the regular CI unit-test
suite (which runs on shared/variably-loaded GitHub runners that are
~10× slower than the baseline workstation) doesn't false-fail. The
nightly workflow sets `AML_RUN_PERF=1` and tightens the threshold
to 2× on its dedicated runner.

Run locally with:

    AML_RUN_PERF=1 pytest tests/perf/test_engine_baseline.py -q
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from tests.perf.run_engine_baseline import run_baseline

PERF_DIR = Path(__file__).resolve().parent
BASELINE = json.loads((PERF_DIR / "expected_baseline.json").read_text(encoding="utf-8"))

# Pytest threshold (when opt-in). Nightly workflow drives a tighter
# 2× threshold via `run_engine_baseline.py` directly.
PYTEST_THRESHOLD = 5.0


@pytest.mark.skipif(
    os.environ.get("AML_RUN_PERF") != "1",
    reason="AML_RUN_PERF not set; perf smoke test is opt-in (nightly workflow runs it)",
)
def test_engine_baseline_within_threshold():
    """Run the baseline and assert no stage timing regresses by >5×
    the committed expected. A real regression that the nightly job
    catches will typically also fail here on most hardware."""
    spec_path = PERF_DIR.parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
    result = run_baseline(
        spec_path=spec_path,
        n_customers=100,
        n_noise_txns=10_000,
        as_of=datetime(2026, 4, 28),
    )
    for stage, expected in BASELINE["stage_seconds"].items():
        actual = result["stage_seconds"][stage]
        assert actual <= expected * PYTEST_THRESHOLD, (
            f"perf regression in `{stage}`: {actual}s > {expected}s × {PYTEST_THRESHOLD} "
            f"({expected * PYTEST_THRESHOLD}s). Re-baseline if intentional."
        )
    # Sanity: alerts shouldn't disappear under a future refactor.
    assert result["alert_count"] >= BASELINE["alert_count"] // 2, (
        f"alert count dropped sharply: {result['alert_count']} vs baseline {BASELINE['alert_count']}"
    )
