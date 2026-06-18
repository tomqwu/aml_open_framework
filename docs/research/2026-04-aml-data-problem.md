# Data is the AML problem — 2026

*Date: 2026-04-01 · Audience: CCO / MLRO / Head of Financial Crime / CRO / 2LoD model validation. Companion docs: [`2026-04-aml-process-pain.md`](./2026-04-aml-process-pain.md) for the leader-pain style guide; [`2026-04-competitive-positioning.md`](./2026-04-competitive-positioning.md) for the vendor landscape.*

## How to read this doc

The pain doc argues that **audit-defensibility, not detection, is the dominant pain in 2026**. This doc argues the next layer down: **the binding constraint underneath audit-defensibility is data**. Detection presumes data the bank often does not have. Audit-defensibility presumes a lineage the bank often cannot reproduce. Vendor AI presumes a quality of input that public enforcement orders show does not exist.

That claim is not novel; what is new in 2026 is that regulators are now writing it down. FRB SR 26-2 (effective April 17, 2026 — sixteen days from this edition's date), OSFI's September 2025 E-23 final guidance, the Basel Committee's 2023 progress report on BCBS 239, and the FCA's March 2024 Annex 1 letter all converge on the same thesis from different angles. The FinCEN Effectiveness NPRM (Federal Register 2026-07033) is expected to be submitted in April 2026, formalising what "an effective AML/CFT program" must prove. This document collects the language regulators use and maps each claim to the framework capability that responds to it.

Three rules behind the analysis below — they mirror the pain doc's rules and apply identically here:

1. **Audit-defensibility, not detection, is the dominant pain.** Across recent enforcement orders surveyed (TD 2024, RBC 2024, HSBC 2012, Wells 2024, NatWest), regulators rarely allege the bank missed a typology — they allege the bank could not produce the data, evidence the lineage, or reconcile the systems. *The data problem is the audit-defensibility problem one layer down.*
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
| **Primary source** | BCBS 239 Principle 3 — Accuracy and Integrity + Principle 5 — Timeliness: *"A bank should be able to generate aggregate and up-to-date risk data in a timely manner."* — [BCBS 239, BIS](https://www.bis.org/publ/bcbs239.pdf). The Wolfsberg Group's CBDDQ standard formally requires correspondent-banking due-diligence information be *"kept current and… updated no less frequently than every eighteen months"* — [Wolfsberg CBDDQ V1.4 (April 2024)](https://wolfsberg-group.org/resources/correspondent-banking). |
| **Roles affected** | MLRO, 1LoD analyst, 2LoD model validation |
| **Cost type** | Cost + audit-defensibility |
| **Framework capability** | Perpetual KYC trigger engine (`pkyc/`) fires on transaction-pattern deltas that should re-trigger refresh. *Customer 360* page surfaces the staleness clock per attribute. The data-contract block can pin a `last_refreshed_at` column as required, so any detector consuming a customer field also consumes the freshness of that field. Point-in-time reference joins (`effective_dated` + `enrich` on `aggregation_window` rules) are on the framework roadmap to close this gap programmatically — a rule will resolve the reference row in force *at the transaction date*, not the latest row. |

### DATA-3 · "Three systems, three answers."

| | |
|---|---|
| **Plain-English description** | The KYC system says the customer is a small business. The transaction-monitoring system has them flagged as retail. The case-management system has them as a high-risk SME. Whichever surface the analyst opens, the analyst gets a different story — and so does the regulator on examination day. |
| **Primary source** | BCBS 239 Principle 2 — Data Architecture and IT Infrastructure: *"A bank should design, build and maintain data architecture and IT infrastructure which fully supports its risk data aggregation capabilities."* — [BCBS 239, BIS](https://www.bis.org/publ/bcbs239.pdf). HSBC (DOJ, December 2012): the bank classified Mexico as *"standard"* risk — its lowest AML risk category — *"resulting in the bank's failure to monitor more than $670 billion in wire transfers and more than $9.4 billion in purchases of physical U.S. dollars from HSBC Mexico."* — [DOJ press conference, 11 Dec 2012](https://www.justice.gov/archives/opa/documents-and-resources-december-11-2012hsbc-press-conference). |
| **Roles affected** | CCO, MLRO, 1LoD, 2LoD, Internal Audit |
| **Cost type** | Audit-defensibility |
| **Framework capability** | One Compliance Manifest references one set of data contracts. The detector cannot fire on a different definition of "customer" than the case-bundling logic uses, because both reference the same `customer` contract by ID. *Spec Editor* surfaces the contract; *Investigations* aggregator joins back to it. The reconciliation problem becomes a validator problem — not an end-of-year project. |

### DATA-4 · "Where did this number come from?"

| | |
|---|---|
| **Plain-English description** | The board pack shows a 14% increase in high-risk-customer alerts quarter-over-quarter. The CCO is asked, in front of the audit committee, where the 14 came from. The honest answer is "the dashboard." The defensible answer requires walking back through the source extracts, the threshold settings, the model versions, and the manual reclassifications that produced the number. Most banks cannot walk back that far. |
| **Primary source** | FCA Dear CEO Letter to Annex 1 firms (March 2024, still operative in 2026): *"Decisions made in relation to financial crime were not supported by evidence or an audit trail of debate and challenge."* — [FCA letter](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf). The May 2018 ECB review of the largest 25 institutions' BCBS 239 implementation found *"none of those significant institutions… have fully implemented the BCBS 239 principles"* — lineage is the principle most banks miss most consistently. |
| **Roles affected** | CCO, 2LoD model validation, Internal Audit, Audit Committee |
| **Cost type** | Audit-defensibility |
| **Framework capability** | The append-only `decisions.jsonl` ledger captures every input dataset's SHA-256 hash, every rule version, every threshold, every manual reclassification — chained so any tampering is detectable. *Audit & Evidence* dashboard page lets a 2LoD reviewer click any number on the executive dashboard and walk back to the run that produced it, the spec version that defined the rule, and the input file that fed it. |

### DATA-5 · "Your data leaves our perimeter."

| | |
|---|---|
| **Plain-English description** | The vendor wants the bank's transactions, KYC profiles, and case data in their cloud, where their model runs and their dashboard renders. The CCO knows this is structurally incompatible with how the regulator looks at outsourcing — but the procurement process keeps producing SaaS shortlists anyway. *"Your data leaves our perimeter"* is the first question the OSFI / Fed / FCA exam team asks. |
| **Primary source** | OSFI Guideline B-13 — Technology and Cyber Risk Management (issued July 2022): *"how third parties handle data and the potential impact of disruptions or data breaches."* — [OSFI B-13 page](https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/guideline-b-13-technology-and-cyber-risk-management). EBA Guidelines on outsourcing arrangements (EBA/GL/2019/02): pre-existing cloud arrangements had to be brought into compliance by 31 December 2021 — [EBA outsourcing page](https://www.eba.europa.eu/activities/single-rulebook/regulatory-activities/internal-governance/guidelines-outsourcing-arrangements). |
| **Roles affected** | CCO, CRO, CIO, Procurement, Vendor Risk |
| **Cost type** | Audit-defensibility + cost |
| **Framework capability** | Apache 2.0, single Python package, deployable into VPCs, on-prem, or air-gapped environments. The bank owns the spec, the engine, the audit ledger, the case data, and the operating cost — no per-event meter, no perpetual data-export contract, no cross-border data-residency negotiation. |

### DATA-6 · "AI presumes data we don't have."

| | |
|---|---|
| **Plain-English description** | The vendor pitch shows the AI model finding the suspicious pattern that the rules-based system missed. The pitch presumes a quality of input — clean, complete, reconciled, lineage-traced — that the bank's recent consent orders explicitly say it did not have. *"Garbage in, garbage out"* is not a slogan; it is the operating reality regulators have been writing down for fifteen years. |
| **Primary source** | OSFI Guideline E-23 — Model Risk Management (final published 11 September 2025; effective 1 May 2027): *"Artificial intelligence and machine learning (AI/ML) methods are expressly included in the definition of model."* — [OSFI E-23 backgrounder](https://www.osfi-bsif.gc.ca/en/news/backgrounder-guideline-e-23-model-risk-management). FRB SR 26-2 (effective April 17, 2026 — 16 days from this edition) folds BSA/AML transaction monitoring, sanctions screening, and customer-risk rating into the same model-risk inventory at US-supervised banks — [FRB SR 26-2](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm). TD's *"trillions of dollars… unmonitored"* and RBC's *"failed to flag suspicious activity"* are not detection-failure cases; they are data cases. |
| **Roles affected** | CCO, 2LoD model validation, MRM Director |
| **Cost type** | Audit-defensibility + cost |
| **Framework capability** | The framework deliberately does **not** ship an in-tree alert-scoring ML model. Where the institution wants to bring its own ML scorer, the `python_ref` rule type is the seam — but the model is recorded with `model_id` + `model_version` per SR 26-2 / E-23, and the input data is still captured by the same data-contract validator that catches DATA-1 / DATA-2. A dedicated model-inventory CLI (`aml model-inventory`) is on the framework's roadmap for Q2 2026. |

### DATA-7 · "Engineering owns the warehouse, Compliance owns the alert."

| | |
|---|---|
| **Plain-English description** | The detection logic lives in Compliance. The data it runs on lives in Engineering. They report to different VPs, work in different ticketing systems, and answer to different boards. When the alert fires — or doesn't — the question of "whose responsibility is the data shape?" gets passed back and forth until it lands on the MLRO's desk because the MLRO's signature is on the SAR. |
| **Primary source** | BCBS 239 Principle 1 — Governance: *"A bank's risk data aggregation capabilities and risk reporting practices should be subject to strong governance arrangements."* — [BCBS 239, BIS](https://www.bis.org/publ/bcbs239.pdf). FCA Dear CEO Letter to UK retail banks (May 2021): firms *"blurred responsibilities between first line business roles and second line compliance roles."* — [Mayer Brown analysis](https://www.mayerbrown.com/en/insights/publications/2021/08/the-fcas-dear-ceo-letter). |
| **Roles affected** | CCO, MLRO, CIO, Head of Data |
| **Cost type** | Audit-defensibility + morale |
| **Framework capability** | The Compliance Manifest is the artifact both sides commit against. The data-contract block belongs to Compliance (it's the schema each rule depends on); the data pipeline that fills it belongs to Engineering. When a contract is violated, the failure mode is loud — the validator surfaces it on the *Data Quality* dashboard, not silently in a missed alert three months later. |

### DATA-8 · "The MLRO has no veto over data shape."

| | |
|---|---|
| **Plain-English description** | The CCO discovers, post-incident, that a new product launched six months ago without surfacing transactions to the AML pipeline. The product PM treated the AML schema as a nice-to-have. The MLRO's name is the one on the SAR — but the MLRO never had a veto over what data the product captured at the source. |
| **Primary source** | OSFI Letter to Industry (11 September 2025): *"a lower tolerance for contraventions… penalties may be issued for lower levels of potential negligence and harm."* — [Fasken summary](https://www.fasken.com/en/knowledge/2026/02/financial-services-regulatory-updates). FCA Dear CEO Annex 1 (March 2024): firms showed *"business growth without evolving financial crime systems and controls."* — [FCA letter](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf). |
| **Roles affected** | MLRO personally, CCO, Audit Committee |
| **Cost type** | Audit-defensibility + personal liability + morale |
| **Framework capability** | The Compliance Manifest is the veto. New product = new data contract entry, validated before the product can ship to production data pipelines. *Multi-jurisdiction* and *Program Maturity* dashboard pages render the coverage gap the moment a new geography or product is added. |

### DATA-9 · "The SAR we filed and the SAR we should have filed."

| | |
|---|---|
| **Plain-English description** | The MLRO signs off on a thousand SARs a year. Some are defensive — filed because the analyst couldn't rule out suspicion. Others are missing — the genuinely suspicious customer's behaviour did not surface in time because a transaction did not arrive in the alert engine, or the prior STR's narrative was not joined to the current alert. The defect is data continuity, not analyst effort. |
| **Primary source** | FINTRAC on RBC (2024, $7.5M penalty): *"failed to flag suspicious activity… did not disclose relevant information in suspicious transaction reports… failed to submit 16 suspicious transactions reports across 130 customer files."* — [ACAMS coverage](https://www.acams.org/en/news/fintrac-fines-royal-bank-of-canada-record-7-5-million-for-aml-failings). The 16 missed STRs across 130 customer files is not a detection failure — the data to file the STR existed; it did not arrive at the regulator-facing form. |
| **Roles affected** | MLRO, 1LoD analyst, FIU lead, Internal Audit |
| **Cost type** | Audit-defensibility + regulatory-penalty exposure |
| **Framework capability** | Investigation-aggregator (`cases/aggregator.py`) joins alerts to a deterministic INV-{sha256[:16]} ID; STR auto-bundling (`cases/str_bundle.py`) packages narrative + goAML XML + Mermaid diagrams + manifest hash. STR filing-latency p95 is a first-class metric on the Executive Dashboard's effectiveness funnel. |

### DATA-10 · "We can't see what the other bank is seeing."

| | |
|---|---|
| **Plain-English description** | A customer wires money out of Bank A and into Bank B. Bank A files an STR. Bank B's monitoring system has no signal that Bank A flagged anything. Cross-bank information sharing is the data layer regulators have been asking banks to operationalise since FATF Recommendation 18 was first written. |
| **Primary source** | Wolfsberg Group CBDDQ V1.4 (April 2024): *"file accurate supplemental information on a timely basis"* with refresh *"no less frequently than every eighteen months."* — [Wolfsberg CBDDQ V1.4](https://wolfsberg-group.org/resources/correspondent-banking). FATF Recommendation 18 (operative in 2026) requires group-wide AML/CFT programs covering information sharing. |
| **Roles affected** | CCO, MLRO, Head of Correspondent Banking, FIU lead |
| **Cost type** | Audit-defensibility + missed-typology risk |
| **Framework capability** | The framework ships a **cross-border information-sharing sandbox** (`compliance/sandbox.py`) — a reference implementation of how a Manifest can declare information-sharing partners, scope, and audit trail under FATF R.18 / 314(b). |

### DATA-11 · "The compliance-defensible answer is a data contract, not a detection upgrade."

| | |
|---|---|
| **Plain-English description** | The framework's load-bearing claim is that everything above is solved at the data-contract layer, before the detector runs. *Disclosure: this framework is positioned around this thesis.* The FinCEN Effectiveness NPRM (expected April 2026) is the most explicit recent statement of what an AML program's evidence layer must produce — risk assessment, internal controls, independent testing, training, and documentation that ties controls back to risks. |
| **Primary source** | FRB SR 26-2 + OCC Bulletin 2026-13 (effective April 17, 2026): require independent challenger validation of model-risk components — [SR 26-2](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm). The April 2026 enforcement perimeter is clear: a program is defensible to the extent its data, its controls, its decisions, and its lineage can be replayed on demand. |
| **Roles affected** | CCO, MLRO, 2LoD, MRM Director, Internal Audit |
| **Cost type** | Audit-defensibility |
| **Framework capability** | One versioned `aml.yaml` declares the data contracts every detector depends on. Two-layer validation (JSON Schema + Pydantic cross-references) catches contract violations before the engine runs. Same spec + same data + same seed = identical output hashes — the deterministic-replay guarantee is what makes the audit ledger byte-replayable rather than just append-only. |

---

## Themes (≈150 words)

The dominant message entering Q2 2026 is that **data, not detection, is the binding constraint on AML program effectiveness**. BCBS 239 has codified this since 2013; the Basel Committee's 2023 progress report shows G-SIBs still don't meet the principles a decade later. FRB SR 26-2 (effective April 17, 2026), OSFI's revised E-23 (final September 2025, effective May 2027), and the FCA's 2024 Annex 1 letter converge on the same operational posture: programs must produce evidence — data lineage, decision rationale, control coverage — on demand. The FinCEN Effectiveness NPRM (expected April 2026) formalises this as a regulatory requirement. The largest 2024 enforcement orders (TD, RBC) are not detection-failure cases; they are data-and-process cases dressed as detection cases. The vendor "AI" wave presumes a data quality the consent orders show does not exist.

---

## Where the framework closes each pain (DATA-N → artifact map)

Every claim above maps to a concrete framework artifact. Items marked **Planned** are on the Q2 2026 roadmap and not yet shipped as of 2026-04-01.

| Pain | Page | CLI | Module / test |
|---|---|---|---|
| **DATA-1** Fail-closed contract validation | Data Integration · Contract roll-up · Data Quality | `aml validate-data <spec> <data-dir>` · `aml run --strict` | `engine/runner.py::_validate_contracts` · `tests/test_contract_validation.py` |
| **DATA-2** Per-attribute freshness pinning | Customer 360 · staleness expander · Data Integration | `aml run --strict` (refuses stale attributes) | `spec/models.py::Column.max_staleness_days` · `engine/freshness.py` — point-in-time enrichment join (`enrich` block) **Planned** |
| **DATA-3** Cross-system reconciliation | Audit & Evidence (decision log) | `aml run` emits `reconciliation.jsonl` per contract | `engine/runner.py` reconciliation pass |
| **DATA-4** Lineage walk-back from KPI | Audit & Evidence · decision log | `aml export --include-lineage` | `engine/audit.py::walk_lineage` |
| **DATA-5** In-bank, not SaaS (data sovereignty) | Data Integration · source catalogue | Docker / Helm — see `deployment.md` | `data/sources.py` (no SaaS dependency) |
| **DATA-6** AI presumes data (fail-closed gate) | Closes transitively via DATA-1 | `aml run --strict` halts on contract violation | `assistant/factory.py` checks contract pass — model-inventory CLI **Planned** |
| **DATA-7** Engineering vs Compliance ownership boundary | Spec Editor · Data Integration | `aml validate <spec>` (engineering) · `aml attest` (compliance) | `spec/models.py` (the boundary IS the spec) |
| **DATA-8** Payment-rail data (ISO 20022 native) | Data Integration · ISO 20022 message-type chart | `aml run --data-source iso20022 --data-dir <xml-dir>` | `data/iso20022/parser.py` (pacs.008/009/004 + pain.001) |
| **DATA-9** STR/SAR filing-latency wall-clock | Audit & Evidence — `cases/<id>__filing.json` sidecars | `aml export` rolls filing latency into the bundle | `cases/str_bundle.py` |
| **DATA-10** Cross-bank information sharing | Information Sharing · share-pattern artifacts | `aml share-pattern` · `aml verify-pattern` | `compliance/sandbox.py` (FATF R.18 / 314(b) seam) |
| **DATA-11** Spec as data contract (versioned, hashable) | Audit & Evidence — spec hash on every run | `aml validate <spec>` (JSON Schema + Pydantic two-layer) | `spec/loader.py` · `engine/audit.py` (hash-chained ledger) |

---

## What changed entering Q2 2026

Three regulatory developments in Q1 2026 sharpened the data-problem framing:

- **SR 26-2 about to land (April 17 — 16 days):** FRB SR 26-2 and OCC Bulletin 2026-13 extend SR 11-7's model-risk inventory to BSA/AML transaction monitoring, sanctions screening, and customer-risk-rating models at US-supervised banks. DATA-6 and DATA-11 are the two framework responses most directly at stake: the `python_ref` model seam records `model_id`/`model_version` per the guidance, and the deterministic-replay guarantee makes the model audit ledger byte-replayable. The framework's M2 roadmap item (a dedicated `aml model-inventory` CLI surfacing all in-spec models) is planned to land in Q2 2026.
- **FinCEN Effectiveness NPRM expected (FR 2026-07033):** The "AML/CFT Program Effectiveness" NPRM is expected to be submitted April 2026 with a June 9 comment deadline. It formalises the evidence standard for the six "effectiveness pillars" — the same pillars the framework's North Star roadmap responds to. DATA-11 (spec as contract) and DATA-4 (lineage) are the load-bearing responses.
- **OSFI E-23 final published (September 2025, effective May 2027):** Canada's model-risk guidance extends the AI/ML perimeter. Canadian institutions using the `canadian_schedule_i_bank` example spec should note that the framework's `python_ref` model seam and `model_risk_report.json` (planned Q2 2026) are designed to align with both OSFI E-23 and SR 26-2 simultaneously.

---

## Style guide — phrases to use, phrases to avoid

### Use these (regulator-sourced, defensible to a buyer)

- *"Capture and aggregate all material risk data"* (BCBS 239 P4 — completeness)
- *"Accurate and reliable risk data"* (BCBS 239 P3 — accuracy and integrity)
- *"An audit trail of debate and challenge"* (FCA Annex 1 2024)
- *"Your data leaves our perimeter"* (the OSFI / Fed / FCA exam-team framing for vendor-cloud risk)
- *"Lineage we can walk back"* (operative phrase for the audit-evidence layer)
- *"Data contract"* (the schema-as-policy artifact — leader-readable framing of what the spec validates)

### Avoid these on leader-facing surfaces

- "data quality" alone — too vague. Use *completeness*, *accuracy*, *staleness*, *reconciliation*, or *lineage* depending on the specific failure mode.
- "ETL", "data pipeline", "warehouse" — engineering vocabulary. Translate to *the data the controls run on*.
- "garbage in, garbage out" — glib. Replace with the FCA / BCBS framing: *"the controls cannot fire on data the bank does not have."*
- "data sovereignty" alone (without a regulator anchor) — translate to *"the bank owns where the data sits"* and cite OSFI B-13 / EBA outsourcing.

---

## Sources

- [BCBS 239 — Principles for effective risk data aggregation and risk reporting (BIS, January 2013)](https://www.bis.org/publ/bcbs239.pdf)
- [BCBS d559 — 2023 Progress in adopting BCBS 239 principles](https://www.bis.org/bcbs/publ/d559.htm)
- [FCA Dear CEO Letter — Annex 1 firms (March 2024)](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf)
- [FCA Dear CEO — UK retail banks (May 2021), via Mayer Brown](https://www.mayerbrown.com/en/insights/publications/2021/08/the-fcas-dear-ceo-letter)
- [FinCEN — TD Bank record $1.3B penalty (October 2024)](https://www.fincen.gov/news/news-releases/fincen-assesses-record-13-billion-penalty-against-td-bank)
- [FRB SR 26-2 — Model Risk Management Guidance for BSA/AML (effective April 17, 2026)](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm)
- [OCC Bulletin 2026-13](https://www.occ.treas.gov/news-issuances/bulletins/2026/bulletin-2026-13.html)
- [OSFI E-23 — Model Risk Management (final September 2025)](https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/guideline-e-23-model-risk-management-2027-letter)
- [OSFI B-13 — Technology and Cyber Risk Management (July 2022)](https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/guideline-b-13-technology-and-cyber-risk-management)
- [FINTRAC — RBC $7.5M penalty (2024), via ACAMS](https://www.acams.org/en/news/fintrac-fines-royal-bank-of-canada-record-7-5-million-for-aml-failings)
- [Wolfsberg CBDDQ V1.4 (April 2024)](https://wolfsberg-group.org/resources/correspondent-banking)
