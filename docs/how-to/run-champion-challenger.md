# How to run a champion-challenger validation

> **When you need this:** You have labelled ground-truth data (which alerts were true positives), and you want to compare your current `prioritization` weights (champion) against a candidate weight set (challenger) to produce an SR 26-2 outcome artifact for your model-risk committee.
>
> **Prereqs:** `prioritization.enabled: true` in your spec (see [enable-prioritization.md](enable-prioritization.md)). A `labels.csv` file with `customer_id,is_true_positive` columns.
>
> **Time:** ~5 min per comparison. The output is frozen, deterministic, and manifest-pinned.

The M3 champion-challenger workflow compares two weight configurations on the same labelled alert set and reports `precision@k` and `recall` for each, picking a `winner`. The output `priority_outcome.json` is the SR 26-2 independent-validation artifact: frozen, read-only, pinned in `manifest.json` as `priority_outcome_hash`. A **temporal-leakage guard** enforces that the scorer reads only as-of alert features — no future-dated signals can creep into the comparison.

---

## Steps

### 1 · Prepare the labels file

```csv
customer_id,is_true_positive
C0001,1
C0002,0
C0003,1
```

The file must have `customer_id` and `is_true_positive` (0 or 1) columns. Every `customer_id` in the file is matched against alerts in the run by `customer_id`. Alerts for customers not in the file are excluded from the outcome metrics (they are not labelled).

### 2 · Run with champion weights only (baseline)

```bash
aml run my_aml.yaml --seed 42 --labels labels.csv
```

This produces `priority_outcome.json` with champion-only metrics. Inspect it:

```bash
jq '{champion_precision_at_k, champion_recall, winner}' \
  .artifacts/run-*/priority_outcome.json
```

### 3 · Run champion vs challenger

```bash
aml run my_aml.yaml --seed 42 \
  --labels labels.csv \
  --challenger-weights '{"severity": 1.5, "amount": 2.0, "risk_tier": 0.5, "volume": 0.25}'
```

Expected output in `priority_outcome.json`:

```json
{
  "champion": {
    "weights":    {"severity": 1.0, "risk_tier": 1.0, "amount": 0.5, "volume": 0.5},
    "precision_at_k": 0.71,
    "recall":         0.83
  },
  "challenger": {
    "weights":    {"severity": 1.5, "amount": 2.0, "risk_tier": 0.5, "volume": 0.25},
    "precision_at_k": 0.68,
    "recall":         0.79
  },
  "winner":      "champion",
  "k":           10
}
```

`k` defaults to `min(10, len(labelled_alerts))`. The winner is picked by `precision@k` — the config that ranks more true positives in the top-k positions wins.

### 4 · Verify the temporal-leakage guard

The guard rejects any feature not in the scorer's as-of allowlist (`severity`, `risk_tier`, `amount`, `volume`). A `--challenger-weights` key outside the allowlist raises:

```
ValueError: challenger weight 'future_field' is not in the allowed feature set
```

This is not a bug — it is the SR 26-2 invariant enforced at runtime.

### 5 · Confirm the artifact is frozen and pinned

```bash
jq .priority_outcome_hash .artifacts/run-*/manifest.json
```

Run twice with the same inputs — the hash must be identical. The artifact is read-only after `finalize()`.

---

## Interpret the outcome artifact for an MRC report

The `priority_outcome.json` is ready for your model-risk committee (MRC) report as-is. Typical framing:

> "Champion weights (severity=1.0, risk_tier=1.0, amount=0.5, volume=0.5) achieved precision@10 = 71%, recall = 83% on the Q2 2026 labelled set (N = 47 labelled alerts). Challenger weights (severity=1.5, amount=2.0, risk_tier=0.5, volume=0.25) achieved precision@10 = 68%, recall = 79%. Champion is retained. Temporal-leakage guard enforced at runtime. Artifact hash: `<priority_outcome_hash>`."

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `--labels required when --challenger-weights given` | Forgot `--labels` | Always pass `--labels` alongside `--challenger-weights` |
| `ValueError: is_true_positive must be 0 or 1` | Non-binary label in CSV | Fix labels file — only 0 and 1 are valid |
| Same hash every run but different `precision@k` | Labels file changed between runs | The hash covers the alert features, not the labels file; use the same labels file for reproducible comparison |
| `priority_outcome_hash` absent from manifest | Prioritization disabled | Set `prioritization.enabled: true` |

---

## Next steps

- If challenger wins consistently on multiple labelled sets, promote its weights to the spec's `prioritization.weights` and re-run.
- See [enable-prioritization.md](enable-prioritization.md) for initial setup.
- See [monitor-model-risk.md](monitor-model-risk.md) for the ongoing drift/cadence monitoring layer.
