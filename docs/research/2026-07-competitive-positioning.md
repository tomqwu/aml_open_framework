# AML Open Framework — Competitive Positioning Report: July 2026

*Date: 2026-07-01 · Scope: post-May 31 security hardening (H0–H6) + M1–M4 ML roadmap delivery, carried into the July deadline window · Companion: [`2026-07-regulator-pulse.md`](./2026-07-regulator-pulse.md) for the regulatory deadline context. Previous edition: [`2026-06-competitive-positioning.md`](./2026-06-competitive-positioning.md).*

> Refresh anchored to 2026-07-01. Four facts shape the competitive map this month: (1) the Effectiveness NPRM + GENIUS Act NPRM dual comment window **closed 2026-06-09** — the rulemakings are now pending (final rule expected late 2026 / early 2027), and comment-window work becomes documented proactive-posture evidence; (2) AUSTRAC Tranche 2 enforcement is **effective today** (2026-07-01); (3) the AMLA RTS submission deadline is **9 days out** (2026-07-10); (4) SR 26-2 is **75 days examination-active** (April 17 anchor) and the M1–M4 ML roadmap continues to strengthen the framework's challenger-model position.

---

## What changed since June

**Wave 2 governance suite shipped mid-June (#523, #528, #529, #531).** Four features delivered between June 4 and June 21 extend the framework's competitive lead in jurisdiction linkage, EU regulatory telemetry, North-Star pillar governance, and Whistleblower-audit readiness — see the June 2026 edition for details. The key competitive facts at July 1:

- **#523 — Fraud↔AML case linkage**: UK APP fraud + POCA layering detection in one evidence artifact. No OSS competitor surfaces the PSR / FCA overlap.
- **#528 — AMLA RTS effectiveness telemetry**: Only OSS CLI mapping a live run to AMLR Art. 28(1) / Art. 26 / Art. 20(1)(d) citation coverage. Directly relevant to the 9-day AMLA RTS submission clock.
- **#529 — Defect lifecycle + risk_tier + model approval gate**: Append-only `defect_lifecycle.jsonl`, mandatory risk-tier advisory, and governed prod-promotion gate backed by the hash-chained ledger. No commercial platform publishes this combination.
- **#531 — Whistleblower internal-channel audit**: `aml whistleblower-audit --format nprm-gap` is the only OSS tool scoped to the FinCEN NPRM's proposed examination criteria — five governance signals in one command.

**The June 9 comment window has closed.** The Effectiveness NPRM + GENIUS Act NPRM dual deadline passed on 2026-06-09. There is no published final-rule outcome — both rulemakings are pending. The competitive implication has shifted from "file before the window closes" to "hold the comment-window work as proactive-posture evidence." Firms that completed a gap analysis or filed a comment letter can cite that work in SR 26-2 model governance; firms that deferred are now playing catch-up against a 12-month implementation clock that starts at the final rule.

**AUSTRAC Tranche 2 is effective today.** Enforcement begins 2026-07-01. The framework ships `examples/austrac_tranche_2_dnfbp` — the only OSS AUSTRAC spec. The first-mover window has not closed — AUSTRAC's first-cycle enforceable-undertaking posture still applies to firms with *documented* good-faith compliance efforts — but it has narrowed from "27 days out" to "live." Programs stood up before today are inside the favourable posture.

**AMLA RTS submission is 9 days away.** AMLA must submit final draft RTS to the European Commission by 2026-07-10. After submission the Commission has three months to endorse before the RTS bind. For EU-supervised obliged entities, the standard locks in 9 days; gaps against it become implementation backlogs against the July 2027 application date. The #528 AMLA effectiveness CLI is the only OSS tool that produces a citation-coverage table against the three AMLA RTS articles ahead of this deadline.

**SR 26-2 is 75 days examination-active** (up from 48 on June 4, April 17 anchor). Q2 examination cycles have run and Q3 cycles are forming. The M2 model-inventory CLI ships the exact artifact second-line MRM teams have been building manually in Excel: `aml model-inventory --markdown` outputs a pipe-formatted table of every rule, every `python_ref` scorer, and the N1 prioritization model — ready for the Q3 model-risk committee report with one command.

---

## What changed since May 25

**FinCEN Whistleblower NPRM comment period closed June 1.** The comment period for the March 30 NPRM (10–30% of collected sanctions from a $300M fund) closed 2026-06-01. The **proposed** award structure is known in outline, but the terms are not settled — FinCEN will consolidate comments and a final rule is expected late 2026 / early 2027, so treat the percentages as proposed, not final. Even so, the incentive signal is real, substantial, and targeted at SAR-backlog and screening-gap failures.

**The May 31 security hardening sprint (H0–H6) closes SR 26-2 gaps directly.** Six PRs shipped in one sprint address the exact controls SR 26-2 examiners will inspect in a challenger-model review: coverage gate enforcement (test-outcome-analysis discipline), zip-slip sanitisation (evidence-bundle integrity), SQL injection prevention (data-integrity chain), and audit pack byte-determinism (same-inputs → identical-output guarantee). The determinism fix is the most competitively significant: no commercial AML platform publishes a same-spec + same-data + same-seed = identical-output guarantee.

**The M1–M4 ML roadmap is fully delivered (v0.1.46 + v0.1.47).** The four Now-tier initiatives off the N1 governed-augmentation seam shipped in a single 24h sprint: Triage Queue dashboard page (M1), SR 26-2 model-inventory CLI `aml model-inventory` (M2), champion-challenger `priority_outcome.json` with temporal-leakage guard (M3), and point-in-time effective-dated joins (M4, Pillar 3 PARTIAL→COVERED). The framework is the only OSS AML platform with a governed ML triage layer, a one-command SR 26-2 model inventory, and a deterministic champion-challenger outcome report.

---

## 1. Competitive Landscape — July 2026 Update

### Commercial enterprise platforms

**Veteran rules-plus-ML platforms (NICE Actimize SAM, Oracle FCCM, SymphonyAI, FIS/SAS AML).** SR 26-2 has been examination-active since April 17 — 75 days. Q2 2026 examination cycles have run and Q3 cycles are forming. Second-line MRM teams have presented gap analyses to boards. The window for platforms to produce SR-26-2-aligned MRM documentation bundles is open, but the framework's challenger-model position is already established for the first examination cycles — and the M2 model-inventory CLI is the one-command gap-filler for teams still building inventory in Excel.

**AI-native challengers (ComplyAdvantage, Hawk:AI, Featurespace/Visa, Feedzai, Lucinity).** The ML-first model-validation burden under SR 26-2 is real and increasing with each examination cycle. A challenger that cannot produce a deterministic replay of a flagged alert — with identical output hashes across runs — fails the SR 26-2 independent-validation test. The M3 champion-challenger outcome report + temporal-leakage guard is the artifact none of these platforms can produce on demand.

**Graph/network specialists (Quantexa, Ripjar, Sayari).** No change. Slot remains case-level visualisation, not full MRM challenger.

### Open source — July 2026

- **Marble (checkmarble/marble):** Strongest direct alternative. Still has no Compliance Manifest, MRM bundle, or deterministic-rerun guarantee — and no SR 26-2 model inventory or champion-challenger outcome report. SR 26-2 examination-active for 75 days — the gap is now being felt and the M2 CLI widens it further.
- **Jube (jube-home):** ML-first. SR 26-2 headwind unchanged.
- **FINOS OpenAML:** Labs-stage. No change.

No OSS competitor has shipped: (a) an AUSTRAC Tranche 2 example spec, (b) a PPSI/GENIUS Act compliance template, or (c) a deterministic-rerun audit guarantee. The framework is the only OSS option with all three in scope.

---

## 2. Where the Framework Wins — July 2026 Update

**The H0–H6 sprint closes the one remaining SR 26-2 gap: demonstrable test coverage of compliance-critical engine paths.** The coverage gate (H0) was non-enforcing — pytest-cov exits 0 on Linux below the threshold, so CI was green at 98.99% despite the advertised 99% floor. The gate is now enforced by a platform-independent script (`scripts/check_coverage_floor.py`). Combined with the determinism fix (audit pack now byte-identical across runs), the framework now satisfies all three SR 26-2 independent-challenger requirements: deterministic rerun, hash-chained audit ledger, and demonstrated test coverage of the scoring and audit logic.

**Zip-slip and SQL injection fixes (H2, H4) directly protect the regulator-evidence bundle.** The ZIP the examiner receives must contain only the intended evidence; the data the framework reads must be validated before it enters the hash chain. These aren't cosmetic — they are the controls that protect the evidential integrity SR 26-2 and the Effectiveness NPRM both require.

**The M1–M4 ML roadmap ships the governed-augmentation seam no commercial platform publishes.** Triage Queue (M1) gives investigators a priority-scored, explainable alert queue — advisory-only, MRM-compliant. Model-inventory CLI (M2) emits the SR 26-2 inventory in one command. Champion-challenger outcome report (M3) with temporal-leakage guard is the independent-validation artifact SR 26-2 requires. Point-in-time joins (M4) closes Pillar 3 (PARTIAL → COVERED): reference data is resolved as-of each transaction, not from the latest row.

**GENIUS Act PPSI template positioning held through the closed comment window.** The NPRM proposes BSA-program + OFAC sanctions compliance for permitted payment stablecoin issuers. The comment window **closed June 9**; the rulemaking is pending. The framework already ships two PPSI example specs — publishing a PPSI-compliance reference template during the comment window positioned the framework as the PPSI baseline before any competitor, and that positioning carries into the pending-rule phase.

**AUSTRAC Tranche 2 is effective today.** The framework ships `examples/austrac_tranche_2_dnfbp` — the only OSS AML spec targeting Australian DNFBPs. One spec, one new buyer segment, enforceable from July 1.

**Wave 2 governance suite (#523, #528, #529, #531) extends the lead into jurisdiction linkage and EU regulatory telemetry.** The Fraud↔AML case linkage (#523) makes the UK PSR / FCA overlap visible in a single audit artifact. The AMLA RTS telemetry (#528) is the only OSS tool that maps a live run to the three AMLA RTS articles in one command — directly relevant to the 9-day AMLA RTS submission clock. The defect lifecycle + risk_tier + model approval gate (#529) closes the governed prod-promotion gap no commercial platform addresses. The Whistleblower audit (#531) is the only OSS tool scoped to the FinCEN NPRM's proposed examination criteria.

---

## 3. Highest-Leverage Next Features — July 2026 Status

All four previously-ranked features shipped in June. The competitive priority table for Q3 2026:

| Priority | Feature | Status | Why now |
|---|---|---|---|
| ~~#1~~ | ~~**AUSTRAC Tranche 2 example spec**~~ | **✅ SHIPPED — sustain** | Enforcement effective July 1. Only OSS AUSTRAC spec. Sustain the lead: audit-pack jurisdiction tags for first enforcement cycle. |
| ~~#2~~ | ~~**AMLA RTS effectiveness telemetry**~~ | **✅ SHIPPED #528** | `aml amla-effectiveness-report` with AMLR Art. 28(1)/26/20(1)(d) citation coverage. 9 days to AMLA RTS submission July 10. |
| ~~#3~~ | ~~**GENIUS Act / PPSI compliance template**~~ | **✅ SHIPPED — sustain** | Two PPSI specs ship. Comment window closed June 9; rulemaking pending. Maintain as PPSI baseline ahead of final rule. |
| ~~#4~~ | ~~**FinCEN Whistleblower audit tool**~~ | **✅ SHIPPED #531** | `aml whistleblower-audit --format nprm-gap` maps five governance signals to the NPRM's proposed examination criteria. Final rule pending late 2026. |
| **#1** | **FinCEN Effectiveness NPRM — 12-month implementation readiness** | Roadmap | Comment window closed June 9; final rule late 2026 / early 2027. 12-month clock starts at the final rule. A `aml effectiveness-gap-check` CLI mapping Manifest rules to proposed NPRM requirements lets firms document readiness before the clock starts. Firms that defer until the final rule will implement under time pressure. |
| **#2** | **AMLA 2027 direct supervision self-assessment** | Roadmap | AMLA selects its first 40 directly-supervised entities July 2027. Cross-border EU groups in 6+ member states need a self-assessment tool against AMLA's published selection criteria — no OSS tool exists. The data-collection exercise underway now feeds the selection methodology. |
| **#3** | **AUSTRAC Tranche 2 sustain — audit-pack jurisdiction tags** | Roadmap | First enforcement cycle now live. Audit packs should emit AUSTRAC-specific jurisdiction metadata (SMR/TTR filing thresholds, Tranche 2 sector tags) for the first inspection cycle. AUSTRAC's first-cycle enforceable-undertaking posture favours firms with documented good-faith efforts — jurisdiction tags make the evidence bundle inspection-ready. |

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
