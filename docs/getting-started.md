# Getting Started

The synthetic demo runs in **2 minutes** and shows you real alerts immediately — no data wrangling. But that's the warm-up, not the job. What the framework is *built* for is running **your** data, audit-defensibly, all the way to a regulator-ready evidence bundle and a **proven legacy↔new migration**. This guide is structured as that production-shaped arc, not a flat tutorial.

## The path

| Stage | What you do | Why it matters |
|---|---|---|
| **0. Warm-up** | The 2-minute synthetic sanity check | Prove the engine works before you invest |
| **1. Bring your own data** | Wire CSVs / 9 source types / ISO 20022 | The real work starts here |
| **2. Shape the program for production** | Custom rules, env promotion, advanced spec fields | Make it production-grade, not a toy run |
| **3. Run a real business month** | Point-in-time, month-end slices | The realistic operational workflow |
| **4. Prove legacy ↔ new equivalence** | The migration gate | Proof the rewrite reproduces the legacy control |
| **5. Bundle + externally verify evidence** | `auditor-pack` + hash verification | What you hand the regulator |

**Synthetic is the warm-up; the 5-year lookback is the destination.**

### TL;DR — prove it runs in 2 minutes

```bash
git clone https://github.com/tomqwu/aml_open_framework.git && cd aml_open_framework
pip install -e ".[dev,dashboard,api]"
aml dashboard examples/community_bank/aml.yaml
# Open http://localhost:8501
```

The dashboard runs the engine on synthetic data with planted positives, so you'll see real alerts immediately — proof it runs, not proof you're done. Keep reading: stages 1–5 are the actual job.

---

## Stage 0: Warm-up (2-minute sanity check)

This stage proves the engine works end-to-end on synthetic data with planted positives, so you have a known-good baseline before you bring real data. Install, pick a spec, run it, and look at the alerts in the dashboard.

### Install (2 min)

The framework is a Python package with optional dashboard + API extras.

```bash
# Clone
git clone https://github.com/tomqwu/aml_open_framework.git
cd aml_open_framework

# Create a venv (Python >= 3.10 required)
python3 -m venv .venv && source .venv/bin/activate

# Install
pip install -e ".[dev,dashboard,api]"

# Verify
aml --help
```

> **macOS note:** the system `python3` shipped with macOS is 3.9, which fails the `>=3.10` pin and surfaces as `ERROR: Package 'aml-open-framework' requires a different Python: 3.9.x not in '>=3.10'`. Install a current Python first (`brew install python`), then re-run the venv step. Verified working on 3.12 and 3.14.

If you only need the engine + CLI, drop the extras: `pip install -e ".[dev]"`. The `dashboard` extra pulls in Streamlit + ECharts + AG Grid; the `api` extra pulls in FastAPI + Uvicorn.

### Pick a spec (1 min)

Fourteen example specs ship in `examples/`, spanning 6 jurisdictions (US, CA, EU, UK, Cross-border, AU) and several typology focuses:

| Spec path | Jurisdiction | Regulator | Use when |
|---|---|---|---|
| `examples/community_bank/aml.yaml` | US | FinCEN | Demo / first-time exploration |
| `examples/canadian_bank/aml.yaml` | CA | FINTRAC | Mid-size Canadian retail / credit union |
| `examples/canadian_schedule_i_bank/aml.yaml` | CA | FINTRAC + OSFI | Big-six Canadian bank |
| `examples/eu_bank/aml.yaml` | EU | EBA / AMLD6 | Eurozone retail bank |
| `examples/uk_bank/aml.yaml` | UK | FCA / POCA | UK challenger or retail |
| `examples/cyber_enabled_fraud/aml.yaml` | US | FinCEN / FATF | Pig-butchering + investment-scam typology |
| `examples/uk_app_fraud/aml.yaml` | UK | FCA + PSR + NCA | UK PSR reimbursement-mandate APP fraud |
| `examples/trade_based_ml/aml.yaml` | US | FinCEN + FATF / Egmont | Trade-based ML typology indicators |
| `examples/us_rtp_fednow/aml.yaml` | US | FinCEN / RTP / FedNow | Real-time-payment push-fraud detection |
| `examples/crypto_vasp/aml.yaml` | Cross-border | FATF R.16 / FinCEN / FINTRAC | VASP STR/SAR + Travel Rule completeness |
| `examples/austrac_tranche_2_dnfbp/aml.yaml` | AU | AUSTRAC | Tranche-2 DNFBPs (lawyers/accountants/real-estate/precious-metals); SMR/TTR |
| `examples/genius_ppsi_issuer/aml.yaml` | US | FinCEN (GENIUS Act) | Permitted-payment stablecoin issuer — mint/burn, nested-VASP, sanctioned-wallet; SAR |
| `examples/genius_ppsi_stablecoin/aml.yaml` | US | FinCEN + OFAC (GENIUS Act NPRM) | Richer PPSI stablecoin — ISO 20022, 31 CFR Part 502 OFAC, SAR/CTR latency SLA |
| `examples/community_bank_lookback/aml.yaml` | US | FinCEN | 5-year legacy→cloud migration lookback (the Stage 3–5 flagship) |

