# AML Open Framework — Competitive Positioning Report: June 2026

*Date: 2026-06-03 · Last updated: 2026-06-16 · Scope: post-May 31 security hardening (H0–H6) + M1–M4 ML roadmap + Wave 2 governance completeness sprint · Companion: [`2026-06-regulator-pulse.md`](./2026-06-regulator-pulse.md) for the regulatory deadline context. Previous edition: [`2026-05-competitive-positioning.md`](./2026-05-competitive-positioning.md).*

> Refresh anchored 2026-06-01, updated through 2026-06-16. Six events now shape the competitive map since May 25: (1) the FinCEN Whistleblower NPRM comment period closed 2026-06-01; (2) the Effectiveness NPRM + GENIUS Act NPRM comment window **closed 2026-06-09** — both rulemakings are now pending (final rule expected late 2026 / early 2027); (3) AUSTRAC Tranche 2 enforcement is in **15 days** (2026-07-01); (4) AMLA RTS submission deadline is **24 days** out (2026-07-10); (5) M1–M4 ML roadmap shipped in v0.1.46–v0.1.47; (6) Wave 2 governance sprint (#523, #528, #529, #531) shipped AMLA RTS telemetry, Whistleblower audit CLI, Fraud↔AML case links, defect lifecycle, risk-tier on rules, and the model-risk approval gate — SR 26-2 **60 days examination-active**.
>
> *Updated 2026-06-16: Wave 2 governance sprint shipped. Priorities #3 (Whistleblower audit) and #4 (AMLA telemetry) are now ✅ SHIPPED. Priorities re-ranked.*

---

## What changed since June 4

**Wave 2 governance sprint fully delivered (2026-06-16).** Six features shipped across #523, #528, #529 (three features), #531 — the compliance-governance seam that completes the framework's North-Star pillars through Pillar 7:

- **AMLA RTS effectiveness telemetry** (#528) — `aml amla-effectiveness-report` emits the AMLA Art. 28/26/20 citation-coverage artifact AMLA examiners will require; surfaced as an EU-only tab on Framework Alignment (page 8). **This was priority #4 — now ✅ SHIPPED.**
- **FinCEN Whistleblower internal-channel audit** (#531) — `aml whistleblower-audit` rolls five governance signals into a `whistleblower_audit_report.json`; `--format nprm-gap` outputs a readiness table against the NPRM's proposed expectations. **This was priority #3 — now ✅ SHIPPED.**
- **Fraud↔AML cross-program case links** (#523) — `case_links.jsonl` frozen at run-end; UK APP-fraud demonstrator (`examples/uk_app_fraud/`); "Linked across domains" panel on Case Investigation page. The FRAML-convergence artifact PSR APP reimbursement and FinCEN NPRM "investigation outcomes" both require.
- **Defect-ticket lifecycle** (#529 / Pillar 2) — `aml defect-update` CLI; append-only `defect_lifecycle.jsonl` companion to the frozen `defect_log.jsonl`. Closes Pillar 2.
- **Risk tier on all active rules** (#529 / Pillars 4+5) — `Rule.risk_tier` expected on every active rule; WARN/strict-ERROR from `aml validate`; all 14 example specs updated.
- **Model-risk approval gate** (#529 / Pillar 7) — blocks unapproved material-tier rules in prod-strict mode; ledger-auditable. Closes Pillar 7.

**June 9 comment window has closed.** The Effectiveness NPRM + GENIUS Act NPRM dual deadline passed 2026-06-09. Both rulemakings are pending (final rule expected late 2026 / early 2027). Firms that completed a gap analysis or filed a comment letter during the window now hold that work as documented proactive-posture evidence. Firms that deferred should complete the gap analysis anyway — the 12-month implementation clock starts at the final rule.

**SR 26-2 is 60 days examination-active** (from April 17). Q2 examination cycles have run; Q3 cycles are forming. The M2 model-inventory CLI + Wave 2 approval-gate audit event are the exact artifacts Q3 board reports require.

**AUSTRAC Tranche 2 is 15 days away.** The framework ships `examples/austrac_tranche_2_dnfbp/` — no OSS competitor exists. AUSTRAC's first-cycle EU posture still applies to firms with documented good-faith compliance efforts; programs stood up before July 1 are inside that window.

---

## What changed since June 1

**June 9 comment deadline is now 5 days away.** The Effectiveness NPRM + GENIUS Act NPRM dual deadline has moved from "8 days" to "5 days." The last realistic working window for completing, reviewing, and filing comment letters is Friday June 5, with Monday June 8 the final business day before the Tuesday June 9 deadline for most firms. Any firm still relying on informal program frameworks for the PPSI NPRM is at high risk of filing no comment at all.

**SR 26-2 is 48 days examination-active** (up from 45 on June 1). Q2 2026 examination cycles are ongoing — second-line MRM teams are mid-presentation to boards, not starting gap analyses. The framework's challenger-model documentation bundle is the gap-filler for Q3 model-risk committee reports.

**AUSTRAC Tranche 2 is 27 days away.** No OSS competitor has moved on this in the 3 days since June 1. The first-mover window is narrowing: AUSTRAC's first-cycle enforceable undertaking posture applies to firms with *documented* good-faith compliance efforts — programs started now still qualify; programs started after July 1 do not.

---

## What changed since May 25

**FinCEN Whistleblower NPRM comment period closed Monday.** The comment period for the March 30 NPRM (10–30% of collected sanctions from a $300M fund) closed 2026-06-01. The **proposed** award structure is known in outline, but the terms are not settled — FinCEN will consolidate comments and a final rule is expected late 2026 / early 2027, so treat the percentages as proposed, not final. Even so, the incentive signal is real, substantial, and targeted at SAR-backlog and screening-gap failures. Compliance teams that haven't reviewed internal escalation channels since Q1 2026 are running behind.

**The May 31 security hardening sprint (H0–H6) closes SR 26-2 gaps directly.** Six PRs shipped in one sprint address the exact controls SR 26-2 examiners will inspect in a challenger-model review: coverage gate enforcement (test-outcome-analysis discipline), zip-slip sanitisation (evidence-bundle integrity), SQL injection prevention (data-integrity chain), and audit pack byte-determinism (same-inputs → identical-output guarantee). The determinism fix is the most competitively significant: no commercial AML platform publishes a same-spec + same-data + same-seed = identical-output guarantee.

**5 days to the Effectiveness NPRM + GENIUS Act NPRM dual deadline (June 9).** Firms that complete gap analyses before June 9 can use their comment-window work as documented evidence of proactive compliance posture in SR 26-2 model governance.

**27 days to AUSTRAC Tranche 2 enforcement (July 1).** No OSS AML framework has shipped an AUSTRAC-specific example spec. The window to position as the go-to open-source baseline for Australian DNFBPs is closing in 27 days.

---

## 1. Competitive Landscape — June 2026 Update

### Commercial enterprise platforms

**Veteran rules-plus-ML platforms (NICE Actimize SAM, Oracle FCCM, SymphonyAI, FIS/SAS AML).** SR 26-2 has been examination-active since April 17 — 48 days. Q2 2026 examination cycles are running. Second-line MRM teams are now presenting gap analyses to boards. The window for platforms to produce SR-26-2-aligned MRM documentation bundles is open, but the framework's challenger-model position is already established for the first examination cycle — and the M2 model-inventory CLI is the one-command gap-filler for teams still building inventory in Excel.

**AI-native challengers (ComplyAdvantage, Hawk:AI, Featurespace/Visa, Feedzai, Lucinity).** The ML-first model-validation burden under SR 26-2 is real and increasing with each examination cycle. A challenger that cannot produce a deterministic replay of a flagged alert — with identical output hashes across runs — fails the SR 26-2 independent-validation test. The M3 champion-challenger outcome report + temporal-leakage guard is the artifact none of these platforms can produce on demand.

**Graph/network specialists (Quantexa, Ripjar, Sayari).** No change. Slot remains case-level visualisation, not full MRM challenger.

### Open source — June 2026

- **Marble (checkmarble/marble):** Strongest direct alternative. Still has no Compliance Manifest, MRM bundle, or deterministic-rerun guarantee — and no SR 26-2 model inventory or champion-challenger outcome report. SR 26-2 examination-active for 48 days — the gap is now being felt and the M2 CLI widens it further.
- **Jube (jube-home):** ML-first. SR 26-2 headwind unchanged.
- **FINOS OpenAML:** Labs-stage. No change.

No OSS competitor has shipped: (a) an AUSTRAC Tranche 2 example spec, (b) a PPSI/GENIUS Act compliance template, or (c) a deterministic-rerun audit guarantee. The framework is the only OSS option with all three in scope.

---

## 2. Where the Framework Wins — June 2026 Update

**The H0–H6 sprint closes the one remaining SR 26-2 gap: demonstrable test coverage of compliance-critical engine paths.** The coverage gate (H0) was non-enforcing — pytest-cov exits 0 on Linux below the threshold, so CI was green at 98.99% despite the advertised 99% floor. The gate is now enforced by a platform-independent script (`scripts/check_coverage_floor.py`). Combined with the determinism fix (audit pack now byte-identical across runs), the framework now satisfies all three SR 26-2 independent-challenger requirements: deterministic rerun, hash-chained audit ledger, and demonstrated test coverage of the scoring and audit logic.

**Zip-slip and SQL injection fixes (H2, H4) directly protect the regulator-evidence bundle.** The ZIP the examiner receives must contain only the intended evidence; the data the framework reads must be validated before it enters the hash chain. These aren't cosmetic — they are the controls that protect the evidential integrity SR 26-2 and the Effectiveness NPRM both require.

**The M1–M4 ML roadmap ships the governed-augmentation seam no commercial platform publishes.** Triage Queue (M1) gives investigators a priority-scored, explainable alert queue — advisory-only, MRM-compliant. Model-inventory CLI (M2) emits the SR 26-2 inventory in one command. Champion-challenger outcome report (M3) with temporal-leakage guard is the independent-validation artifact SR 26-2 requires. Point-in-time joins (M4) closes Pillar 3 (PARTIAL → COVERED): reference data is resolved as-of each transaction, not from the latest row.

**GENIUS Act PPSI templates shipped ahead of the comment window close.** Two PPSI example specs (`genius_ppsi_issuer` + `genius_ppsi_stablecoin`) grounded in NPRM text are now the OSS baseline for permitted payment stablecoin issuers. The comment window closed June 9; the rulemaking is pending — the positioning carries into the pending-rule phase.

**AUSTRAC Tranche 2 example spec shipped — 15 days to enforcement.** `examples/austrac_tranche_2_dnfbp/` is in tree. No OSS competitor exists. AUSTRAC's first-cycle EU posture still applies to firms with documented good-faith compliance efforts standing up a program before July 1.

**Wave 2 governance sprint closes the compliance-governance seam commercial platforms don't publish.** The AMLA RTS telemetry CLI (#528) is the only OSS tool that produces the AMLA Art. 28/26/20 citation-coverage artifact on demand. The Whistleblower audit CLI (#531) is the only OSS tool mapping five internal-escalation governance signals against the FinCEN NPRM's proposed expectations. The fraud↔AML case-links artifact (#523) is the only OSS implementation of the FRAML convergence concept PSR APP reimbursement and FinCEN NPRM "investigation outcomes" both call for. The defect lifecycle (#529/Pillar 2), risk-tier validation (#529/Pillars 4+5), and model-risk approval gate (#529/Pillar 7) complete the North-Star governance pillars through Pillar 7.

---

## 3. Highest-Leverage Next Features — June 2026 Re-ranking (as of 2026-06-16)

| Priority | Feature | Status | Why now |
|---|---|---|---|
| ~~#1~~ | ~~**GENIUS Act / PPSI compliance template**~~ | ~~4 days~~ | **✅ SHIPPED** — `examples/genius_ppsi_issuer/` + `examples/genius_ppsi_stablecoin/` ship; comment window closed June 9. Two PPSI specs grounded in NPRM text now serve as baseline gap-analysis templates for the pending rulemaking. |
| ~~#2~~ | ~~**AUSTRAC Tranche 2 example spec**~~ | ~~4 days~~ | **✅ SHIPPED** — `examples/austrac_tranche_2_dnfbp/`. AUSTRAC Tranche 2 enforcement begins July 1 (15 days). No OSS competitor. |
| ~~#3~~ | ~~**FinCEN Whistleblower internal-channel audit tool**~~ | ~~2~~ | **✅ SHIPPED (#531)** — `aml whistleblower-audit` CLI; `whistleblower_audit_report.json` with five governance signals; `--format nprm-gap` readiness table. |
| ~~#4~~ | ~~**AMLA STR/RTS effectiveness telemetry pack**~~ | ~~6~~ | **✅ SHIPPED (#528)** — `aml amla-effectiveness-report` CLI; `amla_effectiveness_report.json`; AMLA Art. 28(1)/26/20(1)(d) citation-coverage table; surfaced on Framework Alignment page 8. |
| **#1** | **Regulatory-change diff watcher** (`compliance/regwatch.py`) | ~3 days | Hash every `regulation_ref` URL in every shipped spec; alert on drift. The Effectiveness NPRM's 12-month implementation tail makes stale `regulation_ref` values a live risk — a final rule that materially rewrites the BSA program rule will silently invalidate citations in existing specs. No commercial vendor ships this; the framework needs it precisely because it doesn't own the rule library. |
| **#2** | **PSD3 / Verification-of-Payee (VoP) ingestion adapter** (`data/psd3/`) | ~5 days | PSD3 is expected in the Official Journal H2 2026; the 24-month VoP/payee-name-match liability clock starts at publication. An OSS reference adapter before the clock starts positions the framework as the payments-ops baseline before any commercial module exists. |
| **#3** | **FINTRAC pre-examination audit pack** (`aml audit-pack --jurisdiction CA-FINTRAC`) | ~4 days | Canadian Schedule-I bank example spec is already in tree; FINTRAC's 2026 examination-manual update makes the pre-exam evidence demand explicit. Clones the SR 26-2 MRM-bundle pattern to a second jurisdiction — template for FCA-UK and BaFin-DE on the same skeleton. |

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
