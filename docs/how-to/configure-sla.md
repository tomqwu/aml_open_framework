# How to configure SLA monitoring

> **When you need this:** You need alert-disposition SLAs (e.g. "every high-severity case must be resolved within 30 days") + batch-lateness monitoring (e.g. "the daily extract must arrive within 1 day of as_of").
>
> **Prereqs:** `Program.sla` block in `aml.yaml` (PR-LF1 #415, R27).
>
> **Time:** ~5 min to declare. Ongoing monitoring via dashboard / digest.

---

## Steps

> **TODO** — placeholder. The mechanism:
>
> 1. Declare a `program.sla:` block in `aml.yaml`:
>    ```yaml
>    program:
>      sla:
>        alert_disposition_days: 30
>        batch_cadence_days: 1
>        batch_lateness_grace_days: 1
>    ```
> 2. Engine emits `sla_report.json` every run (manifest-pinned)
> 3. Report fields: `total_breaches`, `breaches_by_rule`, `batch_lateness_days`, `batch_late`
> 4. Empty `program.sla` = monitor disabled, report still emitted (always-present contract)

---

## Verify it worked

> **TODO** — read `sla_report.json`, confirm `enabled: true`, examine `breaches`.

---

## Common problems

> **TODO** — full-timedelta vs `.days`-floor (resolved in PR-LF1 codex pass-2), `Z`-suffix datetime parsing (resolved pass-2), terminal events stamped AFTER `as_of` (resolved pass-3).

---

## Next steps

- See [How to triage defects from `defect_log.jsonl`](triage-defects.md) for the Pillar-2 evidence side.
- The Drift Monitor dashboard page (50) visualizes SLA breach rates over time.
