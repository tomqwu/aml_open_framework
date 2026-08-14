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

    Five July 2026 research editions plus a new August 2026 data-problem edition now live. Deadline status (as of 2026-08-13): Effectiveness NPRM + GENIUS Act NPRM comment window **closed 2026-06-09** (rulemaking pending); AUSTRAC Tranche 2 **in effect since 2026-07-01** (43 days in; enrolment grace period **passed 2026-07-29**, 15 days ago; corporate penalty maximum corrected to **A$36.4M** at the current $364 penalty-unit value; AUSTRAC's first two enforcement actions of the window — Sportsbet finalised, bet365 fresh undertaking — landed against pre-existing wagering registrants, not new DNFBPs); AMLA RTS submission **deadline passed 2026-07-10** (34 days ago; Commission's 3-month endorsement clock now running to 2026-10-10, 58 days remaining); SR 26-2 **118 days** examination-active. M1–M4 ML roadmap shipped v0.1.46–v0.1.47.

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
| `docs` | 48 | 2026-08-13 | August 13 docs refresh — deadline countdown corrected to an August 13 baseline across all five `docs/research/2026-07-*.md` editions, `docs/index.md`'s deadline card, and the `docs/pitch/landing/` + `docs/pitch/landing/research/*.html` mirror pages (AUSTRAC Tranche 2 **43 days in**, was 42; enrolment grace period **passed 15 days ago**, was 14; AMLA RTS submission deadline **passed 34 days ago**, was 33; Commission endorsement clock **58 days remaining**, was 59; SR 26-2 **118 days** examination-active, was 117). Also closed two occurrences the Round 47 pass had missed (a "14 days past" phrase in `2026-07-fintech-aml-reality.md` and `2026-07-regulator-pulse.md`, and a "42 days" phrase in `2026-07-competitive-positioning.md`, both untouched by the exact-phrase substitutions those rounds used). Primary-source check, 2026-08-13: web search across all four tracked items (AUSTRAC Tranche 2 DNFBP enforcement, AMLA RTS submission confirmation, FinCEN Effectiveness NPRM, FinCEN Whistleblower NPRM) found no new confirmed developments since Round 47 — AUSTRAC's Tranche 2 compliance assessments remain expected "second half of 2026" with no dated action against the newly regulated DNFBP population; no independently verifiable press release confirms AMLA's RTS submission occurred; both FinCEN NPRMs remain pending rulemakings with no final rule. No new roadmap issue filed — #659 already tracks the confirmed-vs-planning distinction gap; #617/#632/#655 already cover the recurring refresh/pile-up ground; a 70-open-issue backlog scan turned up no gap this round surfaced that isn't already tracked. |
| `docs` | 47 | 2026-08-12 | August 12 docs refresh — deadline countdown corrected to an August 12 baseline across all five `docs/research/2026-07-*.md` editions, `docs/index.md`'s deadline card, and the `docs/pitch/landing/` + `docs/pitch/landing/research/*.html` mirror pages (AUSTRAC Tranche 2 **42 days in**, was 39; enrolment grace period **passed 14 days ago**, was 11; AMLA RTS submission deadline **passed 33 days ago**, was 30; Commission endorsement clock **59 days remaining**, was 62; SR 26-2 **117 days** examination-active, was 114). Primary-source check, 2026-08-12: no new confirmed developments on any of the four tracked items since Round 46. No new roadmap issue filed — #659 already tracks the confirmed-vs-planning distinction gap; #617/#632/#655 already cover the recurring refresh/pile-up ground. |
| `docs` | 46 | 2026-08-09 | August 9 docs refresh — deadline countdown corrected to an August 9 baseline across all five `docs/research/2026-07-*.md` editions, `docs/index.md`'s deadline card, and the `docs/pitch/landing/` + `docs/pitch/landing/research/*.html` mirror pages (AUSTRAC Tranche 2 **39 days in**, was 37; enrolment grace period **passed 11 days ago**, was 9; AMLA RTS submission deadline **passed 30 days ago**, was 28; Commission endorsement clock **62 days remaining**, was 64; SR 26-2 **114 days** examination-active, was 112). Primary-source check, 2026-08-09: no new confirmed developments on any of the four tracked items since Round 45. Filed **[#659](https://github.com/tomqwu/aml_open_framework/issues/659)** — the Regulatory Calendar page (#511) doesn't visually distinguish confirmed statutory deadlines from framework-internal planning milestones, a gap flagged since Round 43 but never tracked; no other new roadmap issue filed per #644/#632's anti-pile-up guidance. |
| `docs` | 45 | 2026-08-07 | August 7 docs refresh — deadline countdown corrected to an August 7 baseline across all five `docs/research/2026-07-*.md` editions, `docs/index.md`'s deadline card, and the `docs/pitch/landing/` + `docs/pitch/landing/research/*.html` mirror pages (AUSTRAC Tranche 2 **37 days in**, was 35; enrolment grace period **passed 9 days ago**, was 7; AMLA RTS submission deadline **passed 28 days ago**, was 26; Commission endorsement clock **64 days remaining**, was 66; SR 26-2 **112 days** examination-active, was 110). New finding: AUSTRAC finalised its enforceable undertaking with Sportsbet (2026-07-03) and entered a fresh one with bet365 days later — the first two enforcement actions since Tranche 2 commenced, correctly scoped as landing against pre-existing wagering registrants, not the newly regulated Tranche 2 DNFBP population. No new roadmap issue filed — #617, #655, #632 already track the open work this round touches. *(This row was omitted when Round 45 shipped; backfilled by Round 46 for changelog completeness.)* |
| `docs` | 44 | 2026-08-05 | August 5 docs refresh — deadline countdown corrected to an August 5 baseline across all five `docs/research/2026-07-*.md` editions, `docs/index.md`'s deadline card, and the `docs/pitch/landing/` + `docs/pitch/landing/research/*.html` mirror pages (AUSTRAC Tranche 2 **35 days in**, was 33; enrolment grace period **passed 7 days ago**, was 5; AMLA RTS submission deadline **passed 26 days ago**, was 24; Commission endorsement clock **66 days remaining**, was 68; SR 26-2 **110 days** examination-active, was 108). Also brought the four `2026-07-*.md` editions and their html mirrors — left at an August 1 baseline by Round 43, which only refreshed `docs/index.md` and the new August edition — up to the same August 5 baseline, closing the cross-doc inconsistency that had crept in between rounds. Primary-source check, 2026-08-05: no new developments on any of the four tracked items (AUSTRAC enforcement outcome, AMLA RTS submission confirmation, FinCEN Effectiveness NPRM, FinCEN Whistleblower NPRM all remain as reported in Round 43). No new roadmap issue filed — #617 already tracks the full 5-file August refresh (still open; the four remaining editions are carried-forward July content, not new August editions), #655 already tracks the Actions-permissions gap; filing another day-count-refresh issue would add to the pile-up #644 documents. |
| `docs` | 43 | 2026-08-03 | Completed the `monthly-research-refresh` workflow's auto-generated stub (#654, #512) into a full [`2026-08-aml-data-problem.md`](research/2026-08-aml-data-problem.md) edition; added it to the MkDocs nav. New finding: AUSTRAC's Tranche 2 corporate penalty maximum was stale in `2026-07-regulator-pulse.md` (**A$31.3M**, the pre-indexation $313 penalty-unit value) — corrected to **A$36.4M** at the current $364 unit value effective 2026-07-01. Deadline countdown also refreshed to an August 3 baseline (AUSTRAC **33 days in**; AMLA RTS passed **24 days ago**, endorsement clock **68 days remaining**; SR 26-2 **108 days** examination-active). No new roadmap issue filed — #617 already tracks the full 5-file August refresh, #655 already tracks the Actions-permissions gap behind #654. |
| `docs` | 42 | 2026-08-01 | August 1 docs refresh — deadline countdown corrected to August 1 baseline (AUSTRAC Tranche 2 **31 days in**, was 23; enrolment grace period **passed 2026-07-29** — reframed from a countdown to "passed, 3 days ago" since the deadline has now elapsed; AMLA RTS submission deadline **passed 22 days ago**, was 14; SR 26-2 **106 days** examination-active, was 98; Commission endorsement clock **70 days remaining**, was 78); no new regulatory finding this round (web research confirmed no primary-source updates to AUSTRAC enforcement outcomes, AMLA RTS submission confirmation, or the FinCEN Whistleblower final rule since Round 41) — pure day-count refresh, no new roadmap issue filed. |
| `docs` | 41 | 2026-07-24 | July 24 docs refresh — deadline countdown corrected to July 24 baseline (AUSTRAC Tranche 2 **23 days in**, was 18; enrolment grace period ends 2026-07-29, **5 days** away, was 10; AMLA RTS submission deadline **passed 14 days ago**, was 9; SR 26-2 **98 days** examination-active, was 93); builds on #648 (Round 40) rather than re-deriving. |
| `docs` | 40 | 2026-07-19 | July 19 docs refresh — deadline countdown corrected to July 19 baseline (AUSTRAC Tranche 2 **18 days in**, was 15; new fact: enrolment grace period for newly regulated entities ends **2026-07-29**, 10 days; AMLA RTS submission deadline **passed 11 days ago**; SR 26-2 **93 days** examination-active, was 90); consolidates and supersedes #646. |
| `docs` | 39 | 2026-07-16 | July 16 docs refresh — deadline countdown corrected to July 16 baseline (AUSTRAC Tranche 2 **15 days in**, was 7; AMLA RTS submission deadline **passed 2026-07-10** — reframed from a countdown to "deadline passed, Commission's 3-month endorsement clock running to 2026-10-10" per #605; SR 26-2 **90 days** examination-active, was 82); `docs/how-to/produce-amla-effectiveness-pack.md` gets a post-submission note on how `rts_coverage` gaps now read once the RTS is locked in. |
| `docs` | 38 | 2026-07-08 | July 8 docs refresh — deadline countdown corrected to July 8 baseline (AUSTRAC Tranche 2 now **in effect** since July 1, no longer "9 days away"; AMLA RTS **2 days** not 18; SR 26-2 **82 days** examination-active, was 66/75); regulator-pulse's AMLA RTS citations corrected to match the code (`AMLR Art. 26` for ongoing-monitoring, `AMLR Art. 20(1)(d)` for targeted-financial-sanctions RTS, replacing the stale `Art. 19(9)`/`AMLD6 53(10)` — closes the Round 36 follow-up). |
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
