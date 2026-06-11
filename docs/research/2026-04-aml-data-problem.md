# Data is the AML problem — April 2026

*Date: 2026-04-09 · Audience: CCO / MLRO / Head of Financial Crime / CRO / 2LoD model-validation. Companion docs: [`2026-04-aml-process-pain.md`](./2026-04-aml-process-pain.md) for the leader-pain style guide; [`2026-04-competitive-positioning.md`](./2026-04-competitive-positioning.md) for the vendor landscape. Next edition: [`2026-05-aml-data-problem.md`](./2026-05-aml-data-problem.md).*

## What changed between March and April 2026

*Updated 2026-04-09.*

### FRB SR 26-2 effective April 17, 2026 — model-risk perimeter expands to AML

FRB SR 26-2 (with companion OCC Bulletin 2026-13) becomes effective **April 17, 2026** — eight days from publication of this edition. US-supervised banks must now treat BSA/AML transaction monitoring, sanctions screening, and customer-risk-rating models under the same model-risk management framework as credit and market models. The SR 11-7 / OCC 2011-12 inventory, conceptual-soundness, and independent-challenge requirements now formally extend to AML. **DATA-6** (AI presumes data we don't have) moves from a regulatory-posture expectation to an examination requirement: before an AML model's conceptual soundness can be validated, the completeness and accuracy of its training and inference data must be documented. The `aml model-inventory` CLI is the tool that produces that inventory on demand (v0.1.47 M2, shipped 2026-06-04).

### FinCEN Effectiveness NPRM + GENIUS Act PPSI NPRM published April 10, 2026

FinCEN, OCC, FDIC, and NCUA jointly published the AML/CFT Program Effectiveness NPRM ([Federal Register 2026-07033](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs)) on April 10, 2026, with a public comment deadline of **June 9, 2026**. On the same date, FinCEN and OFAC published the GENIUS Act PPSI NPRM ([Federal Register 2026-06963](https://www.federalregister.gov/documents/2026/04/10/2026-06963/permitted-payment-stablecoin-issuer-anti-money-launderingcountering-the-financing-of-terrorism)) with the same June 9 deadline. The Effectiveness NPRM's "risk assessment as a pillar" requirement, if finalised as proposed, formally elevates DATA-1 through DATA-8 from process expectations to program-structure requirements. Comments are open through June 9.

### AUSTRAC Tranche 2 — 83 days to enforcement (July 1, 2026)

AUSTRAC's Tranche 2 AML/CTF reform brings Australian lawyers, accountants, real-estate agents, and dealers in precious metals and stones (DPMS) under mandatory AML/CTF obligations **effective July 1, 2026 — 83 days from this edition**. AUSTRAC has published its regulatory expectations for 2025–26 confirming that enrolment and a board-approved AML/CTF program are required from day one. The framework's AU/AUSTRAC example spec (`examples/au_dnfbp/aml.yaml`) covers all four DNFBP categories with SMR/TTR filing.

### AMLA consultation windows closing April–May 2026

AMLA's CDD RTS and business-relationships RTS consultation windows close in April and May 2026. Institutions operating in 6+ EU member states should complete their alignment-gap assessments before these consultations close — the window to influence the standard is measured in weeks. The statutory RTS submission deadline to the European Commission is July 10, 2026 (91 days from this edition).

## How to read this doc

The pain doc argues that **audit-defensibility, not detection, is the dominant pain in 2026**. This doc argues the next layer down: **the binding constraint underneath audit-defensibility is data**. Detection presumes data the bank often does not have. Audit-defensibility presumes a lineage the bank often cannot reproduce. Vendor AI presumes a quality of input that public enforcement orders show does not exist.

That claim is not novel; what is new in 2026 is that regulators are now writing it down. FinCEN's April 2026 NPRM, OSFI's September 2025 letter and revised E-23, the Basel Committee's 2023 progress report on BCBS 239, and the FCA's March 2024 Annex 1 letter all converge on the same thesis from different angles. This document collects the language they use and maps each claim to the framework capability that responds to it.

Three rules behind the analysis below — they mirror the pain doc's rules and apply identically here:

1. **Audit-defensibility, not detection, is the dominant pain.** Across recent enforcement orders surveyed (TD 2024, RBC 2023, HSBC 2012, Wells 2024, NatWest), regulators rarely allege the bank missed a typology — they allege the bank could not produce the data, evidence the lineage, or reconcile the systems. *The data problem is the audit-defensibility problem one layer down.*
2. **CCOs publicly say "alert volume," but the underlying ailment is "alert quality" — and quality is a function of data.** A 95% false-positive rate is what you get when you run a typology against incomplete KYC, stale customer profiles, and unreconciled transaction streams. *Frame data work in terms of analyst attention bought.*
3. **Write the way regulators speak.** "We failed to capture all material risk data." "The bank could not aggregate exposures fully, quickly and accurately." "Decisions were not supported by an audit trail." These are the actual primary-source phrases — copy them before paraphrasing.

This doc uses the **DATA-N** identifier convention. Future docs (deck slides, dashboard descriptions, README sections) should cite DATA-N the same way they cite PAIN-N.

---

## The 11 faces of the data problem

### DATA-1 · "We can't capture what we don't have."

| | |
|---|---|
| **Plain-English description** | The bank's typology fires on data the bank thinks it has. A subset of customers have no occupation field. A subset of corporate clients have no UBO record. A whole product line was onboarded before the current KYC schema existed. The detector cannot fire on what was never captured — and the regulator counts the gap, not the alert. |
| **Primary source** | BCBS 239 Principle 4 — Completeness: *"A bank should be able to capture and aggregate all material risk data across the banking group."* — [BCBS 239, BIS, January 2013](https://www.bis.org/publ/bcbs239.pdf). The Basel Committee's 2023 implementation progress report finds that, more than a decade after publication, *"banks are at different stages in terms of alignment"* and *"significant work remaining at most banks"* — [BCBS d559 progress report](https://www.bis.org/bcbs/publ/d559.htm). TD Bank (FinCEN, October 2024): TD allowed *"trillions of dollars in transactions annually to go unmonitored"* — the ultimate completeness failure. — [FinCEN release](https://www.fincen.gov/news/news-releases/fincen-assesses-record-13-billion-penalty-against-td-bank). |
| **Roles affected** | CCO, MLRO, 1LoD analyst, 2LoD model validation, Internal Audit |
| **Cost type** | Audit-defensibility |
| **Framework capability** | Every detector declares its `data_contract` — the schema it depends on. The validator fails closed if the schema isn't present. The Compliance Manifest's data-contract block is the document the bank can hand a regulator that says *"these are the fields this control depends on."* When fields are missing in production data, the validator surfaces that as a control gap — not as a silent zero alert. *Data Quality* dashboard page renders the gap. |

### DATA-2 · "Stale beats stale beats stale."

| | |
|---|---|
| **Plain-English description** | The customer's address has not been updated in seven years. The occupation field still says *"student"* on a 41-year-old. The UBO list was captured at onboarding and never refreshed. The detector runs against today's transactions but yesterday's profile, and the false-positive rate is the price the analyst pays. |
| **Primary source** | BCBS 239 Principle 3 — Accuracy and Integrity: *"A bank should be able to generate accurate and reliable risk data to meet normal and stress/crisis reporting accuracy requirements"* — [BCBS 239, BIS](https://www.bis.org/publ/bcbs239.pdf). The Wolfsberg Group's CBDDQ standard formally requires correspondent-banking due-diligence information be *"kept current and… updated no less frequently than every eighteen months."* — [Wolfsberg CBDDQ V1.4 (April 2024)](https://wolfsberg-group.org/resources/correspondent-banking). |
| **Roles affected** | MLRO, 1LoD analyst, 2LoD model validation |
| **Cost type** | Cost + audit-defensibility |
| **Framework capability** | Perpetual KYC trigger engine (`pkyc/`) fires on transaction-pattern deltas that should re-trigger refresh. *Customer 360* page surfaces the staleness clock per attribute. The data-contract block can pin a `last_refreshed_at` column as required, so any detector consuming a customer field also consumes the freshness of that field. |

### DATA-3 · "Three systems, three answers."

| | |
|---|---|
| **Plain-English description** | The KYC system says the customer is a small business. The transaction-monitoring system has them flagged as retail. The case-management system has them as a high-risk SME. Whichever surface the analyst opens, the analyst gets a different story — and so does the regulator on examination day. |
| **Primary source** | BCBS 239 Principle 2 — Data Architecture and IT Infrastructure — [BCBS 239, BIS](https://www.bis.org/publ/bcbs239.pdf). HSBC (DOJ, December 2012): the bank classified Mexico as *"standard"* risk, *"resulting in the bank's failure to monitor more than $670 billion in wire transfers."* — [DOJ press conference, 11 Dec 2012](https://www.justice.gov/archives/opa/documents-and-resources-december-11-2012hsbc-press-conference). |
| **Roles affected** | CCO, MLRO, 1LoD, 2LoD, Internal Audit |
| **Cost type** | Audit-defensibility |
| **Framework capability** | One Compliance Manifest references one set of data contracts. The reconciliation problem becomes a validator problem — not an end-of-year project. |

### DATA-4 · "Where did this number come from?"

| | |
|---|---|
| **Plain-English description** | The board pack shows a 14% increase in high-risk-customer alerts quarter-over-quarter. The CCO is asked, in front of the audit committee, where the 14 came from. Most banks cannot walk back that far. |
| **Primary source** | FCA Dear CEO Letter to Annex 1 firms (March 2024): *"Decisions made in relation to financial crime were not supported by evidence or an audit trail of debate and challenge."* — [FCA letter](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf). |
| **Roles affected** | CCO, 2LoD model validation, Internal Audit, Audit Committee |
| **Cost type** | Audit-defensibility |
| **Framework capability** | The append-only `decisions.jsonl` ledger captures every input dataset's SHA-256 hash, every rule version, every threshold, every manual reclassification — chained so any tampering is detectable. |

### DATA-5 · "Your data leaves our perimeter."

| | |
|---|---|
| **Plain-English description** | The vendor wants the bank's transactions, KYC profiles, and case data in their cloud. The CCO knows this is structurally incompatible with how the regulator looks at outsourcing. |
| **Primary source** | OSFI Guideline B-13 — Technology and Cyber Risk Management (issued July 2022) — [OSFI B-13](https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/guideline-b-13-technology-and-cyber-risk-management). EBA Guidelines on outsourcing arrangements (EBA/GL/2019/02) — [EBA outsourcing page](https://www.eba.europa.eu/activities/single-rulebook/regulatory-activities/internal-governance/guidelines-outsourcing-arrangements). |
| **Roles affected** | CCO, CRO, CIO, Procurement, Vendor Risk |
| **Cost type** | Audit-defensibility + cost |
| **Framework capability** | Apache 2.0, single Python package, deployable into VPCs, on-prem, or air-gapped environments. No per-event meter, no perpetual data-export contract. |

### DATA-6 · "AI presumes data we don't have."

| | |
|---|---|
| **Plain-English description** | The vendor pitch shows the AI model finding the suspicious pattern the rules-based system missed. The pitch presumes a quality of input — clean, complete, reconciled, lineage-traced — that the bank's recent consent orders explicitly say it did not have. |
| **Primary source** | OSFI Guideline E-23 — Model Risk Management (final published 11 September 2025; effective 1 May 2027) explicitly extends the model-risk perimeter to AI/ML methods — [OSFI E-23 backgrounder](https://www.osfi-bsif.gc.ca/en/news/backgrounder-guideline-e-23-model-risk-management). FRB SR 26-2 (effective **April 17, 2026**) folds BSA/AML transaction monitoring, sanctions screening, and customer-risk rating into the same model-risk inventory — [FRB SR 26-2](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm). |
| **Roles affected** | CCO, 2LoD model validation, MRM Director |
| **Cost type** | Audit-defensibility + cost |
| **Framework capability** | The framework deliberately does **not** ship an in-tree alert-scoring ML model. Where the institution wants to bring its own ML scorer, the `python_ref` rule type is the seam — but the model is recorded with `model_id` + `model_version` per SR 26-2 / E-23. The framework's position is that detection improvements compound only after the data layer is defensible. |

### DATA-7 · "Engineering owns the warehouse, Compliance owns the alert."

| | |
|---|---|
| **Plain-English description** | The detection logic lives in Compliance. The data it runs on lives in Engineering. They report to different VPs, work in different ticketing systems, and answer to different boards. |
| **Primary source** | BCBS 239 Principle 1 — Governance — [BCBS 239, BIS](https://www.bis.org/publ/bcbs239.pdf). FCA Dear CEO Letter to UK retail banks (May 2021): firms *"blurred responsibilities between first line business roles and second line compliance roles."* |
| **Roles affected** | CCO, MLRO, CIO, Head of Data |
| **Cost type** | Audit-defensibility + morale |
| **Framework capability** | The Compliance Manifest is the artifact both sides commit against. When a contract is violated, the failure mode is loud — the validator surfaces it on the *Data Quality* dashboard, not silently in a missed alert three months later. |

### DATA-8 · "The MLRO has no veto over data shape."

| | |
|---|---|
| **Plain-English description** | The CCO discovers, post-incident, that a new product launched six months ago without surfacing transactions to the AML pipeline. The MLRO's name is on the SAR — but the MLRO never had a veto over what data the product captured at the source. |
| **Primary source** | OSFI Letter to Industry (11 September 2025), introducing the new AMP Guide: OSFI announced *"a lower tolerance for contraventions… penalties may be issued for lower levels of potential negligence and harm, and more frequently in 2026."* — [Fasken summary](https://www.fasken.com/en/knowledge/2026/02/financial-services-regulatory-updates). FinCEN April 2026 NPRM: AML/CFT programs *"must be approved by a board of directors."* |
| **Roles affected** | MLRO personally, CCO, Audit Committee |
| **Cost type** | Audit-defensibility + personal liability + morale |
| **Framework capability** | The Compliance Manifest is the veto. New product = new data contract entry, validated before the product can ship to production data pipelines. |

### DATA-9 · "The SAR we filed and the SAR we should have filed."

| | |
|---|---|
| **Plain-English description** | The MLRO signs off on a thousand SARs a year. Some are defensive; others are missing because a transaction did not arrive in the alert engine or a prior STR's narrative was not joined to the current alert. |
| **Primary source** | FINTRAC on RBC (2023, $7.5M penalty): the bank *"failed to flag suspicious activity… failed to submit 16 suspicious transactions reports across 130 customer files."* — [ACAMS coverage](https://www.acams.org/en/news/fintrac-fines-royal-bank-of-canada-record-7-5-million-for-aml-failings). FinCEN's April 2026 NPRM names the effectiveness metric: programs must demonstrate that *suspicious activity is identified, escalated, and reported* — the unbroken chain, not the alert volume. |
| **Roles affected** | MLRO, 1LoD analyst, FIU lead, Internal Audit |
| **Cost type** | Audit-defensibility + regulatory-penalty exposure |
| **Framework capability** | Investigation-aggregator (`cases/aggregator.py`) joins alerts to a deterministic INV-{sha256[:16]} ID; STR auto-bundling (`cases/str_bundle.py`) packages narrative + goAML XML + manifest hash. |

### DATA-10 · "We can't see what the other bank is seeing."

| | |
|---|---|
| **Plain-English description** | A customer wires money out of Bank A and into Bank B. Bank A files an STR. Bank B's monitoring system has no signal that Bank A flagged anything. |
| **Primary source** | The Wolfsberg Group's CBDDQ V1.4 (April 2024) binds counterparties to *"file accurate supplemental information on a timely basis"* — [Wolfsberg CBDDQ V1.4](https://wolfsberg-group.org/resources/correspondent-banking). FATF Recommendation 18 requires group-wide AML/CFT information-sharing programs. |
| **Roles affected** | CCO, MLRO, Head of Correspondent Banking, FIU lead |
| **Cost type** | Audit-defensibility + missed-typology risk |
| **Framework capability** | The framework ships a **cross-border information-sharing sandbox** (`compliance/sandbox.py`) — a reference implementation of 314(b) / Wolfsberg / FATF R.18 compliance as a configurable contract. |

### DATA-11 · "The compliance-defensible answer is a data contract, not a detection upgrade."

| | |
|---|---|
| **Plain-English description** | The framework's load-bearing claim is that everything above is solved at the data-contract layer, before the detector runs. |
| **Primary source** | FinCEN April 2026 NPRM (Federal Register 2026-07033) is the most explicit recent statement of what an AML program's evidence layer must produce — board approval, designated officer, *risk assessment, internal controls, independent testing,* training, and documentation that ties controls back to risks. Comment window open through June 9. — [Federal Register 2026-07033](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs). |
| **Roles affected** | CCO, MLRO, 2LoD, MRM Director, Internal Audit |
| **Cost type** | Audit-defensibility |
| **Framework capability** | One versioned `aml.yaml` declares the data contracts every detector depends on. Same spec + same data + same seed = identical output hashes. The Manifest is the document Compliance and Engineering both commit against. |

---

## Where the framework closes each pain (DATA-N → artifact map)

Every claim above maps to a concrete framework artifact — a dashboard
page, a CLI command, a Python module, or a test file. This table is
the contract: if the artifact doesn't close the pain, the claim is
broken. The same map renders inside the dashboard itself on the
[Data Integration page](../dashboard-tour.md#data-integration) so
operators can verify each row in one click.

| Pain | Page | CLI | Module / test |
|---|---|---|---|
| **DATA-1** Fail-closed contract validation | [Data Integration · Contract roll-up](../dashboard-tour.md#data-integration) · [Data Quality](../dashboard-tour.md#data-quality) | `aml validate-data <spec> <data-dir>` · `aml run --strict` | `engine/runner.py::_build_warehouse` + `engine/dq.py::evaluate_contract_checks` · `tests/test_contract_validation.py` |
| **DATA-2** Per-attribute freshness pinning | [Customer 360 · staleness expander](../dashboard-tour.md#customer-360) · Data Integration · contract roll-up | `aml run --strict` (refuses stale attributes) | `spec/models.py::Column.max_staleness_days` · `engine/freshness.py` |
| **DATA-3** Cross-system reconciliation | Audit & Evidence (decision log) | `aml run` emits `reconciliation.jsonl` per contract | `engine/runner.py` reconciliation pass |
| **DATA-4** Lineage walk-back from KPI | [Audit & Evidence · decision log](../dashboard-tour.md#audit--evidence) | `aml lineage <case_id>` | `engine/audit.py::walk_lineage` |
| **DATA-5** In-bank, not SaaS (data sovereignty) | [Data Integration · source catalogue](../dashboard-tour.md#data-integration) | Docker / Helm — see [`deployment.md`](../deployment.md) | `data/sources.py` (no SaaS dependency in any loader) |
| **DATA-6** AI presumes data (fail-closed gate) | Closes transitively via DATA-1 | `aml run --strict` halts on contract violation before any LLM call | `engine/runner.py::_build_warehouse` raises `ContractViolation` before any AI invocation |
| **DATA-7** Engineering vs Compliance ownership boundary | [Spec Editor](../dashboard-tour.md#spec-editor--rule-builder) · Data Integration | `aml validate <spec>` (engineering) · `aml attest` (compliance) | `spec/models.py` (the boundary IS the spec) |
| **DATA-8** Payment-rail data (ISO 20022 native) | [Data Integration · ISO 20022 message-type chart](../dashboard-tour.md#data-integration) | `aml run --data-source iso20022 --data-dir <xml-dir>` | `data/iso20022/parser.py` (pacs.008/009/004 + pain.001) |
| **DATA-9** STR/SAR filing-latency wall-clock | [Audit & Evidence](../dashboard-tour.md#audit--evidence) — `cases/<id>__filing.json` sidecars | `aml export` rolls filing latency into the bundle | `cases/str_bundle.py` (real wall-clock per filing) |
| **DATA-10** Cross-bank information sharing | [Information Sharing](../dashboard-tour.md#information-sharing) | `aml share-pattern` · `aml verify-pattern` | `compliance/sandbox.py` (FATF R.18 / 314(b) seam) |
| **DATA-11** Spec as data contract (versioned, hashable) | [Audit & Evidence](../dashboard-tour.md#audit--evidence) — spec hash on every run | `aml validate <spec>` (JSON Schema + Pydantic two-layer) | `spec/loader.py` · `engine/audit.py` (hash-chained ledger) |

---

## Sources

- [BCBS 239 — Principles for effective risk data aggregation and risk reporting (BIS, January 2013)](https://www.bis.org/publ/bcbs239.pdf)
- [BCBS d559 — 2023 Progress in adopting BCBS 239 principles](https://www.bis.org/bcbs/publ/d559.htm)
- [FCA Dear CEO Letter — Annex 1 firms (March 2024)](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf)
- [FinCEN — TD Bank record $1.3B penalty (October 2024)](https://www.fincen.gov/news/news-releases/fincen-assesses-record-13-billion-penalty-against-td-bank)
- [FinCEN — AML Program NPRM, Federal Register 2026-07033](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs)
- [GENIUS Act PPSI NPRM — Federal Register 2026-06963](https://www.federalregister.gov/documents/2026/04/10/2026-06963/permitted-payment-stablecoin-issuer-anti-money-launderingcountering-the-financing-of-terrorism)
- [DOJ — HSBC press conference (December 11, 2012)](https://www.justice.gov/archives/opa/documents-and-resources-december-11-2012hsbc-press-conference)
- [ACAMS — FINTRAC fines RBC record $7.5M for AML failings (2023)](https://www.acams.org/en/news/fintrac-fines-royal-bank-of-canada-record-7-5-million-for-aml-failings)
- [OSFI — Guideline E-23 Model Risk Management (final, 2027)](https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/guideline-e-23-model-risk-management-2027-letter)
- [OSFI — Guideline B-13 Technology and Cyber Risk Management (2022)](https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/guideline-b-13-technology-and-cyber-risk-management)
- [FRB SR 26-2 — Revised Model Risk Management guidance (effective April 17, 2026)](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm)
- [OCC Bulletin 2026-13 — Model Risk Management](https://www.occ.treas.gov/news-issuances/bulletins/2026/bulletin-2026-13.html)
- [Wolfsberg Group — Correspondent Banking resources & CBDDQ](https://wolfsberg-group.org/resources/correspondent-banking)
- [AUSTRAC — AML/CTF Reform hub](https://www.austrac.gov.au/amlctf-reform)

---

*Last updated: 2026-04-09 · Next edition: [2026-05-aml-data-problem.md](./2026-05-aml-data-problem.md).*
