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

    Five July 2026 research editions now live: regulator-pulse, competitive-positioning, process-pain, fintech-aml-reality, data-problem. Deadline status (as of 2026-06-26): Effectiveness NPRM + GENIUS Act NPRM comment window **closed 2026-06-09** (rulemaking pending); AUSTRAC Tranche 2 **2026-07-01 — 5 days**; AMLA RTS **2026-07-10 — 14 days**; SR 26-2 **70 days** examination-active. M1–M4 ML roadmap shipped v0.1.46–v0.1.47.

    [:octicons-arrow-right-24: Research](research/2026-07-regulator-pulse.md)

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
| `docs` | 38 | 2026-06-26 | June 26 docs refresh — deadline countdown rebased to June 26 (AUSTRAC Tranche 2 **5 days**, AMLA RTS **14 days**, SR 26-2 **70 days** active); all 5 July 2026 research editions updated; 2 new roadmap issues filed (#616 July AMLA citation fix, #617 August research refresh). |
| `docs` | 37 | 2026-06-22 | June 22 docs refresh — deadline countdown corrected to June 22 baseline (AMLA RTS 18 days, AUSTRAC 9 days, SR 26-2 66 days); `produce-amla-effectiveness-pack.md` + `run-whistleblower-audit.md` added to MkDocs nav; `2026-04-aml-data-problem.md` archive stub added (closes #561). |
| `docs` | — | 2026-07-01 | July 2026 research refresh — all five editions carried forward to a 2026-07-01 as-of date: Effectiveness NPRM + GENIUS Act comment window **closed June 9** (rulemaking pending, no outcome asserted); AUSTRAC Tranche 2 **9 days** (July 1); AMLA RTS **18 days** (July 10); SR 26-2 **66 days** examination-active. |
| `docs` | — | 2026-06-05 | Regulatory Calendar — a live forward-deadline view (Regulatory Calendar page + a countdown banner on Today) mapping each NPRM/enforcement deadline to the framework features that evidence readiness. |
| `docs` | 33 | 2026-06-05 | June 2026 research complete: data-problem June edition added (SR 26-2 examination-active 49 days, M4 point-in-time joins closes DATA-2, `aml model-inventory` closes DATA-6 gap); all 4 canonical research HTML files synced to June 2026 versions on static site. Effectiveness NPRM + GENIUS Act deadline June 9 — 4 days. |
| `v0.1.47` + `docs` | M1–M4 | 2026-06-04 | ML/AI roadmap Now tier fully delivered: Triage Queue dashboard (M1), SR 26-2 model-inventory CLI `aml model-inventory` (M2), champion-challenger `priority_outcome.json` with temporal-leakage guard (M3), point-in-time effective-dated joins (M4, Pillar 3 COVERED). All four June 2026 research docs refreshed: June 9 NPRM deadline **5 days away** (file Fri/Sat June 5–6); AUSTRAC 27 days; AMLA RTS 36 days; SR 26-2 48 days active |
| `docs` | — | 2026-06-03 | June 2026 research refresh — regulator-pulse + competitive-positioning updated to 2026-06-03: June 9 Effectiveness NPRM + GENIUS Act NPRM dual deadline now **6 days away** (last viable filing window Fri/Sat June 5–6); AUSTRAC Tranche 2 28 days; AMLA RTS 37 days; SR 26-2 47 days examination-active |
| `docs` | — | 2026-06-01 | June 2026 research whitepapers added — regulator-pulse extended to 2026-06-01 (covering a three-month forward calendar, Jun–Aug 2026: Effectiveness NPRM + GENIUS Act NPRM deadlines 2026-06-09, AUSTRAC Tranche 2 enforcement 2026-07-01, AMLA RTS submission 2026-07-10); competitive-positioning updated post-June-1 deadline |
| `security` | — | 2026-05-31 | H0–H6 security hardening: coverage gate enforcement (H0), zip-slip sanitisation in audit packs (H4), SQL identifier validation in data sources (H2), audit pack byte-determinism fix, freshness tz-by-instant correctness (H6), matched-row observability (H6) |
| `docs` | — | 2026-05-29 | Research whitepapers refreshed to May 2026 editions — regulator-pulse extended to 2026-05-27 (116 days, 33 events); process-pain, fintech, competitive-positioning updated with SR 26-2, GENIUS Act NPRM, AUSTRAC Tranche 2 context |
| `v0.1.41` | 30 | 2026-05-24 | gap-audit-driven docs polish + page_header guard |
| `v0.1.40` | 28 | 2026-05-24 | Pillar 2/4/6 closure + legacy-import wizard (8 PRs) |
| `v0.1.39` | 27 | 2026-05-24 | SLA monitor + cost-volume + monitoring digest |
| `v0.1.38` | 27 | 2026-05-23 | Dashboard batch + PR-A2 follow-up + B1 validity |

Full journal: [Progress](progress.md). Live API: [`/api/v1/health`](https://ca-aml-api-dev.wittyhill-44456789.canadacentral.azurecontainerapps.io/api/v1/health).
