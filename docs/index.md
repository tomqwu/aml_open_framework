# AML Open Framework

> **An anti-money-laundering program you can show to your regulator without a six-week reconstruction.**

This is the engineering documentation site. For the executive deck and pitch materials, see the [landing page](https://tomqwu.github.io/aml_open_framework_docs/).

## Where to start

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **New here?**

    ---

    Five-minute setup, your first run, what the framework actually does.

    [:octicons-arrow-right-24: Getting Started](getting-started.md)

-   :material-bank:{ .lg .middle } **Migrating from a legacy stack?**

    ---

    CSV/JSON import wizard for SAS / Actimize / Mantas rule dumps.

    [:octicons-arrow-right-24: Legacy Import](legacy-import.md)

-   :material-file-document-multiple:{ .lg .middle } **Show me the evidence**

    ---

    Per-run artifacts, SHA-256 hash chain, regulator-ready audit bundle.

    [:octicons-arrow-right-24: Audit Evidence](audit-evidence.md)

-   :material-monitor-dashboard:{ .lg .middle } **Dashboard tour**

    ---

    All 53+ Streamlit pages walked through by persona.

    [:octicons-arrow-right-24: Dashboard Tour](dashboard-tour.md)

</div>

## What the framework gives you

The hard part of AML at a bank is **not** detection — it's proving, months later, that the right rule fired, was reviewed, was acted on, and that nothing was quietly turned off.

This framework is the **spec / control-plane layer above your AML stack**:

- **One versioned `aml.yaml`** drives whatever detection engine, data pipeline, and case tool you already own
- **Deterministic replay** — same spec + same data + same seed = identical output hashes
- **SHA-256 hash-chained audit ledger** makes the trail tamper-evident
- **Eight manifest-pinned evidence artifacts per run** — decisions, DQ exceptions, field lineage, SLA report, run cost/volume, monitoring digest, defect log, reconciliation report
- **53+ Streamlit dashboard pages** across 9 categories, audience-aware persona filtering
- **In-bank, not SaaS** — Apache 2.0, runs in your perimeter, federated identity end-to-end on Azure

## Architecture at a glance

```
aml.yaml (spec)
  → spec/loader.py        JSON Schema + Pydantic validation
  → generators/            SQL, DAG stubs, control matrix, STR narratives
  → engine/runner.py       Execute rules on in-memory DuckDB
  → metrics/engine.py      Compute metrics → RAG bands
  → engine/audit.py        Immutable evidence ledger (SHA-256 hash chain)
  → export.py              Regulator-ready ZIP bundle
  → dashboard/             53+ page Streamlit web app
  → api/                   FastAPI REST layer with JWT/OIDC auth
```

See [Architecture](architecture.md) for the full design rationale.

## Live demo

The running dashboard is at [`ca-aml-dashboard-dev.wittyhill-44456789.canadacentral.azurecontainerapps.io`](https://ca-aml-dashboard-dev.wittyhill-44456789.canadacentral.azurecontainerapps.io/) — spec-driven rules, alerts, cases, evidence — no install.

## What's new

- **v0.1.41** (2026-05-24) — Round 30: gap-audit-driven docs polish, page_header guard
- **v0.1.40** (2026-05-24) — Round 28: Pillar 2/4/6 closure + legacy-import wizard (8 PRs)
- **v0.1.39** (2026-05-24) — Round 27 close: SLA monitor + cost-volume + monitoring digest
- **v0.1.38** (2026-05-23) — Round 27: dashboard batch + PR-A2 follow-up + B1 validity + SLA monitor

Full journal: [Progress](progress.md).
