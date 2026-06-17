# Data is the AML problem — April 2026

*Date: 2026-04-29 · Audience: CCO / MLRO / Head of Financial Crime / CRO / 2LoD model-validation. Companion docs: [`2026-04-aml-process-pain.md`](./2026-04-aml-process-pain.md) for the leader-pain style guide; [`2026-04-competitive-positioning.md`](./2026-04-competitive-positioning.md) for the vendor landscape.*

## April 2026: The Data Thesis Just Got Statutory Authority

Three April 2026 regulatory events convert the data-problem from "institutional inconvenience" to "examination-active obligation":

1. **SR 26-2 (April 17)** — The Federal Reserve, OCC, and FDIC jointly revised interagency model risk management guidance (superseding SR 11-7 and SR 21-8), explicitly folding BSA/AML transaction monitoring, sanctions screening, name-matching, and customer risk-rating into the same model-inventory framework as credit and market models. Every AML detection rule that scores or categorises customers now requires model documentation: conceptual soundness, data lineage, ongoing monitoring, outcome analysis. The data that feeds those models is no longer an engineering concern — it is a model-risk artefact.

2. **AML/CFT Program Effectiveness NPRM (April 7/10, FR 2026-07033)** — FinCEN, OCC, FDIC, and NCUA jointly proposed reframing the BSA program rule around an "effective, risk-based, reasonably designed" standard. A documented enterprise-wide risk assessment becomes a pillar; "effectiveness" splits into (1) program established and (2) program maintained. Comment deadline: 2026-06-09.

3. **GENIUS Act PPSI NPRM (April 8/10, FR 2026-06963)** — FinCEN and OFAC jointly proposed treating permitted payment stablecoin issuers (PPSIs) as Bank Secrecy Act financial institutions, introducing mandatory OFAC-specific sanctions compliance programs under new 31 CFR Part 502. Same comment deadline: 2026-06-09.

Each event imposes new documentation burdens that land directly on the data layer. SR 26-2 requires every AML model to have a provable data lineage. The Effectiveness NPRM requires the program to demonstrate that risk data is being captured, processed, and acted on. These aren't new ideas — they are the same eleven data problems the industry has managed around for a decade, now with enforcement teeth.

---

## How to read this doc

The pain doc argues that **audit-defensibility, not detection, is the dominant pain in 2026**. This doc argues the next layer down: **the binding constraint underneath audit-defensibility is data**. Detection presumes data the bank often does not have. Audit-defensibility presumes a lineage the bank often cannot reproduce. Vendor AI presumes a quality of input that public enforcement orders show does not exist.

Three rules behind the analysis:

1. **Audit-defensibility, not detection, is the dominant pain.** Across recent enforcement orders (TD 2024, RBC 2024, HSBC 2012, Wells 2024, NatWest), regulators rarely allege the bank missed a typology — they allege the bank could not produce the data, evidence the lineage, or reconcile the systems.
2. **CCOs publicly say "alert volume," but the underlying ailment is "alert quality" — and quality is a function of data.** A 95% false-positive rate is what you get when you run a typology against incomplete KYC, stale customer profiles, and unreconciled transaction streams.
3. **Write the way regulators speak.** "We failed to capture all material risk data." "The bank could not aggregate exposures fully, quickly and accurately." "Decisions were not supported by an audit trail."

This doc uses the **DATA-N** identifier convention.

---

## Artifact map: framework capabilities vs. April 2026 obligations

| DATA-N | Problem | Framework capability | April 2026 hook |
|--------|---------|---------------------|-----------------|
| DATA-1 | No data for the detector to fire on | `data_contract` block + validator fails closed on schema gaps | Effectiveness NPRM: program must demonstrate all material risk categories are monitored |
| DATA-2 | Stale KYC feeds the detector | `effective_dated` contract + `enrich` as-of JOIN | SR 26-2: model inputs must be accurate and current; stale-feed documentation is MRM-reportable |
| DATA-3 | Three systems, three answers | One Compliance Manifest → one contract ID per data table | Effectiveness NPRM: a documented risk assessment requires a single authoritative customer-risk view |
| DATA-4 | "Where did this number come from?" | Append-only `decisions.jsonl` with per-run input SHA-256 hashes | SR 26-2: model documentation requires lineage from model output back to input data and version |
| DATA-5 | Data leaves the perimeter | Apache 2.0 in-bank deployment; no SaaS data-export contract | SR 26-2 + OSFI B-13: third-party data-risk assessment now a formal MRM obligation |
| DATA-6 | AI presumes data we don't have | `python_ref` seam captures `model_id` + `model_version` per SR 26-2; detection improvements compound only after data is defensible | SR 26-2: AML scoring models must have validated data inputs; TM, sanctions, and name-matching explicitly named |
| DATA-7 | Engineering owns the warehouse, Compliance owns the alert | Compliance Manifest as shared contract both sides commit against | Effectiveness NPRM: program must identify "the person responsible for each element of the risk assessment" |
| DATA-8 | MLRO has no veto over data shape | New product = new data contract entry; validator blocks before production pipeline | OSFI AMP Guide (January 2026): lower tolerance for personal-accountability contraventions |
| DATA-9 | SAR filed vs SAR that should have been filed | Investigation aggregator + STR bundle with SHA-256 chain txn → case → narrative | Effectiveness NPRM: "suspicious activity is identified, escalated, and reported" — the unbroken chain |
| DATA-10 | Can't see what the other bank sees | `resolved_entity_link` + `aml detect-mule-rings` for cross-account network view | FATF R.18 group-wide AML/CFT program requirement; AMLA cross-border supervision mandate |
| DATA-11 | The five-year lookback problem | `aml run --replay` reconstructs any historical run byte-identically | FinCEN exam standard; TD Bank consent order five-year lookback obligation |

