# Reference Architecture

## Principle

**The spec is the source of truth.** Policy, data contracts, detection rules,
case workflow, and regulator mapping live in one versioned YAML file. Every
runtime artifact — SQL, DAGs, data-quality tests, dashboards, alert payloads,
audit log entries — is *generated* from the spec, never hand-written in
parallel. This is what kills the drift that causes AML fines.

## Layered view

```
┌───────────────────────────────────────────────────────────────────────────┐
│  POLICY LAYER      aml.yaml  (plain YAML, reviewed via PR)                │
│                    ├── program metadata (jurisdiction, regulator, owner)  │
│                    ├── data_contracts    (tables, columns, SLAs, PII)     │
│                    ├── rules             (logic + regulation citations)   │
│                    ├── workflow          (queues, SLAs, escalations)      │
│                    └── reporting         (SAR/CTR/STR forms)              │
├───────────────────────────────────────────────────────────────────────────┤
│  GENERATION LAYER  spec → artifacts (deterministic, reproducible)         │
│                    ├── sql_generator     → rule SQL on DuckDB/Snowflake   │
│                    ├── dag_generator     → Airflow / Dagster stubs        │
│                    ├── tests_generator   → data-quality + rule fixtures   │
│                    ├── docs_generator    → persona-specific markdown      │
│                    └── control_matrix    → auditor-facing mapping         │
├───────────────────────────────────────────────────────────────────────────┤
│  RUNTIME LAYER     execute rules, produce alerts + cases                  │
│                    ├── ingest            (data contract enforced)         │
│                    ├── rule engine       (windowed aggregations, joins)   │
│                    ├── case manager      (queues, SLAs, reviewer notes)   │
│                    └── regulator export  (SAR bundle, CTR batch)          │
├───────────────────────────────────────────────────────────────────────────┤
│  EVIDENCE LAYER    immutable audit ledger, signed manifests               │
│                    ├── spec_version_hash (git SHA + content hash)         │
│                    ├── input_hash        (data snapshot hash)             │
│                    ├── rule_output_hash  (deterministic rerun proof)      │
│                    └── decision_log      (reviewer actions, with reason)  │
└───────────────────────────────────────────────────────────────────────────┘
```

## What the spec controls

| Concern                         | Where it lives in the spec          | Generated artifact                      |
|---------------------------------|-------------------------------------|-----------------------------------------|
| Data freshness / SLAs           | `data_contracts[*].freshness_sla`   | Pipeline sensor + alert                 |
| PII classification              | `data_contracts[*].columns[*].pii`  | Column masks, access policy             |
| Detection logic                 | `rules[*].logic`                    | SQL query + unit fixture                |
| Regulation traceability         | `rules[*].regulation_refs`          | Control matrix row + audit metadata     |
| Reviewer workflow               | `workflow.queues`                   | Case routing + SLA timers               |
| SAR / CTR reporting             | `reporting.forms`                   | Regulator export templates              |
| Retention                       | `retention_policy`                  | Ledger TTL + export redaction           |

## Determinism & reproducibility

Every rule execution records:

1. `spec_version` — git SHA of `aml.yaml` plus a content hash.
2. `input_hash` — hash of the ordered input rows used (or snapshot id).
3. `output_hash` — hash of the alert set.
4. `engine_version` — version of this framework.

An auditor can re-run any historical execution and verify the output hash
matches. If it doesn't, the chain of custody is broken and the run is flagged.

## Why not a rules engine in application code?

A pure Python/Java rules engine lets any developer tweak detection logic in a
Monday-morning hotfix, and the CCO only hears about it three audits later.
Declarative specs with PR-based review force a control point: policy changes
go through compliance sign-off *before* they change pipeline behaviour. The
same argument is why Terraform, dbt, and Kubernetes manifests won — spec > code
for regulated change.

## Extensibility

Two escape hatches, by design:

- **`custom_sql`** on a rule lets an engineer drop in handwritten SQL when the
  declarative logic primitives aren't expressive enough. The spec still
  carries the regulation citation, severity, workflow, and evidence list, so
  the audit trail survives.
- **`python_ref`** on a rule points at a Python callable (e.g. an ML scorer)
  that returns an alert set. The spec captures the model id and version so
  model risk management can validate it.

Both escape hatches mean some generation properties weaken (e.g. the control
matrix can't auto-extract thresholds), but the policy layer is preserved.

## What this framework is *not*

- **Not a replacement for a core banking system or transaction store.** It
  reads from whatever warehouse you have.
- **Not a certified detection model catalogue.** Rules in the examples are
  illustrative starting points, not validated typologies.
- **Not a SAR filing service.** It produces a well-formed bundle; the
  regulatory submission step is institution-specific.

See [`personas.md`](personas.md) for the role-by-role interaction model and
[`regulator-mapping.md`](regulator-mapping.md) for regime-specific notes.
