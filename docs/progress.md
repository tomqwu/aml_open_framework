# Project Progress

Snapshot of where the AML Open Framework is as of 2026-04-27. This document is a fact-based audit of what's shipped, not a roadmap or marketing piece. For "what's next?" see [`getting-started.md`](getting-started.md) and the [Changelog](../CHANGELOG.md).

---

## At a Glance

| Metric | Value |
|---|---|
| Source code | 19,642 lines across 18 top-level modules |
| Tests | 991 collected, 953 passing on the unit-test image (excluding e2e) |
| Test files | 34 |
| Documentation | 1,852 lines across 10 docs + 1,476-line CHANGELOG + 123-line README |
| Example specs | 7 (US, CA, EU, UK, crypto VASP, cyber-fraud, plus a TD-case-study variant) |
| Unique regulation citations | 61+ across all bundled specs and library snippets |
| Dashboard pages | 24 |
| Merged PRs in latest sprint (2026-04-27) | 17 (#46–#72) |

---

## Module Surface

```
src/aml_framework/
├── api/              FastAPI REST layer (JWT auth, multi-tenant DB, rate limiting)
├── cases/            Investigation aggregator, SLA timer, STR bundling (Round 6)
├── dashboard/        24-page Streamlit web app (mobile-responsive, multi-tenant)
├── data/             Synthetic generator + 8 source loaders + ISO 20022 parser
│   ├── iso20022/     pacs.008, pacs.009, pain.001, pacs.004 ingestion (Round 5)
│   └── lists/        Sanctions, adverse media, sanctioned wallets, purpose codes
├── engine/           Rule executor on DuckDB, audit ledger with SHA-256 hash chain
├── generators/       SQL, DAG stubs, control matrix, STR narratives, board PDF,
│                     goAML XML, AMLA STR, MRM bundle, effectiveness pack
├── integrations/     Jira, Slack/Teams, SIEM/CEF connectors
├── metrics/          Metric evaluation engine + RAG bands + audience routing
├── models/           ML scoring callables for python_ref rules + travel-rule validator
├── narratives/       LLM-backed narrative drafting (Ollama, OpenAI backends)
├── pkyc/             Perpetual KYC trigger engine
├── sanctions/        OFAC SDN refresh + fuzzy match
├── spec/             JSON Schema + Pydantic validation + reusable rule library
└── vasp/             Public-data VASP attribution (Chainalysis alternative)
```

---

## Round-by-Round Delivery

### Round 5 — Payment Rails Ingestion (5 PRs, ~16 days)

Goal: ingest the messages banks actually move money with, after SWIFT's MX-only cutover (2025-11-22).

| PR | Feature | Driving signal |
|---|---|---|
| #56 | ISO 20022 `pacs.008` + `pacs.009` ingestion adapter | SWIFT MX-only cutover |
| #57 | FATF R.16 Travel Rule field validator (`python_ref` callable) | FATF Feb 2026 plenary deficiency call-out |
| #58 | ISO 20022 purpose-code typology library (4 reusable snippets) | ExternalPurpose1Code now mandatory |
| #59 | `pain.001` corporate-batch ingestion | Wolfsberg Feb 2026 correspondent-banking guidance |
| #60 | `pacs.004` payment-return + return-reason mining library (3 snippets) | UK PSR APP-fraud reimbursement (Apr 2026 full effect) |

**Result**: framework can natively consume every major ISO 20022 message type. Travel-rule completeness is automated. Two reusable spec-library files ship 7 typology rule snippets keyed to FATF / FinCEN / UK PSR / Wolfsberg guidance.

### Round 6 — Case Management as First-Class Surface (5 PRs, ~17 days)

Goal: make investigation (not alert) the unit of analyst work, per FinCEN's 2024 effectiveness rule.

| PR | Feature | Driving signal |
|---|---|---|
| #61 | Investigation aggregator (`cases/aggregator.py`) | FinCEN NPRM measures effectiveness per investigation |
| #62 | Multi-tenant dashboard surfacing (sidebar selector) | API had it; dashboard didn't |
| #63 | SLA timer + escalation engine (`cases/sla.py`) | FCA Mar 2026 Dear CEO letter on SAR backlogs |
| #64 | Case-to-STR auto-bundling (`cases/str_bundle.py`) | Wolfsberg Feb 2026 "submission-ready packages" |
| #65 | Investigations dashboard page #24 | Operator surface for the above |

**Result**: cases now aggregate into investigations with deterministic IDs. Live SLA tracking surfaces backlog state per-queue. Self-contained STR ZIPs bundle narrative + goAML XML + Mermaid diagrams + manifest hash. New dashboard page consolidates the workflow.

### Workflow Polish (4 PRs)

| PR | Feature |
|---|---|
| #67 | README refactor 582 → 123 lines + Getting Started guide + Dashboard Tour + Jurisdictions doc |
| #69 | `aml --help` typer/click compatibility fix; crypto_vasp doc gap |
| #70 | Mobile-responsive dashboard overlay (closes #66) |
| #71 | Workflow audit: executive font scale + 4 pages made interactive + missing pages registered |
| #72 | Synthetic data enriched with ISO 20022 fields + planted INVS positive |

**Result**: new-user onboarding path is 15 minutes. Mobile viewports work. Executive personas (SVP/CTO/CCO/VP/Director) get auto-scaled fonts. Default `aml run --seed 42` demo now exercises all Round 5/6 features.

---

## What the Framework Does Today

### For the policy author (CCO / MLRO)
- Authors a versioned `aml.yaml` — every rule cites a specific regulation
- Two-layer validation (JSON Schema + Pydantic cross-references)
- Reusable rule snippet library (`spec/library/`) for ISO 20022 typologies
- Reviewable diff between spec versions (`aml diff`)

### For the data engineer
- Generates SQL, DAG stubs, and control matrix from spec
- 8 supported data sources: synthetic, CSV, Parquet, DuckDB, S3, GCS, Snowflake, BigQuery
- Native ISO 20022 ingestion (pacs.008/009/pain.001/pacs.004)
- Schema validation at load time

### For the analyst (L1/L2)
- 24-page web dashboard with persona-filtered navigation
- Investigation-level review (not just alerts)
- Per-case live SLA + escalation recommendations
- Network-pattern explainability with Mermaid diagrams
- One-click STR submission bundle

### For the auditor / regulator
- Append-only decisions ledger with SHA-256 hash chain
- Reproducible runs (same spec + data + seed → identical hashes)
- Regulator-ready evidence ZIP (`aml export`)
- goAML 5.0.2 XML and AMLA RTS JSON exports

### For the ML modeler
- `python_ref` rule type with security gate (callables restricted to `aml_framework.models.*`)
- MRM bundle generator (SR 26-2 / OCC Bulletin 2026-13 dossiers)
- Tuning Lab — threshold sweep with shadow diff + precision/recall
- Effectiveness Evidence Pack (FinCEN April 2026 NPRM artifact)

### For the operations team
- Multi-tenant dashboard (single process, multiple programs)
- Mobile-responsive layout
- REST API with JWT/OIDC auth, rate limiting, run persistence
- Integrations: Jira, Slack/Teams, SIEM/CEF
- Docker + Helm chart for K8s deployment

---

## Shipped Capabilities by Regulatory Regime

| Regulator / regime | What's covered |
|---|---|
| **FinCEN BSA** (US) | 6-pillar mapping including the April 2026 proposed 6th pillar; SAR/CTR exports; investigation-aggregation per the 2024 effectiveness rule |
| **FinCEN April 2026 NPRM** | Effectiveness Evidence Pack generator (`aml effectiveness-pack`) |
| **OFAC** | Fuzzy + exact name screening; SDN list refresh from upstream XML |
| **FINTRAC + OSFI** (CA) | PCMLTFA section-level citations; STR/LCTR/EFTR; OSFI B-8 alignment; TD case-study patterns spec |
| **AMLD6 + EBA** (EU) | Article-level citations; AMLA RTS JSON draft (effective July 2026); 5-year retention |
| **FCA + POCA + PSR** (UK) | UK SAR via NCA; PSR APP-fraud reimbursement signals (return-reason mining); FCA Mar 2026 SAR-backlog response |
| **FATF** | R.16 Travel Rule validator; R.15-16 crypto adaptations (`crypto_vasp` spec); Feb 2026 Cyber-Enabled Fraud typologies |
| **Wolfsberg** | Feb 2026 correspondent-banking gaps (pain.001 ingestion, submission-ready STR packages) |
| **SR 26-2 / OCC 2026-13** | MRM bundle generator for python_ref models |

---

## Test Coverage

```
test_engine.py                  108  Engine, audit ledger, hash chain, all 5 rule types
test_iso20022.py                 34  pacs.008/009 parsing
test_pain001.py                  29  Corporate batch ingestion
test_pacs004.py                  36  Payment-return ingestion + library
test_iso20022_purpose_codes.py   16  Purpose-code library + planted positive
test_travel_rule.py              29  FATF R.16 validator
test_cases_aggregator.py         34  Investigation grouping (3 strategies)
test_cases_sla.py                25  SLA classification + escalation + backlog
test_cases_str_bundle.py         23  Per-investigation ZIP determinism
test_dashboard_workflows.py      15  Audience map + executive scale + page registration
test_dashboard_tenants.py        26  Multi-tenant config validation
test_dashboard_mobile_css.py     10  Mobile responsive overlay
test_e2e_dashboard.py            30  Playwright — every page renders
test_e2e_dashboard_mobile.py      9  Mobile viewports (375/414/768)
test_dashboard_investigations    9   Investigations page wiring
test_docs_links.py               19  Link rot prevention
test_api.py                      54  FastAPI auth, runs, validation, rate limiting
test_data_sources.py             37  All 8 source types
test_generators.py               26  All export formats
test_metrics.py                  30  Metric evaluation + RAG + audience
test_integrations.py             24  Jira, Slack/Teams, SIEM/CEF
test_spec.py                     28  Spec validation + EU/UK runs + AMLD6 alignment
test_performance.py               2  10k+ row engine throughput
… plus 19 other test files       … 
```

Total: 991 tests collected, 34 test files.

---

## What's NOT in the Framework (by design)

These are documented "won't ship" decisions, not gaps:

- **Generative AI rule-authoring** (English → YAML rule). Would destroy the "human-readable spec written by a human" moat that's the framework's whole differentiation.
- **Native graph DB backend** (Neo4j / TigerGraph). DuckDB-with-graph-views is fast enough for FI-scale datasets, and "one binary, one DuckDB file" deployability is the moat.
- **Alert-scoring ML model in-tree**. Would erode the deterministic re-run guarantee that the MRM bundle (PR #53) builds on. We document the `python_ref` seam; institutions ship their own model.

See `memory/project_round5to9_plan.md` (private) for the full "three new traps" rationale.

---

## Open Items

- Issue #66 — closed (PR #70 mobile-responsive)
- Issue #68 — effectively closed (PR #69 docs sweep)
- No other tracked issues open as of this snapshot

---

## Documentation Index

Every doc has a single-line "use when" hook in [`README.md`](../README.md). The full set:

- `README.md` — hub-style entry point with documentation map
- `docs/getting-started.md` — 15-min onboarding path
- `docs/architecture.md` — reference design
- `docs/dashboard-tour.md` — all 24 pages organized by workflow
- `docs/jurisdictions.md` — US / CA / EU / UK / crypto / cyber-fraud specs
- `docs/personas.md` — role-based workflows
- `docs/spec-reference.md` — field-by-field `aml.yaml` guide
- `docs/api-reference.md` — REST endpoint catalogue
- `docs/audit-evidence.md` — evidence bundle specification
- `docs/metrics-framework.md` — metric types, RAG, audience routing
- `docs/regulator-mapping.md` — coverage matrix
- `docs/deployment.md` — Docker + Helm
- `docs/case-studies/` — TD 2024 enforcement walkthrough
- `docs/progress.md` — this file