---

## Key items — April 2026 edition

### DATA-2 · Stale beats stale beats stale — now an SR 26-2 finding

SR 26-2's conceptual-soundness requirement means that a detector fed stale KYC is not just operationally noisy — it is a documentable model deficiency. The model's stated purpose ("detect structuring against customer risk profile") cannot be met if the risk profile is seven years old. That gap now belongs in the model-inventory entry alongside the model's validation schedule.

The framework's M4 response (point-in-time effective-dated joins, v0.1.47): `DataContract.effective_dated: {valid_from, valid_to}` + `aggregation_window.enrich: {contract, key, where}` make the SQL generator emit an as-of JOIN so a rule resolves the customer's risk state *contemporaneous with each transaction*, not the latest row. A customer whose risk goes low→high mid-window is counted only for the transactions booked while high.

**Sources:** [SR 26-2, 2026-04-17](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm) · [BCBS 239 Principle 3 (Accuracy and Integrity)](https://www.bis.org/publ/bcbs239.pdf)

---

### DATA-4 · "Where did this number come from?" — SR 26-2 makes lineage mandatory

SR 26-2's model-documentation requirements explicitly cover the chain from model output to input data, including version control and reproducibility. The FCA Dear CEO letter (March 2024) phrased the same failure in enforcement terms: "Decisions made in relation to financial crime were not supported by evidence or an audit trail of debate and challenge."

The framework's response: the append-only `decisions.jsonl` ledger captures every input dataset's SHA-256 hash, every rule version, every threshold, and every manual reclassification — chained so any tampering is detectable. The *Audit & Evidence* dashboard page lets a 2LoD reviewer click any number on the executive dashboard and walk back to the run that produced it, the spec version that defined the rule, and the input file that fed it.

**Sources:** [SR 26-2, 2026-04-17](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm) · [FCA Dear CEO Letter, March 2024](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf)

---

### DATA-6 · AI presumes data we don't have — SR 26-2 gives this a formal inventory entry

The vendor pitch shows the AI finding the suspicious pattern the rules missed. SR 26-2 now requires that the same model-documentation framework applying to credit models applies to that detection model: purpose statement, conceptual soundness, data-quality assessment, ongoing monitoring, outcome analysis, independent validation for material-tier models.

The framework's position: the `python_ref` rule type is the seam for bringing institution-built ML scorers into the detection pipeline. Each `python_ref` rule carries `model_id` + `model_version` per SR 26-2 / OSFI E-23. The `aml model-inventory` CLI (M2, v0.1.47) produces the full SR 26-2 model-population inventory on demand — covering every rule, every `python_ref` external model, and the N1 prioritization scorer.

**Sources:** [SR 26-2, 2026-04-17](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm) · [OSFI E-23 final, September 2025](https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/guideline-e-23-model-risk-management-2027-letter) · [OCC Bulletin 2026-13](https://www.occ.treas.gov/news-issuances/bulletins/2026/bulletin-2026-13.html)

---

### DATA-9 · The SAR chain — Effectiveness NPRM makes it an explicit program requirement

The Effectiveness NPRM names the outcome it measures: programs must demonstrate that "suspicious activity is identified, escalated, and reported." That is a data-continuity requirement, not a detection requirement. The bank must show the chain is unbroken from the data that fed the detector, through the alert, through the case, through the SAR narrative, to the submitted form.

The FINTRAC RBC penalty (2024, $7.5M — FINTRAC's largest ever): the bank "failed to submit 16 suspicious transaction reports across 130 customer files." The data to file existed somewhere; it did not arrive at the regulator-facing form.

The framework's response: the investigation aggregator (`cases/aggregator.py`) joins alerts to a deterministic INV-{sha256[:16]} ID; STR auto-bundling packages narrative + goAML XML + Mermaid diagrams + manifest hash. STR filing-latency p95 is a first-class metric on the Executive Dashboard's effectiveness funnel.

**Sources:** [FR 2026-07033 — Effectiveness NPRM](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs) · [FINTRAC on RBC, 2024](https://www.acams.org/en/news/fintrac-fines-royal-bank-of-canada-record-7-5-million-for-aml-failings)

---

*Next edition: [`2026-05-aml-data-problem.md`](./2026-05-aml-data-problem.md) — covers what changed between April and May, with an updated artifact map. Full regulatory log: [`2026-04-regulator-pulse.md`](./2026-04-regulator-pulse.md) — 89 days, 30 events.*
