# AML Open Framework — Competitive Positioning Report: June 2026

*Date: 2026-06-01 · Scope: post-May 31 security hardening (H0–H6) · Companion: [`2026-06-regulator-pulse.md`](./2026-06-regulator-pulse.md) for the regulatory deadline context. Previous edition: [`2026-05-competitive-positioning.md`](./2026-05-competitive-positioning.md).*

> Refresh commissioned 2026-06-01, 7 days after the May 25 edition. Four events materially shift the competitive map since May 25: (1) the FinCEN Whistleblower NPRM comment period closed today (2026-06-01) — the proposed award structure (final rule expected late 2026 / early 2027) sharpens the internal-reporting risk calculus even before it's finalized; (2) the Effectiveness NPRM + GENIUS Act NPRM comment deadline is in 8 days (2026-06-09); (3) AUSTRAC Tranche 2 enforcement is in 30 days (2026-07-01); (4) the May 31 security hardening sprint (H0–H6) shipped determinism, injection-safety, and coverage-gate fixes that directly strengthen the framework's SR 26-2 challenger-model position.

---

## What changed since May 25

**FinCEN Whistleblower NPRM comment period closed today.** The comment period for the March 30 NPRM (10–30% of collected sanctions from a $300M fund) closed 2026-06-01. The **proposed** award structure is known in outline, but the terms are not settled — FinCEN will consolidate comments and a final rule is expected late 2026 / early 2027, so treat the percentages as proposed, not final. Even so, the incentive signal is real, substantial, and targeted at SAR-backlog and screening-gap failures. Compliance teams that haven't reviewed internal escalation channels since Q1 2026 are running behind.

**The May 31 security hardening sprint (H0–H6) closes SR 26-2 gaps directly.** Six PRs shipped in one sprint address the exact controls SR 26-2 examiners will inspect in a challenger-model review: coverage gate enforcement (test-outcome-analysis discipline), zip-slip sanitisation (evidence-bundle integrity), SQL injection prevention (data-integrity chain), and audit pack byte-determinism (same-inputs → identical-output guarantee). The determinism fix is the most competitively significant: no commercial AML platform publishes a same-spec + same-data + same-seed = identical-output guarantee.

**8 days to the Effectiveness NPRM + GENIUS Act NPRM dual deadline (June 9).** Firms that complete gap analyses before June 9 can use their comment-window work as documented evidence of proactive compliance posture in SR 26-2 model governance.

**30 days to AUSTRAC Tranche 2 enforcement (July 1).** No OSS AML framework has shipped an AUSTRAC-specific example spec. The window to position as the go-to open-source baseline for Australian DNFBPs is closing in 30 days.

---

## 1. Competitive Landscape — June 2026 Update

### Commercial enterprise platforms

**Veteran rules-plus-ML platforms (NICE Actimize SAM, Oracle FCCM, SymphonyAI, FIS/SAS AML).** SR 26-2 has been examination-active since April 17 — 45 days. Q2 2026 examination cycles are running. Second-line MRM teams are now presenting gap analyses to boards. The window for platforms to produce SR-26-2-aligned MRM documentation bundles is open, but the framework's challenger-model position is already established for the first examination cycle.

**AI-native challengers (ComplyAdvantage, Hawk:AI, Featurespace/Visa, Feedzai, Lucinity).** The ML-first model-validation burden under SR 26-2 is real and increasing with each examination cycle. A challenger that cannot produce a deterministic replay of a flagged alert — with identical output hashes across runs — fails the SR 26-2 independent-validation test.

**Graph/network specialists (Quantexa, Ripjar, Sayari).** No change. Slot remains case-level visualisation, not full MRM challenger.

### Open source — June 2026

- **Marble (checkmarble/marble):** Strongest direct alternative. Still has no Compliance Manifest, MRM bundle, or deterministic-rerun guarantee. SR 26-2 examination-active for 45 days — the gap is now being felt.
- **Jube (jube-home):** ML-first. SR 26-2 headwind unchanged.
- **FINOS OpenAML:** Labs-stage. No change.

No OSS competitor has shipped: (a) an AUSTRAC Tranche 2 example spec, (b) a PPSI/GENIUS Act compliance template, or (c) a deterministic-rerun audit guarantee. The framework is the only OSS option with all three in scope.

---

## 2. Where the Framework Wins — June 2026 Update

**The H0–H6 sprint closes the one remaining SR 26-2 gap: demonstrable test coverage of compliance-critical engine paths.** The coverage gate (H0) was non-enforcing — pytest-cov exits 0 on Linux below the threshold, so CI was green at 98.99% despite the advertised 99% floor. The gate is now enforced by a platform-independent script (`scripts/check_coverage_floor.py`). Combined with the determinism fix (audit pack now byte-identical across runs), the framework now satisfies all three SR 26-2 independent-challenger requirements: deterministic rerun, hash-chained audit ledger, and demonstrated test coverage of the scoring and audit logic.

**Zip-slip and SQL injection fixes (H2, H4) directly protect the regulator-evidence bundle.** The ZIP the examiner receives must contain only the intended evidence; the data the framework reads must be validated before it enters the hash chain. These aren't cosmetic — they are the controls that protect the evidential integrity SR 26-2 and the Effectiveness NPRM both require.

**GENIUS Act PPSI template window closes June 9.** The NPRM proposes BSA-program + OFAC sanctions compliance for permitted payment stablecoin issuers. The comment deadline is June 9 — 8 days. Publishing a PPSI-compliance reference template during the comment window positions the framework as the PPSI baseline before any competitor.

**AUSTRAC Tranche 2 deadline is July 1 — 30 days.** No OSS competitor exists. One PR, one new buyer segment, enforceable from July 1.

---

## 3. Highest-Leverage Next Features — June 2026 Re-ranking

| Priority | Feature | Days | Why now |
|---|---|---|---|
| #1 | **AUSTRAC Tranche 2 example spec** (`examples/austrac_tranche2/`) | 4 | July 1 enforcement. No OSS competitor. First-mover in an uncontested buyer segment. |
| #2 | **GENIUS Act / PPSI compliance template** (`examples/genius_act_ppsi/`) | 4 | June 9 comment deadline. Template during comment window = PPSI baseline positioning. |
| #3 | **SR 26-2 model inventory CLI** (`aml model-inventory`) | 3 | SR 26-2 45 days examination-active. Second-line MRM teams building inventory manually in Excel. One command → YAML output. |
| #4 | **FinCEN Whistleblower internal-channel audit tool** | 2 | Comment period closed today. Final rule coming late 2026. Internal-escalation audit is the pre-implementation action. |
| #5 | **AMLA STR/RTS effectiveness telemetry pack** | 6 | AMLA RTS submission July 10. Alert→case→STR funnel per-rule precision/recall, packaged against AMLA standard. |

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
