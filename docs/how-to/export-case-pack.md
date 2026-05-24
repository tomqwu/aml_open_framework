# How to export per-case / per-batch evidence packs

> **When you need this:** A regulator/auditor asks for evidence on a SPECIFIC case (or a hand-selected batch), not the whole run. The full audit pack is 50+ MB; the case pack is ~50 KB.
>
> **Prereqs:** A finished run directory. `aml export-case` and `aml export-batch` CLI commands (shipped in PR-D4 #424).
>
> **Time:** ~30 sec per export.

---

## Steps

> **TODO** — placeholder. The mechanism:
> 1. `aml export-case <spec> <run_dir> <case_id> [--out case.zip] [--signing-key ...]`
> 2. `aml export-batch <spec> <run_dir> --cases c1,c2,c3 [--out batch.zip]`
> 3. Pack contents: spec_snapshot.yaml, cases/<id>.json, decisions/<id>.jsonl (filtered), alerts/<id>.jsonl (case-canonical, no sibling leak), lineage/<id>.json, rules/<rule>.sql, manifest.json
> 4. Optional HMAC-SHA256 manifest signature via signing-key (PR-D4 codex review)
> 5. PII masking honoured — field-aware leaf + token-level compound masking preserves the run's masking contract

---

## Verify it worked

> **TODO** — unzip the case pack, walk the manifest hashes, confirm `aml verify-decisions` (PARTIAL mode) passes on the filtered decisions.

---

## Common problems

> **TODO** — case_id not in run, sibling-alert leak (resolved in PR-D4 codex pass), corrupt `pii_map.jsonl` sidecar (`PiiMapCorruptError`).

---

## Next steps

- See [How to verify the audit chain](verify-audit-chain.md) for full-run verification.
- See [How to walk the lineage chain](walk-lineage.md) to trace what's INSIDE the case pack.