For your first run pick **`community_bank`** — it's the smallest, fastest, and best-documented.

See [`docs/jurisdictions.md`](jurisdictions.md) for what each spec covers and how to adapt it to your institution.

### Run your first spec (2 min)

```bash
# Validate the spec (JSON Schema + cross-reference integrity)
aml validate examples/community_bank/aml.yaml

# Execute against synthetic data with planted positives
aml run examples/community_bank/aml.yaml --seed 42
```

You'll see output like:
```
[engine] 6 rules executed against 1,311 transactions, 100 customers
[engine] 45 alerts produced, 45 cases opened
[audit] decisions ledger: 90 events, hash-chain verified
[run] artifacts at /tmp/aml_run_<id>/
```

Open the `cases/` directory under that artifacts path to see one JSON per alert — those are the auditable case files.

### Launch the dashboard (1 min)

```bash
aml dashboard examples/community_bank/aml.yaml
# Open http://localhost:8501
```

Three pages to start with:
- **Executive Dashboard** — program-level KPIs at a glance
- **Alert Queue** — every alert the engine fired, filterable by rule + severity
- **Case Investigation** — drill into one case for the full evidence pack

The sidebar **Audience** selector filters pages to a persona (CCO, Manager, Analyst, Auditor, etc.) — switch to "analyst" to see the L1 review surface.

Full page-by-page walkthrough: [`docs/dashboard-tour.md`](dashboard-tour.md).

> **That's the warm-up — it proves the engine works. Everything real starts now, with your data.**

---

## Stage 1: Bring your own data

This is where the real work starts. The synthetic baseline is behind you; now feed the framework the data your program actually runs on. Two options: drop CSVs in `data/input/`, or point the CLI at any of 9 supported source types (`synthetic`, `csv`, `parquet`, `duckdb`, `iso20022`, `s3`, `gcs`, `snowflake`, `bigquery`).

### Option A: CSV files (simplest)

```bash
mkdir -p data/input
# Populate these two files matching the spec's data_contract schema:
#   data/input/txn.csv      — txn_id, customer_id, amount, currency, channel, direction, booked_at
#   data/input/customer.csv — customer_id, full_name, country, risk_rating, onboarded_at
aml run examples/community_bank/aml.yaml --data-source csv --data-dir data/input/
```

Sample CSV files with 1,311 transactions and 100 customers ship in `data/input/` for immediate testing.

### Option B: Other sources

```bash
aml run spec.yaml --data-source parquet  --data-dir data/parquet/        # local Parquet dir
aml run spec.yaml --data-source s3        --data-dir s3://bucket/path/    # S3 (CSV or Parquet)
aml run spec.yaml --data-source gcs       --data-dir gs://bucket/path/    # GCS
aml run spec.yaml --data-source iso20022  --data-dir mx_messages/         # ISO 20022 pacs/pain
aml run spec.yaml --data-source snowflake                                 # uses SNOWFLAKE_* env vars
aml run spec.yaml --data-source bigquery                                  # uses GOOGLE_APPLICATION_CREDENTIALS
```

ISO 20022 ingestion handles pacs.008 / pacs.009 (FI-to-FI), pain.001 (corporate batch), and pacs.004 (returns) natively — see [Round-5 changelog entries](../CHANGELOG.md) for the full surface.

