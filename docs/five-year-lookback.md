# Running a 5-Year Transaction-Monitoring Lookback with the AML Open Framework

How to use this framework to actually execute the regulatory 5-year
TM lookback playbook described in
[`aml_learning_for_fintech/docs/02-5year-lookback-azure-modernization.md`](https://github.com/tomqwu/aml_learning_for_fintech/blob/main/docs/02-5year-lookback-azure-modernization.md).

This doc mirrors that reference's structure. Each section maps the
lookback requirement to a specific framework feature, file, or command
— operator-grade, not positioning.

The framework is not a replacement for your data platform (ADLS,
Delta, Databricks, Fabric). It is the **rule-execution + evidence
layer** that sits on top: it consumes your curated tables, produces
deterministic alerts/cases/decisions, and emits the regulator-facing
evidence chain. Everything Azure-side stays Azure-side.

> **⚠ Verify before quoting in evidence packs.** This doc has been
> through 7 rounds of automated source-of-truth review against the
> code on `main`, and is reasonably accurate as of the merge date —
> but new framework features land continuously and review can still
> miss subtle CLI flag / manifest field / event-name drift. Before
> citing a specific command, flag, manifest field, or event in a
> regulator-facing artefact, **re-verify against the actual source**
> (CLI: `aml <cmd> --help`; manifest shape: `engine/audit.py`;
> events: `engine/constants.py`). The architectural posture (PIT
> discipline + hash-chained ledger + sidecar wall-clock separation)
> is stable; the exact field names and flags are the moving parts.
>
> **Implemented today vs. TM-roadmap planned.** Items marked **🛠
> planned · TM Gap N** are not on `main` yet — the TM roadmap that
> sequences them is the plan file `Roadmap: Transaction-Monitoring
> feature gaps`, not `progress.md` (which is a chronological progress
> log, not a roadmap). The "lookback in N commands" runbook at §10
> uses only commands that exist today — including `aml equivalence`,
> which shipped the legacy↔new parallel-run path (formerly TM Gap 1).

!!! tip "Try it now — copy-paste runbook"

    This doc is the architectural overview. If you'd rather skip the
    framing and run a 60-month lookback against a synthetic dataset on
    your laptop in under an hour, jump straight to
    **[How to run a 5-year transaction-monitoring lookback](how-to/run-five-year-lookback.md)** —
    every command is pinned to the `community_bank_lookback` example
    spec and verified against the implementation.

---

## 1. The 8 properties of a lookback — where the framework delivers each

The reference doc names eight properties: a lookback must be
*complete, point-in-time correct, repeatable, performant, auditable,
explainable, reconciled, signed off.* Mapping each to a concrete
mechanism the framework already ships:

| Property | How the framework enforces it |
|---|---|
| **Complete** | `aml validate` checks spec structure + cross-references. `aml validate-data` + the engine's `_build_warehouse` fail-closed *only on missing non-nullable contract columns* — they raise `ContractViolation` before any rule fires. **Missing nullable columns are silently `None`-filled** (a rule filtering on that column will produce zero matches, not a build failure), so author your contracts with `nullable: false` for every field a rule depends on. Run-time `engine/freshness.py` adds DQ floors on staleness. |
| **Point-in-time correct** | Engine threads `as_of` through every rule. `custom_sql` rules get `{as_of}`, `{window_start}`, `{recent_start}`, `{baseline_start}`, `{dormant_cutoff}` substituted at compile time so the SQL operates on the business date. PIT-correctness of *reference data* (e.g. risk rating valid on the transaction date) is *the author's job*: declare an effective-dated contract and encode the `effective_start_date`/`effective_end_date` join in your `custom_sql`. The framework provides the `as_of` placeholder; it does not auto-apply effective-date filters. |
| **Repeatable** | The deterministic-replay contract: same spec + same data + same `as_of` + same seed ⇒ byte-identical alert/case/decision hashes. Pinned by `tests/test_engine.py::test_run_is_reproducible`. |
| **Performant** | DuckDB in-memory for the engine; cloud sources (Snowflake/BigQuery/S3/GCS/Parquet) loaded by `data/sources.py`. The loaders pull whole files/tables — there is no source-side predicate pushdown of `{as_of}`/`{window_start}` to the warehouse. Performance for 5-year scale comes from *you* materializing one-month slices upstream (per §4 Pattern 1) and feeding each slice as the run's input. |
| **Auditable** | `engine/audit.py` writes a SHA-256-hash-chained `decisions.jsonl`. `AuditLedger.verify_decisions()` is regulator-grade *only when called with `--expected-hash`* — the chain head must be stored out-of-band (WORM bucket, signed log) at run time and passed back at verify time (see §10 step 7). Without it, the verifier falls back to comparing against the same directory's `manifest.json`, which an attacker who rewrote `decisions.jsonl` can usually rewrite too. The chain itself is real; the trust anchor is your responsibility. |
| **Explainable** | `aggregation_window` rules auto-stamp `matched_row_ids` referencing the exact source rows (#341 fix replays the rule filter so audit evidence matches the alert's own SQL). `custom_sql` only carries row IDs if the SQL `SELECT`s them explicitly; `python_ref` only if the scorer implements the optional inspection hook. `walk_lineage` reconstructs alert → rule → data when row IDs are present. |
| **Reconciled** | `aml equivalence` (`engine/equivalence.py`) joins legacy ↔ new outputs and classifies each `(customer, period, rule)` cell as MATCH / NEW_ONLY / LEGACY_ONLY / DIFF; you triage each divergence as a `data` / `rule` / `mapping` defect vs. an intentional change. See Pattern 5 below. |
| **Signed off** | Cases carry a disposition + reviewer; `cases/filing.py` enforces a wall-clock sidecar that's *out* of the deterministic-replay contract so signoff timing is preserved without breaking reproducibility. |

---

## 2. The framework sits on top of your Azure stack, not against it

Your Azure modernization target architecture stays exactly as the
reference doc draws it. The framework slots into the **Rule Execution
+ Alert/Evidence + Analytics layers**:

```text
Legacy / Source Systems              (unchanged — SAS, Oracle, IMS, files)
        ↓
Azure Data Factory / Fabric          (unchanged — orchestration)
        ↓
ADLS Bronze / Silver                 (unchanged — raw / cleaned)
        ↓
ADLS Gold (rule-ready Delta tables)  ←─── framework reads here via
        ↓                                  `aml run --data-source <X> --data-dir <Y>`:
        ↓                                    --data-source parquet   (Delta is Parquet-compatible —
        ↓                                                             point at a Parquet view of Delta)
        ↓                                    --data-source duckdb
        ↓                                    --data-source csv        (POC / dev)
        ↓                                    --data-source synthetic  (default — generated fixtures)
        ↓
        ↓                                  Cloud connectors (Snowflake / BigQuery /
        ↓                                  S3 / GCS) live in `data/sources.py` but
        ↓                                  are PROGRAMMATIC today, not exposed as
        ↓                                  `aml run --data-source` flags. The
        ↓                                  production shape is: ADF / Lakeflow
        ↓                                  materializes the per-month Gold slice to
        ↓                                  Parquet on a mounted volume, then
        ↓                                  `aml run --data-source parquet --data-dir
        ↓                                  /mnt/gold/2021-09/`.
        ↓
┌──────── FRAMEWORK ────────────────────────────────────────────────┐
│                                                                   │
│  Rule Execution Layer                                             │
│    spec/loader.py    JSON Schema + Pydantic cross-validation      │
│    engine/runner.py  evaluate aggregation_window / custom_sql /   │
│                       list_match / python_ref against DuckDB      │
│                                                                   │
│  Alert / Evidence Layer                                           │
│    alerts/*.jsonl                                                 │
│    cases/aggregator.py  → cases/*.json                            │
│    metrics/engine.py    → run_dir/metrics/metrics.json            │
│    engine/audit.py      → run_dir/decisions.jsonl (hash-chained)  │
│    export.py            → regulator-ready ZIP bundle              │
│                                                                   │
│  Analytics / Review Layer                                         │
│    dashboard/ (44 Streamlit pages, persona-routed by audience.py) │
│    api/main.py + /api/v1/health for ops                           │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
        ↓
Microsoft Purview                    ←─── framework can publish lineage
                                          via tests/test_integrations_purview.py
                                          surfaces (alert → rule →
                                          matched_row_ids → source).
        ↓
Synapse / Fabric / Power BI          ←─── consume alerts/*.jsonl,
                                          cases/*.json, metrics.json
                                          directly (JSON-Lines is
                                          first-class in all three).
```

The deliberate boundary: **your data platform owns the medallion
layers; the framework owns the spec, the engine, the audit chain, and
the evidence.** Lakeflow / ADF / Databricks orchestrate; the framework
runs the rules and produces the regulator-facing artefacts.

---

## 3. Component-by-component map

For each Azure component the reference doc names, where the framework
contributes:

| Azure component | What the framework adds |
|---|---|
| **ADLS Gen2 / OneLake** | The production shape: ADF / Lakeflow materializes per-month Gold Parquet to a mount; `aml run --data-source parquet --data-dir /mnt/gold/<month>/` reads it. The `data/sources.py` module also has S3 / GCS / Snowflake / BigQuery resolvers (programmatic), but `aml run`'s `--data-source` only exposes synthetic / csv / parquet / duckdb today; broader exposure is a follow-up. |
| **Azure Data Factory / Fabric Data Factory** | The framework's CLI (`aml run`, `aml validate`, `aml export`) is wrap-friendly. A typical ADF pipeline: *Extract → land Parquet → DQ in Lakeflow/dbt/Spark → `aml run` activity → publish run_dir back to Gold → publish ZIP to evidence container*. Note: `aml validate-data` is CSV-only (it reads `<contract_id>.csv` and runs `validate_csv`) — for Parquet-native flows, run your `not_null`/`unique`/RI/PIT checks upstream and pass clean data to `aml run`. Native parquet `validate-data` is a planned loader extension. |
| **Databricks / Spark / Lakeflow** | Your Lakeflow pipelines produce the rule-ready Gold tables; the framework reads them. For Spark-native rule execution you don't need this framework, but you give up the spec contract + the deterministic audit chain. The framework's value-add is the **defensible spec + evidence**, not raw compute. |
| **Delta Lake** | The framework's `--data-source parquet` loader (`data/sources.py:load_parquet_source`) reads a single file per contract — `<data-dir>/<contract_id>.parquet`. It does **not** read Delta directories, Delta versions, or partitioned Parquet directories directly. Pin Delta's version on your side, then `SELECT * FROM delta.\`...\`` and export to flat per-contract `.parquet` files for the framework to consume. Native Delta support is a planned loader extension. |
| **Microsoft Fabric Lakehouse / Warehouse** | Same as Databricks — Fabric produces the curated layer, framework consumes. The Streamlit dashboard can be embedded in Fabric or run standalone (current Azure deploy is Container Apps). |
| **Microsoft Purview** | `walk_lineage` is the framework-side equivalent: alert → rule → matched_row_ids → source row. Already exercised by `tests/test_integrations_purview.py`; the lineage events can publish to Purview's REST API for full enterprise-catalog integration. |
| **Synapse Analytics** | The framework's outputs are JSON-Lines + Parquet-friendly + markdown reports. Synapse SQL can query the alert/case JSONLs via OPENROWSET; Power BI can consume metrics.json. |

---

## 4. The 5 historical-replay patterns — how the framework implements each

This is the heart of the doc. Each of your reference doc's five
patterns has a specific framework expression.

### Pattern 1 — Partition by business time

The framework's run model is **one `run_dir` under `--artifacts` per
(`spec`, `as_of`, `seed`)**.

```bash
# Rerun September 2021 only. ADF / Lakeflow materializes the per-month
# Gold slice to a Parquet mount; `aml run` reads it deterministically.
aml run examples/your_program/aml.yaml \
    --as-of 2021-09-30T23:59:59 \
    --data-source parquet \
    --data-dir /mnt/gold/2021-09/ \
    --seed 42 \
    --artifacts /evidence/runs/2021-09/
```

Backfill is just a loop over months (ISO timestamps; no `--output-dir`
flag — use `--artifacts` to scope the run dir):

```bash
months=(
  "2021-01-31T23:59:59" "2021-02-28T23:59:59" "2021-03-31T23:59:59"
  # ... 60 month-end timestamps ...
  "2025-12-31T23:59:59"
)
for ts in "${months[@]}"; do
    ym=${ts:0:7}                                    # e.g. 2021-09
    aml run examples/your_program/aml.yaml \
        --as-of "$ts" \
        --data-source parquet \
        --data-dir   "/mnt/gold/${ym}/" \
        --seed 42 \
        --artifacts  "/evidence/runs/${ym}/"
done
```

Each `/evidence/runs/YYYY-MM/run-<timestamp>/` is self-contained:
manifest, alerts, cases, decisions, hash chain. (The `run-<timestamp>/`
subdirectory naming is the engine's, not yours — `--artifacts <dir>`
creates `<dir>/run-<ISO-timestamp>/`.) A defect fix means re-running
only the affected months.

### Pattern 2 — Idempotent writes via deterministic keys

The reference doc's "even better design" is exactly the framework's
default. `engine/audit.py` uses `_canonical_json()` + `_sha256()` to
build deterministic decision hashes. The hash chain is the
deterministic key.

A rerun on identical inputs produces byte-identical output. Detect it:

```bash
sha256sum /runs/2021-09/decisions.jsonl
# Compare to the previously-archived hash. Match ⇒ no replay needed.
```

For *alert-level* dedupe across runs, the engine does not emit a
pre-computed `alert_key` field today. The deterministic primitives
you stitch are:

- `manifest.json:spec_content_hash` (rule version proxy — any rule
  edit changes it)
- `manifest.json:decisions_hash` (whole-run hash)
- The alert's own keys it already carries (`customer_id`,
  `window_start`/`window_end` for `aggregation_window`, or the column
  set your `custom_sql` returned)

Compute the dedupe key downstream in your warehouse / Spark step
(`hash(rule_id, rule_version, customer_id, window_start, window_end)`)
— the framework gives you the inputs; an alert-level deterministic key
column inside `alerts/*.jsonl` is a planned addition.

### Pattern 3 — Batch ID everywhere

Every run produces one `<artifacts>/run-<timestamp>/manifest.json`
(`run-<timestamp>` is the natural batch ID — directory name is the
ISO timestamp the run was created at). Real shape on `main`:

```json
// run_dir/manifest.json (real shape — copy from engine/audit.py:finalize +
// engine/runner.py post-finalize patches)
{
  "engine_version":     "0.1.x",
  "run_dir":            "/evidence/runs/2021-09/run-2026-05-20T01-16-00Z/",
  "spec_path":          "examples/your_program/aml.yaml",
  "spec_content_hash":  "b09f...",     // raw SHA-256 hex of the YAML bytes,
                                       //   no "sha256:" prefix
  "as_of":              "2021-09-30T23:59:59+00:00",
  "inputs": {                          // keyed by contract id (NOT an array)
    "txn":      { "row_count": 4923711, "content_hash": "...",
                  "earliest_ts": "...", "latest_ts": "...",
                  "source_path": "...", "schema_columns": [...],
                  "schema_hash": "..." },
    "customer": { "row_count":   91842, "content_hash": "...", ... }
  },
  "rule_outputs": {                    // rule_id -> SHA-256 hex of the
                                       //   alerts/<rule_id>.jsonl file
    "structuring_cash_deposits": "a1b2c3...",
    "wire_high_risk_country":    "d4e5f6..."
  },
  "decisions_hash":     "...",         // chain head (hex)
  "finalised_at":       "2026-05-20T01:17:23+00:00",
  "metrics":            [ ... ],       // appended by runner after finalize()
  "reports":            [ "svp_exec_brief", "data_quality" ]
}
```

Alert counts per rule are **not** in the manifest — recover them by
counting lines in `alerts/<rule_id>.jsonl`. The manifest gives you
the file hash so you can prove the count came from the sealed file.

The directory name (`run-<timestamp>`) is the batch ID you reference
when verifying or exporting. `aml verify-decisions --run-dir <path>`
and `aml audit-pack --run-dir <path>` both take the `run-<ts>/`
directory (or omit it to pick the latest under `--artifacts`).

### Pattern 4 — Point-in-time reference data

PIT is **author-encoded, not auto-applied**. The framework gives you
the building blocks; you wire the effective-date join yourself:

- **`as_of` placeholder** in `custom_sql` rules — the engine
  substitutes the business date at compile time, so the SQL operates
  on the business date naturally.
- **Effective-dated reference contracts** — declare an
  `customer_risk_ratings_pit` (or similar) `data_contract` whose
  columns include `effective_start_date` and `effective_end_date`. The
  loader treats these as ordinary declared columns — *no special PIT
  machinery*. Your `custom_sql` rule joins on `t.booked_at BETWEEN
  r.effective_start_date AND COALESCE(r.effective_end_date,
  TIMESTAMP '9999-12-31')` and you have PIT correctness.
- **The bigger discipline**: the *spec* is point-in-time too. Tag
  your `aml.yaml` per period (`my_program/aml.yaml@2021-09-30`) so
  you can rerun the *rules as they were on 2021-09-30* against the
  *data as it was on 2021-09-30*. `manifest.spec_content_hash` is
  the raw SHA-256 of the YAML bytes — it pins the *exact content* of
  the spec used (a single character change breaks the hash), but it
  is **not** the git commit SHA. To prove which git revision produced
  that content, also record the commit SHA out-of-band at run time
  (e.g. `jq` the manifest with `git rev-parse HEAD` into your evidence
  log), or add a wrapper that writes `git_commit_sha` next to the
  manifest as a sidecar.

Non-`custom_sql` rules (`aggregation_window`, `list_match`,
`python_ref`) don't have a PIT-join knob today — they read whatever
the data load produces. If a rule needs PIT-correct reference data,
use `custom_sql` or pre-join the effective-dated view into your Gold
table before the engine runs.

```yaml
# Example: rule that uses risk_rating *as of the transaction date*,
# not today's risk_rating.
#
# Two things to know about custom_sql placeholders:
#   1. `compile_rule_sql` (`generators/sql.py`) only substitutes time
#      keys: {as_of}, {window_start}, {recent_start}, {baseline_start},
#      {dormant_cutoff}. Use real contract table names (txn,
#      customer_risk_ratings_pit, etc.) — there is NO {transactions}
#      placeholder.
#   2. The substituted timestamps need explicit `TIMESTAMP '...'`
#      quoting for DuckDB / standard SQL.
rules:
  - id: high_risk_jurisdiction_with_pit_rating
    logic:
      type: custom_sql
      sql: |
        SELECT t.customer_id, SUM(t.amount) AS sum_amount
        FROM txn t
        JOIN customer_risk_ratings_pit r
          ON r.customer_id = t.customer_id
         AND t.booked_at BETWEEN r.effective_start_date
                             AND COALESCE(r.effective_end_date, TIMESTAMP '9999-12-31')
        WHERE t.booked_at BETWEEN TIMESTAMP '{window_start}' AND TIMESTAMP '{as_of}'
          AND r.risk_rating = 'high'
        GROUP BY t.customer_id
        HAVING SUM(t.amount) >= 100000
```

The point-in-time `customer_risk_ratings_pit` table is just another
declared `data_contract` in `aml.yaml` with `effective_start_date` /
`effective_end_date` columns; load it the same way as `txn`.

### Pattern 5 — Parallel validation (legacy ↔ new) · **shipped**

`aml equivalence` (PR-LOOKBACK-3, wrapping `engine/equivalence.py`) joins your
legacy alert export against the framework's per-month `alerts/*.jsonl` and
classifies every `(customer, period, rule)` cell into four buckets:

```text
MATCH        both systems alerted the same cell  → control reproduced
NEW_ONLY     new engine alerted, legacy didn't   → intentional gain OR over-firing defect
LEGACY_ONLY  legacy alerted, new engine didn't   → coverage gap to investigate
DIFF         same cell, different severity        → mapping / threshold drift
```

You then triage each non-MATCH cell into a **data**, **rule**, **mapping**,
**reference-data**, or **timing/window** defect — vs. an intentional change.

```bash
aml equivalence evidence/runs/2021-09/run-*/ \
    --legacy legacy/tm/2021-09/alerts.csv \
    --markdown equivalence-2021-09.md --out equivalence-2021-09.json
```

The legacy CSV needs `customer_id, period_start, period_end, rule_id_legacy`
(optional `severity`). Pass `--rule-map` (the **complete** new→legacy map)
when ids differ, and `--max-severity-diff N` to fail a CI gate on drift. The
matching CLI walkthroughs: [getting-started §8](getting-started.md#8-the-flagship-scenario-5-year-legacy-to-cloud-lookback-10-min)
and [runbook step 8](how-to/run-five-year-lookback.md#8-prove-legacy-new-equivalence).

The spec also carries a first-class **`program.legacy_reference`** block
(`spec/models.py:LegacyReference`, validated against the rule corpus). `aml
equivalence` reads its `rule_map` + `key_columns` automatically, so you don't
repeat those as flags — but you still pass the legacy export itself via the
required `--legacy <csv>` (the CLI does not load `legacy_reference.path`).

**Or roll your own** — the alerts are deterministic JSONL, so a pandas
outer-join works too if you want the divergence inside an existing notebook:

```python
import pandas as pd
new = pd.read_json(
    "evidence/runs/2021-09/run-2026-05-20T01-16-00Z/"
    "alerts/structuring_cash_deposits.jsonl",
    lines=True,
)
old = pd.read_csv("legacy/tm/2021-09/alerts.csv")
diff = new.merge(old, on=["customer_id", "window_start"], how="outer", indicator=True)
# diff["_merge"] ∈ {"left_only", "right_only", "both"} — `aml equivalence`
# does this join + the four-way classification for you.
```

---

## 5. Data stitching — what the framework catches before rules run

The reference doc's stitching-failure table maps to framework controls
*at different layers*. Be precise about which command catches what
today (Codex caught false-assurance phrasing in an earlier draft):

| Failure mode | Where today |
|---|---|
| Type / null / encoding errors per row | `aml validate-data` (CSV only — see §6+§10 note) runs `validate_csv` per contract column: type coercion + non-null check + row-num-anchored error messages. |
| Missing customer/account link (referential integrity) | **Not enforced anywhere in the framework today.** The `data_contract.quality_checks` block accepts arbitrary keys, but only `not_null` and `unique` are actually evaluated (by `pages/14_Data_Quality.py`, not by `validate-data`). FK-style integrity is *your platform's job* — gate it in Lakeflow expectations / dbt tests / Spark before the engine runs. |
| Duplicate transaction | Declare `quality_checks: [{unique: [transaction_id]}]` in your contract; the DQ dashboard page **does** evaluate `unique` and shows pass/fail. But `aml validate-data` does NOT — same Lakeflow/dbt enforcement note as above. |
| Late-arriving record | `aggregation_window` rules automatically constrain `booked_at >= window_start AND booked_at < as_of` (compiled by `generators/sql.py`). `custom_sql` rules do NOT — the author must include the `t.booked_at <= TIMESTAMP '{as_of}'` predicate themselves. `engine/freshness.py` surfaces "rows arriving late" on `pages/14_Data_Quality.py`. |
| Current reference data used for old transaction | Author-encoded effective-date join in your `custom_sql` rule (Pattern 4). No auto-PIT machinery. |
| Wrong currency conversion date | Same pattern — declare an FX rate contract with `effective_start_date`/`effective_end_date` and join on `t.booked_at` in `custom_sql`. |
| Many-to-many ownership ignored | Explicit join shape in `custom_sql`. The framework deliberately doesn't auto-resolve M:M — silent M:M is the bug, not the feature. |

**Why the framework draws this line.** Pre-engine DQ enforcement
belongs in your data platform (Lakeflow / dbt / Spark expectations)
where it has full table-level capacity. The framework's `data_contract`
+ dashboard layer give you the *spec for what should be true* + the
*visibility when it isn't* — the gate-vs-visibility split is the same
discipline as separating policy from enforcement.

---

## 6. Performance — multi-year scale

The framework's compute model is **DuckDB in-memory per run, scoped by
`as_of` + `data-dir`**. For a single month of a mid-sized bank
(~50M txns), an in-memory run is fast. For a 5-year backfill:

1. **Run per-month in parallel.** Each `run_dir` is independent; the
   audit chain is per-run. A 60-month backfill is 60 independent
   jobs — wrap with Lakeflow / ADF parallel branches.
2. **Pre-filter at the source — outside the framework.** The
   framework's loaders today read the contract file/table whole (CSV /
   Parquet load, `SELECT *`-equivalent for DuckDB); `{as_of}` /
   `{window_start}` are substituted in the rule SQL *after* the load,
   in-process in DuckDB, so they do NOT push down to Snowflake /
   BigQuery / Spark via the framework. Your Lakeflow / ADF / Spark
   pipeline must materialize *only the month's rule-ready slice* to
   the Parquet mount the engine reads. Sizing a 5-year backfill on
   the assumption of source-side pushdown by the framework will
   process far more data than necessary.
3. **Cache the spec compilation.** `setuptools-scm` + git SHA mean
   "same spec" is hash-comparable across months; if you didn't change
   the rules, you don't recompile them.
4. **Defect remediation = single-partition rerun.** Fix the rule,
   bump the spec git tag, rerun the affected month, write the new
   `run_dir/${month}/`, leave the other 59 untouched. The hash chain
   makes this safe.

The Spark/SQL bottlenecks the reference doc lists (huge joins,
missing partition filters, skew) all live in *your* curated layer —
not in the framework. The framework's job is to keep the rule
execution + audit deterministic; the data platform does the heavy
lifting.

---

## 7. Evidence produced per run — side-by-side

Mapping the reference doc's "mature lookback pipeline should produce"
checklist to where the framework already emits each artefact:

| Reference-doc artefact | Where the framework emits it |
|---|---|
| `run_manifest` (batch_id, source periods/tables, rule versions, parameter versions, code commit hash, status) | `run_dir/manifest.json` — has `engine_version`, `run_dir` (= batch id), `spec_path`, `spec_content_hash` (YAML bytes, not git SHA — see §5), `as_of`, `inputs` (per-contract source_path + row_count + content_hash + earliest_ts/latest_ts + schema_columns + schema_hash), `rule_outputs` (per-rule alert-file hash), `decisions_hash`, `finalised_at`. **Not in the manifest today**: git commit SHA (write `git rev-parse HEAD` to a sidecar), parameter-version field (versioning lives in your git history of the spec), pipeline status flag (your orchestrator owns success/fail status). |
| `reconciliation_report` (source row count, target row count, totals, exceptions, alert count) | `run_dir/reports/*.md` per spec-declared `report:` carry alert/case totals + counts. The legacy-vs-new divergence report ships via `aml equivalence` (`--markdown` / `--out` — see Pattern 5). |
| `rule_output_report` (alert count by month / customer segment / geography / reason code) | `run_dir/alerts/*.jsonl` (raw) + the **Rule Performance** + **Comparative Analytics** dashboard pages (`pages/5_Rule_Performance.py`, `pages/19_Comparative_Analytics.py`) |
| `dq_report` (completeness, duplicates, validity, referential integrity, PIT coverage) | **Partial.** The framework emits `not_null` + `unique` results via the **Data Quality** dashboard (`pages/14_Data_Quality.py`) and staleness via `engine/freshness.py`. **Referential integrity, PIT-coverage, FX-rate-date, and many-to-many ownership are NOT evaluated by the framework today** (see §5 stitching table) — produce that part of `dq_report` in your upstream Lakeflow/dbt/Spark step and stitch it into evidence alongside `run_dir/`. |
| `defect_log` (defect_id, severity, root cause, owner, fix version, retest evidence) | **🛠 External / planned.** The framework emits `rule_failed` events (engine/constants.py:Event.RULE_FAILED) for `python_ref` failures with an `error` string — that's the *signal*, not a structured defect_log. The dashboard's `_FAILED` future is specific to AI section-explanation, not rule-execution. A proper defect_log (defect_id, severity, root cause, owner, fix version, retest evidence) is your remediation-system's job today (Jira/ServiceNow). Land it next to `run_dir/` as a wall-clock sidecar per `cases/filing.py`'s `append_to_run_dir` pattern. |

The reference doc says: *"can you prove what data was run, which
rules ran, why outputs were created, what exceptions occurred, and
how defects were resolved?"* — every "prove" answer above is a
specific framework file in `run_dir/`.

---

## 8. Role focus — which framework surfaces each lookback role lives in

| Role | Primary framework surfaces |
|---|---|
| **Data engineer** | `data/sources.py` (cloud connectors) + `data/synthetic.py` (test fixtures) + `data_contract` YAML. Ownership: the Gold-layer Delta tables are framework-readable. |
| **Data analyst** | `pages/3_Alert_Queue.py`, `pages/4_Case_Investigation.py`, `pages/17_Customer_360.py`, `pages/10_Network_Explorer.py`. Daily case work. |
| **QA / DQ engineer** | `aml validate-data`, `engine/freshness.py`, `pages/14_Data_Quality.py`, the `quality_checks` block in each `data_contract`. Defect log → audit ledger via `_log_failure_to_audit`. |
| **Data scientist** | `python_ref` rule type, `models/scoring.py`, `pages/13_Model_Performance.py`, `engine/tuning.py` for threshold sweeps, `engine/backtest.py` for replay. |
| **Lead / architect** | `spec/models.py` + `schema/aml-spec.schema.json` (the contract), `engine/audit.py` (the chain), `docs/progress.md` (the roadmap), the regulator-pulse Knowledge page (`pages/27_Regulator_Pulse.py`). Sign-off: every PR carries Codex review + green CI + spec validation. |

---

## 9. Active-recall answers in framework terms

The reference doc's 8 questions, answered through this framework's
specific mechanisms:

1. **What makes a 5-year lookback different from normal monthly monitoring?** Point-in-time correctness across changing data, schemas, rules, reference values, ownership — and *proof* for every period. The framework enforces this via the `as_of` discipline + git-tagged specs + the hash-chained audit ledger.
2. **Why does partitioning matter?** Each `run_dir` is one partition; defect remediation rewrites one partition without touching the rest. The audit chain segments cleanly per-month.
3. **What does idempotence mean here?** Same spec + same data + same `as_of` + same seed ⇒ byte-identical `decisions.jsonl`. `test_run_is_reproducible` pins this.
4. **Why is batch ID important?** `run_dir/manifest.json` is the batch ID + every artefact it produced. Every alert/case/decision references it.
5. **What fields are needed for point-in-time reference data?** `effective_start_date`, `effective_end_date`, declared in `data_contracts[].columns` + joined with the `as_of` placeholder.
6. **Common stitching failures?** Only the two `quality_checks` your dashboard DQ page evaluates today (`not_null`, `unique`) are caught by the framework itself. Referential integrity, point-in-time reference joins, FX-rate date joins, and many-to-many ownership are **not** enforced by `aml validate-data` or the engine — they are platform/spec-author responsibility (table in §5 has the full picture). For a compliance lookback, treat the framework as the rule engine + audit chain, not as your data-quality gate.
7. **What evidence should a lookback run automatically generate?** Everything in §7 — already in `run_dir/`.
8. **How would you explain ADLS / Databricks / Delta / Fabric / Synapse / Purview?** The framework is *layered on top of* this stack, not a replacement (§2–§3).

---

## 10. A 5-year lookback in commands you can actually run today

Every command below is a real `aml` subcommand on `main`. The one
step that's roadmap-gated (parallel-run vs legacy) is called out.

```bash
# 1. Clone and install.
git clone https://github.com/tomqwu/aml_open_framework
cd aml_open_framework
pip install -e ".[dev,dashboard,api]"

# 2. Author your spec (one-time; iteratively refined). Two paths:
#    a) Scaffold via the wizard:
aml init ./my_program            # 5 questions → starter aml.yaml
#    b) Or copy an example close to your program and tailor it:
cp -r examples/community_bank examples/my_program
$EDITOR examples/my_program/aml.yaml

# 3. Validate the spec.
aml validate examples/my_program/aml.yaml

# 4. Map your warehouse to the spec's contracts. NOTE: `aml byod`
#    profiles CSV today — point it at a representative CSV sample
#    (one month of Gold exported to CSV is enough) during onboarding.
#    In production you don't run byod against the live Parquet feed
#    — the mapping it produces is a one-time artefact.
aml byod examples/my_program/aml.yaml /tmp/gold_sample_csv/
$EDITOR data_mapping.yaml

# 5. Validate one month of historical data against the spec's
#    contracts. NOTE: `aml validate-data` is CSV-only today (it
#    looks for `<contract.id>.csv` under DATA_DIR). For the Parquet
#    production path, fail data quality in your Lakeflow / dbt /
#    Spark pipeline before the engine runs (see §5). Use this CLI
#    during dev against a CSV sample:
aml validate-data examples/my_program/aml.yaml /tmp/gold_sample_csv/

# 6. Backfill — one independent run per business month. In
#    production, ADF / Lakeflow materializes the per-month Gold slice
#    to a Parquet mount and wraps this loop in parallel branches.
#    --artifacts <dir> creates <dir>/run-<timestamp>/ — that is the
#    run_dir name everything else references.
months=(
  "2021-01-31T23:59:59" "2021-02-28T23:59:59" "2021-03-31T23:59:59"
  # ... 60 month-end timestamps ...
  "2025-12-31T23:59:59"
)
for ts in "${months[@]}"; do
    ym=${ts:0:7}
    aml run examples/my_program/aml.yaml \
        --as-of      "$ts" \
        --data-source parquet \
        --data-dir   "/mnt/gold/${ym}/" \
        --seed       42 \
        --artifacts  "/evidence/runs/${ym}/"
done

# 7. Verify the hash chain per month. ALWAYS pass --expected-hash from
#    an out-of-band store (WORM bucket, signed log, regulator-witnessed
#    DB). Without it, verify-decisions falls back to comparing against
#    the SAME directory's manifest.json — an attacker who rewrites
#    decisions.jsonl can usually rewrite manifest.json too, so that
#    path only catches *partial* tampering. Store each month's
#    decisions_hash externally at run time:
#       sha=$(jq -r .decisions_hash $run_dir/manifest.json)
#       echo "$ym $sha" >> /worm/decisions-hashes.log    # WORM bucket
for ym_dir in /evidence/runs/*/; do
    ym=$(basename "$ym_dir")
    expected=$(grep "^$ym " /worm/decisions-hashes.log | awk '{print $2}')
    aml verify-decisions --artifacts "$ym_dir" --expected-hash "$expected"
done

# 8. Build the regulator-ready bundles. Both `audit-pack` and `export`
#    default their --run-dir to "latest under --artifacts" the same
#    way — one invocation per month picks up that month's run-*/.
for ym_dir in /evidence/runs/*/; do
    ym=$(basename "$ym_dir")
    aml audit-pack examples/my_program/aml.yaml \
        --artifacts "$ym_dir" \
        --out       "${ym_dir}audit-pack.zip"
    aml export examples/my_program/aml.yaml \
        --artifacts "$ym_dir" \
        --out       "${ym_dir}evidence.zip"
done

# 9. Reconcile against the legacy system per month:
#      aml equivalence "$ym_dir"run-*/ --legacy legacy/$ym/alerts.csv \
#          --markdown "${ym_dir}equivalence.md" --out "${ym_dir}equivalence.json"
#    Classifies each cell MATCH / NEW_ONLY / LEGACY_ONLY / DIFF. See
#    Pattern 5 above.

# 10. Build per-rule MRM dossiers when ML scorers are in play.
#     Same `--artifacts` defaulting as audit-pack:
aml mrm-bundle examples/my_program/aml.yaml \
    --artifacts /evidence/runs/2025-12/
```

Each per-month bundle contains the spec it ran against, the run
manifest, all alerts/cases JSONLs, the hash-chained `decisions.jsonl`,
the metric report markdowns, and (when applicable) the sanctions
evidence + jurisdiction-specific section maps. Concatenated, those
60 bundles are the 5-year evidence package you hand to the examiner.

---

## What's still required from you (the framework doesn't do)

Honest boundaries:

- **You own the medallion data platform.** ADLS / Delta / Lakeflow /
  ADF / Databricks pipelines that produce the Gold rule-ready tables
  are yours. The framework reads from them; it doesn't replace them.
- **You own the legacy parallel-run extract; the framework classifies
  the divergence.** The framework can't generate the legacy side — that
  export is yours. Once you have it, `aml equivalence`
  (`engine/equivalence.py` + the `Program.legacy_reference` spec block,
  both on `main`) does the join and the four-way MATCH / NEW_ONLY /
  LEGACY_ONLY / DIFF classification for you; see §4 Pattern 5.
- **You own the historical schema-evolution story.** If your
  `transactions` schema changed in 2023, you need versioned
  `data_contracts[]` (the framework supports it; you have to author
  it).
- **You own MRM signoff for ML scorers** (`python_ref` rules).
  `generators/mrm.py` emits the pack; the committee approves it.

What the framework gives you is the **deterministic rule-execution +
audit-chain + evidence-bundle layer** that turns the lookback from a
"trust us" project into a "verify the SHA-256 chain yourself"
artefact. That's the regulator-defensible boundary.

---

## See also

- The reference framing: [`aml_learning_for_fintech/docs/02-5year-lookback-azure-modernization.md`](https://github.com/tomqwu/aml_learning_for_fintech/blob/main/docs/02-5year-lookback-azure-modernization.md)
- [`docs/architecture.md`](architecture.md) — engine internals, deterministic-replay design decisions
- [`docs/audit-evidence.md`](audit-evidence.md) — hash-chain shape, evidence-bundle layout
- [`docs/spec-reference.md`](spec-reference.md) — every `aml.yaml` field
- [`docs/progress.md`](progress.md) — in-flight TM roadmap Track A (Gaps 1, 4, 7 = the equivalence + temporal-leakage + QA-labels combo that unblocks the 5-year-lookback headline)
- [`docs/jurisdictions.md`](jurisdictions.md) — US / CA / EU / UK / crypto example specs to start from
