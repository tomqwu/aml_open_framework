# Data is the AML problem — August 2026

*Date: 2026-08-01 · Audience: CCO / MLRO / Head of Financial Crime / CRO / 2LoD model-validation. Previous edition: [`2026-07-aml-data-problem.md`](./2026-07-aml-data-problem.md). Companion docs: [`2026-07-aml-process-pain.md`](./2026-07-aml-process-pain.md), [`2026-07-competitive-positioning.md`](./2026-07-competitive-positioning.md) — a standalone August edition of those two was not authored this round; see the note at the end of this doc.*

---

## What changed since last month

These regulatory deadlines entered a tighter urgency band this month (computed from the bundled regulatory calendar):

| Deadline | Date | Days remaining | Band transition | Source |
|---|---|---|---|---|
| AUSTRAC Tranche 2 enforcement begins (AU DNFBPs) | 2026-07-01 | -31 | error → expired | [source](https://www.austrac.gov.au/business/how-comply-guidance-and-resources) |
| EU AMLA Regulatory Technical Standards submission window | 2026-07-10 | -22 | warning → expired | [source](https://www.eba.europa.eu/) |
| FinCEN AML Program Effectiveness rule — implementation planning | 2026-08-15 | 14 | info → warning | [source](https://www.fincen.gov/) |

---

## Deadline countdown

All non-expired regulatory deadlines as of 2026-08-01, with the framework surfaces each one maps to:

| Deadline | Date | Days remaining | Urgency band | Framework alignment | Source |
|---|---|---|---|---|---|
| FinCEN AML Program Effectiveness rule — implementation planning | 2026-08-15 | 14 | warning | Pages: North-Star Pillar Coverage, False-Positive Analysis, Threshold Sensitivity<br>Specs: examples/community_bank/aml.yaml<br>Fields: program.sla | [source](https://www.fincen.gov/) |

**A note on the row above, for readers new to this table:** the "FinCEN AML Program Effectiveness rule — implementation planning" entry is *not* a published FinCEN deadline. No final rule has issued — the Effectiveness NPRM's comment window closed 2026-06-09 and the rulemaking remains pending, with a final rule still expected late 2026 / early 2027 and (per the proposal) a 12-month implementation clock starting only once it is finalised. The 2026-08-15 date is this framework's own internally-generated planning checkpoint — a nudge to complete a gap analysis now rather than wait for the final rule — carried in the bundled `regulatory_calendar.yaml` alongside the three *confirmed* statutory deadlines above it. Distinguishing a binding-law date from a self-imposed planning date matters precisely because of the theme below: a compliance program's own forward calendar is data, too, and it is only audit-defensible if a reader can tell which entries are law and which are judgment calls.

---

## The data problem this month

This edition's finding is reflexive: it is about a stale number in *this framework's own* research doc, caught during this month's routine refresh — and it is a clean illustration of **DATA-4** ("Where did this number come from?") applied to the documents a compliance function produces about itself, not just to the transaction-monitoring dashboards it produces for others.

**The number:** July's `2026-07-regulator-pulse.md` cited AUSTRAC's maximum civil penalty for a Tranche 2 corporate contravention as "up to A$31.3M" — correct arithmetic for the Commonwealth penalty unit value that was in force when the figure was first written (100,000 penalty units × $313/unit). But the penalty unit is a statutorily indexed figure, not a fixed one, and it moved twice in the twelve months leading into Tranche 2 enforcement: to $330/unit, then again to **$364/unit effective 1 July 2026** under the *Crimes (Amount of a Penalty Unit) Instrument 2026*, made under s.4AA of the Crimes Act 1914 as amended by the *Crimes and Other Legislation Amendment (Omnibus No. 1) Act 2024*. At the current $364 rate, the same 100,000-unit corporate maximum is **up to A$36.4M** — roughly 16% higher than the figure this research series had been carrying since Round 38's citation-accuracy pass, without any change to the underlying AML/CTF Act penalty *structure* at all. The $31.3M figure has been corrected to $36.4M in `2026-07-regulator-pulse.md` as part of this edition's publication (see Framework response, below); the individual-liability maximum (20,000 penalty units) moves from roughly A$6.26M to **A$7.28M** on the same basis.

**Why this is a DATA-4 problem, not a one-off typo:** a dollar-denominated penalty figure that is arithmetically correct at the moment it is written is not a fact with a fixed value — it is a *derived* number (penalty units × the unit value in force on the contravention date), and the unit value itself moves on a legislated schedule independent of any AML-specific news event. A document (or, worse, a dashboard) that hardcodes the dollar result rather than the formula and its as-of date will silently drift out of date on every future indexation cycle, with no AML-specific trigger to prompt a review. The Crimes Act's own 2024 amendment makes this concrete going forward: the unit value now auto-adjusts to CPI every three years starting from the 1 July 2026 value, rather than being set by ad hoc instrument — which means the *next* scheduled drift point for anyone citing this figure is already knowable (mid-2029) and should be tracked the same way a data contract tracks a `last_refreshed_at` column, not left to be caught by chance during a routine docs sweep.

**The other three tracked items have no primary-source movement to report this month** (verified by web research during this edition's authoring pass, 2026-08-03): the FinCEN AML Program Effectiveness NPRM and the FinCEN Whistleblower Incentives and Protections NPRM both remain pending rulemakings with no final rule published; no independently verifiable press release confirms AMLA's 2026-07-10 RTS submission to the European Commission actually occurred (the statutory deadline having passed is reported, not an outcome that hasn't been confirmed); and AUSTRAC has publicly signalled — consistent with prior editions' framing — that its initial Tranche 2 enforcement posture will prioritise entities that "wilfully ignore" their obligations over those making good-faith compliance efforts, which does not change this doc's practice of documenting the deadline as passed without asserting an enforcement outcome.

## Primary sources

- [Crimes Act 1914 (Cth) — s.4AA Penalty units (AustLII, consolidated)](https://www5.austlii.edu.au/au/legis/cth/consol_act/ca191482/s4aa.html) — the statutory formula and the post-2024-amendment indexation cadence (CPI-linked, three-yearly from 1 July 2026).
- [Australian Financial Security Authority — Penalty units](https://www.afsa.gov.au/professionals/resource-hub/penalty-units) — plain-English confirmation of the current $364 Commonwealth penalty unit value effective 1 July 2026 (up from $330) and the prior ad hoc indexation history.
- [Tranche 2 Penalties: What AUSTRAC Can Actually Do to You (NameScan)](https://namescan.io/insights/tranche-2-enforcement-penalties/) — the 100,000-penalty-unit corporate maximum / 20,000-unit individual maximum figures for a Tranche 2 civil-penalty contravention, restated at the current $364 unit value (~A$36.4M / ~A$7.28M).
- [AUSTRAC — How to comply: guidance and resources](https://www.austrac.gov.au/business/how-comply-guidance-and-resources) — enforcement-posture framing (enforceable undertakings favoured over penalties for entities showing good-faith compliance effort in the first cycle).
- [Federal Register 2026-07033 — AML/CFT Program Effectiveness NPRM](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs) — confirms the comment window closed 2026-06-09 and the rulemaking remains pending; no final-rule date has been set.
- [Federal Register 2026-06271 — FinCEN Whistleblower Incentives and Protections NPRM](https://www.federalregister.gov/documents/2026/04/01/2026-06271/whistleblower-incentives-and-protections) — confirms the comment window closed 2026-06-01 with no final rule published as of this edition.
- [AMLA — RTS Level-2 package due 10 July 2026 (financialregulations.eu explainer)](https://financialregulations.eu/blog/amla-level-2-rts-package-july-2026) — restates the 2026-07-10 submission-completeness deadline and the subsequent Commission endorsement window; used here only to corroborate the deadline date, not as confirmation of a submission outcome.

## Framework response

| Finding | Framework artifact |
|---|---|
| **DATA-4** — stale hardcoded penalty figure in `2026-07-regulator-pulse.md` | Corrected in this edition's PR (A$31.3M → A$36.4M corporate maximum; ~A$6.26M → ~A$7.28M individual maximum), alongside this doc. The framework's own `AuditLedger` pattern — never hardcode a derived number, always retain the inputs that produced it — is the same discipline this fix applies to the research series itself. |
| Distinguishing confirmed regulatory deadlines from framework-internal planning milestones (the 2026-08-15 row above) | `src/aml_framework/dashboard/regulatory_calendar.yaml` — the `source_url` field is the tell: a specific Federal Register / AMLA / AUSTRAC document URL marks a confirmed statutory deadline, a bare agency homepage marks an internally-generated planning nudge. The Regulatory Calendar dashboard page (page 54, #511) renders both types today without visually distinguishing them; **not fixed in this pass** — flagged here rather than silently left for a future docs sweep to rediscover. |
| AUSTRAC Tranche 2 penalty exposure, at the current $364 unit value | `examples/austrac_tranche_2_dnfbp/aml.yaml` remains the reference Compliance Manifest for a Tranche 2-scoped program; `program.risk_segmentation` is the spec field the calendar entry maps to. |
| FinCEN Effectiveness NPRM gap-analysis readiness (still pending, no final rule) | `aml model-inventory` (SR 26-2 / M2, v0.1.47) already produces the model-population inventory the NPRM's "risk assessment as a pillar" requirement would examine; no code change needed to stay ready for a final rule that has not yet issued. |

---

*A full August 2026 edition of the other four research whitepapers (`regulator-pulse`, `competitive-positioning`, `aml-process-pain`, `fintech-aml-reality`) was not authored this round — Round 42 flagged that as a larger content-authoring undertaking than a single edition's scope, and this session prioritised completing the already-open stub (this file) plus fixing the stale figure it surfaced. Issue #617 already tracks the full 5-file August refresh; no new issue filed.*
