"""Perf-regression smoke test — pytest version of the nightly check.

Runs the same baseline as `run_engine_baseline.py` but with a more
generous 5× threshold so the regular CI unit-test suite (which runs
on slower / variably-loaded shared runners) doesn't false-fail. The
nightly workflow uses a tighter 2× threshold on dedicated hardware.

Skipped when the env says `AML_SKIP_PERF=1` so contributors with
slow machines aren't blocked.
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

# Generous threshold for the regular unit suite — nightly perf workflow
# tightens this to 2× on dedicated runners.
PYTEST_THRESHOLD = 5.0


@pytest.mark.skipif(
    os.environ.get("AML_SKIP_PERF") == "1",
    reason="AML_SKIP_PERF=1; perf smoke test skipped",
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
