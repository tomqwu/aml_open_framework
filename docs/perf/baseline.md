# Engine perf baseline

Tracking the per-stage wall-clock of `run_spec` on a representative
small-mid-bank load. CI's nightly perf workflow re-runs the same
shape and fails when any stage regresses >2× this baseline.

## Sizing

Chosen to represent a small-mid bank's daily run without making the
nightly job expensive:

| Variable           | Value  |
|--------------------|--------|
| spec               | `examples/canadian_schedule_i_bank/aml.yaml` |
| n_customers        | 100    |
| n_noise_txns       | 10,000 |
| as_of              | `2026-04-28T00:00:00` |
| seed               | 42     |

Operators with bigger expectations can override via env vars
(`AML_PERF_N_CUSTOMERS`, `AML_PERF_N_NOISE_TXNS`, `AML_PERF_SPEC`)
and re-baseline locally.

## Committed numbers

Measured on an M-series MacBook (2026-spec). CI runners are slower,
hence the 2× nightly threshold buffer.

| Stage              | Seconds |
|--------------------|---------|
| `generate_dataset` | 0.05    |
| `run_spec`         | 1.30    |
| **total**          | **1.35** |

Alert count baseline: **47** (across all canadian_schedule_i_bank
rules on the seed-42 dataset). The smoke test also asserts the
post-refactor alert count doesn't drop to less than half of this.

## Re-baselining

When an intentional perf-affecting change lands (e.g. a new rule, a
schema change, an engine refactor), re-capture:

```bash
python -m tests.perf.run_engine_baseline > tests/perf/expected_baseline.json
```

Hand-edit the `_schema._comment` field if the sizing/spec changes
materially, then commit. Keep the file scannable — it's a baseline,
not a histogram.

## Out of scope (Round 19+)

- **locust harness against FastAPI**: needs a real load environment
  (Container Apps autoscale + Postgres baseline) to produce numbers
  an operator can trust. The engine-side baseline in this PR is the
  defensive complement so a regression on `run_spec` itself gets
  caught.
- **Grafana dashboard JSON**: needs the live deploy's Application
  Insights instance to bind queries against.
- **Per-rule profiling**: today's baseline is whole-`run_spec`. A
  per-rule breakdown would help diagnose which rule changed when a
  regression fires, but adds bookkeeping to the engine; queued.
