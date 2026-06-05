# How to monitor model risk + per-rule drift

> **When you need this:** Your SR 11-7 / OSFI E-23 model-risk-management posture needs ongoing evidence that the detection population is behaving — a rule that suddenly fires 3× more (or collapses to near-zero) is a model-risk signal a validator should see, and so is a model whose validation cadence is overdue. The model-risk-monitoring block (#497) is the governed, advisory way to roll all of that into one frozen, regulator-facing artifact each run.
>
> **Prereqs:** A spec that `aml validate` passes. At least **two runs** of the same spec against the same backend, so a prior baseline exists for drift to compare against (the first run reports `drift="unknown"` by design). `engine/model_risk_monitoring.py::build_model_risk_report` is the canonical, pure builder.
>
> **Time:** ~10 min.

Model-risk monitoring is **advisory / monitoring only**. The `model_risk_report.json` it emits *never blocks a run and never changes a model* — the deterministic rules stay authoritative, every alert lands in the ledger exactly as it would have. It is a validator's lens: an inventory roll-up, a per-rule drift flag, and a cadence read-out. It is explainable (every entry carries the counts and ratio that produced its `drift`), deterministic (`generated_at` is the ledger `as_of`, no wall-clock), and evidenced (the frozen report is one of the manifest-hashed artifacts, pinned as `model_risk_report_hash`).

---

## Steps

### 1 · Declare a `model_risk_monitoring` block

Add the block under `program`. The minimal form is one field:

```yaml
program:
  name: canadian_schedule_i_aml
  model_risk_monitoring:
    enabled: true
    # drift_high_ratio defaults to 2.0 — flag a rule "high" when its
    #   current/prior count ratio is >= 2.0 (a spike) or <= 0.5 (a collapse)
    # baseline_runs   defaults to 10  — RESERVED for a future multi-run baseline;
    #                                    the MVP compares against the immediately-prior run only
```

`drift_high_ratio` must be `>= 1`; `baseline_runs` must be `>= 1`. Both are optional — start with the defaults and tighten `drift_high_ratio` later (e.g. `1.5`) off your own validation evidence, as a spec PR.

### 2 · Validate

```bash
aml validate aml.yaml
```

Validation confirms the block's shape. With `enabled: false` (or the block omitted) the engine runs unchanged and no `model_risk_report.json` is written — the disabled path is byte-identical to a spec without the block.

### 3 · Run at least twice

Drift compares the current run's per-rule alert counts against the **prior** run's. So you need a baseline:

```bash
aml run aml.yaml --seed 42      # run 1 — establishes the baseline (drift="unknown")
aml run aml.yaml --seed 42      # run 2 — now drift is computed vs run 1
```

Each run the engine rolls the model inventory + per-rule count drift + validation cadence into a `ModelRiskReport` and writes it to the run directory. The builder is pure / deterministic / stdlib — same spec + same data + same seed yields an identical report (`generated_at` is the ledger `as_of`, not a clock read).

### 4 · Read `model_risk_report.json`

```bash
jq . .artifacts/run-*/model_risk_report.json
```

The frozen, regulator-facing summary:

```json
{
  "enabled": true,
  "n_models": 6,
  "n_high_drift": 1,
  "entries": [
    {
      "model_key": "structuring_burst",
      "kind": "rule",
      "tier": "high",
      "owner": "mlro_2lod",
      "current_alerts": 9,
      "prior_alerts": 3,
      "drift": "high",
      "drift_ratio": 3.0,
      "cadence_months": 12
    }
  ],
  "generated_at": "2026-06-05T00:00:00+00:00"
}
```

Entries are sorted **high-drift-first**, then tier, then key — the model-risk signals you care about are at the top. The report's SHA-256 is pinned in `manifest.json` as `model_risk_report_hash`.

### 5 · Interpret the drift flag

| `drift` | Meaning | What to do |
|---|---|---|
| `high` | The rule's `current/prior` count ratio is **≥ `drift_high_ratio`** (a spike) or **≤ `1 / drift_high_ratio`** (a collapse) | A model-risk signal — route to validation. A spike may be a real typology shift OR a tuning defect; a collapse may mean upstream data stopped arriving. The flag does NOT decide which — it surfaces the candidate. |
| `unknown` | No prior baseline yet (first run, or the rule had no prior counts) | Expected on run 1. Run again to populate the comparison. |
| `normal` | Ratio inside the band | No action; logged for the audit trail. |

`drift_ratio` carries the exact `current/prior` value behind the flag, so the entry is self-explaining.

### 6 · Read it on the dashboard instead

- **Drift Monitor (page 50)** — when `program.model_risk_monitoring` is enabled, the page renders a **Model-risk report** section (alongside the per-scorer volume-drift view, and it renders even for specs with no `python_ref` scorers): the model inventory, per-rule count drift, and validation cadence straight from `model_risk_report.json`. Advisory framing is explicit — nothing on this page blocks a run or mutates a model.

---

## Verify it worked

Three checks:

1. **`model_risk_report.json` exists** in the run dir and `manifest.json::model_risk_report_hash` matches `sha256(model_risk_report.json)`.
2. **The disabled path is unchanged** — diff a run with `model_risk_monitoring.enabled: false` against one with it `true`: same alerts, same dispositions, same audit chain; the only difference is the additive report (and its manifest pin). The monitor never blocks a run or changes a model.
3. **Determinism** — re-run with the same seed; `model_risk_report_hash` is unchanged (`generated_at` is the ledger `as_of`, not a clock read).

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| Every entry reports `drift="unknown"` | First run — there's no prior baseline to compare against | Run the spec a second time; drift is computed vs the prior run |
| `model_risk_report.json` absent | `model_risk_monitoring` omitted or `enabled: false` | Add/enable the block; the runner emits the report only when the monitor is on |
| Validation rejects `drift_high_ratio: 0.5` | The ratio must be `>= 1` — the engine derives the lower band as `1 / drift_high_ratio` | Use a value `>= 1` (e.g. `2.0` flags both a `>=2×` spike and a `<=0.5×` collapse) |
| A real typology shift shows as `high` drift | By design — the flag surfaces the candidate, it does not classify it | Route the entry to validation; the flag is advisory, not a verdict |

---

## Next steps

- [`spec-reference.md`](../spec-reference.md) — `program.model_risk_monitoring` field-by-field.
- [How to verify the audit chain](verify-audit-chain.md) — `model_risk_report.json` is one of the manifest-hashed artifacts; the drift flags are evidenced, not free-floating.
- [How to triage defects](triage-defects.md) — the sibling monitoring lens. Model-risk monitoring flags *population drift*; defects classify *why something didn't fire right*. Both are advisory; the deterministic rules stay authoritative.
