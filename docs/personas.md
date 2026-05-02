# Personas & Responsibilities

The framework only earns its keep if five roles with different vocabularies can
all work from the same spec. This doc describes what each role reads, writes,
and reviews.

## 1. Business Owner / Chief Compliance Officer (CCO)

**Reads**

- `aml.yaml` top-level (`program`, list of rule names and severities).
- Generated `control_matrix.md` — every rule mapped to a regulation clause.
- KPI dashboard: alert volume, false-positive rate, SLA breaches, SAR pipeline.

**Writes / approves**

- Risk appetite (thresholds, windows) via PR review.
- Regulation citations when scope changes (new jurisdiction, new product).
- Retention and reporting-cycle overrides.

**Does not touch**

- SQL, DAGs, anything generated. Generated artifacts are disposable.

## 2. Data Engineer

**Reads**

- `data_contracts` in the spec — schema, SLAs, PII flags.
- Generated DAG stubs and SQL — these are starting points, commit into the
  warehouse project.

**Writes**

- Source-to-contract mappings (landing zone → contract-compliant view).
- Infrastructure glue: schedulers, warehouse credentials, alert channels.

**Constraints**

- Cannot change rule logic without a spec PR. The framework refuses to run if
  the warehouse schema drifts from the contract.

**Where to start**

- [Data Integration page](dashboard-tour.md#data-integration) — the
  30-second answer to *"what data is flowing through this AML
  program?"*. Source catalogue, contract roll-up in whitepaper
  vocabulary (completeness / staleness / checks), ISO 20022
  message-type counts, and a DATA-N → artifact map linking each
  whitepaper claim to the page / CLI / module that closes it.
- [Spec Editor](dashboard-tour.md#spec-editor--rule-builder) — edit
  `data_contracts` declarations + per-attribute freshness pinning
  (`max_staleness_days` + `last_refreshed_at_column`).
- [Run History](dashboard-tour.md#run-history) — per-run lineage,
  spec hashes, ingestion provenance.

## 3. Data / Analytics Team

**Reads**

- Data-quality test results (generated from the spec).
- Freshness monitors, null-rate trends.
- Rule output tables (for typology research and tuning).

**Writes**

- New detection hypotheses as draft rules in the spec (marked
  `status: experimental`, routed to a shadow queue).
- Tuning recommendations: threshold proposals backed by backtest results.

## 4. Auditor (Internal & External)

**Reads**

- `control_matrix.md` — one-page view of controls vs. regulation.
- Evidence bundle (`aml export`) — zipped, signed, contains:
  - spec snapshot at the execution time,
  - input hash manifest,
  - alert set with deterministic output hash,
  - reviewer decision log with timestamps,
  - regulator export (SAR/CTR) if applicable.

**Writes**

- Findings as GitHub issues linked to specific spec clauses or evidence
  bundles. Findings become tracked remediation items in the spec
  (`open_findings` section).

**Key property**

- Can reproduce any historical run by checking out the `spec_version` SHA and
  replaying the referenced input snapshot. A mismatched `output_hash` is a
  reportable control failure.

## 5. Line-of-Defence Reviewers (L1 / L2 Analyst, SAR Filer)

**Reads**

- Case files routed to their queue, each with:
  - triggering transactions,
  - customer KYC snapshot,
  - prior-alert history,
  - the spec clause that triggered the alert (so the reviewer knows *why*).

**Writes**

- Decisions: escalate / close / request-info. Each decision is written to the
  audit ledger with reviewer id, timestamp, and free-text reason. Decisions
  cannot be silently overwritten.

## Collaboration loop

```
             ┌──────── CCO / Compliance ────────┐
             │  proposes threshold / rule PR    │
             ▼                                   │
       aml.yaml (main) ─── PR review ──── approves
             │
   ┌─────────┴──────────┐
   │  generators run    │ ── produces DAG stubs, SQL, docs, control matrix
   ▼                    ▼
Data Engineer      Analytics team
  wires up          backtests,
  pipelines         proposes tuning
             │
             ▼
        Runtime: alerts → queues → reviewer decisions
             │
             ▼
        Evidence bundle ──► Auditor (internal, then regulator)
```

The important property: **no role has an unreviewed write path to production
detection logic.** Every change is a diff on `aml.yaml`. That is the control.
