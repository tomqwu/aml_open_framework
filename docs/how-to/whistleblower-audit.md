# How to run the FinCEN Whistleblower internal-channel audit

> **When you need this:** The FinCEN Whistleblower Incentives and Protections NPRM (Federal Register 2026-06271, comment period closed June 1, 2026) proposes a 10–30% award structure from the $300M Financial Integrity Fund, with anti-retaliation protections. Before the final rule triggers implementation timelines, you need to audit five internal-channel governance signals so gaps are documented and remediable — not surprises on the first exam. The `aml whistleblower-audit` CLI (#531) reads a completed run and emits those five signals as a frozen, regulator-facing report.
>
> **Prereqs:** A completed run directory (`aml run aml.yaml --seed 42` produces one). The CLI is offline and post-run — it never blocks or changes the run. It FAILS CLOSED (non-zero exit) if `manifest.json` lacks `as_of`, so it cannot fabricate a timestamp.
>
> **Time:** ~5 min.

The whistleblower audit is **advisory and observational**. It reads what the run recorded — it never invents signals the run didn't capture. Five signals: SAR-backlog exposure (open alerts >30 days with no terminal close-out), escalation coverage (% of dispositions with a documented reviewer + rationale), triage time (median + p95 alert-to-close-out days), board-documented decisions (decisions tied to a board-report event), and ledger integrity (SHA-256 chain verification). A signal the run doesn't record is reported `0` or `not_tracked`, never fabricated.

---

## Steps

### 1 · Complete a run

```bash
aml run examples/community_bank/aml.yaml --seed 42
```

The auditor CLI reads `manifest.json`, `decisions.jsonl`, and the `cases/` directory from this run.

### 2 · Run the audit

```bash
aml whistleblower-audit examples/community_bank/aml.yaml .artifacts/run-*/
```

Emits a frozen `whistleblower_audit_report.json` in the run directory, pinned in `manifest.json` by SHA-256 hash.

For a board-report pipe table:

```bash
aml whistleblower-audit examples/community_bank/aml.yaml .artifacts/run-*/ --markdown
```

For a ✓/⚠/✗ NPRM readiness table against the NPRM's proposed expectations:

```bash
aml whistleblower-audit examples/community_bank/aml.yaml .artifacts/run-*/ --format nprm-gap
```

### 3 · Read `whistleblower_audit_report.json`

```bash
jq . .artifacts/run-*/whistleblower_audit_report.json
```

Five signals:

```json
{
  "generated_at": "2026-06-19T00:00:00+00:00",
  "sar_backlog_exposure": {
    "open_alerts_over_30d": 4,
    "pct_of_total_open": 0.12
  },
  "escalation_coverage_pct": 0.73,
  "triage_time": {
    "median_days": 6.2,
    "p95_days": 21.4
  },
  "board_documented_decisions": "not_tracked",
  "ledger_integrity": {
    "status": "ok",
    "entries_verified": 142
  }
}
```

### 4 · Interpret each signal

| Signal | What it measures | NPRM relevance |
|---|---|---|
| `sar_backlog_exposure` | Open alerts >30 days with no terminal close-out (`closed` or `escalated_to_str`) | A backlog of unresolved alerts is the primary insider-tip trigger in whistleblower programs |
| `escalation_coverage_pct` | % of disposition decisions with a documented reviewer + rationale | NPRM expects internal escalation channels to be documented — `<50%` is a gap |
| `triage_time.median_days` | Median days from alert open to terminal close-out | NPRM proposes timeliness expectations for internal reporting channels |
| `triage_time.p95_days` | 95th-percentile alert-to-close-out days | Tail exposure: the slow cases are the ones that turn into board-level surprises |
| `board_documented_decisions` | Decisions tied to a board-report event in the ledger | `not_tracked` when no board markers exist in `decisions.jsonl` — not a failure, but a documentation gap |
| `ledger_integrity` | `AuditLedger.verify_decisions()` — SHA-256 chain tamper check | A broken chain is a compliance program failure, not just an IT issue |

**`board_documented_decisions: "not_tracked"`** is expected for most runs — it means no decisions in `decisions.jsonl` carry a board-report marker. Add `aml board-report` attestation events to the ledger to make this signal active.

### 5 · Read the NPRM-gap format

```bash
aml whistleblower-audit examples/community_bank/aml.yaml .artifacts/run-*/ --format nprm-gap
```

Outputs a ✓/⚠/✗ table:

```
| NPRM Expectation                    | Status | Detail                          |
|-------------------------------------|--------|---------------------------------|
| SAR-backlog ≤ 5% open >30d          | ⚠      | 12% open >30d (4 of 33)         |
| Escalation coverage ≥ 80%           | ⚠      | 73% (21 of 29 dispositions)     |
| Triage time p95 ≤ 30d               | ✓      | p95 = 21.4d                     |
| Board-documented decisions          | —      | not tracked                     |
| Ledger integrity                    | ✓      | 142 entries verified             |
```

---

## Verify it worked

Three checks:

1. **`whistleblower_audit_report.json` exists** and `manifest.json::whistleblower_audit_report_hash` matches `sha256(whistleblower_audit_report.json)`.
2. **`generated_at` equals the run's `as_of`** — not a wall-clock read. The CLI fails with a non-zero exit if `manifest.json` lacks `as_of` rather than substituting `datetime.now()`.
3. **`board_documented_decisions` is `"not_tracked"`** unless you have explicit board-report events in `decisions.jsonl` — any other value when no board markers exist is a fabrication bug.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| CLI exits non-zero with "missing as_of" | `manifest.json` lacks the `as_of` field | This is intentional FAIL-CLOSED behaviour — re-run `aml run` to produce a valid manifest |
| All `triage_time` values are `null` | No terminal close-out events in `decisions.jsonl` | Run the engine on data with real case dispositions, or ensure synthetic data plants terminal events |
| `escalation_coverage_pct: 1.0` on synthetic data | Synthetic dispositions always carry the default reviewer | Expected — the signal becomes meaningful on real production data |
| `ledger_integrity.status: "tampered"` | Hash chain verification failed | Investigate the `decisions.jsonl` — entries may have been manually edited (this is a compliance event) |

---

## Next steps

- [How to verify the audit chain](verify-audit-chain.md) — the `ledger_integrity` signal the whistleblower audit checks; details on the SHA-256 chain structure.
- [How to triage defects](triage-defects.md) — the companion defect-lifecycle workflow; defects log *what didn't fire right*, the whistleblower audit logs *whether internal escalation is evidenced*.
- [How to configure SLA monitoring](configure-sla.md) — the SLA timer drives `triage_time`; configure `program.sla` to set per-severity time limits and surface breaches on the dashboard.
- [Source: Federal Register 2026-06271 — FinCEN Whistleblower NPRM](https://www.federalregister.gov/documents/2026/04/01/2026-06271/whistleblower-incentives-and-protections)
