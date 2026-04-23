# AML Open Framework

Spec-driven, audit-ready Anti-Money Laundering automation for banks and other
regulated financial institutions. One versioned `aml.yaml` spec is the single
source of truth for data contracts, detection rules, case workflow, and
regulator reporting — every artifact (SQL, pipelines, dashboards, audit logs,
SAR exports) is generated from it and traceable back to a regulation citation.

## Why

Banks lose years of compliance work to drift between **policy** (what the
regulator expects), **implementation** (what the pipelines actually do), and
**evidence** (what the auditor can prove). The usual result is six-figure
fines, remediation programs, and burned-out compliance teams.

This framework attacks the drift directly:

- **Business owner / Chief Compliance Officer** writes policy in a reviewable
  YAML spec, with every rule annotated to a regulation clause.
- **Data engineer** gets generated DAGs, SQL, and data-quality tests from the
  same spec — no hand-translation from PDF policy docs.
- **Data team** sees lineage and freshness SLAs enforced as code.
- **Auditor** gets a reproducible evidence bundle: spec version + input hash +
  rule output + reviewer decisions, signed and immutable.
- **Regulator** gets a control narrative and SAR-ready exports on demand.

See [`docs/architecture.md`](docs/architecture.md) for the reference design and
[`docs/personas.md`](docs/personas.md) for how each role interacts with the
framework.

## Quickstart

```bash
pip install -e ".[dev]"

# 1. Validate the example spec against the JSON schema.
aml validate examples/community_bank/aml.yaml

# 2. Generate SQL rules, DAG stub, and persona docs into .artifacts/
aml generate examples/community_bank/aml.yaml

# 3. Run end-to-end: synthesize transactions, execute rules, compute
#    metrics, render role-specific reports, and write the audit bundle.
aml run examples/community_bank/aml.yaml --seed 42

# 4. Show or print a role-specific report (SVP / VP / Director / Manager /
#    PM / Developer / Business).
aml report examples/community_bank/aml.yaml --audience svp
aml report examples/community_bank/aml.yaml --report svp_exec_brief --stdout

# 5. Produce a regulator-ready evidence bundle (zipped, signed manifest).
aml export examples/community_bank/aml.yaml --out .artifacts/evidence.zip
```

## Interactive Dashboard

The framework includes a Streamlit web dashboard for interactive demos and
stakeholder presentations. It runs the full engine on startup and presents
results across 9 purpose-built pages.

```bash
pip install -e ".[dev,dashboard]"
aml dashboard examples/community_bank/aml.yaml
# Opens at http://localhost:8501
```

### Executive Dashboard

Program-level KPIs, alert-by-rule breakdown with severity coloring, RAG status
grid for all metrics, and a program health radar chart. Audience filtering in
the sidebar lets you switch between SVP, VP, Director, Manager, PM, Developer,
and Business views.

![Executive Dashboard](docs/screenshots/01_executive_dashboard.png)

### Program Maturity Assessment

12-dimension maturity spider chart based on Big-4 consulting firm methodologies
(Deloitte, EY, PwC, KPMG). Current scores are derived from spec coverage
(number of active rules, workflow queues, data quality checks). Target scores
show where the program needs to be. Expandable dimension cards provide
assessment rationale and recommendations.

![Program Maturity](docs/screenshots/02_program_maturity.png)

### Alert Queue

Filterable, sortable alert triage view for L1 analysts. Filter by rule or
severity, view aggregated amounts and time windows, and drill into individual
alerts. Charts show alert volume by rule and severity distribution.

![Alert Queue](docs/screenshots/03_alert_queue.png)

### Case Investigation

Full investigation workspace with entity profile (customer details, risk
rating, country), alert details (regulation citations, evidence requested),
transaction timeline with alert window highlighting, Sankey flow diagram
showing channel-level fund movement, and evidence panel.

![Case Investigation](docs/screenshots/04_case_investigation.png)

### Rule Performance

Per-rule analytics table showing alert counts, detection rates, and logic
types. Severity distribution charts, detection coverage by logic type, and a
rule-to-regulation cross-reference matrix. Typology tag coverage shows which
declared typologies have active detection.

![Rule Performance](docs/screenshots/05_rule_performance.png)

### Risk Assessment

Customer risk distribution (low/medium/high), geographic exposure by country,
transaction volume heatmap (risk rating x channel), and a table of all alerted
customers with their profiles.

![Risk Assessment](docs/screenshots/06_risk_assessment.png)

### Audit & Evidence

Full run manifest with JSON viewer, SHA-256 hash verification for every rule
output, append-only decision log, evidence bundle file tree with byte sizes,
and the spec snapshot captured at execution time. This is the auditor and
regulator view.

