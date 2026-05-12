"""Perf-baseline harness for the AML Open Framework.

The unit/API test suites verify correctness on toy data (~25 customers,
~400 noise txns). This package verifies behaviour-under-load — what
happens when the engine processes 10k+ txns / 100+ customers / 50+
rules. Intentionally separate from the regular pytest run because the
perf jobs take minutes, not seconds.

What's here
-----------
- `run_engine_baseline.py` — drive `run_spec` over a parameterised
  synthetic dataset and print per-stage wall-clock timings. Outputs a
  JSON line per run for nightly diffing.
- `expected_baseline.json` — committed baseline numbers; the nightly
  workflow fails if any per-stage timing regresses >2× this baseline.

What's NOT here (yet)
---------------------
- locust harness against the FastAPI surface. Listed in Round 19 —
  needs a real load environment (Container Apps autoscale + Postgres
  baseline) to produce numbers an operator can trust. The scaffold
  in this PR is the engine-side complement so the nightly check has
  *something* to catch p95 regressions on `run_spec` itself.
- Grafana dashboard JSON. Same reason: needs the live deploy's
  Application Insights instance to bind queries against.
"""
