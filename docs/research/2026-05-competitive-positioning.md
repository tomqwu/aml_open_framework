# AML Open Framework — Competitive Positioning Report: May 2026

*Date: 2026-05-25 · Scope: post-Round 6 (PR #72), 24 dashboard pages, 991 tests · Companion: [`2026-05-fintech-aml-reality.md`](./2026-05-fintech-aml-reality.md) for the FinTech buyer lens. Previous edition: [`2026-04-competitive-positioning.md`](./2026-04-competitive-positioning.md).*

> Refresh commissioned 2026-05-25, 38 days after the April edition. Three events materially shift the competitive map since April 29: SR 26-2 became operative on 17 April (it was 12 days old at last refresh; it is now 38 days old and examination-active); the GENIUS Act NPRM (April 8) created a new regulated buyer segment (permitted payment stablecoin issuers); and AUSTRAC's Tranche 2 enforcement deadline of 1 July 2026 places Australian DNFBPs inside the addressable market. All three are worked into the analysis below.

---

## What changed since April

**SR 26-2 is no longer incoming — it is the baseline.** The April edition noted SR 26-2 was "12 days old" and that examination cycles from Q2 2026 onward would test against it. By May 25, it is 38 days operative. OCC and Fed examiners are writing requests against it. The second-line model-risk persona — the framework's natural early-2026 champion — is no longer in procurement planning; it is in gap analysis. The window between "I need this" and "I need to document that I have it" is closing.

**GENIUS Act NPRM (April 8) adds a previously unregulated buyer segment.** Permitted payment stablecoin issuers (PPSIs) are proposed as financial institutions under the Bank Secrecy Act, requiring full BSA-program equivalents and — for the first time for any payment-system participant — a mandatory OFAC-specific sanctions compliance program under new 31 CFR Part 502. Comments due June 9. The framework's VASP/crypto tooling (ISO 20022, Travel Rule validator, multi-jurisdiction templating) is the fastest route to a PPSI-compliant posture in OSS.

**AUSTRAC Tranche 2 enforcement begins July 1.** Australian lawyers, accountants, real-estate agents, and dealers in precious metals and stones become enforceable from July 1. No OSS AML framework has shipped an AUSTRAC-specific example spec. The framework's multi-jurisdiction pattern can close that gap in one PR.

**OCC/FDIC reputation-risk final rule (April 7) reshapes risk-model documentation.** The joint final rule prohibiting reputation-based debanking means MLROs whose risk-rating models cite "reputation" as a rationale for high-risk-customer tiers must now re-document around concrete BSA/sanctions risk drivers. The Compliance Manifest's `regulation_ref` per-rule forces every risk rating to cite a specific regulatory basis — a rule that previously cited examiner pressure on customer type cannot survive the new rule.

---

## 1. Competitive Landscape

### Commercial enterprise platforms

**Veteran rules-plus-ML platforms — NICE Actimize SAM, Oracle FCCM, SymphonyAI Sensa-NetReveal, FIS/SAS AML.** These dominate Tier-1 RFPs by default. SR 26-2 adds a model-validation overhead to every ML scenario in these platforms — second-line teams are now asking vendors for SR-26-2-aligned documentation packages they cannot always produce quickly. The framework slots in as the **independent challenger model** — the third acceptable SR-26-2 validation method — without displacing the production engine.

**AI-native challengers — ComplyAdvantage, Hawk:AI, Featurespace (Visa), Feedzai, Lucinity.** SR 26-2 is a structural headwind: their ML-first designs now carry a model-validation tax on every typology. A challenger that reduces false positives but cannot produce an SR-26-2-aligned model inventory per scenario is harder to procure in a Cat-2+ examination cycle. Buyers now arrive to the framework specifically because SR 26-2 makes the ML-first alternative more expensive to govern.

**Graph/network specialists — Quantexa, Ripjar, Sayari.** No material change since April. Slot: case-level visualisation, not full graph-DB workloads.

**Regtech utilities — Fenergo, ComplyAdvantage data, Refinitiv WorldCheck.** Orthogonal.

### Open source / neighbour OSS

- **Marble (checkmarble/marble)** — AGPL/MIT, real-time decision engine, Go/TS stack. Strongest direct alternative. SR 26-2 gap: no Compliance Manifest as source-of-truth, no MRM bundle, no deterministic-rerun guarantee. The examination cycle makes that gap more visible to buyers.
- **Jube (jube-home)** — AGPLv3, ML-first. SR 26-2 is a direct headwind to ML-first OSS for the same reasons as commercial challengers.
- **FINOS OpenAML** — Labs-stage, on-chain focus. No change.

No OSS competitor has shipped an AUSTRAC example spec or a PPSI (GENIUS Act) compliance template.

### Internal "build it yourself"

Tier-1 / Tier-2 banks continue to build on Databricks/Snowflake lakehouses with bespoke rule libraries. SR 26-2's requirement for independent challenger validation is the new entrypoint: the production engine is not the target — the second-line validation artifact is. The framework displaces the **rule-authoring + audit-trail + MRM-documentation layers** of in-house stacks, while leaving the lakehouse storage layer untouched.

---

## 2. Where the Framework Actually Wins

**SR 26-2 is now examination-active — the independent challenger model is the slot.** Effective 17 April 2026, joint guidance explicitly lists independent re-implementation as one of three acceptable challenger-model validation methods for TM, sanctions screening, and CDD scoring. The framework's deterministic re-run + hash-chained audit ledger is the most complete OSS implementation of that method. No commercial platform publishes a same-Manifest + same-data + same-seed = identical-output guarantee. **Buyer: second-line MRM/validation function at any Cat-2+ bank.**

**GENIUS Act NPRM creates a new compliance buyer — the stablecoin issuer.** The April 8 NPRM proposes full BSA-program equivalents and a mandatory OFAC sanctions compliance program for PPSIs. No commercial platform has positioned specifically for PPSIs; the framework's existing VASP tooling (Travel Rule validator, multi-jurisdiction templating, `compliance/sandbox.py` for 314(b) / OFAC sharing) is the fastest route to a PPSI-defensible posture. Comment deadline June 9, 2026 — same day as the Effectiveness NPRM.

**AUSTRAC Tranche 2 enforcement July 1 creates an addressable Australian market.** No OSS framework has shipped an AUSTRAC-specific example spec. AUSTRAC's stated first-cycle posture favours enforceable undertakings for firms with documented good-faith programs. The framework's multi-jurisdiction pattern can serve as the template in one PR — the only OSS alternative for Australian DNFBPs with 37 days until enforcement.

**Reputation-risk final rule changes risk-model documentation.** The OCC/FDIC final rule (effective 60 days after Federal Register publication, April 7) prohibits examiner criticism based on reputation alone. MLROs must re-document risk-rating rationale around concrete BSA/sanctions risk drivers. The Compliance Manifest's mandatory `regulation_ref` per rule is the artefact that evidences the re-documentation. **Buyer: any bank that has used examiner pressure as cover to exit lawful-but-disfavoured segments (crypto, cannabis, MSBs, firearms).**

**ISO 20022 native ingestion.** SWIFT MX-only cutover was November 22, 2025; full structured-address deadline is November 2026. No OSS competitor has an ISO 20022 adapter in tree. Uncontested. **Buyer: correspondent-banking / payments-ops at challengers and VASPs.**

**Investigation-aggregator matching the Effectiveness NPRM framing.** FinCEN's NPRM frames effectiveness as the *investigation outcome chain* — suspicious activity identified, escalated, and reported — not alert volume. Deterministic INV-{sha256[:16]} grouping with auto-bundled STR ZIP (network Mermaid + narrative + goAML XML + manifest hash) is the right shape for the evidence the NPRM requires.

---

## 2.5. Where the framework lands by buyer archetype (May 2026 update)

| Archetype | Team size · program | Top-3 wins they care about | What's new in May vs. April |
|---|---|---|---|
| **★ FinTech / EMI applicant** | 1 MLRO, ≤5 FTE | (1) Pilot in weeks; (2) Cure-notice pack via one CLI command; (3) Sponsor-bank survival | Whistleblower NPRM makes internal-escalation documentation urgent even at small fintechs |
| **Mid-tier bank · pilot + 2LoD challenger** | 5-25 FTE | (1) Independent challenger model under SR 26-2 — **now examination-active**; (2) Per-rule MRM dossier + backtester; (3) ISO 20022 native ingestion | SR 26-2 shifted from "upcoming" to "current examination gap" — urgency is real |
| **Tier-1 bank · MRM challenger model** | 50+ FTE | (1) Deterministic re-run + hash-chained audit ledger; (2) SR-26-2-aligned MRM bundle; (3) Multi-jurisdiction templating | Q2-Q4 2026 are the first live SR 26-2 examination cycles — procurement motion is now |
| **Scaling fintech / VASP · cross-border** | 5-15 FTE | (1) ISO 20022 + Travel Rule validator; (2) INV-grouping + goAML XML; (3) Multi-jurisdiction templating | GENIUS Act NPRM adds stablecoin issuers as a buyer — VASP tooling serves PPSIs |
| **NEW: Australian DNFBP · Tranche 2** | 1-3 MLRO/compliance | (1) AUSTRAC example spec (gap in OSS market); (2) Pilot in weeks before July 1; (3) Board-approved program as enforcement defence | Enforcement begins July 1 — no OSS alternative exists |
| **NEW: Stablecoin issuer / PPSI** | 1-5 MLRO/compliance | (1) BSA-program equivalent via Compliance Manifest; (2) OFAC sanctions compliance posture; (3) VASP/Travel Rule tooling in the same binary | GENIUS Act NPRM creates first-ever BSA obligation for PPSIs — comment window closes June 9 |

---

## 3. Highest-Leverage Next Features (May 2026 re-ranking)

Re-ranked with the April 17 SR 26-2 effective date and June 9 / July 1 / July 10 deadlines as the decision axes.

### #1 — AUSTRAC Tranche 2 example spec (`examples/austrac_tranche2/`) · 4 days · IMPACT/EFFORT: HIGHEST
July 1 enforcement deadline for Australian lawyers, accountants, real-estate agents, DPMS. No OSS competitor has shipped this. AUSTRAC's first-cycle posture favours documented good-faith programs. The example spec is the documented good-faith program — one PR, one new buyer segment, zero OSS competition.
**Source:** [AUSTRAC Regulatory Expectations 2025–26](https://www.austrac.gov.au/amlctf-reform/austrac-regulatory-expectations-and-priorities-2025-26)

### #2 — GENIUS Act / PPSI compliance template (`examples/genius_act_ppsi/`) · 4 days · IMPACT/EFFORT: HIGHEST
FinCEN/OFAC NPRM proposes BSA-program + mandatory OFAC sanctions compliance for PPSIs. Comment deadline June 9 — same day as Effectiveness NPRM. Publishing a reference template during the comment window positions the framework as the PPSI compliance baseline before any competitor moves.
**Source:** [Federal Register 2026-06963](https://www.federalregister.gov/documents/2026/04/10/2026-06963/permitted-payment-stablecoin-issuer-anti-money-launderingcountering-the-financing-of-terrorism)

### #3 — SR 26-2 model inventory CLI command (`aml model-inventory`) · 3 days · IMPACT/EFFORT: HIGHEST
SR 26-2 requires every TM scenario, sanctions rule, CDD scoring model, and customer-risk-rating tool to be in a named model inventory. `aml model-inventory --output sr26-2-manifest.yaml` produces the inventory from the Compliance Manifest in one command. **Buyer: any second-line MRM team currently hand-building the inventory in Excel.**
**Source:** [SR 26-2](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm)

### #4 — Regulatory-change diff watcher (`compliance/regwatch.py`) · 3 days · IMPACT/EFFORT: HIGH
Hash every `regulation_ref` URL in every shipped spec; alert on drift. FinCEN Effectiveness NPRM will finalise late 2026 / early 2027, meaning every `regulation_ref` pointing to current BSA program rules will need updating. The watcher catches that automatically before the next examination cycle.
**Risk:** false positives on cosmetic page edits — mitigation: textual-diff threshold + human approval gate.

### #5 — AMLA STR/RTS effectiveness telemetry pack · 6 days · IMPACT/EFFORT: HIGH
Alert→case→STR funnel with per-rule precision/recall, packaged against the AMLA RTS due July 10, 2026. AMLA must submit final RTS to the Commission by July 10 — locking the standard for EU-supervised obliged entities. One feature, two regulators (AMLA + FinCEN), both with hard 2026 deadlines.
**Source:** [AMLA consultation landing page](https://www.amla.europa.eu/policy/public-consultations/consultation-draft-rts-criteria-identifying-business-relationships-occasional-and-linked_en)

---

## Sources

- [SR 26-2, FRB April 17 2026](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm)
- [SR 26-2 Attachment (full guidance)](https://www.federalreserve.gov/supervisionreg/srletters/SR2602a1.pdf)
- [OCC Bulletin 2026-13](https://www.occ.treas.gov/news-issuances/bulletins/2026/bulletin-2026-13.html)
- [FDIC FIL on SR 26-2](https://www.fdic.gov/news/financial-institution-letters/2026/agencies-revise-interagency-model-risk-management-guidance)
- [FinCEN AML Program NPRM, Federal Register 2026-07033](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs)
- [GENIUS Act NPRM, Federal Register 2026-06963](https://www.federalregister.gov/documents/2026/04/10/2026-06963/permitted-payment-stablecoin-issuer-anti-money-launderingcountering-the-financing-of-terrorism)
- [Treasury Press Release SB0435 — GENIUS Act NPRM](https://home.treasury.gov/news/press-releases/sb0435)
- [OCC / FDIC Final Rule: Reputation Risk prohibited, NR-IA-2026-26](https://www.occ.gov/news-issuances/news-releases/2026/nr-ia-2026-26.html)
- [FDIC FIL on reputation risk final rule](https://www.fdic.gov/news/financial-institution-letters/2026/agencies-issue-final-rule-prohibit-use-reputation-risk)
- [AUSTRAC: Regulatory expectations and priorities 2025–26](https://www.austrac.gov.au/amlctf-reform/austrac-regulatory-expectations-and-priorities-2025-26)
- [AUSTRAC AML/CTF Reform hub](https://www.austrac.gov.au/amlctf-reform)
- [AMLA — major step toward harmonised EU supervision](https://www.amla.europa.eu/amla-takes-major-step-toward-harmonised-eu-supervision_en)
- [AMLA advances preparations for 2027 selection exercise](https://www.amla.europa.eu/amla-advances-preparations-2027-selection-exercise_en)
- [SymphonyAI: Top 10 AML software for banks in 2026](https://www.symphonyai.com/resources/blog/financial-services/top-10-aml-software-banks-2026/)
- [Marble (checkmarble/marble) GitHub](https://github.com/checkmarble/marble)
- [Jube — open source AML & fraud TM](https://github.com/jube-home/aml-fraud-transaction-monitoring)
- [Databricks lakehouse AML pattern](https://www.databricks.com/blog/2021/07/16/aml-solutions-at-scale-using-databricks-lakehouse-platform.html)
- [Hawk:AI Series C, SiliconANGLE 2025-04-08](https://siliconangle.com/2025/04/08/hawk-secures-56-million-expand-financial-crime-detection-platform/)
- [FATF Plenary outcomes, February 2026](https://www.fatf-gafi.org/en/publications/Fatfgeneral/outcomes-FATF-plenary-february-2026.html)
- [BNY: ISO 20022 end-of-coexistence (Nov 22 2025)](https://www.bny.com/assets/corporate/documents/pdf/iso-20022-end-of-coexistence_-may-2025-final.pdf)
- [FinCEN Whistleblower NPRM, Federal Register 2026-06271](https://www.federalregister.gov/documents/2026/04/01/2026-06271/whistleblower-incentives-and-protections)
