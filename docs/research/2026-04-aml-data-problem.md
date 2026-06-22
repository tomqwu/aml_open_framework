# Data is the AML problem — April 2026

*Date: 2026-04-29 · Audience: CCO / MLRO / Head of Financial Crime / CRO / 2LoD model-validation. Companion docs: [`2026-04-aml-process-pain.md`](./2026-04-aml-process-pain.md) for the leader-pain style guide; [`2026-04-competitive-positioning.md`](./2026-04-competitive-positioning.md) for the vendor landscape. Next edition: [`2026-05-aml-data-problem.md`](./2026-05-aml-data-problem.md).*

> **Archive edition.** This is the April 2026 snapshot of the data-problem analysis — added to the archive in Round 37 (2026-06-22) to close the gap noted in issue #561 (the April research archive was 4/5 editions). The May edition ([`2026-05-aml-data-problem.md`](./2026-05-aml-data-problem.md)) picks up the SR 26-2 (April 17) and FinCEN Effectiveness NPRM (April 10) context that defines the current enforcement posture; start there for the complete analysis.

---

## What defined the data-problem landscape in April 2026

Three events in the April window reshaped the data-layer enforcement perimeter:

**2026-04-17 · SR 26-2 goes live.** The joint Fed/OCC/FDIC model risk management guidance became effective on April 17, superseding both SR 11-7 (2011) and the 2021 BSA/AML-specific SR 21-8. Transaction monitoring, sanctions screening, customer risk-rating, and CDD scoring models are now in the model-risk inventory with documentation requirements. The key data implication: before a model's conceptual soundness can be validated under SR 26-2, the completeness and accuracy of its training and inference data must be documented. **DATA-6** (AI presumes data we don't have) becomes an examiner-facing issue, not just an architectural concern.

**2026-04-10 · FinCEN Effectiveness NPRM published.** The joint FinCEN/OCC/FDIC/NCUA NPRM (Federal Register 2026-07033) proposes reframing the BSA program rule around an "effective, risk-based, reasonably designed" standard. The NPRM's "risk assessment as a pillar" requirement elevates DATA-1 through DATA-8: a board-approved, documented enterprise-wide risk assessment becomes a program pillar, not expected practice. Institutions that cannot trace how each detector was designed relative to the risk assessment cannot demonstrate the "effective, risk-based, reasonably designed" standard. *Comment deadline: 2026-06-09 (now closed).*

**2026-04-10 · GENIUS Act PPSI NPRM published.** FinCEN and OFAC jointly propose treating permitted payment stablecoin issuers (PPSIs) as financial institutions under the Bank Secrecy Act. Stablecoin transaction flows use ISO 20022 pacs.008/009/004 formats — **DATA-8** (MLRO has no veto over data shape) applies directly. *Comment deadline: 2026-06-09 (now closed).*

---

## The 11 faces of the data problem — April 2026 baseline

The DATA-1 through DATA-11 framework introduced in the May 2026 edition applies from this baseline. See [`2026-05-aml-data-problem.md`](./2026-05-aml-data-problem.md) for the full analysis and the artifact map. The April inflection points above are what moved each DATA-N from "architectural awareness" to "examiner-facing risk":

| Pain | April 2026 inflection |
|---|---|
| **DATA-1** — Can't capture what we don't have | SR 26-2 requires model-inventory documentation: gaps in input data now surface in MRM examinations, not just alert counts |
| **DATA-2** — Stale beats stale | SR 26-2 ongoing-monitoring requirement highlights reference-data freshness as a first-class model characteristic |
| **DATA-3** — Three systems, three answers | Effectiveness NPRM's "reasonably designed" standard requires demonstrating that controls run on consistent, reconciled data |
| **DATA-4** — Where did this number come from? | SR 26-2 requires outcome analysis and lineage — the "14% increase" question becomes a model-governance question |
| **DATA-5** — Your data leaves our perimeter | OSFI B-13 / EBA outsourcing in force; SR 26-2 adds a US-side MRM dimension to cloud-vendor risk |
| **DATA-6** — AI presumes data we don't have | SR 26-2 is the first US guidance that explicitly requires model-inventory documentation for AML TM scenarios |
| **DATA-7** — Engineering owns the warehouse | Effectiveness NPRM's program-pillar framing makes the boundary explicit: the documented risk assessment must cover the data the controls depend on |
| **DATA-8** — MLRO has no veto over data shape | Effectiveness NPRM + GENIUS Act NPRM both require the MLRO to attest to a program that may depend on data she did not design |
| **DATA-9** — SAR we filed vs SAR we should have filed | Effectiveness NPRM: "suspicious activity identified, escalated, and reported" is the effectiveness metric — data continuity is the enabler |
| **DATA-10** — Can't see what the other bank is seeing | FATF R.18 + FinCEN 314(b) posture unchanged; Effectiveness NPRM references cross-bank program coverage |
| **DATA-11** — Compliance-defensible answer is a data contract | The Compliance Manifest's data-contract layer is the direct response to the Effectiveness NPRM's risk-assessment pillar |

---

## Sources

- [FRB SR 26-2 — Revised Model Risk Management guidance (effective April 17, 2026)](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm)
- [OCC Bulletin 2026-13 — Model Risk Management](https://www.occ.treas.gov/news-issuances/bulletins/2026/bulletin-2026-13.html)
- [FinCEN — AML Program Effectiveness NPRM, Federal Register 2026-07033 (April 10, 2026)](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs)
- [FinCEN + OFAC — GENIUS Act PPSI NPRM, Federal Register 2026-06963 (April 10, 2026)](https://www.federalregister.gov/documents/2026/04/10/2026-06963/permitted-payment-stablecoin-issuer-anti-money-launderingcountering-the-financing-of-terrorism)
- [BCBS 239 — Principles for effective risk data aggregation and risk reporting (BIS, January 2013)](https://www.bis.org/publ/bcbs239.pdf)
- [BCBS d559 — 2023 Progress in adopting BCBS 239 principles](https://www.bis.org/bcbs/publ/d559.htm)
- [OSFI — Guideline B-13 Technology and Cyber Risk Management (2022)](https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/guideline-b-13-technology-and-cyber-risk-management)
- [EBA — Guidelines on outsourcing arrangements EBA/GL/2019/02](https://www.eba.europa.eu/activities/single-rulebook/regulatory-activities/internal-governance/guidelines-outsourcing-arrangements)
