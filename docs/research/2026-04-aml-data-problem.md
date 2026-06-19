# Data is the AML problem — April 2026

*Date: 2026-04-29 · Audience: CCO / MLRO / Head of Financial Crime / CRO / 2LoD model-validation. Companion docs: [`2026-04-aml-process-pain.md`](./2026-04-aml-process-pain.md) for the leader-pain style guide; [`2026-04-competitive-positioning.md`](./2026-04-competitive-positioning.md) for the vendor landscape. Next edition: [`2026-05-aml-data-problem.md`](./2026-05-aml-data-problem.md).*

## Regulatory context — April 29, 2026

**SR 26-2 became examination-active twelve days ago (April 17, 2026).** FRB SR 26-2 folds BSA/AML transaction monitoring, sanctions screening, and customer-risk rating into the model-risk inventory at US-supervised banks. The model-risk management requirements — model inventory, independent challenger validation, conceptual-soundness documentation — apply immediately. DATA-6 (AI presumes data we don't have) is the first point of examiner challenge: before a model's conceptual soundness can be validated, the completeness and accuracy of its training and inference data must be documented.

**Effectiveness NPRM comment window: 41 days remaining (closes June 9, 2026).** FinCEN, OCC, FDIC, and NCUA jointly propose reframing the BSA program rule around an "effective, risk-based, reasonably designed" standard. A documented enterprise-wide risk assessment becomes a program-structure pillar, not just expected practice. DATA-1 through DATA-8 move from process expectations to program-structure requirements if finalised as proposed.

**GENIUS Act PPSI NPRM: 41 days remaining (closes June 9, 2026).** FinCEN and OFAC jointly propose treating permitted payment stablecoin issuers (PPSIs) as financial institutions under the BSA, with mandatory OFAC sanctions compliance programs under new 31 CFR Part 502. Stablecoin transaction flows use ISO 20022 pacs.008/009/004 formats — DATA-8 applies directly.

**AUSTRAC Tranche 2: 63 days remaining (July 1, 2026).** Australian DNFBPs (lawyers, accountants, real-estate agents, dealers in precious metals and stones) must have a board-approved AML/CTF program enforceable from July 1.

**FinCEN Whistleblower NPRM: 33 days remaining (closes June 1, 2026).** Proposes 10–30% whistleblower awards from the $300M Financial Integrity Fund. SAR-backlog and screening-gap failures are the primary insider-tip triggers.

---

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
| **Primary source** | BCBS 239 Principle 3 — Accuracy and Integrity: *"A bank should be able to generate accurate and reliable risk data to meet normal and stress/crisis reporting accuracy requirements"* + *"Data should be aggregated on a largely automated basis so as to minimise the probability of errors."* — [BCBS 239, BIS](https://www.bis.org/publ/bcbs239.pdf). BCBS 239 Principle 5 — Timeliness: *"A bank should be able to generate aggregate and up-to-date risk data in a timely manner."* — same source. The Wolfsberg Group's CBDDQ standard formally requires correspondent-banking due-diligence information be *"kept current and… updated no less frequently than every eighteen months"* — [Wolfsberg CBDDQ V1.4 (April 2024)](https://wolfsberg-group.org/resources/correspondent-banking). |
| **Roles affected** | MLRO, 1LoD analyst, 2LoD model validation |
| **Cost type** | Cost + audit-defensibility |
| **Framework capability** | Perpetual KYC trigger engine (`pkyc/`) fires on transaction-pattern deltas that should re-trigger refresh. *Customer 360* page surfaces the staleness clock per attribute. The data-contract block can pin a `last_refreshed_at` column as required, so any detector consuming a customer field also consumes the freshness of that field. Point-in-time effective-dated reference-data joins (resolving reference state contemporaneous with each transaction) are on the ML/AI roadmap for Q2 2026 — see the Now-tier M4 initiative. |

### DATA-3 · "Three systems, three answers."

| | |
|---|---|
| **Plain-English description** | The KYC system says the customer is a small business. The transaction-monitoring system has them flagged as retail. The case-management system has them as a high-risk SME. Whichever surface the analyst opens, the analyst gets a different story — and so does the regulator on examination day. |
| **Primary source** | BCBS 239 Principle 2 — Data Architecture and IT Infrastructure: *"A bank should design, build and maintain data architecture and IT infrastructure which fully supports its risk data aggregation capabilities."* — [BCBS 239, BIS](https://www.bis.org/publ/bcbs239.pdf). HSBC (DOJ, December 2012): the bank classified Mexico as *"standard"* risk, its lowest AML risk category, *"resulting in the bank's failure to monitor more than $670 billion in wire transfers and more than $9.4 billion in purchases of physical U.S. dollars from HSBC Mexico."* The risk-rating system and the wire-monitoring system held different views; nobody noticed for years. — [DOJ press conference, 11 Dec 2012](https://www.justice.gov/archives/opa/documents-and-resources-december-11-2012hsbc-press-conference); [OCC Civil Money Penalty 2012-262](https://www.occ.gov/news-issuances/news-releases/2012/nr-occ-2012-173b.pdf). |
| **Roles affected** | CCO, MLRO, 1LoD, 2LoD, Internal Audit |
| **Cost type** | Audit-defensibility |
| **Framework capability** | One Compliance Manifest references one set of data contracts. The detector cannot fire on a different definition of "customer" than the case-bundling logic uses, because both reference the same `customer` contract by ID. *Spec Editor* surfaces the contract; *Investigations* aggregator joins back to it. The reconciliation problem becomes a validator problem — not an end-of-year project. |

### DATA-4 · "Where did this number come from?"

| | |
|---|---|
| **Plain-English description** | The board pack shows a 14% increase in high-risk-customer alerts quarter-over-quarter. The CCO is asked, in front of the audit committee, where the 14 came from. The honest answer is "the dashboard." The defensible answer requires walking back through the source extracts, the threshold settings, the model versions, and the manual reclassifications that produced the number. Most banks cannot walk back that far. |
| **Primary source** | FCA Dear CEO Letter to Annex 1 firms (March 2024, still operative in 2026): *"Decisions made in relation to financial crime were not supported by evidence or an audit trail of debate and challenge."* — [FCA letter](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf). The May 2018 ECB review of the largest 25 institutions' BCBS 239 implementation found *"none of those significant institutions… have fully implemented the BCBS 239 principles"* with implementation schedules extending past 2019; the 2023 Basel Committee progress report ([BCBS d559](https://www.bis.org/bcbs/publ/d559.htm)) confirms the gap persists across G-SIBs in 2023. Lineage is the principle most banks miss most consistently. |
| **Roles affected** | CCO, 2LoD model validation, Internal Audit, Audit Committee |
| **Cost type** | Audit-defensibility |
| **Framework capability** | The append-only `decisions.jsonl` ledger captures every input dataset's SHA-256 hash, every rule version, every threshold, every manual reclassification — chained so any tampering is detectable. *Audit & Evidence* dashboard page lets a 2LoD reviewer click any number on the executive dashboard and walk back to the run that produced it, the spec version that defined the rule, and the input file that fed it. The 14 comes from somewhere — and the framework can show *exactly* where. |

### DATA-5 · "Your data leaves our perimeter."

| | |
|---|---|
| **Plain-English description** | The vendor wants the bank's transactions, KYC profiles, and case data in their cloud, where their model runs and their dashboard renders. The CCO knows this is structurally incompatible with how the regulator looks at outsourcing — but the procurement process keeps producing SaaS shortlists anyway. *"Your data leaves our perimeter"* is the first question the OSFI / Fed / FCA exam team asks. |
| **Primary source** | OSFI Guideline B-13 — Technology and Cyber Risk Management (issued July 2022): the Guideline applies to all federally regulated financial institutions and requires comprehensive third-party risk assessment specifically covering *"how third parties handle data and the potential impact of disruptions or data breaches."* — [OSFI B-13 page](https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/guideline-b-13-technology-and-cyber-risk-management). EBA Guidelines on outsourcing arrangements (EBA/GL/2019/02, in force 30 September 2019) — [EBA outsourcing page](https://www.eba.europa.eu/activities/single-rulebook/regulatory-activities/internal-governance/guidelines-outsourcing-arrangements). The ECB's 2024 cloud-outsourcing draft guidance reinforces the same posture for SSM-supervised banks — [ECB cloud-outsourcing draft](https://www.bankingsupervision.europa.eu/framework/legal-framework/public-consultations/pdf/ssm.pubcon240603_draftguide.en.pdf). |
| **Roles affected** | CCO, CRO, CIO, Procurement, Vendor Risk |
| **Cost type** | Audit-defensibility + cost |
| **Framework capability** | Apache 2.0, single Python package, deployable into VPCs, on-prem, or air-gapped environments. The bank owns the spec, the engine, the audit ledger, the case data, and the operating cost — no per-event meter, no perpetual data-export contract, no cross-border data-residency negotiation. The framework's deployability shape is itself a response to DATA-5 — the data-sovereignty constraint is the framework's load-bearing differentiation. |

### DATA-6 · "AI presumes data we don't have."

| | |
|---|---|
| **Plain-English description** | The vendor pitch shows the AI model finding the suspicious pattern that the rules-based system missed. The pitch presumes a quality of input — clean, complete, reconciled, lineage-traced — that the bank's recent consent orders explicitly say it did not have. *"Garbage in, garbage out"* is not a slogan; it is the operating reality regulators have been writing down for fifteen years. |
| **Primary source** | OSFI Guideline E-23 — Model Risk Management (final published 11 September 2025; effective 1 May 2027) explicitly extends the model-risk perimeter: *"Artificial intelligence and machine learning (AI/ML) methods are expressly included in the definition of model."* — [OSFI E-23 backgrounder](https://www.osfi-bsif.gc.ca/en/news/backgrounder-guideline-e-23-model-risk-management). FRB SR 26-2 (effective 17 April 2026) folds BSA/AML transaction monitoring, sanctions screening, and customer-risk rating into the same model-risk inventory at US-supervised banks — [FRB SR 26-2](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm). |
| **Roles affected** | CCO, 2LoD model validation, MRM Director |
| **Cost type** | Audit-defensibility + cost |
| **Framework capability** | The framework deliberately does **not** ship an in-tree alert-scoring ML model. Detection rules are human-authored, regulation-cited, and reviewable as policy — not model artefacts. Where the institution wants to bring its own ML scorer, the `python_ref` rule type is the seam — but the model is recorded with `model_id` + `model_version` per SR 26-2 / E-23, and the input data is still captured by the same data-contract validator that catches DATA-1 / DATA-2. A one-command SR 26-2 model-population inventory (`aml model-inventory --markdown`) covering every rule, every external scorer, and the N1 prioritization scorer is on the ML/AI roadmap for Q2 2026. The framework's position is that detection improvements compound only after the data layer is defensible. |

### DATA-7 · "Engineering owns the warehouse, Compliance owns the alert."

| | |
|---|---|
| **Plain-English description** | The detection logic lives in Compliance. The data it runs on lives in Engineering. They report to different VPs, work in different ticketing systems, and answer to different boards. When the alert fires — or doesn't — the question of "whose responsibility is the data shape?" gets passed back and forth until it lands on the MLRO's desk because the MLRO's signature is on the SAR. |
| **Primary source** | BCBS 239 Principle 1 — Governance: *"A bank's risk data aggregation capabilities and risk reporting practices should be subject to strong governance arrangements"* — [BCBS 239, BIS](https://www.bis.org/publ/bcbs239.pdf). FCA Dear CEO Letter to UK retail banks (May 2021, still cited in 2025–26 supervisory framing): firms *"blurred responsibilities between first line business roles and second line compliance roles."* — [Mayer Brown analysis](https://www.mayerbrown.com/en/insights/publications/2021/08/the-fcas-dear-ceo-letter). |
| **Roles affected** | CCO, MLRO, CIO, Head of Data |
| **Cost type** | Audit-defensibility + morale |
| **Framework capability** | The Compliance Manifest is the artifact both sides commit against. The data-contract block belongs to Compliance (it's the schema each rule depends on); the data pipeline that fills it belongs to Engineering. When a contract is violated, the failure mode is loud — the validator surfaces it on the *Data Quality* dashboard, not silently in a missed alert three months later. The Manifest moves the boundary from "whose Jira ticket?" to "whose pull request against the contract?" |

### DATA-8 · "The MLRO has no veto over data shape."

| | |
|---|---|
| **Plain-English description** | The CCO discovers, post-incident, that a new product launched six months ago without surfacing transactions to the AML pipeline. The product PM treated the AML schema as a nice-to-have. By the time anyone walks back the lineage, the gap is in the consent order. |
| **Primary source** | OSFI Letter to Industry (11 September 2025), introducing the new AMP Guide effective 29 January 2026: OSFI announced *"a lower tolerance for contraventions… penalties may be issued for lower levels of potential negligence and harm, and more frequently in 2026."* — [Fasken summary](https://www.fasken.com/en/knowledge/2026/02/financial-services-regulatory-updates). FinCEN April 2026 NPRM: AML/CFT programs *"must be approved by a board of directors… designated AML/CFT officer must be located in the United States."* — [Federal Register 2026-07033](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs). FCA Dear CEO Annex 1 (March 2024): firms showed *"business growth without evolving financial crime systems and controls."* — [FCA letter](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf). |
| **Roles affected** | MLRO personally, CCO, Audit Committee |
| **Cost type** | Audit-defensibility + personal liability + morale |
| **Framework capability** | The Compliance Manifest is the veto. New product = new data contract entry, validated before the product can ship to production data pipelines. *Multi-jurisdiction* and *Program Maturity* dashboard pages render the coverage gap the moment a new geography or product is added. |

### DATA-9 · "The SAR we filed and the SAR we should have filed."

| | |
|---|---|
| **Plain-English description** | The MLRO signs off on a thousand SARs a year. Some are defensive — filed because the analyst couldn't rule out suspicion, even when nothing in the data pattern made the case. Others are missing — the genuinely suspicious customer's behaviour did not surface in time, because a transaction did not arrive in the alert engine. |
| **Primary source** | FINTRAC on RBC (2023, $7.5M penalty — the largest in FINTRAC history): the bank *"failed to flag suspicious activity, neglected to keep its written AML policies and procedures up to date and did not disclose relevant information in suspicious transaction reports… failed to submit 16 suspicious transactions reports across 130 customer files."* — [ACAMS coverage](https://www.acams.org/en/news/fintrac-fines-royal-bank-of-canada-record-7-5-million-for-aml-failings). TD Bank's $1.3B FinCEN penalty (October 2024) similarly turned on monitoring gaps that prevented downstream reporting — [FinCEN release](https://www.fincen.gov/news/news-releases/fincen-assesses-record-13-billion-penalty-against-td-bank). |
| **Roles affected** | MLRO, 1LoD analyst, FIU lead, Internal Audit |
| **Cost type** | Audit-defensibility + regulatory-penalty exposure |
| **Framework capability** | Investigation-aggregator (`cases/aggregator.py`) joins alerts to a deterministic INV-{sha256[:16]} ID; STR auto-bundling packages narrative + goAML XML + Mermaid diagrams + manifest hash. STR filing-latency p95 is a first-class metric on the Executive Dashboard's effectiveness funnel. The chain from raw transaction → alert → case → narrative → submitted STR is one append-only ledger. |

### DATA-10 · "We can't see what the other bank is seeing."

| | |
|---|---|
| **Plain-English description** | A customer wires money out of Bank A and into Bank B. Bank A files an STR. Bank B's monitoring system has no signal that Bank A flagged anything. The typology that requires both halves of the transaction to be visible to fire correctly only exists across institutional boundaries. |
| **Primary source** | The Wolfsberg Group's CBDDQ V1.4 (April 2024) sets the global standard for what information correspondent banks share — [Wolfsberg CBDDQ V1.4](https://wolfsberg-group.org/resources/correspondent-banking). FATF Recommendation 18 (still operative in 2026) requires financial institutions to apply group-wide AML/CFT programs including policies for sharing information required for customer due diligence. FinCEN's section 314(b) of the USA PATRIOT Act provides the US-domestic safe harbour for voluntary information sharing. |
| **Roles affected** | CCO, MLRO, Head of Correspondent Banking, FIU lead |
| **Cost type** | Audit-defensibility + missed-typology risk |
| **Framework capability** | The framework ships a **cross-border information-sharing sandbox** (`compliance/sandbox.py`) — a reference implementation of how a Manifest can declare information-sharing partners, scope, and audit trail, so that 314(b) / Wolfsberg / FATF R.18 compliance becomes a configurable contract rather than a bilateral negotiation re-invented per partnership. |

### DATA-11 · "The compliance-defensible answer is a data contract, not a detection upgrade."

| | |
|---|---|
| **Plain-English description** | The framework's load-bearing claim is that everything above is solved at the data-contract layer, before the detector runs. *Disclosure: this framework is positioned around this thesis.* It is included in this doc not as marketing but because the doc would be incomplete without naming what the alternative posture looks like. The PAIN doc style guide warned against framework promotion in leader-facing copy; in this section, the framework is the worked example. |
| **Primary source** | FinCEN April 2026 NPRM (Federal Register 2026-07033) is the most explicit recent statement of what an AML program's evidence layer must produce — board approval, designated officer, *risk assessment, internal controls, independent testing,* training, and documentation that ties controls back to risks. Comment window closes June 9, 2026 (41 days). — [Federal Register 2026-07033](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs). FRB SR 26-2 + OCC Bulletin 2026-13 (effective 17 April 2026) require independent challenger validation of model-risk components — [SR 26-2](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm). |
| **Roles affected** | CCO, MLRO, 2LoD, MRM Director, Internal Audit |
| **Cost type** | Audit-defensibility |
| **Framework capability** | One versioned `aml.yaml` declares the data contracts every detector depends on. Two-layer validation (JSON Schema + Pydantic cross-references) catches contract violations before the engine runs. Same spec + same data + same seed = identical output hashes — the deterministic-replay guarantee is what makes the audit ledger byte-replayable rather than just append-only. The Manifest is the document Compliance and Engineering both commit against. The audit ledger is the document the regulator replays. |

---

## Themes (≈150 words)

The dominant message in 2026 primary sources is that **data, not detection, is the binding constraint on AML program effectiveness**. BCBS 239 has codified this since 2013; the Basel Committee's 2023 progress report shows G-SIBs still don't meet the principles a decade later. FinCEN's April 2026 NPRM (comment window open through June 9), OSFI's revised E-23 (effective 2027), FRB SR 26-2 (examination-active April 17, 2026), and the FCA's 2024 Annex 1 letter converge on the same operational posture: programs must produce evidence — data lineage, decision rationale, control coverage — on demand. The largest recent enforcement orders (TD 2024, RBC 2023) are not detection-failure cases; they are data-and-process cases dressed up as detection cases. The vendor "AI" wave presumes a data quality the consent orders show does not exist. The framework's position — spec-as-data-contract, deterministic re-run, hash-chained audit ledger — is a response to the data layer, not the detection layer.

---

## Where the framework closes each pain (DATA-N → artifact map)

Every claim above maps to a concrete framework artifact — a dashboard page, a CLI command, a Python module, or a test file.

| Pain | Page | CLI | Module / test |
|---|---|---|---|
| **DATA-1** Fail-closed contract validation | Data Integration · Contract roll-up · Data Quality | `aml validate-data <spec> <data-dir>` · `aml run --strict` | `engine/runner.py::_validate_contracts` · `tests/test_contract_validation.py` |
| **DATA-2** Per-attribute freshness pinning | Customer 360 · staleness expander · Data Integration | `aml run --strict` (refuses stale attributes) | `spec/models.py::Column.max_staleness_days` · `engine/freshness.py` |
| **DATA-3** Cross-system reconciliation | Audit & Evidence (decision log) | `aml run` emits `reconciliation.jsonl` per contract | `engine/runner.py` reconciliation pass |
| **DATA-4** Lineage walk-back from KPI | Audit & Evidence · decision log | `aml export --include-lineage` | `engine/audit.py::walk_lineage` |
| **DATA-5** In-bank, not SaaS (data sovereignty) | Data Integration · source catalogue | Docker / Helm — see `deployment.md` | `data/sources.py` (no SaaS dependency in any loader) |
| **DATA-6** AI presumes data (fail-closed gate) | Closes transitively via DATA-1 | `aml run --strict` halts on contract violation | `assistant/factory.py` checks contract pass before backend invocation |
| **DATA-7** Engineering vs Compliance ownership boundary | Spec Editor · Data Integration | `aml validate <spec>` (engineering) · `aml attest` (compliance) | `spec/models.py` (the boundary IS the spec) |
| **DATA-8** Payment-rail data (ISO 20022 native) | Data Integration · ISO 20022 message-type chart | `aml run --data-source iso20022 --data-dir <xml-dir>` | `data/iso20022/parser.py` (pacs.008/009/004 + pain.001) |
| **DATA-9** STR/SAR filing-latency wall-clock | Audit & Evidence — `cases/<id>__filing.json` sidecars | `aml export` rolls filing latency into the bundle | `cases/str_bundle.py` |
| **DATA-10** Cross-bank information sharing | Information Sharing · share-pattern artifacts | `aml share-pattern` · `aml verify-pattern` | `compliance/sandbox.py` (FATF R.18 / 314(b) seam) |
| **DATA-11** Spec as data contract (versioned, hashable) | Audit & Evidence — spec hash on every run | `aml validate <spec>` (JSON Schema + Pydantic two-layer) | `spec/loader.py` · `engine/audit.py` (hash-chained ledger) |

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
- "garbage in, garbage out" — replace with the FCA / BCBS framing: *"the controls cannot fire on data the bank does not have."*
- "data sovereignty" alone — translate to *"the bank owns where the data sits"* and cite OSFI B-13 / EBA outsourcing.

---

## Sources

- [BCBS 239 — Principles for effective risk data aggregation and risk reporting (BIS, January 2013)](https://www.bis.org/publ/bcbs239.pdf)
- [BCBS d559 — 2023 Progress in adopting BCBS 239 principles](https://www.bis.org/bcbs/publ/d559.htm)
- [FCA Dear CEO Letter — Annex 1 firms (March 2024)](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf)
- [FCA Dear CEO — UK retail banks (May 2021), via Mayer Brown](https://www.mayerbrown.com/en/insights/publications/2021/08/the-fcas-dear-ceo-letter)
- [FinCEN — TD Bank record $1.3B penalty (October 2024)](https://www.fincen.gov/news/news-releases/fincen-assesses-record-13-billion-penalty-against-td-bank)
- [FinCEN — AML Program NPRM, Federal Register 2026-07033](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs)
- [DOJ — HSBC press conference (December 11, 2012)](https://www.justice.gov/archives/opa/documents-and-resources-december-11-2012hsbc-press-conference)
- [OCC — HSBC Civil Money Penalty 2012-262](https://www.occ.gov/news-issuances/news-releases/2012/nr-occ-2012-173b.pdf)
- [ACAMS — FINTRAC fines RBC record $7.5M for AML failings (2023)](https://www.acams.org/en/news/fintrac-fines-royal-bank-of-canada-record-7-5-million-for-aml-failings)
- [OSFI — Guideline E-23 Model Risk Management (final, 2027)](https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/guideline-e-23-model-risk-management-2027-letter)
- [OSFI — Guideline B-13 Technology and Cyber Risk Management (2022)](https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/guideline-b-13-technology-and-cyber-risk-management)
- [OSFI Letter to Industry — September 11, 2025 (AMP guide)](https://www.fasken.com/en/knowledge/2026/02/financial-services-regulatory-updates)
- [EBA — Guidelines on outsourcing arrangements EBA/GL/2019/02](https://www.eba.europa.eu/activities/single-rulebook/regulatory-activities/internal-governance/guidelines-outsourcing-arrangements)
- [ECB — Cloud-outsourcing draft guide (June 2024)](https://www.bankingsupervision.europa.eu/framework/legal-framework/public-consultations/pdf/ssm.pubcon240603_draftguide.en.pdf)
- [FRB SR 26-2 — Revised Model Risk Management guidance (effective April 17, 2026)](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm)
- [OCC Bulletin 2026-13 — Model Risk Management](https://www.occ.treas.gov/news-issuances/bulletins/2026/bulletin-2026-13.html)
- [Wolfsberg Group — Correspondent Banking resources & CBDDQ](https://wolfsberg-group.org/resources/correspondent-banking)
- [FinCEN Whistleblower NPRM — Federal Register 2026-06271](https://www.federalregister.gov/documents/2026/04/01/2026-06271/whistleblower-incentives-and-protections)
- [GENIUS Act PPSI NPRM — Federal Register 2026-06963](https://www.federalregister.gov/documents/2026/04/10/2026-06963/permitted-payment-stablecoin-issuer-anti-money-launderingcountering-the-financing-of-terrorism)

*Next edition: [May 2026 data-problem whitepaper](./2026-05-aml-data-problem.md).*
