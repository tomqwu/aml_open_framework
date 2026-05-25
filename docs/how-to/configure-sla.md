# How to configure SLA monitoring

> **When you need this:** You want first-class evidence for the two SLAs every AML examiner asks about: *"how long do open alerts sit?"* and *"how fresh is the data the rules ran against?"* You want this **declared in the spec** (peer-reviewed, replayable) rather than tracked in a side spreadsheet.
>
> **Prereqs:** `Program.sla` block on `aml.yaml`. Shipped in PR-LF1 (#415) / Round 27.
>
> **Time:** ~5 min to declare. Ongoing monitoring via reading `sla_report.json` directly — no dashboard page or `notify-digest` flow currently consumes the SLA artifact (see §4 below).

The Pillar-6 SLA monitor (`engine/sla.py`) evaluates two breach types per run and emits `sla_report.json` — one of the eight manifest-hashed artifacts, so the SLA evidence is part of the immutable audit ledger. The monitor is **observational, not enforcing**: the engine never aborts on a breach; it records it for downstream surfaces.

---

## Steps

### 1 · Declare the SLA block

```yaml
program:
  name: community_bank_aml
  jurisdiction: US
  regulator: FinCEN
  owner: chief_compliance_officer
  effective_date: 2026-01-01
  sla:
    alert_disposition_days: 30          # default 30; days before an open alert is "stale"
    batch_cadence_days: 1               # default 1; expected cadence of the data extract
    batch_lateness_grace_days: 1        # default 1; grace before late batch flagged
```

All three sub-fields are optional with the defaults shown. Omitting the whole `sla:` block disables the monitor (the report still emits, with `enabled: false`).

### 2 · Tune for your operational reality

| Field | Typical value | Why |
|---|---|---|
| `alert_disposition_days` | 30 (FinCEN guidance) for high-volume programs, 14 for fintechs | The threshold above which open alerts become an exam finding |
| `batch_cadence_days` | 1 for batch programs, 0 for near-real-time | Sets the "expected" gap between `as_of` and the most recent transaction |
| `batch_lateness_grace_days` | 1 (24h) for batch, 0 for SLA-critical pipelines | Late-but-acceptable buffer before the run is flagged |

### 3 · Run + read the report

```bash
aml run aml.yaml --seed 42
jq . .artifacts/run-*/sla_report.json
```

Output shape (fields from `engine/sla.py::SLAReport`):

```json
{
  "enabled": true,
  "alert_disposition_days": 30,
  "batch_cadence_days": 1,
  "batch_lateness_grace_days": 1,
  "total_breaches": 1,
  "breaches_by_rule": {"structuring_burst": 1},
  "breaches": [
    {"case_id": "C0042-...", "opened_at": "2026-04-10T...", "age_days": 45, "rule_id": "structuring_burst"}
  ],
  "batch_lateness_days": 2,
  "batch_late": true,
  "latest_transaction_at": "2026-05-23T18:42:00Z"
}
```

### 4 · Visualize over time

The SLA artifact is **emitted to disk only** today — `sla_report.json` per run, manifest-hash pinned, but no dashboard page currently subscribes to it. The Today landing card pack for Manager personas has a `_sla_breach_count()` helper that reads an `sla_state` column off `df_cases`, but the default DataFrame loader doesn't populate that column from `program.sla` / `sla_report.json` — so unless a custom loader enriches it, the breach count renders as 0 regardless of what the run actually emitted. For trend visualization you currently chart externally; a future dashboard surface that reads `sla_report.json` per archived run is the natural follow-up.

### 5 · Wire into ops escalation

The framework records the breach; **routing the human escalation is yours**. Common patterns:

- Read `sla_report.json` from a downstream CI job; open a Linear/Jira ticket when **either** `total_breaches > 0` (stale open alerts) **or** `batch_late == true` (late data extract). The two metrics are independent — a late batch with no stale cases sets `batch_late` true but leaves `total_breaches` at 0, so a single-field trigger would silently skip pipeline lateness. This OR-trigger is the recommended integration today.
- `aml notify-digest` (CLI) generates a Markdown run summary — note that it reads `decisions.jsonl` events, not `sla_report.json`, so it doesn't currently surface SLA breaches in the digest. Wiring an `sla_breach` decision-event emitter alongside the JSON report would surface it; until then, treat the artifact as the source of truth.
- The post-run `monitoring_digest.json` (Pillar-2 sibling, PR-LF4) carries the per-rule alert count delta — combine with the SLA report for "rules accumulating backlog."

---

## Verify it worked

Four checks:

1. **`sla_report.json` exists and `enabled: true`** when the spec declares a `sla:` block.
2. **`manifest.json::sla_report_hash`** matches `sha256(sla_report.json)`. `aml verify-decisions` only checks the `decisions.jsonl` chain — to verify the SLA artifact hash, recompute manually: `sha256sum sla_report.json` and compare to `manifest.json::sla_report_hash`.
3. **A planted late case** (an open `case_opened` event older than `alert_disposition_days` and no terminal decision) appears in `breaches`.
4. **A planted late batch** (`as_of - latest_transaction_at > cadence + grace`) flips `batch_late: true`.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| Report exists but `enabled: false` | `Program.sla` block omitted | Add the block (the report is always emitted; only the monitor needs explicit enablement) |
| `age_days` looks off by 1 | Full-timedelta vs `.days`-floor (resolved PR-LF1 codex pass-2) | Re-run on R27+; the floor is now correct |
| Late `case_opened` event ignored | The opened-at timestamp has no timezone suffix | The parser handles `Z`/`+00:00`/naive (PR-LF1 codex pass-2). If still off, check that the event's timestamp ISO-formats correctly |
| Cases with terminal events AFTER `as_of` still flagged as open | Pre-PR-LF1 codex pass-3 bug | Re-run on R27+; the comparison now respects `as_of` strictly |
| Batch never flagged late | `as_of` overridden via `--as-of` to a recent date | Expected. The check uses the run's `as_of`, not wallclock |

---

## Next steps

- [How to triage defects](triage-defects.md) — Pillar-2 ticket queue (`defect_log.jsonl`) for the sibling evidence: not "is alert stale?" but "did the data pipeline cough up something the engine couldn't process?"
- Note: `pages/50_Drift_Monitor.py` plots `python_ref` alert-volume drift, NOT SLA breach trends. Adding an SLA-trend chart is a small follow-up that would consume `sla_report.json` per archived run.
- The [audit-evidence reference](../audit-evidence.md) explains where `sla_report.json` sits in the eight manifest-hashed artifacts.