![Audit & Evidence](docs/screenshots/07_audit_evidence.png)

### Framework Alignment

Three-tab mapping of spec primitives to international regulatory standards:
- **FATF 40 Recommendations** — 10 key recommendations mapped with coverage status
- **FinCEN BSA 6 Pillars** — including the April 2026 proposed 6th pillar (formalized risk assessment)
- **Wolfsberg Principles** — 8 principles with gap identification

Each mapping shows fully mapped, partially mapped, and gap status with explanatory notes.

![Framework Alignment](docs/screenshots/08_framework_alignment.png)

### Transformation Roadmap

4-phase Gantt chart following Big-4 AML program transformation patterns:
Assessment (Weeks 1-4), Foundation (Weeks 5-16), Advanced Analytics
(Weeks 17-30), and Optimization (Weeks 31-52). Each phase includes milestones,
deliverables, and status tracking.

![Transformation Roadmap](docs/screenshots/09_transformation_roadmap.png)

## Detection Rules

The example spec includes 6 detection rules covering core AML typologies:

| Rule | Typology | Severity | Logic |
|------|----------|----------|-------|
| `structuring_cash_deposits` | Cash structuring below $10k threshold | High | Aggregation window |
| `rapid_movement_cash_to_wire` | Cash-in then wire-out pass-through | Medium | Aggregation window |
| `high_risk_jurisdiction` | Significant activity from FATF high-risk countries | High | Custom SQL (JOIN) |
| `large_cash_ctr` | Daily cash exceeding $10,000 CTR threshold | Medium | Aggregation window |
| `unusual_volume_spike` | Recent volume >5x historical baseline | Medium | Custom SQL |
| `dormant_account_activity` | Dormant account reactivation with large transaction | High | Custom SQL |

Each rule cites specific regulation references (31 CFR, FinCEN Advisories, FATF
Recommendations) and specifies evidence requirements and escalation queues.

## Metrics & Reporting

13 metrics across 5 categories, each with RAG thresholds and audience routing:

| Category | Metrics |
|----------|---------|
| **Operational** | Total alerts, cases opened, cases routed to L1, transaction volume, SLA compliance rate, avg resolution time |
| **Effectiveness** | Typology coverage, false positive rate |
| **Risk** | High-severity alert ratio, distinct customers alerted |
| **Regulatory** | Alert-to-SAR conversion rate |
| **Delivery** | Active high-severity rules, total active rules |

Reports are rendered per audience (SVP, VP, Director, Manager, PM, Developer,
Business) with RAG indicators and owner accountability.

## Collaboration across roles

The same `aml.yaml` drives:

| Audience     | Artifact                                          |
|--------------|---------------------------------------------------|
| SVP          | `reports/svp_exec_brief.md` (quarterly, RAG)      |
| VP           | `reports/vp_compliance_review.md` (monthly)       |
| Director     | `reports/director_program_health.md` (monthly)    |
| Manager      | `reports/manager_weekly.md` (weekly, queue load)  |
| PM           | `reports/pm_delivery.md` (weekly, catalogue)      |
| Developer    | `reports/developer_runtime.md` (daily runtime)    |
| Business     | `reports/business_owner_daily.md` (customer pulse)|
| Auditor      | `control_matrix.md` + the evidence bundle         |

Every metric in every report is defined once in the spec, with an owner and
RAG thresholds. See [`docs/metrics-framework.md`](docs/metrics-framework.md).

## Repository layout

```
schema/aml-spec.schema.json     JSON Schema for aml.yaml (the contract)
examples/community_bank/        Example spec for a US community bank (6 rules, 13 metrics)
src/aml_framework/
  spec/                         Parse + validate the spec (JSON Schema + Pydantic)
  generators/                   Emit SQL, DAG stubs, control matrix
  engine/                       Execute rules on DuckDB, audit ledger
  metrics/                      Metric evaluation engine + report rendering
  cases/                        Case files, reviewer workflow artifacts
  data/                         Synthetic data generator with planted positives
  dashboard/                    Streamlit web dashboard (9 pages)
  cli.py                        `aml` command-line entry point
docs/
  architecture.md               Reference architecture
  personas.md                   Who does what
  regulator-mapping.md          FinCEN / FINTRAC / OFAC / AMLD6 coverage
  spec-reference.md             Field-by-field spec guide
  metrics-framework.md          Metric types, RAG thresholds, audience model
  audit-evidence.md             Evidence bundle specification
  screenshots/                  Dashboard screenshots
```

## Status

Reference implementation — not a certified compliance product. Use it to
prototype controls, drive internal conversations, or anchor a spec-first
migration of an existing AML program. Any production deployment needs
institution-specific tuning, model validation, and sign-off from your 2nd line.

## License

Apache-2.0.
