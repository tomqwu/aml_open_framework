# How to manage the defect lifecycle

> **When you need this:** A run has produced a `defect_log.jsonl` (emitted by the data-quality and model-risk passes) and your compliance team needs to triage, acknowledge, resolve, and close each defect with a documented reviewer and resolution — in an auditable, append-only trail. The offline `aml defect-update` command (#529, North Star Pillar 2) is the post-run tool for this workflow. The frozen `defect_log.jsonl` is never modified; all state transitions land on the companion `defect_lifecycle.jsonl`.
>
> **Prereqs:** A completed `aml run` that produced a `defect_log.jsonl` in the run directory. `engine/defect_lifecycle.py::append_defect_lifecycle_event` is the canonical pure writer.
>
> **Time:** ~5 min per defect.

The defect lifecycle is **append-only and advisory** — it mirrors the `decisions.jsonl` posture. `defect_log.jsonl` is frozen at run time and manifest-pinned; the `defect_lifecycle.jsonl` companion carries the triage history. Neither file is ever rewritten. An unknown `defect_id` (not present in the frozen log) is rejected so the companion cannot drift from its source.

---

## Steps

### 1 · Inspect the defect log

```bash
jq . .artifacts/run-<ts>/defect_log.jsonl | head -40
```

Each line is a frozen defect record:

```json
{
  "defect_id": "def-001",
  "rule_id": "structuring_cash",
  "category": "threshold_calibration",
  "description": "Alert volume 18% above expected for customer segment retail_low",
  "severity": "medium",
  "detected_at": "2026-06-09T18:28:30.520354",
  "status": "open"
}
```

The `defect_id` is stable across the run's lifetime — use it in all `defect-update` calls.

### 2 · Acknowledge a defect

Acknowledging signals that a reviewer has seen the defect and is tracking it:

```bash
aml defect-update .artifacts/run-<ts> def-001 \
  --status acknowledged \
  --reviewer alice@bank.example
```

This appends one canonical-JSON line to `defect_lifecycle.jsonl`:

```json
{
  "defect_id": "def-001",
  "status": "acknowledged",
  "reviewer": "alice@bank.example",
  "timestamp": "2026-06-09T18:31:51.015515",
  "resolution": null
}
```

The `timestamp` is anchored to the run's `manifest.json::as_of` (never wall-clock) for byte-stability — re-running the same command against the same run produces an identical event.

### 3 · Resolve a defect

Once the underlying issue is addressed (threshold adjusted, data contract corrected, model retrained), mark it `resolved` with a non-empty resolution:

```bash
aml defect-update .artifacts/run-<ts> def-001 \
  --status resolved \
  --reviewer alice@bank.example \
  --resolution "Adjusted structuring_cash threshold from 9_500 to 9_800 after FP analysis — see PR #553"
```

`resolved` and `closed` both require a non-empty `--resolution`; the command rejects the transition without one.

### 4 · Close a defect

Final close-out, typically after a sign-off review:

```bash
aml defect-update .artifacts/run-<ts> def-001 \
  --status closed \
  --reviewer mlro@bank.example \
  --resolution "Confirmed resolved in next run (2026-06-10). No repeat; threshold change effective."
```

### 5 · Read the full lifecycle trail

```bash
jq . .artifacts/run-<ts>/defect_lifecycle.jsonl
```

Each line is one transition event. The trail is append-only — every `acknowledged` → `resolved` → `closed` step is individually recorded, never overwritten.

---

## Verify it worked

Three checks:

1. **`defect_lifecycle.jsonl` exists** alongside `defect_log.jsonl` in the run dir and the status progression is complete.
2. **`defect_log.jsonl` is unchanged** — the frozen log's line count and hash are the same as at run time. Only `defect_lifecycle.jsonl` grows.
3. **Unknown defect IDs are rejected** — try `aml defect-update .artifacts/run-<ts> def-DOES-NOT-EXIST --status acknowledged --reviewer test` and confirm you get a non-zero exit code and an error message.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `Unknown defect_id: def-XXX` | The ID isn't in `defect_log.jsonl` for this run | Check the ID with `jq .defect_id .artifacts/run-<ts>/defect_log.jsonl` |
| `--resolution is required for status resolved/closed` | Omitted `--resolution` flag | Add `--resolution "<your rationale>"` |
| `defect_lifecycle.jsonl` timestamp doesn't match wall-clock | Expected — timestamps derive from `manifest.json::as_of`, not the clock | This is the designed determinism guarantee; use the run's `as_of` as the reference |
| The frozen `defect_log.jsonl` looks different from a prior run | Re-runs produce fresh frozen logs | Each run mints its own `defect_log.jsonl`; manage each run's companion lifecycle independently |

---

## Next steps

- [Triage defects from `defect_log.jsonl`](triage-defects.md) — the classification and decision-tree guide for deciding which category each defect falls into before you update its status.
- [Verify the audit chain](verify-audit-chain.md) — `defect_lifecycle.jsonl` is append-only for the same reason `decisions.jsonl` is: both are immutable evidence that survives an examiner's replay.
- [Monitor model risk + drift](monitor-model-risk.md) — the model-risk monitoring report (`model_risk_report.json`) is the per-rule lens that surfaces the defects this workflow closes.
