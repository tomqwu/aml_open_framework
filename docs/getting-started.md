# Getting Started

A 15-minute path from `git clone` to a running AML program with alerts you can investigate. If you've used Streamlit before, skip ahead to [Run Your First Spec](#run-your-first-spec); if not, the install step is one command.

## TL;DR

```bash
git clone https://github.com/tomqwu/aml_open_framework.git && cd aml_open_framework
pip install -e ".[dev,dashboard,api]"
aml dashboard examples/community_bank/aml.yaml
# Open http://localhost:8501
```

The dashboard runs the engine on synthetic data with planted positives, so you'll see real alerts immediately — no data wrangling required to start exploring.

---

## 1. Install (2 min)

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

---

## 2. Pick a Spec (1 min)

Ten example specs ship in `examples/`, spanning 5 jurisdictions and several typology focuses:

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

For your first run pick **`community_bank`** — it's the smallest, fastest, and best-documented.

See [`docs/jurisdictions.md`](jurisdictions.md) for what each spec covers and how to adapt it to your institution.

---

## 3. Run Your First Spec (2 min)

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

---

## 4. Launch the Dashboard (1 min)

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

---

## 5. Bring Your Own Data (5 min)

Two options to feed real data into the framework: drop CSVs in `data/input/`, or point the CLI at any of 9 supported source types (`synthetic`, `csv`, `parquet`, `duckdb`, `iso20022`, `s3`, `gcs`, `snowflake`, `bigquery`).

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
aml run spec.yaml --data-source parquet  --data-dir s3://bucket/path/
aml run spec.yaml --data-source duckdb   --data-dir warehouse.duckdb
aml run spec.yaml --data-source iso20022 --data-dir mx_messages/
aml run spec.yaml --data-source snowflake # uses SNOWFLAKE_* env vars
aml run spec.yaml --data-source bigquery  # uses GOOGLE_APPLICATION_CREDENTIALS
```

ISO 20022 ingestion handles pacs.008 / pacs.009 (FI-to-FI), pain.001 (corporate batch), and pacs.004 (returns) natively — see [Round-5 changelog entries](../CHANGELOG.md) for the full surface.

> **Watch the data layer in the dashboard**: the [Data Integration page](dashboard-tour.md#data-integration) renders a 30-second view of every wired source, contract roll-up, and ISO 20022 message-type counts — plus a DATA-N → artifact map linking each whitepaper data pain to its concrete framework artifact.

---

## 6. Author Your First Custom Rule (5 min)

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

Four rule types are supported: `aggregation_window`, `custom_sql`, `list_match`, `python_ref`. Full reference: [`docs/spec-reference.md`](spec-reference.md).

After editing, validate before running:
```bash
aml validate examples/community_bank/aml.yaml
```

The validator catches typos, broken cross-references, and structural errors before the engine ever touches data.

---

## 6.1. Promote Across Environments (PR-D3)

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

---

## 6.2. Advanced spec features

Five spec fields shipped in Rounds 26–28 that operators routinely miss because they're optional and default to a sensible no-op. Each one closes a specific compliance-pillar gap; reach for them when your program matures past the first-run shape.

### `program.sla` — operational SLA monitor (PR-LF1)

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

### `quality_checks[*].severity` — DQ triage tier (PR-B5)

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

### `rule.risk_tier` — risk-based-controls axis (PR-RISK-1)

A first-class `low` / `medium` / `high` tier on each rule, independent of `severity` (alert urgency) and `model_tier` (model-risk validation cadence). Closes the Pillar-5 "risk-based controls" gap on the North-Star Coverage page — until this shipped, the only risk signal was `severity`, which is an alert-priority field. Optional (defaults to `None`). PR-RISK-1 is additive-only: the field lands on the loaded spec, flows into the rule-version hash, and surfaces in the spec-diff path. Engine-time wire-in (alert priority + queue routing) is a follow-up PR.

```yaml
rules:
  - id: structuring_cash_deposits
    severity: high           # alert urgency
    risk_tier: high          # risk-based-controls posture
    # ... logic ...
```

Spec model: `src/aml_framework/spec/models.py::RiskTier`. Test: [`tests/test_spec_risk_tier.py`](../tests/test_spec_risk_tier.py).

### `rule.business_intent` + `out_of_scope` — examiner-readable rationale (PR-A2)

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

---

## 7. Generate the Audit Bundle (1 min)

```bash
# Point --run-dir at the artifacts directory printed by `aml run` in step 3
# (e.g. /tmp/aml_run_<id>/) — replace RUN_DIR below.
aml auditor-pack examples/community_bank/aml.yaml --run-dir RUN_DIR --out evidence.zip

# Granular subsets (PR-D4) — same RUN_DIR:
aml export-case  examples/community_bank/aml.yaml RUN_DIR CASE_ID --out case.zip
aml export-batch examples/community_bank/aml.yaml RUN_DIR --cases c1,c2 --out batch.zip
```

Produces an evidence ZIP containing:
- The spec snapshot at execution time
- Every input dataset's SHA-256 hash
- Every rule's output (alerts, cases)
- The append-only decisions ledger with hash-chain verification
- The control matrix mapping rules → regulations

This is what you hand to your 2nd line of defense or an external auditor. Full spec: [`docs/audit-evidence.md`](audit-evidence.md).

---

## What Next?

| If you want to... | Read |
|---|---|
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
