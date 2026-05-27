# How to walk the lineage chain for a case

> **When you need this:** An examiner asks "show me why this case fired — every source row, every transform, every rule version, every decision event." A regulator queries provenance during an exam. A 2LoD reviewer wants to confirm the alert is byte-stable replayable from the inputs.
>
> **Prereqs:** A finished run directory with the target `case_id` in scope. `engine/audit.py::walk_lineage` shipped in PR-LIN-19.
>
> **Time:** ~30 sec per case via CLI. ~1 min via the dashboard. Instant via the REST API.

The lineage chain answers "from what facts did this alert arise?" by linking the case back through six artifacts: **case → rule SQL → source data path + schema hash → matched input rows → `rule_version` → decisions sub-chain**. The chain is a **derived view** computed on demand by `walk_lineage()` — it isn't persisted as a single file at run-finalize.

What's persisted on disk: `cases/*.json`, `decisions.jsonl`, input contract metadata, `rules/*.sql`, and the eight manifest-hashed artifacts (`decisions_hash`, `dq_exceptions_hash`, `field_lineage_hash`, `sla_report_hash`, `run_cost_volume_hash`, `monitoring_digest_hash`, `defect_log_hash`, `reconciliation_report_hash`). **Tamper-detection caveats**: only the eight named artifacts (plus alert output hashes + input file hashes) are hashed into `manifest.json`. Post-finalize POSIX read-only protection is set on the artifacts listed in `AuditLedger._FROZEN_SNAPSHOT_TARGETS` — currently `rules/` but **not** `cases/`. So `cases/*.json` is neither manifest-hashed nor chmod-frozen; a privileged in-place edit of a case file would not be caught by recomputing manifest hashes alone. For full tamper-evidence of lineage, pair the manifest hashes with an external `decisions_hash` pin (see [verify-audit-chain.md](verify-audit-chain.md)) and a separate inventory hash over `cases/`.

---

## Steps

### 1 · CLI (fastest, scriptable)

```bash
aml lineage C0042-cash_structuring-001
```

By default this picks the latest run under `.artifacts/`. To target a specific run:

```bash
aml lineage C0042-cash_structuring-001 --run-dir .artifacts/run-2026-05-25T10-15-30Z
```

JSON is the default — pipe to `jq` (note the nested keys returned by `walk_lineage()`):

```bash
# How many input rows triggered this case? (matched_row_ids lives on the case's alert payload)
aml lineage C0042-... | jq '.case.alert.matched_row_ids | length'

# Which decisions belong to this case?
aml lineage C0042-... | jq '.decisions | map(.event)'

# Which input files / source paths were involved?
aml lineage C0042-... | jq '.input_files | map({contract_id, source_path, content_hash})'
```

For a human-readable layout:

```bash
aml lineage C0042-... --format table
```

### 2 · Dashboard (Lineage Explorer page)

`pages/32_Lineage_Explorer.py` — paste a `case_id`, the page renders the same chain plus a clickable graph of the link traversal. Useful when an investigator wants to **see** the structure, not parse JSON.

### 3 · REST API

```bash
curl -H "Authorization: Bearer $JWT" \
     "https://aml-api.example.com/api/v1/runs/$RUN_ID/cases/C0042-cash_structuring-001/lineage" \
  | jq .
```

Same shape as the CLI JSON output — embed in your case-management tool, ticket system, or examiner portal.

---

## What's in the chain

A `walk_lineage()` result has these top-level keys (verbatim from `engine/audit.py::walk_lineage`):

