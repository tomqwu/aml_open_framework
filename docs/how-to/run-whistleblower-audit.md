# How to run a FinCEN Whistleblower internal-channel audit

> **When you need this:** Your MLRO / compliance-officer wants to demonstrate — in front of the board or an examiner — that the institution's internal reporting and escalation machinery actually works: alerts don't rot into a SAR backlog, escalations carry a documented reviewer and rationale, triage is timely, and material matters reach the board. FinCEN's proposed **Whistleblower Incentives and Protections** rule ([Federal Register 2026-06271](https://www.federalregister.gov/documents/2026/04/01/2026-06271/whistleblower-incentives-and-protections)) presses institutions to evidence exactly that internal channel. The offline `aml whistleblower-audit` CLI (#531) is the readiness mirror of that ask — computed only from artifacts a run already produced.
>
> **Prereqs:** A finalized run directory (`aml run aml.yaml`) — the audit reads its `manifest.json`, `decisions.jsonl`, and `cases/`. A spec that `aml validate` passes (it's loaded for cross-reference integrity). `engine/whistleblower_audit.py::build_whistleblower_audit_report` is the canonical, pure builder.
>
> **Time:** ~5 min.

The whistleblower audit is **advisory / readiness only**. The `whistleblower_audit_report.json` it emits *never blocks a run, never changes an alert, and never auto-dispositions a case*. It is a compliance-readiness lens: five governance signals rolled out of the audit ledger. It is explainable (every signal traces to a named ledger field), deterministic (`generated_at` is the run's `as_of` from `manifest.json`, never a wall-clock read), and honest (a signal a run does not record — e.g. board-report events — is reported as **0 / not-tracked**, never fabricated).

---

## What it measures

| Signal | Derived from | Reads as |
|---|---|---|
| `sar_backlog_exposure` | cases with a `case_opened` event but **no** terminal disposition, aged from `as_of` | `{open_stale_alerts, oldest_days}` — alerts open > 30 days never resolved to a SAR or a documented non-suspicious disposition |
| `escalation_coverage_pct` | disposition decisions (`escalated` / `escalated_to_str` / `closed` / `manual_review`) | % that carry **both** a documented reviewer (`reviewer`/`override_by`/… or a human `source`) **and** a rationale (`rationale`/`override_reason`/`narrative`/…) — vs system-auto |
| `triage_time` | `case_opened` → first terminal disposition (prefers the engine-stamped `resolution_hours`) | `{median_days, p95_days, n_decisions}` |
| `board_documented_decisions` | disposition decisions whose case also has a `board_report` / `board_review` / `board_escalation` event | a count — or **not-tracked** when no board markers appear anywhere |
| `ledger_integrity` | `AuditLedger.verify_decisions()` over the hash chain | `"verified"` / `"broken"` |

---

## Steps

### 1 · Run the spec

```bash
aml run examples/community_bank/aml.yaml --seed 42
```

The audit reads the run directory the engine just wrote (newest under `.artifacts/`).

### 2 · Run the audit

```bash
aml whistleblower-audit examples/community_bank/aml.yaml .artifacts/run-<ts>
```

This writes `whistleblower_audit_report.json` into the run directory (atomic write — an I/O error never leaves a partial file) and prints a one-line summary:

```
Wrote whistleblower audit JSON -> .artifacts/run-<ts>/whistleblower_audit_report.json
backlog: 0 stale (oldest 0d) | escalation coverage: 0% | triage median: 0.825d | ledger: verified
```

`--out <path>` overrides the destination. The report's `generated_at` is anchored to `manifest.json::as_of`, so re-running the audit against the same run is byte-deterministic.

### 3 · Read the JSON

```bash
jq . .artifacts/run-<ts>/whistleblower_audit_report.json
```

```json
{
  "enabled": true,
  "sar_backlog_exposure": { "open_stale_alerts": 0, "oldest_days": 0 },
  "escalation_coverage_pct": 0.0,
  "n_disposition_decisions": 46,
  "triage_time": { "median_days": 0.825, "p95_days": 3.9, "n_decisions": 46 },
  "board_documented_decisions": 0,
  "board_reporting_tracked": false,
  "ledger_integrity": "verified",
  "ledger_integrity_detail": "Decision log integrity verified",
  "generated_at": "2026-06-09T18:28:30.520354"
}
```

On the bundled synthetic run, escalation coverage reads `0%` and board reporting is `not tracked` — **by design**. The synthetic engine simulates dispositions as system-auto events with no reviewer/rationale metadata, and records no board-report events. Those are honest "not-tracked" zeros, not gaps the tool invents. They populate once real analysts disposition cases through the dashboard (which stamps `source: dashboard_ui` + a rationale) and a board-report event is appended.

### 4 · Board-report table

```bash
aml whistleblower-audit examples/community_bank/aml.yaml .artifacts/run-<ts> --markdown board.md
```

A pipe table you can paste straight into a board pack:

```
| Signal | Value |
| --- | --- |
| SAR backlog — open stale alerts (>30d) | 0 |
| SAR backlog — oldest (days) | 0 |
| Escalation coverage (documented reviewer + rationale) | 0% (46 disposition decisions) |
| Triage time — median (days) | 0.825 |
| Triage time — p95 (days) | 3.9 |
| Board-documented decisions | not tracked |
| Ledger integrity | verified |
```

### 5 · NPRM readiness gap

```bash
aml whistleblower-audit examples/community_bank/aml.yaml .artifacts/run-<ts> --format nprm-gap
```

A structured gap table mapping each NPRM-proposed expectation to ✓ / ⚠ / ✗ with the evidence field that decided it:

```
| Proposed requirement | Status | Evidence |
| --- | :---: | --- |
| Internal reporting channel documented | ✓ | `ledger_integrity=verified` |
| Median triage < 30d | ✓ | `triage_time.median_days=0.825` |
| SAR backlog ≤ 0 | ✓ | `sar_backlog_exposure.open_stale_alerts=0` |
| Board-level escalation documented | ⚠ | `board_documented_decisions=not tracked` |
```

✓ = met · ⚠ = not tracked in this run · ✗ = gap. The thresholds (backlog ≤ 0, median triage < 30 days) are explicit so the verdict is auditable, not a black box.

---

## Verify it worked

1. **`whistleblower_audit_report.json` exists** in the run dir and parses as the `WhistleblowerAuditReport` shape above.
2. **Determinism** — re-run the audit against the same run; the JSON is byte-identical (`generated_at` is the ledger `as_of`, not a clock read).
3. **Integrity reflects tampering** — edit a line in `decisions.jsonl` after finalize, re-run the audit, and `ledger_integrity` flips to `"broken"`.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `escalation_coverage_pct` is `0` | The run's dispositions are engine-simulated (system-auto, no reviewer/rationale) | Expected on a synthetic run. Coverage rises as analysts disposition cases through the dashboard, which stamps `source` + a rationale |
| `board_documented_decisions` is `not tracked` | No `board_report` / `board_review` / `board_escalation` event in the ledger | Expected when board reporting isn't wired into the ledger yet; the tool reports `not-tracked` rather than inventing a zero |
| `ledger_integrity` is `broken` | `decisions.jsonl` no longer matches the manifest's hash chain | A tamper signal — investigate before trusting any other number in the report |
| `triage_time.median_days` is `null` | The run has no disposition decisions yet (only `case_opened`) | Run a spec that exercises the workflow, or wait for analysts to disposition cases |

---

## Next steps

- [How to verify the audit chain](verify-audit-chain.md) — the same hash chain `ledger_integrity` reads; this audit's integrity signal is just that check surfaced as a governance KPI.
- [Configure SLA monitoring](configure-sla.md) — the sibling timeliness lens. SLA monitoring tracks *per-case breach against a configured clock*; the whistleblower audit tracks *aggregate triage time + SAR backlog* against the NPRM's 30-day reference.
- The source: [FinCEN Whistleblower Incentives and Protections, Federal Register 2026-06271](https://www.federalregister.gov/documents/2026/04/01/2026-06271/whistleblower-incentives-and-protections).
