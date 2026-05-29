---
hide:
  - navigation
  - toc
---

<div class="aml-hero" markdown>
<div class="aml-eyebrow">AML Open Framework · 2026</div>

# An AML program your regulator can <em>replay</em>.

<p class="aml-lede">
One <strong>Compliance Manifest</strong> defines the program. The engine generates
SQL, runs detectors, produces alerts, writes a SHA-256 hash-chained audit ledger,
and emits a regulator-ready ZIP — same spec + same data + same seed = identical
output hashes. <strong>In-bank, not SaaS.</strong> Apache 2.0.
</p>
</div>

## Pick your door

<div class="grid cards" markdown>

-   :material-presentation:{ .lg .middle } **Board / business audience**

    ---

    Animated deck, board video, real screenshots — ~10 min to understand the value.

    [:octicons-arrow-right-24: Business deck](https://tomqwu.github.io/aml_open_framework_docs/business/)

-   :material-bank-outline:{ .lg .middle } **MLRO / 2LoD reviewer**

    ---

    Technical brief walking architecture, audit posture, model risk.

    [:octicons-arrow-right-24: Technical brief](https://tomqwu.github.io/aml_open_framework_docs/technical/)

-   :material-rocket-launch:{ .lg .middle } **Engineer**

    ---

    Five-minute setup, your first run, audit-pack on regulator-ready output.

    [:octicons-arrow-right-24: Getting Started](getting-started.md)

-   :material-book-open-variant:{ .lg .middle } **Researcher / regulator**

    ---

    Five May 2026 whitepapers: regulator pulse (116-day log), data problem, process pain, fintech reality, competitive positioning.

    [:octicons-arrow-right-24: Research](research/2026-05-regulator-pulse.md)

</div>

<div class="aml-hero" markdown>
<div class="aml-eyebrow">The data layer underneath</div>

# <em>Connect once.</em> Validate forever.

<p class="aml-lede">
AML's binding constraint isn't detection — it's getting <strong>one clean view</strong>
across nine source systems with eleven kinds of data pain. The framework declares
contracts, validates against them, and emits <strong>eight manifest-hashed evidence
artifacts</strong> per run so reconciliation isn't an offline spreadsheet.
</p>
</div>

## Operations

<div class="grid cards" markdown>

-   :material-monitor-dashboard:{ .lg .middle } **Dashboard tour**

    ---

    All 53+ Streamlit pages walked through by persona.

    [:octicons-arrow-right-24: Dashboard Tour](dashboard-tour.md)

-   :material-file-document-multiple:{ .lg .middle } **Audit evidence**

    ---

    Per-run artifacts, SHA-256 chain, regulator-ready bundle.

    [:octicons-arrow-right-24: Audit Evidence](audit-evidence.md)

-   :material-server-network:{ .lg .middle } **Deployment**

    ---

    Helm chart, Terraform Container Apps, federated identity end-to-end.

    [:octicons-arrow-right-24: Deployment](deployment.md)

-   :material-bank:{ .lg .middle } **Legacy import**

    ---

    CSV/JSON wizard for SAS / Actimize / Mantas rule dumps.

    [:octicons-arrow-right-24: Legacy Import](legacy-import.md)

</div>

<div class="aml-hero" markdown>
<div class="aml-eyebrow">The walk-back regulators ask for</div>

# <em>Trace every alert.</em> Down to the row.

<p class="aml-lede">
When an examiner asks "show me why this alert fired," the answer is one paste
of a case_id away — the seven-link lineage chain (case → rule → version →
spec hash → input file hash → run timestamp → byte-stable replay) is built
into every audit bundle. <strong>No reconstruction. No after-the-fact narrative.</strong>
</p>
</div>

## What's new

| Version | Round | Date | Shipped |
|---------|-------|------|---------|
| `docs` | — | 2026-05-29 | Research whitepapers refreshed to May 2026 editions — regulator-pulse extended to 2026-05-27 (116 days, 33 events); process-pain, fintech, competitive-positioning updated with SR 26-2, GENIUS Act NPRM, AUSTRAC Tranche 2 context |
| `v0.1.41` | 30 | 2026-05-24 | gap-audit-driven docs polish + page_header guard |
| `v0.1.40` | 28 | 2026-05-24 | Pillar 2/4/6 closure + legacy-import wizard (8 PRs) |
| `v0.1.39` | 27 | 2026-05-24 | SLA monitor + cost-volume + monitoring digest |
| `v0.1.38` | 27 | 2026-05-23 | Dashboard batch + PR-A2 follow-up + B1 validity |

Full journal: [Progress](progress.md). Live API: [`/api/v1/health`](https://ca-aml-api-dev.wittyhill-44456789.canadacentral.azurecontainerapps.io/api/v1/health).