> **Watch the data layer in the dashboard**: the [Data Integration page](dashboard-tour.md#data-integration) renders a 30-second view of every wired source, contract roll-up, and ISO 20022 message-type counts — plus a DATA-N → artifact map linking each whitepaper data pain to its concrete framework artifact.

---

## Stage 2: Shape the program for production

With your data flowing, the next job is to make the program production-grade: author the rules your typologies actually need, gate them through environments so nothing untested fires in prod, and reach for the advanced spec fields that close specific compliance-pillar gaps. This is not a naive linear step — it's where the spec becomes an examiner-defensible control program.

### Author your first custom rule (5 min)

Every rule in `aml.yaml` cites a regulation. Here's the minimum viable rule shape:

```yaml
rules:
  - id: my_first_rule
    name: Cash deposits over USD 9,500 within 24h
    severity: high
    regulation_refs:
      - citation: "31 CFR 1010.314"
        description: "Anti-structuring under BSA"
    logic:
      type: aggregation_window
      source: txn
      filter:
        channel: cash
        direction: in
        amount: { between: [8000, 9500] }
      group_by: [customer_id]
      window: 24h
      having:
        count: { gte: 3 }
    escalate_to: l1_analyst
    evidence:
      - all_matching_transactions
      - customer_kyc_profile
    tags: [structuring, cash, bsa]
```

Five rule types are supported: `aggregation_window`, `list_match`, `custom_sql`, `python_ref`, and `network_pattern` (the entity-resolution graph type — runs a recursive CTE up to `max_hops` from each seed customer and flags subgraphs satisfying a `having` condition, typically minimum component size or shared-counterparty count). Full reference: [`docs/spec-reference.md`](spec-reference.md).

After editing, validate before running:
```bash
aml validate examples/community_bank/aml.yaml
```

The validator catches typos, broken cross-references, and structural errors before the engine ever touches data.

### Promote across environments (PR-D3)

Specs run in one of four lanes — `dev` / `test` / `uat` / `prod` — declared on `program.environment` (defaults to `dev`). Each rule carries an `environments` list naming the lanes it has been signed off for (defaults to `["dev"]`):

```yaml
program:
  environment: prod                    # this spec runs in the prod lane
  strict_environment_gating: true      # block any rule not signed off for prod

rules:
  - id: structuring_velocity
    # ... logic ...
    environments: [dev, test, uat, prod]   # cleared all the way through
  - id: experimental_layering
    status: pending_promotion
    environments: [dev, test]              # still in test — won't fire in prod
```

At run time the engine asks `is_rule_approved_for_environment` for every rule. When the rule's lane list does not include `program.environment`:

- **Soft mode** (default): the engine emits a `WARN` log line and lets the rule fire.
- **Strict mode** (`strict_environment_gating: true`): the engine raises `EnvironmentGatingError` and aborts the run.

Either way, an `environment_gate_check` event is appended to `decisions.jsonl` for **every** rule (approved or blocked) — the audit pack proves the gate was consulted on each rule, each run.

### Advanced spec features

Five spec fields shipped in Rounds 26–28 that operators routinely miss because they're optional and default to a sensible no-op. Each one closes a specific compliance-pillar gap; reach for them when your program matures past the first-run shape.

#### `program.sla` — operational SLA monitor (PR-LF1)

Declares two operational SLAs the engine evaluates per run and writes to `sla_report.json` in the run directory: **alert disposition aging** (open cases older than `alert_disposition_days` with no terminal `closed` / `escalated_to_str` event) and **batch lateness** (the gap between `run.as_of` and the most-recent transaction exceeds `batch_cadence_days + batch_lateness_grace_days`). The engine never raises on a breach — it records the breach so the Pillar-6 dashboard and the audit pack surface it. Omit the block to disable the monitor (empty report).

```yaml
program:
  name: community_bank_aml
  # ... other program fields ...
  sla:
    alert_disposition_days: 30      # open alerts older than this = breach
    batch_cadence_days: 1           # expected daily extract
    batch_lateness_grace_days: 1    # 1-day grace before flagging late
```

Spec model: `src/aml_framework/spec/models.py::ProgramSLA`. Test: [`tests/test_engine_sla.py`](../tests/test_engine_sla.py).

#### `quality_checks[*].severity` — DQ triage tier (PR-B5)

Each `quality_checks` entry on a `data_contract` can carry a `severity` of `critical` / `high` / `medium` / `low` / `info` (defaults to `high` — the prior uniform posture, so the field is a no-op for existing specs). The engine threads severity into every `DQException` written to `dq_exceptions.jsonl`, so the Data Quality dashboard page and triage routing can filter on it. Use `critical` for required-column / unique-key breaks and `info` for canonicalisation drift.

```yaml
data_contracts:
  - id: txn
    quality_checks:
      - { not_null: [txn_id, customer_id, amount, booked_at], severity: critical }
      - { unique: [txn_id], severity: critical }
      - { enum: { currency: [USD, CAD, EUR] }, severity: medium }
      - { regex: { phone: "^\\+?[0-9]{7,15}$" }, severity: info }
```

Spec model: `src/aml_framework/spec/models.py::QualityCheck` (`DQSeverity` literal). Test: [`tests/test_engine_dq_exceptions.py`](../tests/test_engine_dq_exceptions.py).

#### `rule.risk_tier` — risk-based-controls axis (PR-RISK-1)

A first-class `low` / `medium` / `high` tier on each rule, independent of `severity` (alert urgency) and `model_tier` (model-risk validation cadence). Closes the Pillar-5 "risk-based controls" gap on the North-Star Coverage page — until this shipped, the only risk signal was `severity`, which is an alert-priority field. Optional (defaults to `None`). PR-RISK-1 is additive-only: the field lands on the loaded spec, flows into the rule-version hash, and surfaces in the spec-diff path. Engine-time wire-in (alert priority + queue routing) is a follow-up PR.

```yaml
rules:
  - id: structuring_cash_deposits
    severity: high           # alert urgency
    risk_tier: high          # risk-based-controls posture
    # ... logic ...
```

Spec model: `src/aml_framework/spec/models.py::RiskTier`. Test: [`tests/test_spec_risk_tier.py`](../tests/test_spec_risk_tier.py).

#### `rule.business_intent` + `out_of_scope` — examiner-readable rationale (PR-A2)

Free-text prose declaring **why this rule exists** and **what it explicitly does NOT catch**, written for an examiner or 2LoD reviewer (not a regulation citation — those go in `regulation_refs`). At generation time these fields flow into four downstream artifacts: the STR narrative preamble, the MRM dossier's conceptual-soundness section, the control-matrix program-intent block, and the audit pack's `program_intent.md` / `inventory.json`. `business_intent` is `None` until authored; `out_of_scope` defaults to an empty list (the downstream renderers collapse the exclusions block when empty).

```yaml
rules:
  - id: structuring_cash_deposits
    business_intent: >
      Detect customers depositing cash in the $7,000–$9,999 just-below-CTR
      band three or more times within 30 days summing to $25,000+ — the
      classic anti-structuring pattern targeted by 31 CFR 1010.314.
    out_of_scope:
      - single cash deposits at or above $10,000 (covered by large_cash_ctr)
      - cash withdrawals (this rule is inbound-only)
```

Spec model: `src/aml_framework/spec/models.py::Rule` (`business_intent`, `out_of_scope`). Test: [`tests/test_program_intent_wiring.py`](../tests/test_program_intent_wiring.py).

#### `program.prioritization` — governed alert triage score

Advisory, explainable ML-style scoring that ranks alerts by risk so
investigators triage highest-first — **without ever changing an alert's
disposition**. Off by default.

```yaml
program:
  prioritization:
    enabled: true
    weights: { severity: 1.0, risk_tier: 1.0, amount: 0.5, volume: 0.5 }
```

Each alert gains `priority_score` (0–1) + `priority_explanation` (per-feature
contributions); the run emits a frozen, manifest-pinned `priority_report.json`.
The score is deterministic and in the hash-chained ledger — governed
augmentation, not a black box. See [`tests/test_prioritization.py`](../tests/test_prioritization.py).

Spec model: `src/aml_framework/spec/models.py::ProgramPrioritization`. Test: [`tests/test_prioritization.py`](../tests/test_prioritization.py).

---

## Stage 3: Run a real business month

The 5-year legacy-to-cloud lookback is not an appendix scenario — it **is** the realistic production workflow. You replay history through your modernised rules one month at a time, point-in-time, exactly as an examiner expects when you migrate a SAS / Actimize / Mantas TM stack to the cloud. This stage and stages 4–5 use the [`examples/community_bank_lookback`](../examples/community_bank_lookback) example spec — the lookback variant of `community_bank`.

The full copy-paste runbook (the 60-month loop, WORM-style hash log, per-month verification) lives in [`docs/how-to/run-five-year-lookback.md`](how-to/run-five-year-lookback.md); this is the orientation.

### Generate 60 month-end slices

```bash
python scripts/generate_lookback_dataset.py \
  --years 5 --end 2025-12-31 --seed 42 \
  --spec examples/community_bank_lookback/aml.yaml \
  --out examples/community_bank_lookback/data/
```

Writes `data/{parquet,csv}/<YYYY-MM>/{txn,customer}.*` for 60 months, with the synthetic seed pinned so planted-positive customers stay reproducible month to month. (Needs the `dashboard` extra for pyarrow; `--formats csv` skips it.)

### Run one business month (loop the rest)

```bash
aml run examples/community_bank_lookback/aml.yaml \
  --as-of 2026-01-01T00:00:00 \
  --data-source parquet \
  --data-dir examples/community_bank_lookback/data/parquet/2025-12 \
  --seed 42 --artifacts .artifacts/lookback/2025-12
```

Each month gets its own `run-<ts>/` with an independent manifest, alerts, decisions ledger, and hash chain. The runbook wraps this in a 60-iteration `for` loop.

---

## Stage 4: Prove legacy ↔ new equivalence (the migration gate)

This is the move that separates "we rewrote the rules" from "we *proved* the rewrite is equivalent" — the flagship differentiator. Point `aml equivalence` at the run's alerts and your legacy system's export for the same period — a starter export ships with the example:

```bash
aml equivalence .artifacts/lookback/2025-12/run-*/ \
  --legacy examples/community_bank_lookback/legacy-alerts.csv \
  --markdown equivalence-2025-12.md
```

Every legacy↔new pair is classified into one of four buckets — this *is* your migration-defect triage:

| Class | Meaning | What it tells the examiner |
|---|---|---|
| **MATCH** | Both systems alerted the same customer/period/rule | The migration reproduced the control |
| **NEW_ONLY** | New engine alerted; legacy didn't | An *intentional* improvement — or an over-firing defect to tune |
| **LEGACY_ONLY** | Legacy alerted; new engine didn't | A coverage **gap** to investigate before cut-over |
| **DIFF** | Same cell, different severity | A mapping/threshold drift to reconcile |

> Equivalence keys on the **exact** `(customer, window, rule)` cell, so with the starter `legacy-alerts.csv` against a fresh run you'll typically see only **NEW_ONLY** + **LEGACY_ONLY** — that *is* the divergence you triage (each one a **data**, **rule**, or **mapping** defect vs. an intentional change). A guaranteed **MATCH** needs the legacy period to equal a real alert's window exactly; the runbook + `tests/test_lookback_demo.py` show that by anchoring a legacy row to a live alert. Pass `--rule-map rule-map.yaml` when legacy rule ids differ — but it's the **complete** new→legacy map, so include an identity entry (`rule_x: rule_x`) for every comparable rule too, or you'll see same-id rules reported as false divergence. Omit the flag entirely only when all ids already match. `--max-severity-diff N` fails a CI gate when severity drift exceeds a threshold.

---

## Stage 5: Bundle + externally verify the regulator evidence

The final move is turning a run into evidence you can hand to your 2nd line of defense or an external auditor — and proving its integrity against an out-of-band pin so tampering is detectable. This is *evidence as a product*.

### Generate the audit bundle

```bash
# Point --run-dir at the artifacts directory from the Stage 3 run.
aml auditor-pack examples/community_bank_lookback/aml.yaml --run-dir .artifacts/lookback/2025-12/run-*/ --out evidence.zip

# Granular subsets (PR-D4) — same run dir:
aml export-case  examples/community_bank_lookback/aml.yaml .artifacts/lookback/2025-12/run-*/ CASE_ID --out case.zip
aml export-batch examples/community_bank_lookback/aml.yaml .artifacts/lookback/2025-12/run-*/ --cases c1,c2 --out batch.zip
```

Produces an evidence ZIP containing:
- The spec snapshot at execution time
- Every input dataset's SHA-256 hash
- Every rule's output (alerts, cases)
- The append-only decisions ledger with hash-chain verification
- The control matrix mapping rules → regulations

This is what you hand to your 2nd line of defense or an external auditor. Full spec: [`docs/audit-evidence.md`](audit-evidence.md).

### Verify every month's hash chain against an external pin

```bash
aml verify-decisions --run-dir .artifacts/lookback/2025-12/run-*/ \
  --expected-hash "$(jq -r .decisions_hash .artifacts/lookback/2025-12/run-*/manifest.json)"
```

In production you'd pin `--expected-hash` from an out-of-band store (the runbook's §5 covers the WORM threat model). Exit 0 = the decisions ledger recomputes to the trusted head.

