# How to triage defects from `defect_log.jsonl`

> **When you need this:** A run finished but you suspect "something didn't fire right." The `defect_log.jsonl` artifact (Round 28 PR-C1 #420) is the Pillar-2 ticket queue — one entry per DQ exception, `python_ref` failure, or other detected issue.
>
> **Prereqs:** Finished run directory with `defect_log.jsonl`.
>
> **Time:** ~2 min per defect, on average.

---

## Steps

> **TODO** — placeholder. The mechanism:
>
> 1. Read `defect_log.jsonl` — one JSON line per defect
> 2. Each defect has 4 dimensions:
>    - **Category** (11 values): `data_quality / rule_logic / mapping / threshold / lineage / metric / spec_config / external / runtime / sanctions_ref / typology_coverage`
>    - **Classification** (3 values, triage decision tree): `data / rule / mapping`
>    - **Severity** (5 tiers): `critical / high / medium / low / info`
>    - **Lifecycle**: `open / acknowledged / resolved / closed / wont_fix`
> 3. Sort by `severity` + `created_at`, work top-down
> 4. The `engine/defect_log.py::classify_defect` helper is the canonical classifier — read its body to understand the decision tree

---

## Verify it worked

> **TODO** — defects classified consistently, lifecycle states transition cleanly, manifest hash pins.

---

## Common problems

> **TODO** — `derive_run_id` collision (resolved in PR-C1 codex pass-1), strict python_ref abort skipping defect log (resolved pass-2), declared DQ severity silently demoted (resolved pass-3).

---

## Next steps

- See [How to verify the audit chain](verify-audit-chain.md) — `defect_log_hash` is part of the manifest, ensure it doesn't drift.
- See [Configure SLA monitoring](configure-sla.md) — defect lifecycle states feed into SLA breach detection.
