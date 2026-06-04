# How to triage defects from `defect_log.jsonl`

> **When you need this:** A run finished but you suspect "something didn't fire right" — a data-quality check failed, a `python_ref` scorer raised, a mapping was missing, a lineage chain broke. The `defect_log.jsonl` artifact (Round 28 PR-C1 / #420) is the Pillar-2 ticket queue: one entry per detectable issue, classified along four dimensions so the right human queue picks it up.
>
> **Prereqs:** A finished run directory under `.artifacts/`. `engine/defect_log.py::classify_defect` is the canonical classifier.
>
> **Time:** ~2 min per defect on average. Critical-severity entries should be triaged same-day.

`defect_log.jsonl` is one of the eight manifest-hashed artifacts — the **detected-defect snapshot at run finalize** is part of the immutable audit ledger. Later triage actions (acknowledge / resolve / close) are NOT re-written to the ledger; track those externally (see §5 below).

---

## Steps

### 1 · Read the defect log

```bash
jq -c . .artifacts/run-2026-05-25T10-15-30Z/defect_log.jsonl
```

Each line is a defect with this shape (from `engine/defect_log.py::Defect`):

```json
{
  "id": "DEFECT-...",
  "category": "data_quality",
  "classification": "data",
  "severity": "high",
  "summary": "txn.amount: 12 null values (limit 0)",
  "detected_by": "engine.dq.not_null_check",
  "source_run_id": "a1b2c3d4e5f6a7b8",
  "created_at": "2026-05-25T10:15:32Z",
  "status": "open"
}
```

Free-form description lives in `summary`; the producing component goes in `detected_by`; `source_run_id` is the deterministic 16-hex id returned by `derive_run_id(spec_content_hash, as_of, input_manifest)` — NOT the `.artifacts/run-<timestamp>` directory name. To cross-reference a defect to its run directory, you currently have to grep `defect_log.jsonl` across `.artifacts/run-*/` for the matching `source_run_id` (the manifest schema doesn't expose this id as a top-level field today; adding it is a small follow-up).

### 2 · Understand the four dimensions

| Dimension | Values | What it tells you |
|---|---|---|
| **`category`** (11 declared values) | Declared: `data_quality`, `rule_logic`, `mapping`, `threshold`, `lineage`, `metric`, `spec_config`, `external`, `runtime`, `sanctions_ref`, `typology_coverage`. **Currently emitted by `build_defect_log()`**: `data_quality` (DQ exceptions), `rule_logic` (`python_ref` failures), and `spec_config` (when `evaluate_contract_checks()` flags a malformed `quality_checks` config with `check_type="malformed_check"` — the corresponding `classification` is `mapping`). The remaining 8 categories are reserved for future emitters | The technical surface where the issue arose |
| **`classification`** (3 values) | `data`, `rule`, `mapping` | Which human queue triages it (decision tree in `classify_defect()`) |
| **`severity`** (5 tiers) | `critical`, `high`, `medium`, `low`, `info` | How fast it needs attention |
| **`status`** | `open`, `acknowledged`, `resolved`, `closed`, `wont_fix` | Where it is in the triage workflow |

### 3 · Walk the triage decision tree

The `classification` field tells you who owns the ticket:

```
                 ┌────────────────────────────────────┐
                 │  defect.category                   │
                 └────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼──────────────────────────┐
        ▼                         ▼                          ▼
  data_quality /              rule_logic /             mapping /
  lineage /                   threshold /              sanctions_ref /
  external /                  metric                   typology_coverage
  runtime                          │                          │
        │                          ▼                          ▼
        ▼                  classification = "rule"     classification = "mapping"
classification = "data"          (Engineer)                  (PM)
       (Data Engineer)
```

`classify_defect()` is pure + deterministic; you can re-run it on any `DQException` to recover the same classification.

### 4 · Work the queue top-down by severity

```bash
# Critical defects only, oldest first:
jq -s 'map(select(.severity == "critical")) | sort_by(.created_at)[]' defect_log.jsonl
```

For each defect, choose a target lifecycle:

- **`acknowledged`** — you've seen it; investigating
- **`resolved`** — fixed and verified (usually paired with a spec PR or pipeline fix)
- **`closed`** — resolved + verified across a subsequent run (manifest-hash-pinned proof)
- **`wont_fix`** — accepted as a known limitation; document why on the spec

Track transitions in your ticket-of-record system (Linear / Jira / GitHub issues) cross-referencing the defect `id` + `source_run_id`. The defect log itself is emitted fresh per run from the detected exceptions — a recurring underlying issue produces a new `Defect` row each run with a new `id`, so the absence of the defect in a later run IS the closure proof (verified via the manifest's `defect_log_hash`).

### 5 · Re-run to confirm

After a fix, re-run the spec:

```bash
aml run aml.yaml --seed 42
```

The next `defect_log.jsonl` shouldn't contain the same defect. If it does, the fix was incomplete.

### 6 · Triage equivalence divergences by cluster

When the defect is a **legacy↔new divergence** (a cell the legacy system fired that the new spec didn't, or vice versa), run the equivalence comparison and render the Markdown report:

```bash
aml equivalence .artifacts/run-2026-05-25T10-15-30Z --legacy legacy_alerts.csv --markdown report.md
```

Open `report.md` and read the **`## Divergence clusters`** table. Work the **largest cluster first** (rows are sorted by size descending): each cluster is one defect shape — same rule, severity, and window length — so a single root cause (data, rule logic, or mapping) usually explains the whole cluster, and one fix clears many cells.

The same clusters appear on **dashboard page 48 (Equivalence)** with a per-cluster drill-down into the member customers. Clustering is a **triage lens only** — the four-way MATCH / NEW_ONLY / LEGACY_ONLY / DIFF classification is what lands in the ledger.

---

## Verify it worked

Four checks:

1. **`defect_log.jsonl` exists** in the run dir (always emitted, even when empty).
2. **`manifest.json::defect_log_hash`** matches `sha256(defect_log.jsonl)` — `aml verify-decisions` only checks the `decisions.jsonl` chain, so verify this artifact hash manually: `sha256sum defect_log.jsonl` and compare to the manifest field.
3. **Re-running a known good spec** produces an empty (or expected-only) defect log.
4. **`classify_defect()` is idempotent** — re-running the classifier on the same input yields the same category + classification.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| Two different runs produce different `defect.id` for the same underlying exception | Expected when inputs / `as_of` / spec change — `derive_run_id()` hashes `spec_content_hash + as_of + input_manifest`, so a different `source_run_id` produces a different `defect.id`. For genuinely-identical runs the id should match (deterministic-replay contract). | Re-derive both runs' ids by hand and confirm the inputs/`as_of`/spec really are identical |
| Strict `python_ref` failure not in the defect log | Pre-PR-C1 codex pass-2: scorer abort skipped the log write | Re-run on R28+; the log write happens BEFORE the abort path |
| Declared DQ severity silently demoted to `medium` | Pre-PR-C1 codex pass-3: severity not honored from `quality_checks.severity` | Re-run on R28+; declared severity flows through (PR-B5 `QualityCheck.severity` field) |
| Same defect repeats every run | Underlying issue not actually fixed | The defect log is honest — keep working until the issue stops surfacing |

---

## Next steps

- [How to configure SLA monitoring](configure-sla.md) — the sibling Pillar-6 evidence (`sla_report.json`). Together: "is alert stale?" + "did the pipeline produce something processable?"
- [How to verify the audit chain](verify-audit-chain.md) — the **initial** `defect_log.jsonl` is one of the eight manifest-hashed artifacts, so the detected-state snapshot is on the chain. Lifecycle transitions after the run (acknowledged → resolved → closed) are NOT currently re-written to the ledger; track those externally (Linear / Jira) and rely on the absence of the same defect in a later run as the closure proof.
- [`audit-evidence.md`](../audit-evidence.md) — the eight manifest-hashed artifacts and how `defect_log.jsonl` sits among them.
