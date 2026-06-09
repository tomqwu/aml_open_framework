# How to run a champion-challenger validation

> **When you need this:** You have labelled ground-truth data (which alerts were true positives), and you want to compare your current `prioritization` weights (champion) against a candidate weight set (challenger) to produce an SR 26-2 outcome artifact for your model-risk committee.
>
> **Prereqs:** `prioritization.enabled: true` in your spec (see [enable-prioritization.md](enable-prioritization.md)). A `labels.csv` file with `customer_id,is_true_positive` columns.
>
> **Time:** ~5 min per comparison. The output is frozen, deterministic, and manifest-pinned.

The M3 champion-challenger workflow compares two weight configurations on the same labelled alert set and reports `precision_at_k` (at k = 5, 10, 20) and `recall` for each, picking a `winner`. The output `priority_outcome.json` is the SR 26-2 independent-validation artifact: frozen, read-only, pinned in `manifest.json` as `priority_outcome_hash`. A **temporal-leakage guard** enforces that the scorer reads only as-of alert features (`sum_amount`, `amount`, `count`, `matched_row_ids` — the `LEAKAGE_SAFE_FEATURES` allowlist) — no future-dated signals can creep into the comparison.

---

## Steps

### 1 · Prepare the labels file

```csv
customer_id,is_true_positive
C0001,1
C0002,0
C0003,1
```

The file must have `customer_id` and `is_true_positive` (0 or 1) columns. Every `customer_id` in the file is matched against alerts in the run by `customer_id`. Alerts for customers **not** in the file are still ranked and still occupy top-k slots — they are simply not counted as hits. Because `precision@k` divides hits by `k` (not by the number of *labelled* rows in the top-k), an unlabeled alert sitting in the top-k **lowers** precision rather than being dropped. So a sparse labels file penalises precision: label every alert you can adjudicate.

### 2 · Run with champion weights only (baseline)

```bash
aml run my_aml.yaml --seed 42 --labels labels.csv
```

With `--labels` but no `--challenger-weights`, the challenger defaults to the champion config — so both columns report identical metrics and the `winner` is `"tie"`. This is the baseline. Inspect it:

```bash
jq '{champion: .champion.precision_at_k, recall: .champion.recall, winner}' \
  .artifacts/run-*/priority_outcome.json
```

### 3 · Run champion vs challenger

```bash
aml run my_aml.yaml --seed 42 \
  --labels labels.csv \
  --challenger-weights '{"severity": 1.5, "amount": 2.0, "risk_tier": 0.5, "volume": 0.25}'
```

`--challenger-weights` is a partial override: it is merged over the champion weights, so you only need to name the keys you change. Expected output in `priority_outcome.json`:

```json
{
  "enabled": true,
  "n_alerts": 47,
  "n_labelled_positives": 12,
  "k_values": [5, 10, 20],
  "champion": {
    "precision_at_k": {"5": 0.6, "10": 0.5, "20": 0.3},
    "recall":         0.83,
    "mean_score":     0.61,
    "weights":        {"severity": 1.0, "risk_tier": 1.0, "amount": 0.5, "volume": 0.5}
  },
  "challenger": {
    "precision_at_k": {"5": 0.6, "10": 0.4, "20": 0.3},
    "recall":         0.75,
    "mean_score":     0.64,
    "weights":        {"severity": 1.5, "risk_tier": 0.5, "amount": 2.0, "volume": 0.25}
  },
  "winner": "champion"
}
```

`precision_at_k` is a map keyed by k (`5`, `10`, `20`). The winner is decided by **recall first, then precision@20** (the largest k) as a deterministic tiebreak; equal on both yields `"tie"`. The config that surfaces more labelled true positives — and ranks them higher — wins.

### 4 · The temporal-leakage guard

The scorer only ever reads the as-of alert-feature keys in the `LEAKAGE_SAFE_FEATURES` allowlist (`sum_amount`, `amount`, `count`, `matched_row_ids`) — never a post-as_of field that happens to ride on the alert dict — so a champion-challenger replay cannot bias scores with future-dated data. Separately, the **challenger weights themselves** are constrained: `PrioritizationWeights` is `extra="forbid"`, so a `--challenger-weights` key outside `{severity, risk_tier, amount, volume}` is rejected at load time with a pydantic validation error:

```
1 validation error for PrioritizationWeights
future_field
  Extra inputs are not permitted [type=extra_forbidden, input_value=1.0, input_type=float]
    For further information visit https://errors.pydantic.dev/2.13/v/extra_forbidden
```

This is not a bug — it is the SR 26-2 invariant enforced at runtime.

### 5 · Confirm the artifact is frozen and pinned

```bash
jq .priority_outcome_hash .artifacts/run-*/manifest.json
```

Run twice with the same inputs — the hash must be identical. The artifact is read-only after `finalize()`. (When no `--labels` are supplied the `priority_outcome.json` artifact is never written and the `priority_outcome_hash` key is **omitted entirely** from the manifest — not stored as `null` — so a run without champion-challenger stays manifest-key-identical to the pre-M3 baseline. The `jq` above prints `null` in that case simply because the key is absent.)

---

## Interpret the outcome artifact for an MRC report

The `priority_outcome.json` is ready for your model-risk committee (MRC) report as-is. Typical framing:

> "Champion weights (severity=1.0, risk_tier=1.0, amount=0.5, volume=0.5) achieved precision@10 = 50%, recall = 83% on the Q2 2026 labelled set (n_labelled_positives = 12 over 47 alerts). Challenger weights (severity=1.5, amount=2.0, risk_tier=0.5, volume=0.25) achieved precision@10 = 40%, recall = 75%. Champion is retained (higher recall). Temporal-leakage guard enforced at runtime. Artifact hash: `<priority_outcome_hash>`."

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| No `priority_outcome.json` written, no error | Passed `--challenger-weights` but forgot `--labels` | The outcome artifact is only emitted when `--labels` is supplied; always pass both |
| A row counts as a negative you meant as positive | `is_true_positive` value not in the true-set | The parser treats only `1`/`true`/`yes`/`y`/`t` (case-insensitive) as a positive; anything else (incl. blank) is a negative — no error is raised, so check the CSV |
| `ValidationError: extra_forbidden` on a challenger key | Misspelled or non-existent weight name | Challenger keys must be exactly `severity`, `risk_tier`, `amount`, or `volume` |
| `priority_outcome_hash` key missing from the manifest | `--labels` not supplied, or `prioritization.enabled: false` | The outcome file is written (and its hash key added to the manifest) only when both hold; otherwise the key is omitted entirely (`jq` prints `null` for an absent key) |

---

## Next steps

- If challenger wins consistently on multiple labelled sets, promote its weights to the spec's `prioritization.weights` and re-run.
- See [enable-prioritization.md](enable-prioritization.md) for initial setup.
- See [monitor-model-risk.md](monitor-model-risk.md) for the ongoing drift/cadence monitoring layer.
