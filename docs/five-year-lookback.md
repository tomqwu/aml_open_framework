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

> **Implemented today vs. TM-roadmap planned.** This doc names the
> commands and spec fields that exist on `main` *and* the items that
> the TM roadmap in [`docs/progress.md`](progress.md) explicitly
> sequences for later. The line is marked inline (look for **🛠
> planned · TM Gap N**). The "lookback in N commands" runbook at §10
> uses only commands that exist today; the equivalence/parallel-run
> path is gated behind Gap 1 and §10 says so.

---

## 1. The 8 properties of a lookback — where the framework delivers each

The reference doc names eight properties: a lookback must be
*complete, point-in-time correct, repeatable, performant, auditable,
explainable, reconciled, signed off.* Mapping each to a concrete
mechanism the framework already ships:

| Property | How the framework enforces it |
|---|---|
| **Complete** | `aml validate` + `aml validate-data` cross-check every rule's contract columns against the loaded data before any rule fires — a missing column is a build failure, not a silent zero. Run-time `engine/freshness.py` adds DQ floors. |
| **Point-in-time correct** | Engine threads `as_of` through every rule. `custom_sql` rules get `{as_of}`, `{window_start}`, `{recent_start}`, `{baseline_start}`, `{dormant_cutoff}` auto-substituted. Reference data joined as of the transaction date, not "now". |
| **Repeatable** | The deterministic-replay contract: same spec + same data + same `as_of` + same seed ⇒ byte-identical alert/case/decision hashes. Pinned by `tests/test_engine.py::test_run_is_reproducible`. |
| **Performant** | DuckDB in-memory for the engine; cloud sources (Snowflake/BigQuery/S3/GCS/Parquet) loaded by `data/sources.py` with predicate pushdown via the placeholder system. |
| **Auditable** | `engine/audit.py` writes a SHA-256-hash-chained `decisions.jsonl`. `AuditLedger.verify_decisions()` proves no tampering at any horizon. |
| **Explainable** | Every alert carries `matched_row_ids` referencing the exact source rows (#341 fix replays the rule filter so audit evidence matches the alert's own SQL). `walk_lineage` reconstructs alert → rule → data. |
| **Reconciled** | **🛠 planned · TM Gap 1.** An `engine/equivalence.py` module is sequenced in [`docs/progress.md`](progress.md) — joins legacy ↔ new outputs and classifies each divergence (`data` / `rule` / `mapping` / `intentional`). Until it lands, reconciliation today is "diff your legacy export against `run_dir/alerts/*.jsonl` in your own SQL/Spark step." |
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
│    dashboard/ (40 Streamlit pages, persona-routed by audience.py) │
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
| **Azure Data Factory / Fabric Data Factory** | The framework's CLI (`aml run`, `aml validate`, `aml export`) is wrap-friendly. A typical ADF pipeline: *Extract → land Parquet → `aml validate-data` activity → `aml run` activity → publish run_dir back to Gold → publish ZIP to evidence container*. |
| **Databricks / Spark / Lakeflow** | Your Lakeflow pipelines produce the rule-ready Gold tables; the framework reads them. For Spark-native rule execution you don't need this framework, but you give up the spec contract + the deterministic audit chain. The framework's value-add is the **defensible spec + evidence**, not raw compute. |
| **Delta Lake** | The framework treats Delta tables as Parquet (Delta's read API is Parquet-compatible). Delta's time-travel + the framework's `as_of` together give you full point-in-time replay: pin Delta's version + the framework's `as_of` to the same business date. |
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

Each `/evidence/runs/YYYY-MM/.artifacts/<run_id>/` is self-contained:
spec, manifest, alerts, cases, decisions, hash chain. A defect fix
means re-running only the affected months.

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

For alert-level dedupe across runs, the `alert_key` field is computed
as `hash(rule_id, rule_version, customer_id, window_start,
window_end, ...)` — same recipe the reference doc proposes.

### Pattern 3 — Batch ID everywhere

Every artefact in `run_dir` carries the run identifiers:

```json
// run_dir/manifest.json (extract)
{
  "run_id":         "01J7XK8Q9...",
  "spec_path":      "examples/your_program/aml.yaml",
  "spec_hash":      "sha256:b09f...",
  "as_of":          "2021-09-30T23:59:59Z",
  "seed":           42,
  "git_sha":        "00ca73c",
  "app_version":    "0.1.28",
  "build_time":     "2026-05-20T01:16Z",
  "input_manifest": [{ "table": "transactions", "rows": 4923711,
                       "sha256": "..." }, ...],
  "decisions_count": 312,
  "decisions_hash":  "sha256:..."   // chain head
}
```

Every alert / case / decision row references the `run_id`. The
manifest is itself sealed into the audit chain.

### Pattern 4 — Point-in-time reference data

The framework supports point-in-time reference data via:

- **`as_of` placeholders** in `custom_sql` rules — the engine
  substitutes the business date at run time, so the SQL naturally
  pulls reference values valid at that date.
- **Effective-dated contracts** — `data_contracts[].columns` can
  declare `effective_start_date` / `effective_end_date` columns; the
  loader and rules respect them.
- **The bigger discipline**: the *spec* is point-in-time too. Tag your
  `aml.yaml` per period
  (`examples/your_program/aml.yaml@2021-09-30`) so you can rerun the
  *rules as they were on 2021-09-30* against the *data as it was on
  2021-09-30*. The framework's `setuptools-scm` + git-tag-driven
  version IDs make this natural: every run carries the spec's git
  commit SHA.

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
      source: txn
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

### Pattern 5 — Parallel validation (legacy ↔ new) · **🛠 planned · TM Gap 1**

The framework's TM-roadmap Track A Gap 1 in [`docs/progress.md`](progress.md)
sequences a `Program.legacy_reference` field + an `engine/equivalence.py`
module that joins legacy ↔ new alerts and classifies each divergence as:

```text
expected difference
source data mismatch
mapping defect
rule logic defect
reference data defect
timing/window defect
legacy defect exposed by migration
```

Once merged, classifications will be written as `LEGACY_EQUIV_CHECK`
audit events in the deterministic ledger (`as_of`-stamped, hash-chained,
IN the replay contract). The legacy file will be content-hashed into the
`input_manifest` so future reruns can prove they compared against the
same legacy snapshot.

**Today, before Gap 1 lands:** the framework's deterministic
`alerts/*.jsonl` per month is your right-side input — diff it against
your legacy alert export in a 20-line SQL/Spark/pandas step:

```python
# Pseudocode — pandas-style diff once each side is one row per alert
import pandas as pd
new = pd.read_json("evidence/runs/2021-09/.artifacts/<run_id>/alerts/structuring_cash_deposits.jsonl", lines=True)
old = pd.read_csv("legacy/tm/2021-09/alerts.csv")
diff = new.merge(old, on=["customer_id", "window_start"], how="outer", indicator=True)
# diff["_merge"] ∈ {"left_only", "right_only", "both"} → classify by hand
# until Gap 1 lands the classifier inline.
```

Spec field `Program.legacy_reference` is **not yet a real field**
(`Program` is `extra="forbid"`); don't add it to your YAML until the
schema lands.

---

## 5. Data stitching — what the framework catches before rules run

The reference doc's stitching-failure table maps directly to
framework controls:

| Failure mode | Where the framework catches it |
|---|---|
| Missing customer/account link | `aml validate-data` fails: the `data_contract` declares `customer_id` as non-null with FK to `customers.id`. |
| Duplicate transaction | `data_contract.quality_checks.unique: [transaction_id]` flags it pre-run. |
| Late-arriving record | The `as_of` bound: any row with `booked_at > as_of` is excluded. Late arrivals are visible in `engine/freshness.py` reports as "rows landed after as_of". |
| Current reference data used for old transaction | Point-in-time reference contracts + the `effective_start_date` / `effective_end_date` discipline above. |
| Wrong currency conversion date | Same point-in-time pattern applied to FX rate tables. |
| Many-to-many ownership ignored | Explicit join shape in `custom_sql` rules; the framework doesn't auto-resolve M:M (by design — silent M:M is the bug, not the feature). |

The `data_contract` IS your stitching contract — declared in YAML,
validated before every run, version-controlled alongside the rules.

---

## 6. Performance — multi-year scale

The framework's compute model is **DuckDB in-memory per run, scoped by
`as_of` + `data-dir`**. For a single month of a mid-sized bank
(~50M txns), an in-memory run is fast. For a 5-year backfill:

1. **Run per-month in parallel.** Each `run_dir` is independent; the
   audit chain is per-run. A 60-month backfill is 60 independent
   jobs — wrap with Lakeflow / ADF parallel branches.
2. **Pre-filter at the source.** Snowflake / BigQuery / Spark do the
   heavy partition pruning; the framework's placeholder system
   (`{as_of}`, `{window_start}`) pushes down. The DuckDB layer only
   sees the month's rule-ready slice.
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
| `run_manifest` (batch_id, source periods/tables, rule versions, parameter versions, code commit hash, status) | `run_dir/manifest.json` — every field above is already a manifest column |
| `reconciliation_report` (source row count, target row count, totals, exceptions, alert count) | `run_dir/reports/*.md` per spec-declared `report:` + `engine/equivalence.py` divergence report when `legacy_reference` is set |
| `rule_output_report` (alert count by month / customer segment / geography / reason code) | `run_dir/alerts/*.jsonl` (raw) + the **Rule Performance** + **Comparative Analytics** dashboard pages (`pages/5_Rule_Performance.py`, `pages/19_Comparative_Analytics.py`) |
| `dq_report` (completeness, duplicates, validity, referential integrity, PIT coverage) | `data_contract.quality_checks` results + `engine/freshness.py` outputs + the **Data Quality** dashboard page (`pages/14_Data_Quality.py`) |
| `defect_log` (defect_id, severity, root cause, owner, fix version, retest evidence) | The audit ledger's failure-audit rows (every `_FAILED` future writes a `ai_section_explanation_failed`-shape event with `error_type`, `error_message`, `run_dir`, `backend`, `model` — same shape applies to any rule-execution defect). Custom defect_logs land as wall-clock sidecars per `cases/filing.py`'s `append_to_run_dir` pattern. |

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
6. **Common stitching failures?** All caught by `aml validate-data` + `data_contract.quality_checks` (table in §5).
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

# 4. Map your warehouse to the spec's contracts.
aml byod examples/my_program/aml.yaml /mnt/gold/2021-09/
$EDITOR data_mapping.yaml

# 5. Validate one month of historical data against the spec's
#    contracts. Catches stitching failures before any rule runs.
aml validate-data examples/my_program/aml.yaml /mnt/gold/2021-09/

# 6. Backfill — one independent run per business month. In
#    production, ADF / Lakeflow materializes the per-month Gold slice
#    to a Parquet mount and wraps the loop in parallel branches.
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

# 7. Verify the hash chain per month. Wrap this in a script that
#    walks every /evidence/runs/<month>/ — `verify-decisions` takes
#    one --run-dir at a time.
for ym in /evidence/runs/*/; do
    aml verify-decisions \
        --run-dir   "${ym}.artifacts/" \
        --artifacts "${ym}.artifacts/"
done

# 8. Build the regulator-ready bundles. `aml audit-pack` produces the
#    pre-examination bundle per run; `aml export` zips a run dir as
#    a deterministic evidence bundle. Both take ONE --run-dir today;
#    wrap in a loop. Concatenate the per-month ZIPs into your
#    deliverable.
for ym in /evidence/runs/*/; do
    aml audit-pack examples/my_program/aml.yaml \
        --run-dir "${ym}.artifacts/" \
        --out     "${ym}audit-pack.zip"
    aml export examples/my_program/aml.yaml \
        --run-dir "${ym}.artifacts/" \
        --out     "${ym}evidence.zip"
done

# 9. (🛠 Planned · TM Gap 1.) Reconcile against the legacy system per
#    month — `engine/equivalence.py` is roadmap, not on main today.
#    Until it lands, run your own SQL/Spark/pandas diff over each
#    month's alerts/*.jsonl ↔ legacy alert export and classify each
#    divergence by hand. See Pattern 5 above.

# 10. Build per-rule MRM dossiers when ML scorers are in play.
aml mrm-bundle examples/my_program/aml.yaml \
    --run-dir /evidence/runs/2025-12/.artifacts/
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
- **You own the legacy parallel-run extract.** The framework
  classifies divergences, but it can't generate the legacy side.
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