### Bundle from the run's frozen spec snapshot

```bash
# Build from the run's frozen spec_snapshot.yaml — not the live spec — so the
# pack's metadata always describes the exact run it bundles, even if the spec
# changed since.
aml auditor-pack .artifacts/lookback/2025-12/run-*/spec_snapshot.yaml \
  --run-dir .artifacts/lookback/2025-12/run-*/ --out evidence-2025-12.zip
```

**Why this arc is the destination:** stages 3–5 exercise the framework's whole thesis in one pass — *equivalence before optimization* (stage 4), *evidence as a product* (stage 5's bundle + verification), *point-in-time correctness* (stage 3's month-end slices), and *DQ/reconciliation/defect* triage (stage 4's four-way classification). The 2-minute warm-up proves the engine runs; this arc proves you can run *your* program audit-defensibly and migrate to it without losing a single control. See [`docs/five-year-lookback.md`](five-year-lookback.md) for the analytics patterns layered on top.

---

## What Next?

| If you want to... | Read |
|---|---|
| Run the full 5-year lookback end-to-end | [`docs/how-to/run-five-year-lookback.md`](how-to/run-five-year-lookback.md) — the 60-month loop, WORM hash log, per-month verification (the runbook behind stages 3–5) |
| Import from a legacy SAS / Actimize / Mantas dump | [`docs/legacy-import.md`](legacy-import.md) — supported shapes, header aliases, manual-conversion workflow |
| Understand the architecture end-to-end | [`docs/architecture.md`](architecture.md) |
| See every dashboard page | [`docs/dashboard-tour.md`](dashboard-tour.md) |
| Map your role to the framework | [`docs/personas.md`](personas.md) |
| Configure for your jurisdiction | [`docs/jurisdictions.md`](jurisdictions.md) |
| Use the REST API | [`docs/api-reference.md`](api-reference.md) |
| Deploy to Kubernetes | [`docs/deployment.md`](deployment.md) |
| Extend with your own metrics | [`docs/metrics-framework.md`](metrics-framework.md) |
| Cross-reference to a regulation | [`docs/regulator-mapping.md`](regulator-mapping.md) |

---

## Common First-Time Issues

**`aml: command not found`** — the install didn't put the entry point on PATH. Re-install with `pip install -e .[dev]` from the repo root, or run `python -m aml_framework.cli` instead.

**`Spec validation failed: ...`** — the validator's error message points at the offending line. The most common issue is a `regulation_refs` entry with `description` missing — both `citation` and `description` are required.

**Dashboard launches but pages show "no data"** — the dashboard runs the engine on startup using the spec passed on the CLI. If you launched it with no spec, it defaults to `community_bank`. Pass an explicit spec to override.

**Tests fail with `ModuleNotFoundError: streamlit`** — the unit-test CI image only installs `.[dev]`. To run the full e2e suite locally, install the dashboard extras: `pip install -e ".[dev,dashboard]" && playwright install chromium`.

For more, see [`CONTRIBUTING.md`](../CONTRIBUTING.md) or open an issue.
