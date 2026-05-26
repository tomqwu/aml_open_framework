# How to run a 5-year transaction-monitoring lookback

> **When you need this:** A regulator/auditor asks for a 60-month historical replay with point-in-time-correct alerts + a hash-chained audit trail for every month. Or you're rehearsing the lookback before the real one against your warehouse. This runbook is the copy-paste-runnable companion to the architectural overview in [`docs/five-year-lookback.md`](../five-year-lookback.md).
>
> **Prereqs:** A clone of `aml_open_framework` on `main`. Python ≥3.10. ~2 GB free disk for the synthetic 60-month dataset + per-month run artefacts. No warehouse / cloud account needed — the runbook uses the `community_bank_lookback` example spec + a deterministic synthetic generator.
>
> **Time:** ~5 min to install + validate. ~20–40 min for the 60-month loop on a laptop (≤1 min/month on synthetic data). ~2 min to pin hashes and verify. ~30 sec to package the regulator-ready ZIP.

This how-to mirrors [`docs/five-year-lookback.md` §10](../five-year-lookback.md#10-a-5-year-lookback-in-commands-you-can-actually-run-today) but pins every command to the `community_bank_lookback` example so an operator can paste verbatim and watch the artefacts appear under `.artifacts/lookback/<YYYY-MM>/`.

The companion equivalence step — legacy↔new parallel-run classification via `engine/equivalence.py` — is roadmap (TM Gap 1, PR-LOOKBACK-3); §[Equivalence (planned)](#equivalence-planned) below points forward.

---

## Steps

### 1 · Install and verify the CLI

```bash
git clone https://github.com/tomqwu/aml_open_framework
cd aml_open_framework
pip install -e ".[dev,dashboard]"
aml --help | head -3
```

**Expect:**

```text
 Usage: aml [OPTIONS] COMMAND [ARGS]...

 Spec-driven AML automation framework.
```

If `aml` is not on `PATH`, your venv activation didn't stick — re-source the venv and retry.

### 2 · Generate a synthetic 60-month dataset

`scripts/generate_lookback_dataset.py` materialises 60 month-end slices (or fewer with `--months`) under `examples/community_bank_lookback/data/{parquet,csv}/<YYYY-MM>/`, pinning the synthetic seed so planted-positive customers stay reproducible across months.

```bash
python scripts/generate_lookback_dataset.py \
    --years 5 \
    --end   2025-12-31 \
    --out   examples/community_bank_lookback/data
```

**Expect:**

```text
Generating 60 months × ~1300 txns ending 2025-12-31 → examples/community_bank_lookback/data
  [  1/60] 2021-01: customer=100 txn=1220 txn_return=3 hs_code_baseline=5
  [  2/60] 2021-02: customer=100 txn=1220 txn_return=3 hs_code_baseline=5
  ...
  [ 60/60] 2025-12: customer=100 txn=1220 txn_return=3 hs_code_baseline=5
Done. Manifest: examples/community_bank_lookback/data/_manifest.json
```

After the script returns, both formats are present per month:

```text
examples/community_bank_lookback/data/
├── _manifest.json
├── parquet/
│   ├── 2021-01/{customer,txn,txn_return,hs_code_baseline}.parquet
│   ├── 2021-02/...
│   └── 2025-12/...
└── csv/
    ├── 2021-01/{customer,txn,txn_return,hs_code_baseline}.csv
    ├── ...
    └── 2025-12/...
```

The generator pins `--seed 42` by default — re-running the script produces byte-identical per-month files. Smoke-test with `--months 2` first if you want to verify the layout in ~10 sec before committing to the full 60-month run.

### 3 · Validate the spec

```bash
aml validate examples/community_bank_lookback/aml.yaml
```

**Expect:**

```text
OK examples/community_bank_lookback/aml.yaml — 2 contract(s), 7 rule(s), 4 queue(s).
```

This is the same two-layer validation (JSON Schema → Pydantic cross-reference) every spec gets. The `community_bank_lookback` spec mirrors `community_bank/aml.yaml` rule-for-rule — the only difference is the runbook layered on top.

### 4 · Run the 60-month loop (parquet primary)

One `aml run` per business month. Each `--artifacts` invocation creates `<dir>/run-<ISO-timestamp>/` with its own manifest, alerts, cases, decisions ledger, and hash chain.

Iterate directly over the `parquet/<YYYY-MM>/` directories the generator wrote — that way the loop covers exactly the 60 months on disk (no chance of typos in a hard-coded month array, and no risk of the comment "… 48 more …" being copy-pasted as-is and silently skipping months). The loop **pins each month's `decisions_hash` to the WORM-style log immediately after the run finishes** so there's no window where the manifest and ledger can both be rewritten before the head hash is externally captured (see §5 below for the threat model + production-store patterns):

```bash
set -euo pipefail   # fail-fast: any non-zero `aml run` aborts the loop

mkdir -p .artifacts/lookback/_worm
: > .artifacts/lookback/_worm/decisions-hashes.log   # truncate-on-create

for ym_dir in examples/community_bank_lookback/data/parquet/*/; do
    ym=$(basename "$ym_dir")                            # e.g. 2021-09
    # Cutoff = first second of the FOLLOWING month, used as an exclusive
    # upper bound (the engine templates rule windows as
    # `booked_at < TIMESTAMP '{as_of}'`). Passing `${last_day}T23:59:59`
    # would silently drop any transaction landing at exactly 23:59:59
    # or later that same second — fine for synthetic data (max booked_at
    # is 23:50:59) but wrong for production rails like RTP/FedNow.
    next_ym=$(python -c "import datetime; \
y,m=map(int,'$ym'.split('-')); \
n=datetime.date(y,m,28)+datetime.timedelta(days=4); \
print(n.replace(day=1).isoformat())")
    aml run examples/community_bank_lookback/aml.yaml \
        --as-of       "${next_ym}T00:00:00" \
        --data-source parquet \
        --data-dir    "$ym_dir" \
        --seed        42 \
        --artifacts   ".artifacts/lookback/${ym}/"

    # Pin THIS month's decisions_hash before continuing — under an
    # active-attacker model, the WORM append must happen before the
    # next `aml run` writes its own manifest.json. `set -e` above
    # guarantees we only reach here on a successful `aml run`, so the
    # WORM never receives a stale or empty hash from a failed month.
    run_dir=$(ls -1d ".artifacts/lookback/${ym}/run-"* | tail -n1)
    sha=$(python -c "import json,sys; print(json.load(open(sys.argv[1]))['decisions_hash'])" \
              "${run_dir}/manifest.json")
    echo "${ym} ${sha} ${run_dir}" >> .artifacts/lookback/_worm/decisions-hashes.log
done
```

If you'd rather pin the month-end cutoffs explicitly (e.g. you only want to run a subset), the equivalent literal array would start `"2021-02-01T00:00:00" "2021-03-01T00:00:00" … "2026-01-01T00:00:00"` — all 60 entries (one *per* month, exclusive-upper-bound style), no `# …` placeholder, so an operator pasting it never silently skips months.

**Expect per month** (sample, last line of stdout from `aml run`):

```text
Done. 46 alert(s), 46 case(s), 13 metric(s), 7 report(s). Run dir:
.artifacts/lookback/2025-12/run-20260526T130832Z
```

Counts hover in the same band across months because the synthetic generator plants the same positives per slice — small ±N drift from background traffic at the spec's tight thresholds is the realistic false-positive surface (by design — that's what FP-analysis / tuning / backtest exist for; investigate via the Alert Queue dashboard page).

> **CSV alternative.** If your environment doesn't have `pyarrow` (e.g. you installed only `[dev]` and skipped `dashboard`, or your platform's wheel didn't resolve), swap the loader for CSV — the generator writes both formats. The full loop, with the same fail-fast + WORM-init + exclusive-cutoff + in-loop hash-pinning as the parquet primary:
>
> ```bash
> set -euo pipefail
> mkdir -p .artifacts/lookback/_worm
> : > .artifacts/lookback/_worm/decisions-hashes.log
>
> for ym_dir in examples/community_bank_lookback/data/csv/*/; do
>     ym=$(basename "$ym_dir")
>     next_ym=$(python -c "import datetime; \
> y,m=map(int,'$ym'.split('-')); \
> n=datetime.date(y,m,28)+datetime.timedelta(days=4); \
> print(n.replace(day=1).isoformat())")
>     aml run examples/community_bank_lookback/aml.yaml \
>         --as-of       "${next_ym}T00:00:00" \
>         --data-source csv \
>         --data-dir    "$ym_dir" \
>         --seed        42 \
>         --artifacts   ".artifacts/lookback/${ym}/"
>     run_dir=$(ls -1d ".artifacts/lookback/${ym}/run-"* | tail -n1)
>     sha=$(python -c "import json,sys; print(json.load(open(sys.argv[1]))['decisions_hash'])" \
>               "${run_dir}/manifest.json")
>     echo "${ym} ${sha} ${run_dir}" >> .artifacts/lookback/_worm/decisions-hashes.log
> done
> ```
>
> The `decisions_hash` chain itself is loader-agnostic — alerts, decisions, and the metric values match byte-for-byte across the CSV and Parquet paths because the loaded DuckDB tables are the same shape. Other artefacts that record the input source — `manifest.json`'s `inputs[*].sha256` (different content hashes for `.csv` vs `.parquet`), and the per-case evidence-file paths embedded in `cases/*.json` / the auditor pack — **will differ between formats**. Treat the `decisions_hash` as the cross-format equivalence anchor, not the manifest hashes.

### 5 · The WORM-style log — threat model + production-store patterns

Step 4's loop **already** appended each month's `decisions_hash` to `.artifacts/lookback/_worm/decisions-hashes.log` immediately after that month's `aml run` finished. This section explains the threat model that motivates pinning in-loop (rather than as a post-hoc sweep) and lists the production stores you'd swap the flat-file `>>` for in a real evidence pipeline.

**Threat model**: the hash chain inside each run is internally consistent — but an attacker with write access to `manifest.json` can rewrite both the ledger AND the head hash before anyone notices. The defence is to **pin each month's `decisions_hash` to an external store at run time** (WORM bucket / signed log / regulator-witnessed DB row), so the externally-pinned value is the *witness* for the chain head. Doing this post-hoc — as a separate sweep over `.artifacts/lookback/2*/` after all months have run — leaves a window where both files can be tampered with before the WORM gets its first read, so step 4 pins inside the loop.

**Inspect what step 4 wrote:**

```bash
head -3 .artifacts/lookback/_worm/decisions-hashes.log
```

**Expect:**

```text
2021-01 73bed7e380dec1f8460879e73cf6d0162494112c949346496823810b865daeb5 .artifacts/lookback/2021-01/run-20260526T140545Z
2021-02 39c43b36d119ba45a213424d54927f4e45d5ea5e0f5c93b536e0240f2d1ae0b4 .artifacts/lookback/2021-02/run-20260526T140546Z
2021-03 3ddbb0093b3ada61ae9d880ecba689e8b482298df7a6c930189b7a9deb455afb .artifacts/lookback/2021-03/run-20260526T140547Z
```

In production, replace the `>> .artifacts/lookback/_worm/decisions-hashes.log` redirect with whichever of these your bank's evidence policy mandates:

- `aws s3 cp - s3://aml-evidence-worm/decisions-hashes-${ym}.txt` against an S3 Object-Lock-locked bucket,
- `psql -c "INSERT INTO run_manifests (ym, decisions_hash, run_dir) VALUES (...)"` against a Postgres table with row-level immutability,
- a GPG-signed commit to an external git-on-WORM repo.

See [`docs/how-to/verify-audit-chain.md`](verify-audit-chain.md) for the deeper rationale on external pinning.

### 6 · Verify every month against the pinned hash

```bash
set -euo pipefail
while read -r ym sha run_dir; do
    aml verify-decisions --run-dir "$run_dir" --expected-hash "$sha"
done < .artifacts/lookback/_worm/decisions-hashes.log
```

**Expect** (one line per month, all green):

```text
Decision log integrity verified
Decision log integrity verified
Decision log integrity verified
...
```

Exit code 0 = the `decisions.jsonl` hash chain recomputes to the expected head. Non-zero = chain broken or head mismatched. Scope: `aml verify-decisions` covers the decision ledger only — it does **not** recompute `dq_exceptions_hash`, `field_lineage_hash`, `sla_report_hash`, `monitoring_digest_hash`, `defect_log_hash`, `reconciliation_report_hash`, or the per-rule alert-file hashes in `manifest.json`. To prove those artefacts haven't drifted, recompute each one yourself and compare to the pinned manifest field — e.g. `sha256sum "$run_dir/dq_exceptions.jsonl"` against `jq -r .dq_exceptions_hash "$run_dir/manifest.json"`. The combination of `--run-dir` (anchors which month) + `--expected-hash` (anchors the chain's trust root externally) is the production-grade verification path for the ledger; for full-bundle integrity you also need the per-artefact `sha256sum` walk (see the table at the bottom of [`docs/how-to/verify-audit-chain.md`](verify-audit-chain.md#what-the-hash-chain-protects-against)).

### 7 · Build a regulator-ready evidence pack

`aml auditor-pack` bundles the chain-verified ledger, the examination pack, raw manifest, and a one-page `MANIFEST.txt` index into a single ZIP. The auditor opens the ZIP, walks the index, then drills into whichever artefact they want.

Pass the **spec snapshot from the run directory** (not `examples/community_bank_lookback/aml.yaml`) so the pack carries the exact spec content that produced that month's alerts — important if `aml.yaml` is later edited in git:

```bash
aml auditor-pack \
    .artifacts/lookback/2025-12/run-*/spec_snapshot.yaml \
    --run-dir  .artifacts/lookback/2025-12/run-* \
    --out      evidence-2025-12.zip
```

**Expect:**

```text
┌────────────────────┬────────┐
│ MANIFEST.txt       │ ✓      │
│ manifest.json      │ ✓      │
│ decisions.jsonl    │ ✓      │
│ spec_snapshot.yaml │ ✓      │
└────────────────────┴────────┘

✓ Hash chain verified. Decision log integrity verified

Auditor pack written evidence-2025-12.zip
```

To bundle every month at once, wrap step 7 in the same `while read` loop you used for step 6 — one ZIP per month, named `evidence-${ym}.zip`. Concatenated, those 60 ZIPs are the 5-year evidence package you hand to the examiner.

---

## What you should see when the runbook completes

Three things are true:

1. **`.artifacts/lookback/<YYYY-MM>/run-<ISO-timestamp>/`** exists for every month, each containing the same artefact set: `manifest.json`, `alerts/`, `cases/`, `decisions.jsonl`, `metrics/`, `reports/`, `spec_snapshot.yaml`, `field_lineage.jsonl`, `dq_exceptions.jsonl`, `monitoring_digest.json`, `reconciliation_report.json`, `sla_report.json`, `defect_log.jsonl`, `run_cost_volume.json`.
2. **`.artifacts/lookback/_worm/decisions-hashes.log`** has 60 lines, one per month, each pinning that month's `decisions_hash` to its run directory.
3. **Every `aml verify-decisions --expected-hash …` call exits 0** with `Decision log integrity verified`. Anything else means the `decisions.jsonl` chain head diverged from the externally-pinned hash. (For full-bundle integrity — the non-decisions artefacts whose hashes are pinned in `manifest.json` — run a `sha256sum` walk per step 6 above.)

Re-running step 2 with the same seed + step 4 with the same `--as-of` + `--seed 42` produces an **identical `decisions_hash` per month** plus byte-identical `alerts/*.jsonl` and `cases/*.json` files. This is the determinism contract pinned by `tests/test_engine.py::test_run_is_reproducible`. A handful of wall-clock fields are deliberately *outside* that contract — `manifest.json::finalised_at`, `manifest.json::run_dir` (which embeds the run-start timestamp), and the rehashed `monitoring_digest`/`run_cost_volume` artefacts that depend on them — so those will differ across reruns. If your second pass produces a different `decisions_hash` (or different alerts/cases bytes) for any month, that's a bug — file an issue with the diff.

---

## Equivalence (planned)

Step 8 in the full operator playbook is **legacy↔new equivalence**: load your legacy system's alert export for the same month, join against the framework's `alerts/*.jsonl`, and classify each divergence (`data` / `rule` / `mapping` / `intentional`). The framework's roadmap sequences this as `engine/equivalence.py` + a `Program.legacy_reference` spec field — landing in **PR-LOOKBACK-3** of this series. The PR will also commit a representative `legacy-alerts.csv` alongside `examples/community_bank_lookback/aml.yaml` so the equivalence flow demos end-to-end from the same example spec.

Until PR-LOOKBACK-3 lands, follow the pandas-style scaffold in [`docs/five-year-lookback.md` §4 Pattern 5](../five-year-lookback.md#pattern-5-parallel-validation-legacy-new-planned-tm-gap-1) — read your legacy export + the framework's `alerts/<rule_id>.jsonl`, outer-join on `(customer_id, window_start)`, and classify by hand.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `python scripts/generate_lookback_dataset.py` fails with `ModuleNotFoundError: pyarrow` | The `[dev,dashboard]` extras didn't install pyarrow on your platform (rare). | Re-run with `--formats csv` and use the CSV alternative in step 4. |
| `aml run` errors with `ContractViolation: missing required column …` | The synthetic generator's schema drifted vs the example spec. | Pin the framework to the same git SHA the example spec was committed at; re-run step 2. |
| `aml validate-data` against the generator's CSV slices errors on `unexpected column 'uetr'` / `'invoice_id'` / `'counterparty_id'` | The shared synthetic generator emits the union of fields needed across all example specs; `community_bank_lookback`'s contract is a subset, and `validate_csv` treats extras as errors. | The runbook doesn't run `validate-data` against generated slices for this reason. The engine itself silently ignores extras during `aml run`, so the lookback loop is unaffected. To validate-data the slices anyway, project the CSV down to the contract columns first (`csvcut -c txn_id,customer_id,…`). |
| Alert counts drift across months | Real false-positive surface from background traffic at the spec's tight thresholds — by design. | Inspect via the Alert Queue page (`aml dashboard examples/community_bank_lookback/aml.yaml`). Tune via the Threshold Sensitivity page. |
| `aml auditor-pack` errors `multiple matches for --run-dir glob` | The `run-*` glob in step 7 expanded to >1 path because you re-ran step 4. | Pick the latest run explicitly: `run_dir=$(ls -1d .artifacts/lookback/2025-12/run-* \| tail -n1)` and pass it as a literal path. |
| `decisions_hash` differs across two runs of step 4 with the same seed | A non-determinism crept into your rule code or the spec uses wallclock (`datetime.now()`). | Diff the two `manifest.json::inputs` blocks; the differing `content_hash` names the contract that drifted. |
| `aml auditor-pack` warns about a spec hash mismatch | You passed `examples/community_bank_lookback/aml.yaml` instead of the snapshot from the run directory. | Use the snapshot — `.artifacts/lookback/<ym>/run-*/spec_snapshot.yaml`. |

---

## Next steps

- **Verify in CI.** Wire step 6's loop into a daily scheduled job (`.github/workflows/audit-check.yml`) so any tamper of the archive surfaces within 24 hours. See [How to verify the audit chain](verify-audit-chain.md#4-wire-into-ci) for the workflow shape.
- **Add a `python_ref` ML scorer.** The community_bank_lookback spec is `aggregation_window` only. To layer an ML scorer with SR 11-7 evidence in the same monthly run, follow [How to wire a `python_ref` scorer](python-ref-scorer.md).
- **Promote to a real warehouse.** Replace `--data-source parquet --data-dir examples/community_bank_lookback/data/parquet/<ym>/` with a Lakeflow/ADF-materialised Gold mount (`/mnt/gold/<ym>/`). The runbook is identical; the data source changes. See [`docs/five-year-lookback.md` §2](../five-year-lookback.md#2-the-framework-sits-on-top-of-your-azure-stack-not-against-it).
- **Read the architectural overview.** [`docs/five-year-lookback.md`](../five-year-lookback.md) — the 10-section explainer this runbook executes. The mapping is roughly: `§1` (the eight properties) ↔ this runbook's deterministic guarantee; `§4 Pattern 1` ↔ step 4; `§5` ↔ step 3; `§7` ↔ step 7; `§10` ↔ this whole runbook.
