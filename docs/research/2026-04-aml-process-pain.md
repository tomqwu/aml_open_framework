# 10 Daily Pain Points an AML Leader Feels — 2026

*Date: 2026-04-29 · Audience: CCO / MLRO / Head of Financial Crime at a Tier-1 / Tier-2 bank. For FinTech / EMI / MSB / VASP MLRO pain points, see the companion doc [`2026-04-fintech-aml-reality.md`](./2026-04-fintech-aml-reality.md).*

## How to use this doc

This is the **style guide** for every leader-facing word in this repository — README headlines, dashboard page descriptions, deck slides, exec emails. Before you write copy aimed at a CCO, MLRO, Head of Financial Crime, or CRO, find the closest pain point below and **borrow its plain-English phrasing**. Each pain is anchored in a primary source (regulator letter, enforcement order, or cited industry survey) so the copy is defensible the moment a buyer asks "where did you get that?"

Three rules behind everything in the table:

1. **Audit-defensibility, not detection, is the dominant pain in 2026.** Across recent enforcement orders surveyed (TD, RBC, Wells, NatWest, Citibank), regulators rarely allege the bank missed a typology — they allege the bank cannot evidence what it did, when, or why. Process and governance gaps outnumber data and model gaps roughly 2:1 in the consent orders. *Lead with proof, not detection.*
2. **CCOs publicly say "alert volume," but the underlying ailment is "alert quality."** The 95% false-positive figure is industry-canonical; cite it sparingly and never as our number — it's the *baseline* the framework helps escape. *Frame in terms of analyst attention, not alerts.*
3. **Write the way they speak.** "We couldn't prove what ran." "The backlog has been red on the board for years." "My monitoring system is a model and I cannot validate it." These are real CCO sentences from public sources — not vendor copy. Copy paste before paraphrasing.

PR-2 (README), PR-3 (dashboard page descriptions), and PR-4 (glossary) all cite **PAIN-N** identifiers from this table.

---

## The 10 pains

### PAIN-1 · "We can't prove what we did."

| | |
|---|---|
| **Plain-English description** | Decisions get made every day — alerts triaged, customers exited, scenarios re-tuned — but when the regulator asks "show us the working," the audit trail is a Word doc, three people's memory, and a SharePoint folder no one can search. |
| **Primary source** | FCA Dear CEO Letter to Annex 1 firms, March 2024 (still operative in 2026): *"Decisions made in relation to financial crime were not supported by evidence or an audit trail of debate and challenge."* — [FCA letter](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf). Reinforced by K&L Gates' 2024 BSA review which found examiner testing "only determined whether controls existed rather than if they were actually being used." |
| **Roles affected** | CCO, MLRO, Internal Audit |
| **Cost type** | Audit-defensibility |
| **Framework capability** | Hash-chained audit ledger + deterministic replay → any historical run reproducible byte-for-byte. *Audit & Evidence* dashboard page; PR #97 (rule-effectiveness backtester) extends this to "show me the rule's track record." |

### PAIN-2 · "The backlog is red — and the board has known for years."

