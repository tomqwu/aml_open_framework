# Personas & Responsibilities

The framework earns its keep if 13 distinct roles — from board to L1 analyst — can work from the same spec. This doc maps each persona to **what they read**, **what they write**, and the **dashboard pages they own**. Page lists below are the source-of-truth `AUDIENCE_PAGES` table in `src/aml_framework/dashboard/audience.py`; the sidebar **Audience** selector filters to exactly these pages per role (cap: 9 per persona, per `MAX_PAGES_PER_PERSONA`).

Universal pages — Today, Executive Dashboard, North-Star Coverage, FP Analysis, Decision Trail, Experiment Tracking, Equivalence, Threshold Sensitivity, Anomaly Discovery, Drift Monitor, Rule Lifecycle — are visible to every persona regardless of the filter, so the page lists below only enumerate role-specific surfaces.

---

## Executive lane

### `svp` — Senior VP of Risk

Owns the risk function. Cares about board reporting and the regulator relationship.

- **Reads**: Executive Dashboard → Program Maturity → Framework Alignment → Audit & Evidence → Transformation Roadmap
- **Writes**: board narratives, regulator briefings; approves transformation roadmap
- **Does not touch**: rule logic, SQL, generated artifacts

### `cto` — Chief Technology Officer

Owns the platform. Cares about deployability, deterministic replay, vendor risk.

- **Reads**: Executive Dashboard → Program Maturity → Framework Alignment → Audit & Evidence → Model Performance → Data Integration → Run History → Transformation Roadmap
- **Writes**: platform decisions (Helm/Terraform/Postgres), capacity envelope, BCP/DR posture
- **Key property**: any production run is byte-identical replayable from spec hash + input snapshot

### `cco` — Chief Compliance Officer

Owns the AML program. Cares about exam readiness and "can we prove what we did?"

- **Reads**: Executive Dashboard → Program Maturity → Framework Alignment → Risk Assessment → Audit & Evidence → Investigations → Regulator Pulse → Metrics Taxonomy → AI Assistant
- **Writes**: risk appetite (thresholds, windows) via PR review; regulation citations when scope changes; retention and reporting-cycle overrides
- **Does not touch**: SQL, DAGs, anything generated

### `vp` — VP / MLRO

Second line of defence. Reads the spec; challenges the rules; signs the STRs.

- **Reads**: Executive Dashboard → Rule Performance → Framework Alignment → Audit & Evidence → Sanctions Screening → Comparative Analytics → Regulator Pulse → Metrics Taxonomy → AI Assistant
- **Writes**: rule challenges (PR review), STR/SAR sign-offs in the audit ledger, AI provenance approvals
- **Key property**: 2LoD review is captured per case; cannot be silently overwritten

---

## Operations lane

### `director` — Director of Financial Crime

Runs the operation. Cares about backlog, SLA breaches, queue health.

- **Reads**: Executive Dashboard → Alert Queue → Investigations → Framework Alignment → Risk Assessment → Data Quality → Audit & Evidence → Comparative Analytics → Metrics Taxonomy
- **Writes**: SLA tuning, queue routing, analyst capacity decisions

### `manager` — AML Operations Manager

Triage to escalation. Cares about queue throughput and analyst load balance.

- **Reads**: Alert Queue → Investigations → My Queue → Analyst Review Queue → Risk Assessment → Live Monitor → Tuning Lab → Typology Catalogue → Metrics Taxonomy
- **Writes**: tuning proposals (threshold tweaks backed by backtest), reassignments, escalation criteria
- **Daily arc**: triage → investigate → tune

### `analyst` — L1 / L2 Analyst

Works the alerts. Cares about evidence being pre-attached so they can write the narrative.

- **Reads**: Alert Queue → Case Investigation → Lineage Explorer → Investigations → Network Explorer → Sanctions Screening → Customer 360 → My Queue → Analyst Review Queue
- **Writes**: case decisions (escalate / close / request-info) — each with reviewer id, timestamp, free-text reason; STR/SAR draft narratives
- **Key property**: decisions are written to the audit ledger and cannot be silently overwritten

