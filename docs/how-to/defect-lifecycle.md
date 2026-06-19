# How to manage the defect-ticket lifecycle

> **When you need this:** A run produced a `defect_log.jsonl` (via `program.defect_logging: enabled: true`), and you need to triage, acknowledge, resolve, or close individual defect entries — without touching the frozen log itself. The `aml defect-update` CLI (#529, North Star Pillar 2) appends lifecycle transitions to a companion `defect_lifecycle.jsonl`, mirroring the append-only posture of `decisions.jsonl`. The frozen defect log stays a byte-stable, manifest-pinned artifact; only the lifecycle companion grows.
>
> **Prereqs:** A run directory containing a frozen `defect_log.jsonl`. Enable defect logging in your spec with `program.defect_logging: enabled: true`. A `reviewer` identity string (your staff ID, email alias, or any stable label for the audit trail).
>
> **Time:** ~5 min per defect.

Defect tickets are **advisory governance artifacts**. A defect captures something the engine observed that didn't meet the program's own quality bar — a rule that fired zero times against a planted typology, a contract freshness violation, a threshold that never triggered. The lifecycle transitions (`acknowledged` → `resolved` → `closed`) are the compliance team's documented response. The rules, alerts, and dispositions in `decisions.jsonl` are never affected.

---

## Steps

### 1 · Enable defect logging in your spec

```yaml
program:
  name: community_bank_aml
  defect_logging:
    enabled: true
    # severity_threshold: medium   # optional: only log medium/high defects
```

### 2 · Run to generate the frozen defect log

```bash
aml run aml.yaml --seed 42
```

A `defect_log.jsonl` appears in the run directory. Each line is one defect:

```json
{"defect_id": "DFT-a3b1c2", "rule_id": "structuring_burst", "kind": "zero_fire", "severity": "high", "description": "Rule fired 0 alerts against 100 customers at seed 42", "timestamp": "2026-06-19T00:00:00+00:00"}
```

This file is **frozen** — never edited, never rewritten.

### 3 · Acknowledge a defect

```bash
aml defect-update .artifacts/run-*/ DFT-a3b1c2 \
  --status acknowledged \
  --reviewer mlro_jane_smith
```

Appends one line to `defect_lifecycle.jsonl`:

```json
{"defect_id": "DFT-a3b1c2", "status": "acknowledged", "reviewer": "mlro_jane_smith", "resolution": null, "timestamp": "2026-06-19T00:00:00+00:00"}
```

`timestamp` derives from the run's `manifest.json::as_of` — not wall-clock — for byte-stability.

### 4 · Resolve a defect

`resolved` requires a non-empty `--resolution` explaining what was done:

```bash
aml defect-update .artifacts/run-*/ DFT-a3b1c2 \
  --status resolved \
  --reviewer mlro_jane_smith \
  --resolution "Threshold lowered from 10 to 7 txns in 30d — rule now fires at seed 42. See PR #534."
```

### 5 · Close a defect

`closed` also requires a `--resolution`:

```bash
aml defect-update .artifacts/run-*/ DFT-a3b1c2 \
  --status closed \
  --reviewer mlro_jane_smith \
  --resolution "Confirmed resolved in v0.1.62 run 2026-06-22. Re-ran with seed 42 — 3 alerts fired. Defect retired."
```

### 6 · Read the lifecycle log

```bash
jq . .artifacts/run-*/defect_lifecycle.jsonl
```

The companion log is append-only — it contains one line per status transition in chronological order. Multiple transitions for the same `defect_id` are normal (acknowledged → resolved → closed is the standard arc).

### 7 · Review on the dashboard

- **Defect Triage (dashboard)** — when `defect_logging` is enabled, the dashboard renders the frozen defect log alongside the lifecycle companion: open defects sorted by severity, lifecycle status per defect, and resolution text. Advisory framing is explicit — defect triage never auto-closes or modifies the alert queue.

---

## Verify it worked

Three checks:

1. **`defect_lifecycle.jsonl` is append-only** — each `aml defect-update` call adds exactly one line; no lines are deleted or rewritten.
2. **`timestamp` equals the run's `as_of`** — not a wall-clock read. Two invocations against the same run directory produce the same `timestamp` (byte-stable).
3. **Unknown `defect_id` is rejected** — `aml defect-update` with a `defect_id` not present in `defect_log.jsonl` exits non-zero. The companion log cannot drift from the frozen log.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `resolved` / `closed` rejected | Missing or empty `--resolution` | Both statuses require a non-empty `--resolution` string |
| Unknown defect ID error | `defect_id` not in `defect_log.jsonl` for this run | List valid IDs with `jq '.defect_id' defect_log.jsonl` |
| `defect_log.jsonl` absent | `defect_logging` not enabled in the spec | Add `program.defect_logging: enabled: true` and re-run |
| `timestamp` is a wall-clock value | Bug — `timestamp` should equal `manifest.json::as_of` | File a bug; the lifecycle writer must derive timestamp from the manifest, not `datetime.now()` |

---

## Lifecycle state machine

```
(new defect in defect_log.jsonl)
    ↓
acknowledged  ←——  (reviewer reads + documents awareness)
    ↓
resolved      ←——  (fix applied; --resolution required)
    ↓
closed        ←——  (re-run confirms fix; --resolution required)
```

`acknowledged → closed` directly is allowed (skip `resolved` if the fix is immediate). Backward transitions are not enforced by the CLI — but the append-only log makes every transition visible to auditors.

---

## Next steps

- [`spec-reference.md`](../spec-reference.md) — `program.defect_logging` field-by-field, including `severity_threshold` and `kinds`.
- [How to triage defects](triage-defects.md) — the broader defect-triage workflow: how defects are classified, which kinds map to which remediation patterns.
- [How to verify the audit chain](verify-audit-chain.md) — `defect_log.jsonl` is one of the manifest-hashed frozen artifacts; the lifecycle companion is not hashed (it's append-only by design, not frozen).
- [How to monitor model risk](monitor-model-risk.md) — the sibling monitoring lens: defect lifecycle tracks *specific quality failures*; model-risk monitoring tracks *population-level drift*.
