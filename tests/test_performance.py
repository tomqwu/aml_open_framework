"""Performance benchmarks — verify the engine handles scale.

Thresholds are deliberately conservative to avoid flaky failures on
resource-constrained CI runners. The primary purpose is regression
detection, not absolute performance measurement.
"""

import os
import time
from datetime import datetime
from pathlib import Path

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.spec import load_spec

SPEC = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"

# Allow CI to override thresholds via env var for slow runners.
_MIN_TPS_1K = int(os.environ.get("PERF_MIN_TPS_1K", "20"))
_MIN_TPS_5K = int(os.environ.get("PERF_MIN_TPS_5K", "10"))


class TestPerformance:
    def test_1k_transactions(self, tmp_path):
        spec = load_spec(SPEC)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42, n_customers=50, n_noise_txns=1000)
        n_txns = len(data["txn"])

        start = time.time()
        result = run_spec(
            spec=spec, spec_path=SPEC, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        elapsed = time.time() - start

        tps = n_txns / elapsed
        assert result.total_alerts > 0
        assert tps > _MIN_TPS_1K, f"1K benchmark: {tps:.0f} txns/sec (need >{_MIN_TPS_1K})"

    def test_5k_transactions(self, tmp_path):
        spec = load_spec(SPEC)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42, n_customers=100, n_noise_txns=5000)
        n_txns = len(data["txn"])

        start = time.time()
        result = run_spec(
            spec=spec, spec_path=SPEC, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        elapsed = time.time() - start

        tps = n_txns / elapsed
        assert result.total_alerts > 0
        assert tps > _MIN_TPS_5K, f"5K benchmark: {tps:.0f} txns/sec (need >{_MIN_TPS_5K})"