---

## Engineering lane

### `developer` — Engineer / Detection Developer

Authors the detectors. Cares about the spec, tests, and CI feedback loop.

- **Reads**: Spec Editor → Rule Performance → Rule Tuning → Tuning Lab → Model Performance → Data Integration → Data Quality → Audit & Evidence → AI Assistant
- **Writes**: rules, `data_contracts`, `python_ref` scorers, tests; never overrides without a spec PR
- **Constraint**: framework refuses to run if the warehouse schema drifts from the contract

### `data_engineer` — Data Engineer / Head of Data

Owns the pipes. Cares about contracts, freshness, ISO 20022 ingestion, lineage walk-back.

- **Reads**: Data Integration → Data Quality → Customer 360 → Information Sharing → Spec Editor → Run History → Audit & Evidence → AI Assistant
- **Writes**: source-to-contract mappings, ingestion DAGs (from generator stubs), freshness monitors, ISO 20022 message-type adapters
- **Lands first on**: Data Integration — the 30-second answer to *"what data is flowing through this AML program?"*

### `pm` — Program / Product Manager

Plans the roadmap. Cares about coverage gaps and where to invest next.

- **Reads**: Rule Performance → Program Maturity → Transformation Roadmap → Model Performance → Risk Assessment → Case Investigation → Tuning Lab → Typology Catalogue → Metrics Taxonomy
- **Writes**: roadmap, gap analyses, typology investment proposals

---

## Audit + niche lanes

### `auditor` — Auditor (Internal / External)

Replays runs and verifies the chain. Cares about evidence completeness and reproducibility.

- **Reads**: Audit & Evidence → Lineage Explorer → Investigations → Case Investigation → Data Quality → Framework Alignment → Regulator Pulse → Metrics Taxonomy → Information Sharing
- **Writes**: findings as GitHub issues linked to spec clauses or evidence bundles; tracked in `open_findings`
- **Key property**: any historical run is byte-identically replayable from `spec_version` SHA + input snapshot. A mismatched `output_hash` is a reportable control failure.

### `business` — Business Stakeholder

Outside FCC. Cares about the headline picture without operational detail.

- **Reads**: Executive Dashboard → Risk Assessment → Framework Alignment → Audit & Evidence
- **Writes**: nothing in the spec; consumes the regulator-pack summary

### `fintech_mlro` — FinTech / EMI / VASP MLRO

1-MLRO program. Lives with sponsor-bank cure notices and Series-B AML diligence questionnaires.

- **Reads**: FinTech Cockpit → Alert Queue → Audit & Evidence → Investigations → Tuning Lab → Regulator Pulse → Spec Editor → Metrics Taxonomy → AI Assistant
- **Writes**: everything — 1-MLRO is also the spec author, the tuner, the queue triage. Spec → reviewer → STR loop runs on one person's clock.
- **Distinctive surface**: FinTech Cockpit pairs a sponsor-bank cure-notice timer with the 8 AML realities + evidence pack the diligence questionnaire asks for.

---

## Collaboration loop

```
        ┌──────── CCO / SVP / Compliance ────────┐
        │  proposes threshold / rule PR          │
        ▼                                         │
  aml.yaml (main) ─── PR review ──── 2LoD approves
        │
   ┌────┴────────────┐
   │ generators run  │ → DAG stubs, SQL, docs, control matrix, MRM pack
   ▼                 ▼
Data Engineer    Developer / PM
  wires up        authors rules + tests
  pipelines       proposes tuning
        │
        ▼
  Runtime: alerts → analyst → manager → 2LoD → STR/SAR
        │
        ▼
  Evidence bundle ──► Auditor (internal → regulator)
```

The important property: **no role has an unreviewed write path to production detection logic.** Every change is a diff on `aml.yaml`. That is the control.

For a deeper read on the daily painpoints driving these roles' workflows, see *[Process Pain whitepaper](research/2026-04-aml-process-pain.md)*.
