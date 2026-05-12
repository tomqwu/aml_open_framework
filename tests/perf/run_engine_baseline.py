"""Per-stage timing for `run_spec` over a fixed-size synthetic dataset.

Usage (CI nightly):
    python -m tests.perf.run_engine_baseline > baseline.json

The script prints a JSON line per run with timings in seconds:
    {
      "as_of": "2026-04-28T00:00:00",
      "n_customers": 100,
      "n_noise_txns": 10000,
      "stage_seconds": {
        "generate_dataset": 0.31,
        "run_spec": 1.42,
        "total": 1.73
      },
      "alert_count": 24,
      "case_count": 24
    }

The accompanying GitHub Actions workflow diffs against
`tests/perf/expected_baseline.json` and fails when any stage exceeds
2× the committed number.

Designed to be machine-friendly: no logging in stdout, only the JSON
line. stderr carries any warnings.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.spec import load_spec

# Default sizing — chosen to be representative of a small-mid bank's
# daily run (100 active customers, 10k txns) without being so large
# that the nightly job costs $$ to run. Operators with bigger scale
# expectations can override via the env vars below.
DEFAULT_N_CUSTOMERS = 100
DEFAULT_N_NOISE_TXNS = 10_000
DEFAULT_SPEC = "examples/canadian_schedule_i_bank/aml.yaml"
DEFAULT_AS_OF = datetime(2026, 4, 28)


def run_baseline(
    *,
    spec_path: Path,
    n_customers: int,
    n_noise_txns: int,
    as_of: datetime,
) -> dict:
    """Run one timed pass and return the JSON-shaped result dict."""
    timings: dict[str, float] = {}

    t0 = time.perf_counter()
    data = generate_dataset(
        as_of=as_of, seed=42, n_customers=n_customers, n_noise_txns=n_noise_txns
    )
    t1 = time.perf_counter()
    timings["generate_dataset"] = round(t1 - t0, 4)

    spec = load_spec(spec_path)
    with tempfile.TemporaryDirectory() as tmp:
        t2 = time.perf_counter()
        result = run_spec(
            spec=spec,
            spec_path=spec_path,
            data=data,
            as_of=as_of,
            artifacts_root=Path(tmp),
        )
        t3 = time.perf_counter()
    timings["run_spec"] = round(t3 - t2, 4)
    timings["total"] = round(t3 - t0, 4)

    return {
        "as_of": as_of.isoformat(),
        "spec_path": str(spec_path),
        "n_customers": n_customers,
        "n_noise_txns": n_noise_txns,
        "stage_seconds": timings,
        "alert_count": result.total_alerts,
        "case_count": len(result.case_ids),
    }


def main() -> int:
    import os

    n_customers = int(os.environ.get("AML_PERF_N_CUSTOMERS", DEFAULT_N_CUSTOMERS))
    n_noise = int(os.environ.get("AML_PERF_N_NOISE_TXNS", DEFAULT_N_NOISE_TXNS))
    spec_path = Path(os.environ.get("AML_PERF_SPEC", DEFAULT_SPEC))
    if not spec_path.is_absolute():
        spec_path = Path(__file__).resolve().parents[2] / spec_path

    result = run_baseline(
        spec_path=spec_path,
        n_customers=n_customers,
        n_noise_txns=n_noise,
        as_of=DEFAULT_AS_OF,
    )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