| | |
|---|---|
| **Plain-English description** | Alerts pile up faster than analysts can clear them. The dashboards show it. The board approves the program anyway. Then a regulator notices, and what was a slide becomes a consent order. |
| **Primary source** | TD Bank Consent Order (FinCEN, October 2024 — the framing case for every 2025-26 enforcement narrative): TD allowed *"trillions of dollars in transactions annually to go unmonitored"*; the AIU detection queue was in **"red status"** in board reporting for years, attributable to chronic understaffing. — [FinCEN release](https://www.fincen.gov/news/news-releases/fincen-assesses-record-13-billion-penalty-against-td-bank). Also see [TD case study](../case-studies/td-2024.md) in this repo. |
| **Roles affected** | CCO, MLRO, 1LoD analyst, CRO |
| **Cost type** | Audit-defensibility + morale |
| **Framework capability** | SLA timer + escalation engine → red queues become loud, not slide-decoration. *Investigations* dashboard page; per-queue breach-rate badges; FCA-Dear-CEO-letter-style backlog view. |

### PAIN-3 · "95 of every 100 alerts are noise."

| | |
|---|---|
| **Plain-English description** | Analysts spend their week clearing legitimate transactions. The real bad actor is somewhere in the queue they didn't get to. By Friday, the queue has grown — not shrunk. |
| **Primary source** | "With industry false positive rates averaging 95%, financial institutions waste millions investigating legitimate transactions." — [Flagright industry analysis](https://www.flagright.com/post/understanding-false-positives-in-transaction-monitoring); reinforced by Celent / NICE Actimize 2026 framing of *"moving from volume-driven processing to signal-driven decision making"* — [eClerx](https://eclerx.com/insights/three-shifts-reshaping-financial-crime-compliance-in-2026/). |
| **Roles affected** | 1LoD analyst, MLRO |
| **Cost type** | Cost + morale |
| **Framework capability** | Tuning Lab + threshold sweeps with precision/recall scoring → analyst attention buys signal, not noise. PR #97 backtester answers "is this rule still earning its keep?" without commissioning a vendor study. |

### PAIN-4 · "Our risk assessment is a PDF nobody trusts."

| | |
|---|---|
| **Plain-English description** | The Business Risk Assessment is supposed to drive everything — scenarios, thresholds, training, board reporting. In practice it lives in a binder, was last refreshed 18 months ago, and the regulator notices first. |
| **Primary source** | FCA Dear CEO: *"Many Annex 1 firms did not have a BRA in place… the quality of the BRA was poor in terms of detail and methodology."* — [FCA via Waystone](https://compliance.waystone.com/insights-from-the-fcas-dear-ceo-letter-addressing-financial-crime-risks-in-annex-1-firms/). FINTRAC has reclassified missing/stale risk assessments as **"very serious"** violations under its 2025 AMP regime. — [AML Incubator](https://amlincubator.com/blog/fintracs-new-amp-regime-in-2025-record-penalties-and-higher-stakes). |
| **Roles affected** | CCO, 2LoD, Internal Audit |
| **Cost type** | Audit-defensibility |
| **Framework capability** | The Compliance Manifest **is** the risk assessment in machine-readable form — every rule cites the regulation it answers. *Framework Alignment* and *Program Maturity* dashboard pages render the live BRA from the Manifest. |

### PAIN-5 · "Business grew, controls didn't."

| | |
|---|---|
| **Plain-English description** | New product, new geography, new payment rail. The financial-crime team finds out when alerts start firing or when the OCC asks. Growth got an executive sponsor; controls got a Jira ticket. |
| **Primary source** | FCA: firms showed *"business growth without evolving financial crime systems and controls… inadequately resourcing financial crime teams alongside business growth."* — [FCA letter](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf). OCC Wells Fargo enforcement (Sep 2024, still active in 2026): bank now barred from *"expanding into medium-to-high risk products and geographies without prior approval."* — [Banking Dive](https://www.bankingdive.com/news/occ-hits-wells-fargo-with-aml-enforcement-action/726890/). |
| **Roles affected** | CCO, MLRO, CRO |
| **Cost type** | Audit-defensibility |
| **Framework capability** | New product = new Manifest entries in days, not quarters; PR #100 (US RTP/FedNow detector pack) ships in one PR with full citations. *Multi-jurisdiction* page shows coverage gaps the moment a new geography is added. |

### PAIN-6 · "My monitoring system is a model and I cannot validate it."

| | |
|---|---|
| **Plain-English description** | Vendor scenarios are a black box. Tuning takes a quarter. SR 11-7 (and its 2026 rescission in favour of a principles-based framework) still expects evidence the box is fit for purpose. The MLRO has to challenge a system she can't see inside. |
| **Primary source** | ACAMS on the 2021 Interagency Statement (still the reference frame in 2026): transaction-monitoring systems, customer-risk rating, and watch-list filtering *"meet the definition of 'model'… held to the same standard."* — [ACAMS](https://www.acams.org/en/opinion/effective-aml-model-risk-management-for-financial-institutions); [Databricks 2026 banker's guide](https://www.databricks.com/blog/model-risk-management-2026-bankers-guide-revised-interagency-guidance). **Language note:** banks call it "model risk management" in regulatory filings; internally they say *"tuning"* or *"scenario performance"*. **In leader-facing copy use "we can show our model still works" — not "MRM."** |
| **Roles affected** | CCO, 2LoD model validation, Internal Audit |
| **Cost type** | Cost + audit-defensibility |
| **Framework capability** | Per-rule MRM dossier (`generators/mrm.py`) + PR #97 backtester → "rule X precision/recall trend over the last 4 quarters" answered before lunch. The Compliance Manifest itself is human-readable, so "the model" stops being a black box. |

### PAIN-7 · "We file SARs we don't believe in, and we miss the ones we should file."

| | |
|---|---|
| **Plain-English description** | The bank files thousands of defensive SARs the analyst doesn't believe in, while the genuinely-suspicious case sits in the queue past its filing deadline. The defect is data quality and case completeness, not analyst effort. |
| **Primary source** | FINTRAC on RBC (2024, $7.5M penalty): bank *"failed to flag suspicious activity, neglected to keep its written AML policies and procedures up to date and did not disclose relevant information in suspicious transaction reports… failed to submit 16 suspicious transactions reports across 130 customer files."* — [ACAMS](https://www.acams.org/en/news/fintrac-fines-royal-bank-of-canada-record-7-5-million-for-aml-failings); [Global Relay](https://www.grip.globalrelay.com/fintrac-imposes-its-largest-ever-aml-fine-on-royal-bank-of-canada/). |
| **Roles affected** | MLRO, 1LoD analyst |
| **Cost type** | Audit-defensibility |
| **Framework capability** | Case-to-STR auto-bundling (PR #64) + STR filing latency p95 metric + auto-drafted narratives drawing from the alert evidence chain → analyst writes the narrative, not the bundle. |

### PAIN-8 · "$61 billion a year — and I still can't tell the CEO what we got for it."

| | |
|---|---|
| **Plain-English description** | The bill is real and visible. The return is not. Vendor licences, consulting fees, audit-prep contractors, FTE growth — all line items. ROI is uncostable line-by-line, so the CFO ends every annual review with the same question: *"is the juice worth the squeeze?"* |
| **Primary source** | LexisNexis Risk Solutions, *True Cost of Financial Crime Compliance, US & Canada* (Feb 2024): *"annual cost of financial crime compliance totals $61 billion in the United States and Canada."* — [press release](https://risk.lexisnexis.com/about-us/press-room/press-release/20240221-true-cost-of-compliance-us-ca). FinCEN's Sep 2025 RFI on AML compliance costs explicitly framed the question *"Is the juice worth the squeeze?"* — [Mayer Brown summary](https://www.mayerbrown.com/en/insights/publications/2025/10/fincen-issues-request-for-information-on-aml-compliance-costs-is-the-juice-worth-the-squeeze). Vendor-licence dollar amounts are uncostable in published sources — they surface only in vendor-buyer guides ("$800K–$1.2M typical implementation, with hidden costs beyond the licence" — [Finantrix](https://www.finantrix.com/buyer-guides/aml-transaction-monitoring-banks-fintechs)) not in CCO-attributed quotes. |
| **Roles affected** | CCO, CRO, CFO |
| **Cost type** | Cost |
| **Framework capability** | Apache 2.0, runs in your perimeter, no per-seat licence; effectiveness pack quantifies what the spend bought. Deck slide *Cost of Status Quo* maps 6 cost pools to specific framework deltas. |

### PAIN-9 · "1LoD and 2LoD don't know whose risk it is."

| | |
|---|---|
| **Plain-English description** | The business books the customer. Compliance owns the alert. Neither owns the outcome. The auditor finds the gap. Three people answer "who decided?" with the other two people's names. |
| **Primary source** | FCA (2021 retail-bank Dear CEO letter, still cited in 2025-26 supervisory framing): firms *"blurred responsibilities between first line business roles and second line compliance roles, such that first line employees often do not own or fully understand the financial crime risk faced by the firm."* — [Lexology](https://www.lexology.com/library/detail.aspx?g=df2caec4-a52e-4dfe-8d41-715994233b5e); [Mayer Brown](https://www.mayerbrown.com/en/insights/publications/2021/08/the-fcas-dear-ceo-letter). |
| **Roles affected** | 1LoD, 2LoD, CCO |
| **Cost type** | Audit-defensibility + morale |
| **Framework capability** | One Compliance Manifest — same artifact 1LoD ships, 2LoD reviews, 3LoD attests. PR #98 (fraud-AML case linkage) makes overlapping work visible across operational lines. Deck slide *Three Lines of Defence* shows the handoff explicitly. |

### PAIN-10 · "The Officer's name is on the line, personally."

| | |
|---|---|
| **Plain-English description** | OSFI's January 2026 AMP Guide and FINTRAC's 2025 reclassification mean the MLRO is no longer shielded by "the program." Personal accountability is sharper. The signature on the SAR matters; the gap in the audit trail matters more. |
| **Primary source** | OSFI Letter to Industry (11 September 2025): OSFI announced *"a lower tolerance for contraventions… penalties may be issued for lower levels of potential negligence and harm, and more frequently in 2026,"* with new AMP Guide published 29 Jan 2026. — [Fasken summary](https://www.fasken.com/en/knowledge/2026/02/financial-services-regulatory-updates). FinCEN NPRM (Apr 2026) reinforces: AML/CFT programs *"must be approved by a board of directors… designated AML/CFT officer must be located in the United States."* — [Federal Register](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs); [Volkov Law analysis](https://blog.volkovlaw.com/2026/04/fincens-proposed-aml-reform-signals-a-shift-toward-risk-based-enforcement-and-program-accountability/). |
| **Roles affected** | CCO, MLRO personally |
| **Cost type** | Morale + audit-defensibility |
| **Framework capability** | Hash-chained ledger + deterministic replay = the Officer can sign a control attestation she actually believes. PR #102 (FINOS Open Compliance API) lets the institution prove it engaged peers when it should have. |

---

## Themes (≈100 words)

The dominant pain in 2026 sources is **audit-defensibility, not detection** — regulators rarely allege the bank missed a typology; they allege the bank cannot evidence what it did, when, or why (FCA, TD, RBC). Process and governance gaps outnumber data and model gaps roughly 2:1 in the consent orders surveyed. CCOs publicly complain about **alert volume**, but the underlying ailment is **alert quality** — the 95% false-positive figure is industry-canonical. "Model risk management" is the regulators' term; banks internally say "tuning." Vendor-licence cost is real but stays off-record. The single most-quoted CCO frustration is the **backlog-in-red dashboard the board keeps approving anyway** — TD's defining wound, now everyone's reference point.

---

## Style guide — phrases to use, phrases to avoid

### Use these (real CCO sentences, defensible to a buyer)

- *"What you'd hand a regulator if they walked in tomorrow"*
- *"What changed overnight, what needs attention"*
- *"We can show our model still works"* (instead of "MRM")
- *"The backlog is red on the board"*
- *"Decisions you can prove later"*
- *"Active investigations across teams, ranked by SLA urgency"*
- *"Who's behind every entity customer — and which ones need a refresh"* (BOI)

### Avoid these on leader-facing surfaces

- "spec", "aml.yaml", "YAML", "schema", "Pydantic", "DuckDB", "FastAPI" — use **"Compliance Manifest"** when referring to the source-of-truth file
- "decisions.jsonl" — use **"audit ledger"**
- "deterministic", "hash chain" — use "audit trail you can replay"
- "MRM" — use "model validation" or "show the model still works"
- "aggregation strategies", "evidence bundle" — use "examination ZIP" or "regulator pack"
- "primitives", "spec primitives" — use **"Manifest entries"** or "building blocks"
- "rule logic", "rule engine" — use "detector" or "what fires the alert"

These terms are still correct on developer-facing surfaces (Spec Editor page, Run History, code, contributor docs). The goal is **hide them from leaders**, not delete them.
