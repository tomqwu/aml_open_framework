# AML Open Framework

Spec-driven, audit-ready Anti-Money Laundering automation for banks and other regulated financial institutions. One versioned `aml.yaml` spec is the single source of truth for data contracts, detection rules, case workflow, and regulator reporting — every artifact (SQL, pipelines, dashboards, audit logs, SAR exports) is generated from it and traceable back to a regulation citation.

![Framework Overview](docs/pitch/03-framework-overview.png)

## Why

Banks lose years of compliance work to drift between **policy** (what the regulator expects), **implementation** (what the pipelines actually do), and **evidence** (what the auditor can prove). The usual result is six-figure fines, remediation programs, and burned-out compliance teams.

This framework attacks the drift directly: one reviewable YAML spec drives every artifact, and every artifact carries a regulation citation back to that spec. Auditors get a reproducible evidence bundle (spec version + input hash + rule output + reviewer decisions, hash-chained and immutable). Regulators get SAR-ready exports on demand.

See [Architecture principle →](docs/architecture.md#principle) and [How each role uses it →](docs/personas.md).

---

## Quickstart

```bash
git clone https://github.com/tomqwu/aml_open_framework.git && cd aml_open_framework
pip install -e ".[dev,dashboard,api]"
aml dashboard examples/community_bank/aml.yaml
# Open http://localhost:8501
```

**5-minute path with no prior context:** [`docs/getting-started.md`](docs/getting-started.md) — install, pick a spec, run, launch dashboard, bring your own data, write your first rule, generate an audit bundle.

---

## Documentation Map

### Start here

| Doc | Use when |
|---|---|
| 📖 [Getting Started](docs/getting-started.md) | First-time install through your first audit bundle (15 min) |
| 🏛 [Architecture](docs/architecture.md) | End-to-end data flow + design rationale |
| 👥 [Personas & Workflows](docs/personas.md) | Map your role (CCO / Manager / Analyst / Auditor / Developer) to the framework |
| 📊 [Dashboard Tour](docs/dashboard-tour.md) | All 22 pages with screenshots + audience filtering |

### Reference

| Doc | Covers |
|---|---|
| 📜 [Spec Reference](docs/spec-reference.md) | Every field in `aml.yaml` — data contracts, rules, workflow, metrics, reporting |
| 🌍 [Multi-Jurisdiction](docs/jurisdictions.md) | US (FinCEN), CA (FINTRAC/OSFI), EU (EBA/AMLD6), UK (FCA/POCA) example specs + how to adapt |
| 🔌 [REST API](docs/api-reference.md) | FastAPI endpoint catalogue with JWT auth + multi-tenant isolation |
| 📈 [Metrics Framework](docs/metrics-framework.md) | Metric types, RAG thresholds, audience routing, report rendering |
| 🔍 [Audit & Evidence](docs/audit-evidence.md) | Evidence-bundle specification + SHA-256 hash-chain verification |
| ⚖️ [Regulator Mapping](docs/regulator-mapping.md) | FinCEN / FINTRAC / OFAC / AMLD6 coverage matrix |

### Operations

| Doc | Covers |
|---|---|
| 🚀 [Deployment](docs/deployment.md) | Docker Compose + Helm charts for Kubernetes |
| 📚 [Case Studies](docs/case-studies/) | Real enforcement walkthroughs (TD 2024 etc.) |
| 🤝 [Contributing](CONTRIBUTING.md) | Setup, PR process, project rules |
| 📋 [Changelog](CHANGELOG.md) | Round-by-round PR-level history |
| 📊 [Progress Snapshot](docs/progress.md) | Fact-based audit of what's shipped (modules, tests, regulatory coverage) |
| 🔍 [Competitive Positioning Research](docs/research/2026-04-competitive-positioning.md) | Where the framework slots vs. Actimize / Hawk / Marble / Jube + ranked next features |

---

## Key CLI Commands

```bash
aml validate spec.yaml                              # JSON Schema + cross-reference checks
aml run spec.yaml [--data-source csv --data-dir ./] # execute rules
aml dashboard spec.yaml                              # launch web UI
aml api --port 8000                                  # launch REST API
aml export spec.yaml --out evidence.zip              # regulator-ready audit bundle
aml export-goaml spec.yaml --out goaml.xml           # goAML 5.0.2 STR/SAR XML
aml mrm-bundle spec.yaml --out-dir mrm/              # SR 26-2 model-risk dossiers
aml replay spec.yaml run-dir/                        # verify deterministic re-run
```

Full catalogue: [`docs/getting-started.md#cli-commands`](docs/getting-started.md). Data sources: `synthetic` (default), `csv`, `parquet`, `duckdb`, `iso20022`, `s3`, `gcs`, `snowflake`, `bigquery`.

---

## Repository Layout

```
schema/aml-spec.schema.json     JSON Schema for aml.yaml (the contract)
examples/                       5 example specs across 4 jurisdictions
src/aml_framework/
  spec/                         Parse + validate the spec (JSON Schema + Pydantic)
  generators/                   Emit SQL, DAG stubs, control matrix, STR narratives
  engine/                       Execute rules on DuckDB, audit ledger
  metrics/                      Metric evaluation + report rendering
  cases/                        Investigation aggregator, SLA timer, STR bundling
  data/                         Synthetic generator + ISO 20022 ingestion
  dashboard/                    Streamlit web dashboard (22 pages)
  models/                       ML scoring callables for python_ref rules
  api/                          FastAPI REST layer with JWT auth
  vasp/                         Public-data VASP attribution (Chainalysis alternative)
  cli.py                        `aml` command-line entry point
data/input/                     Sample CSV data (438 txns, 25 customers)
deploy/helm/                    Helm chart for Kubernetes
docs/                           Architecture, persona, spec, API, deployment guides
tests/                          886+ tests across unit, API, e2e
```

---

## Testing

```bash
pytest tests/ --ignore=tests/test_e2e_dashboard.py -q   # unit + API (~40s)
pytest tests/test_e2e_dashboard.py                       # Playwright e2e (~2min)
pytest tests/                                            # everything
```

CI runs 5 jobs on every PR: `lint`, `unit-tests`, `api-tests`, `e2e-dashboard`, `docker-build`. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the pre-commit checklist.

---

## Status

Reference implementation — not a certified compliance product. Use it to prototype controls, drive internal conversations, or anchor a spec-first migration of an existing AML program. Any production deployment needs institution-specific tuning, model validation, and sign-off from your second line of defense.

## License

Apache-2.0.
