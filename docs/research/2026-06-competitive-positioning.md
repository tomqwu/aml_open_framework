# AML Open Framework — Competitive Positioning Report: June 2026

*Date: 2026-06-03 · Last updated: 2026-06-21 (mid-month refresh) · Scope: post-May 31 security hardening (H0–H6) + M1–M4 ML roadmap + Wave 2 governance features (#523 #528 #529 #531) · Companion: [`2026-06-regulator-pulse.md`](./2026-06-regulator-pulse.md) for the regulatory deadline context. Previous edition: [`2026-05-competitive-positioning.md`](./2026-05-competitive-positioning.md).*

> Refresh commissioned 2026-06-01, 7 days after the May 25 edition. Four events materially shifted the competitive map since May 25: (1) the FinCEN Whistleblower NPRM comment period closed 2026-06-01; (2) the Effectiveness NPRM + GENIUS Act NPRM comment deadline **closed 2026-06-09** — rulemakings are now pending; (3) AUSTRAC Tranche 2 enforcement is in **10 days** (2026-07-01); (4) the May 31 security hardening sprint (H0–H6) shipped determinism, injection-safety, and coverage-gate fixes that directly strengthen the framework's SR 26-2 challenger-model position.
>
> *Updated 2026-06-21 (mid-month refresh): June 9 comment window closed; Wave 2 governance suite shipped (#523 fraud-AML links, #528 AMLA effectiveness telemetry, #529 North-Star Pillars 2/4/5/7, #531 Whistleblower audit) — SR 26-2 65 days examination-active; AUSTRAC Tranche 2 10 days out; AMLA RTS submission 19 days out.*

---

## What changed since June 4 (mid-June update — 2026-06-21)

**Wave 2 governance suite shipped (#523, #528, #529, #531).** Four additional features delivered since the June 4 Wave 1 sprint close the four remaining competitive gaps across jurisdiction linkage, EU regulatory telemetry, North-Star pillar governance, and Whistleblower-audit readiness:

- **#523 — Fraud↔AML case linkage** (`case_links.jsonl`): The UK APP fraud demonstrator (`examples/uk_app_fraud`) ships a planted mule (C0019) caught by POCA s.327 layering detection, cross-linked to its PSR fraud cases. No OSS competitor surfaces the PSR / FCA overlap in a single evidence artifact.
- **#528 — AMLA RTS effectiveness telemetry** (`aml amla-effectiveness-report`): The only OSS tool that maps a live run's alert→case→STR funnel + AMLR citation coverage directly to the three AMLA RTS articles (Art. 28(1), Art. 26, Art. 20(1)(d)). Directly addresses the 19-day AMLA RTS submission clock.
- **#529 — North-Star Pillars 2, 4, 5, 7**: Defect lifecycle (append-only companion `defect_lifecycle.jsonl`), mandatory `risk_tier` advisory on all active rules, model-approval gate for prod promotion. No commercial platform publishes a governed prod-promotion gate backed by a hash-chained audit ledger.
- **#531 — Whistleblower internal-channel audit** (`aml whistleblower-audit`): Five governance signals in one command (SAR-backlog exposure, escalation coverage %, triage time median/p95, board-documented decisions, ledger integrity). `--format nprm-gap` outputs a ✓/⚠/✗ readiness table against the NPRM's proposed examination criteria — the only OSS tool scoped to the June 1 NPRM.

**June 9 comment window has closed.** The Effectiveness NPRM + GENIUS Act NPRM dual deadline passed 2026-06-09. Both rulemakings are pending (no published final-rule outcome). The competitive discriminator has shifted from "file before the window" to "hold the comment-window gap analysis as documented proactive-posture evidence." Firms that completed a gap analysis or filed a comment letter can cite that work in SR 26-2 model governance; firms that deferred are now racing a 12-month implementation clock that starts at the final rule.

**SR 26-2 is 65 days examination-active** (up from 48 on June 4). Q2 2026 examination cycles have run. Q3 cycles are forming. Second-line MRM teams have presented gap analyses to boards. The M2 model-inventory CLI remains the one-command gap-filler for teams still building inventory in Excel.

**AUSTRAC Tranche 2 is 10 days away.** The framework ships `examples/austrac_tranche_2_dnfbp` — still the only OSS AML spec targeting Australian lawyers, accountants, real-estate agents, and DPMS. The first-mover window has not closed: AUSTRAC's first-cycle enforceable-undertaking posture still applies to firms with *documented* good-faith compliance efforts. A program stood up before July 1 is inside that posture; one started after is not.

**AMLA RTS submission is 19 days away.** The #528 AMLA effectiveness telemetry is the only OSS tool that emits a citation-coverage report against the three AMLA RTS articles ahead of the July 10 Commission submission date.

---

## What changed since June 3

**M1–M4 ML roadmap fully delivered in v0.1.46 + v0.1.47.** The four Now-tier initiatives off the N1 governed-augmentation seam shipped in a single 24h sprint: Triage Queue dashboard page (M1), SR 26-2 model-inventory CLI `aml model-inventory` (M2 — **was priority #3, now complete**), champion-challenger `priority_outcome.json` with temporal-leakage guard (M3), and point-in-time effective-dated joins (M4, Pillar 3 PARTIAL→COVERED). The framework is the only OSS AML platform with a governed ML triage layer, a one-command SR 26-2 model inventory, and a deterministic champion-challenger outcome report.

---

## What changed since June 1

**June 9 comment deadline was 8 days away** (as of June 1). The Effectiveness NPRM + GENIUS Act NPRM dual deadline was June 9. The window has since closed; see the mid-June update above.

**SR 26-2 was 45 days examination-active** (as of June 1). Q2 2026 examination cycles were ongoing — second-line MRM teams were mid-presentation to boards, not starting gap analyses. The framework's challenger-model documentation bundle is the gap-filler for Q3 model-risk committee reports.

**AUSTRAC Tranche 2 was 27 days away** (as of June 1). No OSS competitor had moved on this. The first-mover window was narrowing: AUSTRAC's first-cycle enforceable undertaking posture applies to firms with *documented* good-faith compliance efforts — programs started before July 1 still qualify.

---

## What changed since May 25

**FinCEN Whistleblower NPRM comment period closed Monday.** The comment period for the March 30 NPRM (10–30% of collected sanctions from a $300M fund) closed 2026-06-01. The **proposed** award structure is known in outline, but the terms are not settled — FinCEN will consolidate comments and a final rule is expected late 2026 / early 2027, so treat the percentages as proposed, not final. Even so, the incentive signal is real, substantial, and targeted at SAR-backlog and screening-gap failures. Compliance teams that haven't reviewed internal escalation channels since Q1 2026 are running behind.

**The May 31 security hardening sprint (H0–H6) closes SR 26-2 gaps directly.** Six PRs shipped in one sprint address the exact controls SR 26-2 examiners will inspect in a challenger-model review: coverage gate enforcement (test-outcome-analysis discipline), zip-slip sanitisation (evidence-bundle integrity), SQL injection prevention (data-integrity chain), and audit pack byte-determinism (same-inputs → identical-output guarantee). The determinism fix is the most competitively significant: no commercial AML platform publishes a same-spec + same-data + same-seed = identical-output guarantee.

**5 days to the Effectiveness NPRM + GENIUS Act NPRM dual deadline (June 9).** Firms that complete gap analyses before June 9 can use their comment-window work as documented evidence of proactive compliance posture in SR 26-2 model governance.

**27 days to AUSTRAC Tranche 2 enforcement (July 1).** No OSS AML framework has shipped an AUSTRAC-specific example spec. The window to position as the go-to open-source baseline for Australian DNFBPs is closing in 27 days.

---

## 1. Competitive Landscape — June 2026 Update

### Commercial enterprise platforms

**Veteran rules-plus-ML platforms (NICE Actimize SAM, Oracle FCCM, SymphonyAI, FIS/SAS AML).** SR 26-2 has been examination-active since April 17 — 65 days as of June 21. Q2 2026 examination cycles have run. Q3 cycles are forming. Second-line MRM teams have presented gap analyses to boards. The window for platforms to produce SR-26-2-aligned MRM documentation bundles is open, but the framework's challenger-model position is already established for the first examination cycles — and the M2 model-inventory CLI is the one-command gap-filler for teams still building inventory in Excel.

**AI-native challengers (ComplyAdvantage, Hawk:AI, Featurespace/Visa, Feedzai, Lucinity).** The ML-first model-validation burden under SR 26-2 is real and increasing with each examination cycle. A challenger that cannot produce a deterministic replay of a flagged alert — with identical output hashes across runs — fails the SR 26-2 independent-validation test. The M3 champion-challenger outcome report + temporal-leakage guard is the artifact none of these platforms can produce on demand. The #531 Whistleblower audit tool adds a second unreplicable artifact: a `--format nprm-gap` readiness table scoped to the FinCEN NPRM's proposed examination criteria.

**Graph/network specialists (Quantexa, Ripjar, Sayari).** No change. Slot remains case-level visualisation, not full MRM challenger.

### Open source — June 2026 (mid-month)

- **Marble (checkmarble/marble):** Strongest direct alternative. Still has no Compliance Manifest, MRM bundle, deterministic-rerun guarantee, AUSTRAC Tranche 2 spec, GENIUS Act PPSI template, AMLA RTS telemetry, or Whistleblower audit tool. SR 26-2 examination-active for 65 days — the gap has widened through the Wave 2 sprint.
- **Jube (jube-home):** ML-first. SR 26-2 headwind unchanged. No Whistleblower audit or AMLA coverage.
- **FINOS OpenAML:** Labs-stage. No change.

No OSS competitor has shipped: (a) an AUSTRAC Tranche 2 example spec, (b) a PPSI/GENIUS Act compliance template, (c) a deterministic-rerun audit guarantee, (d) AMLA RTS citation-coverage telemetry, or (e) a FinCEN Whistleblower readiness report. The framework is the only OSS option with all five.

---

## 2. Where the Framework Wins — June 2026 Update

**The H0–H6 sprint closes the one remaining SR 26-2 gap: demonstrable test coverage of compliance-critical engine paths.** The coverage gate (H0) was non-enforcing — pytest-cov exits 0 on Linux below the threshold, so CI was green at 98.99% despite the advertised 99% floor. The gate is now enforced by a platform-independent script (`scripts/check_coverage_floor.py`). Combined with the determinism fix (audit pack now byte-identical across runs), the framework now satisfies all three SR 26-2 independent-challenger requirements: deterministic rerun, hash-chained audit ledger, and demonstrated test coverage of the scoring and audit logic.

**Zip-slip and SQL injection fixes (H2, H4) directly protect the regulator-evidence bundle.** The ZIP the examiner receives must contain only the intended evidence; the data the framework reads must be validated before it enters the hash chain. These aren't cosmetic — they are the controls that protect the evidential integrity SR 26-2 and the Effectiveness NPRM both require.

**The M1–M4 ML roadmap ships the governed-augmentation seam no commercial platform publishes.** Triage Queue (M1) gives investigators a priority-scored, explainable alert queue — advisory-only, MRM-compliant. Model-inventory CLI (M2) emits the SR 26-2 inventory in one command. Champion-challenger outcome report (M3) with temporal-leakage guard is the independent-validation artifact SR 26-2 requires. Point-in-time joins (M4) closes Pillar 3 (PARTIAL → COVERED): reference data is resolved as-of each transaction, not from the latest row.

**GENIUS Act PPSI template — comment window closed June 9.** The NPRM proposes BSA-program + OFAC sanctions compliance for permitted payment stablecoin issuers. The comment window closed June 9. The framework ships two PPSI specs (`genius_ppsi_issuer` and `genius_ppsi_stablecoin`) — the PPSI baseline positioning is established and carries into the pending-rule phase.

**AUSTRAC Tranche 2 deadline is July 1 — 10 days.** The framework ships `examples/austrac_tranche_2_dnfbp`. No OSS competitor. The first-mover documented program is the difference between AUSTRAC's enforceable-undertaking posture and an immediate penalty.

**AMLA RTS submission is July 10 — 19 days.** The #528 AMLA effectiveness CLI is the only OSS tool mapping a live run to the three AMLA RTS articles ahead of the Commission submission date. EU-supervised obliged entities using the framework can produce an AMLR citation-coverage table (`aml amla-effectiveness-report --markdown`) in one command.

---

## 3. Highest-Leverage Next Features — June 2026 Mid-Month Status

| Priority | Feature | Status | Why now |
|---|---|---|---|
| ~~#1~~ | ~~**GENIUS Act / PPSI compliance template**~~ | **✅ SHIPPED** | Two specs ship: `genius_ppsi_issuer` + `genius_ppsi_stablecoin`. Comment window closed June 9; framework is the PPSI baseline ahead of the pending final rule. |
| ~~#2~~ | ~~**AUSTRAC Tranche 2 example spec**~~ | **✅ SHIPPED** | `examples/austrac_tranche_2_dnfbp` — only OSS AUSTRAC spec. 10 days to enforcement; sustain with audit-pack jurisdiction tags. |
| ~~#3~~ | ~~**SR 26-2 model inventory CLI**~~ | **✅ SHIPPED v0.1.47** | `aml model-inventory --markdown` covers all rules, `python_ref` models, and the N1 prioritization scorer. |
| ~~#4~~ | ~~**FinCEN Whistleblower internal-channel audit**~~ | **✅ SHIPPED #531** | `aml whistleblower-audit --format nprm-gap` maps to the NPRM's proposed expectations. Final rule still pending late 2026 / early 2027. |
| ~~#5~~ | ~~**AMLA STR/RTS effectiveness telemetry**~~ | **✅ SHIPPED #528** | `aml amla-effectiveness-report` with AMLR citation coverage. 19 days to AMLA RTS submission July 10 — framework is EU-aligned. |
| **#1** | **FinCEN Effectiveness NPRM — 12-month implementation readiness** | Roadmap | Comment window closed; final rule late 2026 / early 2027. 12-month clock starts at the final rule. A `aml effectiveness-gap-check` CLI that maps Manifest rules to proposed NPRM requirements lets firms document readiness before the clock starts. |
| **#2** | **AMLA 2027 direct supervision self-assessment** | Roadmap | AMLA selects its first 40 directly-supervised entities July 2027. Cross-border EU groups in 6+ member states need a self-assessment tool against AMLA's published selection criteria — no OSS tool exists. |
| **#3** | **AUSTRAC Tranche 2 sustain — audit-pack jurisdiction tags** | Roadmap | First enforcement cycle live July 1. Audit packs should emit AUSTRAC-specific jurisdiction metadata (SMR/TTR filing thresholds, Tranche 2 sector tags) for the first inspection cycle. |

---

## Sources

- [SR 26-2, FRB April 17 2026](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm)
- [FinCEN AML Program NPRM, Federal Register 2026-07033](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs)
- [GENIUS Act NPRM, Federal Register 2026-06963](https://www.federalregister.gov/documents/2026/04/10/2026-06963/permitted-payment-stablecoin-issuer-anti-money-launderingcountering-the-financing-of-terrorism)
- [FinCEN Whistleblower NPRM, Federal Register 2026-06271](https://www.federalregister.gov/documents/2026/04/01/2026-06271/whistleblower-incentives-and-protections)
- [AUSTRAC: Regulatory expectations 2025–26](https://www.austrac.gov.au/amlctf-reform/austrac-regulatory-expectations-and-priorities-2025-26)
- [AMLA CDD RTS consultation](https://www.amla.europa.eu/policy/public-consultations/consultation-draft-rts-customer-due-diligence_en)
- [AMLA selection exercise press release](https://www.amla.europa.eu/amla-advances-preparations-2027-selection-exercise_en)
- [FATF Jurisdictions under Increased Monitoring, February 2026](https://www.fatf-gafi.org/en/publications/High-risk-and-other-monitored-jurisdictions/increased-monitoring-february-2026.html)
- [EU Council 20th Russia sanctions package, 2026-04-23](https://www.consilium.europa.eu/en/press/press-releases/2026/04/23/russia-s-war-of-aggression-against-ukraine-20th-round-of-stern-eu-sanctions-hits-energy-military-industrial-complex-trade-and-financial-services-including-crypto/)
- [Marble (checkmarble/marble) GitHub](https://github.com/checkmarble/marble)
