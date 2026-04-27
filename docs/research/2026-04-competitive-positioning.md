# AML Open Framework — Competitive Positioning Report

*Date: 2026-04-27 · Scope: post-Rounds 5-6 (PR #72), 24 dashboard pages, 991 tests*

> Deep-research output commissioned 2026-04-27 after Rounds 5-6 shipped. Author: deep-research-agent. Methodology: ~10 min web research across vendor sites, regulator notices, OSS repos, and industry analyst blogs. Sources at the bottom of the file.

---

## 1. Competitive Landscape

### Commercial enterprise platforms

The 2026 buyer field separates into four archetypes, and the framework competes against each differently.

**Veteran rules-plus-ML platforms — NICE Actimize SAM, Oracle FCCM, SymphonyAI Sensa-NetReveal, FIS/SAS AML.** These dominate Tier-1 RFPs by default; Actimize-style vendors win on enterprise-scale detection, regulator familiarity, and decades of typology libraries ([SymphonyAI 2026 roundup](https://www.symphonyai.com/resources/blog/financial-services/top-10-aml-software-banks-2026/), [Alessa 2026 roundup](https://alessa.com/blog/top-10-transaction-monitoring-software-solutions/)). Differentiator: scale + audit comfort. Where the framework slots in: **proof-of-concept tier** at large banks (where Actimize's ~18-24-month deploy costs $50M+ TCO per [Tookitaki 2025 buyer guide](https://www.tookitaki.com/compliance-hub/best-aml-solution-for-banks-2025)), and as a **second-line challenger model** for MRM independent re-implementation under SR 26-2.

**AI-native challengers — ComplyAdvantage, Hawk:AI, Featurespace (Visa), Feedzai, Lucinity.** Hawk:AI raised a $56M Series C in April 2025 and another $10M in Jan 2026 explicitly for "AML-as-a-service" ([SiliconAngle 2025-04-08](https://siliconangle.com/2025/04/08/hawk-secures-56-million-expand-financial-crime-detection-platform/)). They differentiate on cloud-native deployment, claimed false-positive reduction (ComplyAdvantage cites 65–85%, [ComplyAdvantage TM page](https://complyadvantage.com/vendor/best-transaction-monitoring-software/)), and explainable-AI marketing. The framework slots in **adjacent, not opposed** — challengers win mid-market RFPs where the framework currently has no commercial sales motion; it competes for the same buyer only when the buyer specifically wants source-available code.

**Graph/network specialists — Quantexa, Ripjar, Sayari.** Quantexa's "contextual decision intelligence" graph is the marketed differentiator for complex layering investigations. The framework's `network_pattern` rule plus Mermaid renders is **functionally narrower** but ships in one binary; Quantexa requires multi-quarter integration. Slot: useful for case-level visualisation, not full graph-DB workloads.

**Regtech utilities — Fenergo (KYC orchestration), ComplyAdvantage data, Refinitiv WorldCheck.** Mostly orthogonal — they sell data and onboarding, not detection.

### Open source / neighbour OSS

Three projects are real competitors today:

- **Marble (checkmarble/marble)** — the only commercially-backed OSS competitor, AGPL/MIT split, real-time decision engine, no-code rule builder, AI investigation assistant ([Marble README](https://github.com/checkmarble/marble), [Marble docs](https://docs.checkmarble.com/docs/welcome-to-marble)). Strongest direct alternative; strength is the no-code UX and modern Go/TS stack. Weakness vs. AML Open Framework: no spec-as-source-of-truth, no MRM bundle, no jurisdiction-specific reporting templates, no deterministic-rerun guarantee.
- **Jube (jube-home)** — AGPLv3, ML-first (adaptive ANN), real-time scoring + workflow ([Jube repo](https://github.com/jube-home/aml-fraud-transaction-monitoring)). Differentiates on built-in models. Weakness: ML-first design is exactly what FinCEN's NPRM and SR 26-2 push back against (model risk surface).
- **FINOS OpenAML (finos-labs/dtcch-2025-OpenAML)** — DTCC hackathon origin, on-chain AML focus, ML-classification of wallets ([FINOS OpenAML repo](https://github.com/finos-labs/dtcch-2025-OpenAML)). Narrow scope (crypto wallets), labs-stage, not a TM platform.

Apache Fineract, OpenCRE and Frankfurter are *adjacent* (core banking, control mappings, FX rates) — none compete on detection.

### Internal "build it yourself"

Tier-1 / Tier-2 banks predominantly **build on Databricks/Snowflake lakehouses** with bespoke Spark or SQL rule libraries, plus a commercial alert manager bolted on top ([Databricks AML pattern](https://www.databricks.com/blog/2021/07/16/aml-solutions-at-scale-using-databricks-lakehouse-platform.html), [Tookitaki 2025](https://www.tookitaki.com/compliance-hub/best-aml-solution-for-banks-2025)). Build-cost cited at >$50M/5y; only viable above ~5B txns/month. The framework displaces **the rule-authoring + audit-trail + reporting layers** of these stacks (which are the parts banks consistently underinvest in), while leaving the lakehouse storage layer untouched. The persona that lands is the **second-line model-risk team** that needs an independent, reproducible re-implementation to validate the production engine — not the production engine itself.

---

## 2. Where the Framework Actually Wins

**Defensible "every line written by a human" moat.** FinCEN's April 2026 NPRM and SR 26-2 (joint Fed/OCC/FDIC, [SR 26-2 letter](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm), effective April 17 2026) explicitly fold BSA/AML transaction monitoring, sanctions screening and CDD into the model-risk inventory. ML-first vendors (Hawk, Feedzai, Jube) now carry a model-validation tax on every typology; the framework's YAML rules with `regulation_ref` are not models under SR 26-2 — they are policy artefacts. **Buyer that lands: second-line MRM/validation function at any Cat-2+ bank, plus FinCEN/OCC examiners.**

**Deterministic re-run + hash-chained audit ledger.** Every commercial platform produces operational logs; none publish a same-spec + same-data + same-seed = identical-output guarantee. Combined with the Round-3 MRM bundle (SR 26-2 / OCC 2026-13 aligned), this makes the framework usable as the **independent challenger model** the new guidance now expects, without buying a second commercial license. Buyer: MRM Director / Chief Model Risk Officer.

**ISO 20022 native ingestion (Round 5).** SWIFT MX-only cutover was 2025-11-22 ([BNY end-of-coexistence note](https://www.bny.com/assets/corporate/documents/pdf/iso-20022-end-of-coexistence_-may-2025-final.pdf)); full structured-address deadline is Nov 2026. Marble, Jube, OpenAML have no ISO 20022 adapter in tree. Commercial — Actimize, ComplyAdvantage, Hawk all support it but as a paid module, not a documented spec. Shipping pacs.008/009/004 + pain.001 + Travel-Rule field validator + 28-row purpose-code reference + 44-row return-reason library as one binary is currently **uncontested in OSS and cheaper than any commercial module**. Buyer: correspondent-banking / payments-ops team at a challenger or VASP.

**Investigation-aggregator vs. alert-centric platforms (Round 6).** FinCEN's NPRM language switched to "investigation outcomes" as the unit of effectiveness; deterministic INV-{sha256[:16]} grouping with three explicit strategies plus auto-bundled STR ZIP (network Mermaid + narrative + goAML XML + manifest) is the right shape. Most commercial platforms still measure SAR-per-alert, not investigation-per-typology. Buyer: BSA Officer / FIU lead at challenger banks; also consultancies running pre-exam mock reviews.

**One-binary deployability.** Pip-installable, DuckDB-in-memory, Streamlit + FastAPI in the same repo. Time-to-first-alert measured in minutes vs. the 9-24 month commercial deploys ([Tookitaki 2025](https://www.tookitaki.com/compliance-hub/best-aml-solution-for-banks-2025)). Buyer: regtech consultancies (mock RFP-responder kits), fintech compliance teams, academic FinCrime programmes.

**Multi-jurisdiction templating.** 7 example specs covering US/CA/EU/UK/VASP/cyber-fraud is unmatched in OSS and rare commercially (most vendors charge per-jurisdiction module). Buyer: cross-border challenger banks, EMI/PI applicants needing AMLA-ready evidence.

What it does **not** win on: real-time sub-second scoring at billions-of-txns scale, sales/support contracts, vendor risk-management process for tier-1 procurement, brand recognition.

---

## 3. Highest-Leverage Next Features

Excluded by memory: generative-AI rule authoring, native graph DB, in-tree alert-scoring ML.

Already on the user's Rounds 7-9 plan but **re-ranked with current evidence** — the AMLA July 2026 deadline ([AMLA portal](https://www.amla.europa.eu/amla-takes-major-step-toward-harmonised-eu-supervision_en)) and the FinCEN NPRM comment-period closing June 9 2026 ([Federal Register 2026-07033](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs)) reshuffle the impact ÷ effort math.

### #1 — Regulatory-change diff watcher (`compliance/regwatch.py`) · 3 days · IMPACT/EFFORT: HIGHEST
Hash every `regulation_ref` URL in every shipped spec; alert on drift. **Why now:** FinCEN BOI was narrowed in March 2025 ([FinCEN BOI page](https://www.fincen.gov/boi)) and FinCEN's April 7 2026 NPRM materially rewrites AML program requirements with a 12-month implementation tail — every example spec's regulator reference is at risk of going stale silently. No commercial vendor ships this because they own the rule library themselves; the framework needs it precisely because it doesn't.
**Risk:** false positives on cosmetic page edits (mitigation: textual-diff threshold + human approval gate).

### #2 — AMLA STR/RTS effectiveness telemetry pack (`metrics/outcomes.py` + `examples/amla_rts_2026/`) · 6 days · IMPACT/EFFORT: HIGH
Alert→case→STR funnel with per-rule precision/recall, packaged against the AMLA RTS due July 10 2026 ([AMLA 23 mandates](https://www.amla.europa.eu/amla-takes-major-step-toward-harmonised-eu-supervision_en), [Protiviti AMLA readiness](https://blog.protiviti.com/2026/03/16/amla-readiness-starts-now-ten-practical-moves-for-2026/)). FinCEN's NPRM enumerates the same metrics. One feature, two regulators, both with hard 2026 deadlines.
**Risk:** outcome data depends on case-disposition labels the framework doesn't currently demand — needs schema additions to cases, not just metrics.

### #3 — TBML + APP-fraud spec pair (`examples/trade_based_ml/` + `examples/uk_app_fraud/`) · 9 days · IMPACT/EFFORT: HIGH
TBML covers FATF/Egmont's continuing focus area (cited in the [FATF Feb 2026 plenary outcomes](https://www.fatf-gafi.org/en/publications/Fatfgeneral/outcomes-FATF-plenary-february-2026.html)); APP-fraud covers the [PSR's expanding scope to CHAPS + Q2 2026 joint review](https://www.psr.org.uk/information-for-consumers/app-scams-reimbursement-dashboard/). Together they answer the FRAML-convergence buyer question ([Hawk FRAML report](https://hawk.ai/news-press/report-us-banks-credit-unions-embracing-framl), [Sutherland FRAML 2.0](https://www.sutherlandglobal.com/insights/blog/framl-for-risk-and-compliance)) without building a fraud engine — just demonstrating the framework can express the typologies.
**Risk:** spec authenticity — needs a real practitioner review or it reads as theoretical (mitigation: cite specific PSR / Egmont indicator lists).

### #4 — PSD3 / Verification-of-Payee (VoP) ingestion adapter (`data/psd3/`) · 5 days · IMPACT/EFFORT: MEDIUM-HIGH
PSD3 + PSR are expected in the Official Journal end-Q2 2026, with VoP / payee-name-match liability applying 24 months after entry into force ([Norton Rose Fulbright PSD3 brief](https://www.nortonrosefulbright.com/en/knowledge/publications/cedd39c6/psd3-and-psr-from-provisional-agreement-to-2026-readiness), [Linklaters PSD3 update](https://financialregulation.linklaters.com/post/102lw90/psd3-breakthrough-eu-legislators-agree-payments-regulation-reforms)). Lands a payments-ops persona that today has no OSS option. **Why now:** the 2-year clock is the right window for a reference implementation to exist before banks have to procure one.
**Risk:** spec instability between Council/Parliament agreement and Official Journal publication — mark the adapter "draft" with a version pinned to the agreed text.

### #5 — FINTRAC pre-examination audit pack (`aml audit-pack --jurisdiction CA-FINTRAC`) · 4 days · IMPACT/EFFORT: MEDIUM-HIGH
The Canadian Schedule-I bank example spec is already in tree; FINTRAC's January 2026 examination manual update ([FINTRAC examination guidance](https://fintrac-canafe.canada.ca/guidance-directives/exam-examen/eng)) makes the pre-exam evidence demand explicit. Clones the SR 26-2 MRM-bundle pattern to a second jurisdiction with proven format. Aligns with the user's stated Canadian-bank focus (memory).
**Risk:** small TAM (Canadian FIs only); mitigation is to use it as the template for a 3rd/4th jurisdiction (FCA-UK, BaFin-DE) on the same skeleton.

### Notable omissions, ranked by why-not

- **AMLA central-register sandbox (Round 9 #5).** Real signal but the register isn't operational until H2 2026 and the API surface is still in [EBA advice](https://www.step.org/industry-news/eba-issues-advice-aml-standards-ahead-amla-operational-launch). Defer until Q3 2026.
- **Notabene/Sumsub Travel-Rule message-bus adapters (Round 7 #4).** Already covered by Round 5's Travel Rule field validator at the spec layer; the message-bus integration is a vendor-specific runtime feature that bloats the binary.
- **FedNow/RTP push-fraud detector pack (Round 8 #2).** Genuinely valuable but requires the APP-fraud spec to land first as the shape-template; sequence after #3.

---

## Sources

- [SymphonyAI: Top 10 AML software for banks in 2026](https://www.symphonyai.com/resources/blog/financial-services/top-10-aml-software-banks-2026/)
- [Alessa: Top 10 Transaction Monitoring Solutions 2026](https://alessa.com/blog/top-10-transaction-monitoring-software-solutions/)
- [ComplyAdvantage: Best transaction monitoring software 2026](https://complyadvantage.com/vendor/best-transaction-monitoring-software/)
- [Tookitaki: Best AML Solutions for Banks 2025](https://www.tookitaki.com/compliance-hub/best-aml-solution-for-banks-2025)
- [Hawk:AI Series C, SiliconANGLE 2025-04-08](https://siliconangle.com/2025/04/08/hawk-secures-56-million-expand-financial-crime-detection-platform/)
- [Marble (checkmarble/marble) GitHub](https://github.com/checkmarble/marble)
- [Marble docs](https://docs.checkmarble.com/docs/welcome-to-marble)
- [Jube — open source AML & fraud TM](https://github.com/jube-home/aml-fraud-transaction-monitoring)
- [FINOS Labs — OpenAML](https://github.com/finos-labs/dtcch-2025-OpenAML)
- [Databricks lakehouse AML pattern](https://www.databricks.com/blog/2021/07/16/aml-solutions-at-scale-using-databricks-lakehouse-platform.html)
- [SR 26-2 Revised Model Risk Management guidance, FRB 2026-04-17](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm)
- [OCC Bulletin 2026-13 — Model Risk Management](https://www.occ.treas.gov/news-issuances/bulletins/2026/bulletin-2026-13.html)
- [FinCEN AML Program NPRM, Federal Register 2026-04-10](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs)
- [FinCEN NPRM Fact Sheet (PDF)](https://www.fincen.gov/system/files/2026-04/Program-NPRM-FactSheet.pdf)
- [WilmerHale FinCEN NPRM client alert 2026-04-13](https://www.wilmerhale.com/en/insights/client-alerts/20260413-fincen-issues-proposed-rule-revising-the-aml-program-requirements-for-financial-institutions)
- [AMLA — major step toward harmonised EU supervision](https://www.amla.europa.eu/amla-takes-major-step-toward-harmonised-eu-supervision_en)
- [Moody's: AMLA & AMLR review 2026](https://www.moodys.com/web/en/us/kyc/resources/insights/a-review-of-amla-and-amlr-2026.html)
- [Protiviti: AMLA Readiness Starts Now 2026-03-16](https://blog.protiviti.com/2026/03/16/amla-readiness-starts-now-ten-practical-moves-for-2026/)
- [STEP: EBA advice on AML standards ahead of AMLA launch](https://www.step.org/industry-news/eba-issues-advice-aml-standards-ahead-amla-operational-launch)
- [FATF Plenary outcomes, Feb 2026](https://www.fatf-gafi.org/en/publications/Fatfgeneral/outcomes-FATF-plenary-february-2026.html)
- [FATF Plenary outcomes, Oct 2025 — AI horizon scan](https://complyadvantage.com/insights/fatf-plenary-october-2025/)
- [PSR APP scams reimbursement dashboard, Q3 2025](https://www.psr.org.uk/information-for-consumers/app-scams-reimbursement-dashboard/)
- [Norton Rose Fulbright: PSD3 / PSR 2026 readiness](https://www.nortonrosefulbright.com/en/knowledge/publications/cedd39c6/psd3-and-psr-from-provisional-agreement-to-2026-readiness)
- [Linklaters: PSD3 breakthrough](https://financialregulation.linklaters.com/post/102lw90/psd3-breakthrough-eu-legislators-agree-payments-regulation-reforms)
- [Hawk: FRAML convergence US banks/credit unions](https://hawk.ai/news-press/report-us-banks-credit-unions-embracing-framl)
- [Sutherland: FRAML 2.0 for Risk & Compliance](https://www.sutherlandglobal.com/insights/blog/framl-for-risk-and-compliance)
- [BNY: ISO 20022 end-of-coexistence (Nov 22 2025)](https://www.bny.com/assets/corporate/documents/pdf/iso-20022-end-of-coexistence_-may-2025-final.pdf)
- [NICE Actimize: ISO 20022 Nov 2025 deadline](https://www.niceactimize.com/blog/aml-iso-20022-deadline)
- [FINTRAC examination guidance](https://fintrac-canafe.canada.ca/guidance-directives/exam-examen/eng)
- [FinCEN BOI page](https://www.fincen.gov/boi)