| Key | What it pins |
|---|---|
| `case_id` | The alert this chain describes |
| `run_dir` | Absolute path to the run directory the chain was walked from |
| `case` | The full `cases/<id>.json` payload. `case.alert.matched_row_ids` lists the input rows that triggered the rule. |
| `rule_id` | Which rule fired |
| `rule_version` | 16-hex SHA-256 of the rule's spec subtree at run time |
| `queue` | The escalation queue the case was routed to |
| `spec_content_hash` | The full spec content hash (proves the whole spec didn't drift) |
| `rule_sql` | Content of `rules/<rule_id>.sql`. For `aggregation_window` + `custom_sql` rules this IS the exact SQL evaluated (template substitutions resolved). For `list_match`, `python_ref`, `network_pattern`, the runner writes a callable/comment stub describing the evaluation path, not literal executed SQL — pair with the rule definition in the spec to reconstruct what ran. |
| `engine_version` | The framework version that produced the case |
| `as_of` | Run's logical `as_of` timestamp |
| `input_files` | **Run-wide** input manifest — one entry per data contract loaded for the run, not filtered to the rule that fired. Each entry: `{contract_id, source_path, schema_hash, content_hash, row_count}`. To answer "which contract did THIS rule actually read?": declarative rule types (`aggregation_window`, `list_match`, `network_pattern`) expose `rule.logic.source` — cross-reference against this list. `custom_sql` rules don't have a single `source` field; inspect the rendered `rules/<rule_id>.sql` (templated SQL with explicit `FROM` clauses). `python_ref` scorers receive a DuckDB connection (`scorer(con, as_of)`); inspect what tables they query (or hook the optional `_inspect_context(con, alerts, as_of)` callback) to find the contracts touched. |
| `decisions` | Sub-chain from `decisions.jsonl` filtered to this case (open / dispositioned / escalated / etc.) |

Together: enough to byte-stable replay the case against the original input snapshot and reproduce the same `decisions_hash` (head of the audit ledger) plus identical per-rule alert-file hashes.

---

## Verify it worked

Four checks:

1. **Every link resolves.** `decisions` non-empty (at minimum `case_opened`). `matched_row_ids` lists **DuckDB `rowid`s generated during rule execution** — they're integer positions in the loaded table, not identifiers stored in the source CSV/parquet, so don't grep the source file for them. Map back by re-loading the contract into DuckDB and selecting `WHERE rowid IN (...)`. For SQL-backed rule types (`aggregation_window`, `custom_sql`), `rule_sql` should be parseable SQL — for `list_match`, `python_ref`, `network_pattern` it's a comment/callable stub, so use "non-empty content" rather than "parses" as the check.
2. **`rule_version` is set.** Pre-PR-DATA-4 runs lack this; modern runs always have it. Empty `rule_version` is the strongest signal you're looking at an old archive.
3. **Hash chain intact.** Pass the run dir to `aml verify-decisions` (see the [verify-audit-chain how-to](verify-audit-chain.md)) — failure here means the case's decisions sub-chain is poisoned and the lineage is suspect.
4. **Replay reproduces.** Without all the right inputs, the new `decisions_hash` won't match — current `aml.yaml` may have drifted, the default data source is `synthetic`, and an omitted `--as-of` stamps wallclock. To deterministic-replay you need to pin **four** things to the archived run:

   ```bash
   # 1) the spec snapshot from the audit pack (NOT current main's aml.yaml)
   # 2) the original as_of from manifest.json
   # 3) the original seed
   # 4) the original data source + path (whatever was used at run time —
   #    --data-source / --data-dir / external warehouse credentials, etc.)
   ORIGINAL_AS_OF=$(jq -r .as_of .artifacts/run-OLD/manifest.json)
   aml run path/to/archived/spec_snapshot.yaml \
     --seed 42 \
     --as-of "$ORIGINAL_AS_OF" \
     --data-source <original> --data-dir <original>
   ```

   The new `decisions_hash` should byte-match the archived one. This is the strongest possible verification — and the strictest, because any drift in any of the four anchors invalidates it.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `rule_version` is empty | Run predates PR-DATA-4 (Round 26+) | Expected for old archives. New runs are stamped; you can't retroactively populate. |
| `matched_row_ids` is empty | Custom SQL rule that didn't surface row ids, or rule predates PR-LIN-12 | Update the rule to emit a `matched_row_ids` field in its custom SQL, or use one of the declarative logic types. |
| CLI says "case_id not found in latest run" | The case lives in an older run | Pass `--run-dir` explicitly. |
| Different `rule_version` than expected | Spec edited between runs | This is correct behavior — the version IS the spec content. Use the spec snapshot in the corresponding audit pack to recover. |
| JSON is enormous | Wide rule with thousands of matched rows | Use `--format table` for a summary, or `jq` to slice |

---

## Next steps

- [How to verify the audit chain](verify-audit-chain.md) — prove the lineage data hasn't been tampered with after the run finalized.
- [How to export a case pack](export-case-pack.md) — hand the lineage chain to a regulator as a self-contained ZIP.
- Lineage Explorer dashboard page — visual graph view of the same chain.
