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
examples/community_bank/        Example spec for a US community bank
src/aml_framework/
  spec/                         Parse + validate the spec
  generators/                   Emit SQL, DAG stubs, docs
  engine/                       Execute rules on DuckDB, audit ledger
  cases/                        Case files, reviewer workflow artifacts
  data/                         Synthetic data for demos and tests
  cli.py                        `aml` command-line entry point
docs/
  architecture.md               Reference architecture (C)
  personas.md                   Who does what
  regulator-mapping.md          FinCEN / FINTRAC / OFAC / AMLD6 coverage
  spec-reference.md             Field-by-field spec guide
```

## Status

Reference implementation — not a certified compliance product. Use it to
prototype controls, drive internal conversations, or anchor a spec-first
migration of an existing AML program. Any production deployment needs
institution-specific tuning, model validation, and sign-off from your 2nd line.

## License

Apache-2.0.
