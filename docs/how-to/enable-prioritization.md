# How to enable the alert prioritization scorer

> **When you need this:** You want investigators to work the highest-SAR-likelihood alerts first, with a transparent, explainable score — without changing any alert's disposition or automating any decision.
>
> **Prereqs:** A working `aml.yaml` spec. `aml validate` succeeds. `pip install -e ".[dev]"` done.
>
> **Time:** ~10 min to declare + verify. The scorer is additive — existing alert/case/audit behaviour is byte-identical when disabled.

The N1 prioritization scorer (`program.prioritization`) stamps every alert with a `priority_score` (0–1) and a `priority_explanation` showing exactly which features contributed what amount. It is **advisory only**: it never changes a disposition, never closes an alert, and never blocks a run. The score is deterministic — same spec + same data + same seed = identical scores.

---

## Steps

### 1 · Add the `prioritization` block to your spec

```yaml
program:
  name: my_aml_program
  # ... existing fields ...
  prioritization:
    enabled: true
    weights:
      severity: 1.0   # ordinal urgency of the rule (low=0.25 / medium=0.5 / high=0.75 / critical=1.0)
      risk_tier: 1.0  # risk posture of the rule (low=0.33 / medium=0.66 / high=1.0; None→0)
      amount: 0.5     # log-scaled txn amount, capped at $100k → [0, 1]
      volume: 0.5     # txn count behind the alert, capped at 50 → [0, 1]
```

The four weights are the defaults. Start with them — tune after you have labelled outcome data (see [run-champion-challenger.md](run-champion-challenger.md)).

### 2 · Validate the spec

```bash
aml validate my_aml.yaml
```

Expected: `✓ Spec is valid`. If you see `program.prioritization.enabled must be a boolean`, check the YAML indentation.

### 3 · Run the engine

```bash
aml run my_aml.yaml --seed 42
```

The engine now stamps `priority_score` and `priority_explanation` on every alert (in the per-rule `alerts/*.jsonl` files), and writes a `priority_report.json` distribution summary to the run directory.

### 4 · Inspect the priority report

`priority_report.json` is a deterministic summary: a per-rule scored count plus the top-N alerts ranked by score. Each `top_alerts` row carries `customer_id`, `rule_id`, and `priority_score` (the per-feature `priority_explanation` rides on the alert record itself, not on this summary).

```bash
jq '.top_alerts[0:5]' .artifacts/run-*/priority_report.json
```

```json
{
  "enabled": true,
  "scored_alerts": 31,
  "by_rule": { "structuring_burst": 4, "rapid_movement": 7 },
  "top_alerts": [
    { "customer_id": "C0001", "rule_id": "structuring_burst", "priority_score": 0.82 }
  ]
}
```

To see the full per-feature paper trail, read `priority_explanation` off the alert itself:

```bash
jq 'select(.priority_score) | {customer_id, priority_score, priority_explanation}' \
  .artifacts/run-*/alerts/*.jsonl
```

```json
{
  "customer_id": "C0001",
  "priority_score": 0.82,
  "priority_explanation": [
    { "feature": "bias",      "value": 1.0,  "contribution": -1.0 },
    { "feature": "severity",  "value": 0.75, "contribution": 0.75 },
    { "feature": "risk_tier", "value": 0.66, "contribution": 0.66 },
    { "feature": "amount",    "value": 0.63, "contribution": 0.32 },
    { "feature": "volume",    "value": 0.20, "contribution": 0.10 }
  ]
}
```

`score = sigmoid(Σ contributions)` — and the `bias` term (value `1.0`, contribution `-1.0`) is part of that sum. The explanation is the full paper trail.

### 5 · Open the Triage Queue dashboard

```bash
aml dashboard my_aml.yaml
```

Navigate to **Triage Queue** (page 52). Alerts are ranked highest-score-first. Click any row to expand the "Why this score?" panel showing the per-feature breakdown.

---

## Verify it worked

```bash
# Check the run dir has the priority artefact
ls .artifacts/run-*/priority_report.json

# Confirm the report is deterministic (re-run and compare hashes)
aml run my_aml.yaml --seed 42
jq .priority_report_hash .artifacts/run-*/manifest.json
```

Run twice — the hash must be identical.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| No `priority_score` on alerts | `enabled: false` or block missing | Set `prioritization.enabled: true` |
| `NaN` in `priority_score` | Spec has `.inf` or `.nan` in a weight | Weights must be finite floats — validation rejects non-finite values |
| Score changes between runs | Non-deterministic data source | Use `--seed` + a deterministic data source (CSV / `--data-source synthetic`) |

---

## Next steps

- **Tune the weights with labelled data**: see [run-champion-challenger.md](run-champion-challenger.md).
- **Layer governed suppression on top**: see [configure-risk-segmentation.md](configure-risk-segmentation.md).
- **View the Drift Monitor**: `program.model_risk_monitoring` watches the N1 scorer's alert-volume drift across runs — see [monitor-model-risk.md](monitor-model-risk.md).
