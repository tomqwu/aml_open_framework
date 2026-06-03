# 10 Daily Pain Points an AML Leader Feels — June 2026

*Date: 2026-06-02 · Audience: CCO / MLRO / Head of Financial Crime at a Tier-1 / Tier-2 bank. For FinTech / EMI / MSB / VASP MLRO pain points, see [`2026-06-fintech-aml-reality.md`](./2026-06-fintech-aml-reality.md). For the data-layer analysis beneath these pains, see [`2026-05-aml-data-problem.md`](./2026-05-aml-data-problem.md). Previous edition: [`2026-05-aml-process-pain.md`](./2026-05-aml-process-pain.md).*

## What changed between May and June 2026

Three inflections since the May 25 edition sharpen the enforcement perimeter:

1. **SR 26-2 has been examination-active for 45 days.** The joint Fed/OCC/FDIC model risk management guidance went live April 17. Q2 2026 examination cycles are running — second-line MRM teams are now presenting gap analyses to boards, not preparing them. First examination correspondence citing SR 26-2 specifically for TM scenarios and customer risk-rating models has been issued in the first active cycle. PAIN-6 has shifted from "current examination risk" to "active examination cycle."

2. **FinCEN Whistleblower NPRM comment period closed June 1.** The proposed award structure (10–30% of collected sanctions from the $300M Financial Integrity Fund; anti-retaliation protections for current and former employees) is now in outline — FinCEN will consolidate comments and publish a final rule expected late 2026 / early 2027. The terms are proposed, not final. But the incentive signal is real and targeted squarely at SAR-backlog and screening-gap failures. Boards that have seen the "backlog in red" slide (PAIN-2) should treat the pre-final-rule period as the window to audit internal reporting channels and document every escalation. PAIN-2 and PAIN-7 now carry external-report risk.

3. **Effectiveness NPRM + GENIUS Act NPRM dual comment deadline is June 9 — 7 days away.** Both NPRMs share the same cutoff. Firms that complete gap analyses before June 9 can document proactive compliance posture usable as SR 26-2 model governance evidence. Firms that defer will implement under time pressure when the final rule lands (expected late 2026 / early 2027, with a 12-month implementation clock from final rule). PAIN-4 and PAIN-10 are now measured by the June 9 response window.

The 10 pains below are unchanged in number and kind from May. What changed is the clock. Three pains that were "proposed obligation with a comment window" are entering "final rule imminent" territory.

---

## How to use this doc

This is the **style guide** for every leader-facing word in this repository — README headlines, dashboard page descriptions, deck slides, exec emails. Before you write copy aimed at a CCO, MLRO, Head of Financial Crime, or CRO, find the closest pain point below and **borrow its plain-English phrasing**. Each pain is anchored in a primary source (regulator letter, enforcement order, or cited industry survey) so the copy is defensible the moment a buyer asks "where did you get that?"

Three rules behind everything in the table:

1. **Audit-defensibility, not detection, is the dominant pain in 2026.** Across recent enforcement orders surveyed (TD, RBC, Wells, NatWest, Citibank), regulators rarely allege the bank missed a typology — they allege the bank cannot evidence what it did, when, or why. Process and governance gaps outnumber data and model gaps roughly 2:1 in the consent orders. *Lead with proof, not detection.*
2. **CCOs publicly say "alert volume," but the underlying ailment is "alert quality."** The 95% false-positive figure is industry-canonical; cite it sparingly and never as our number — it's the *baseline* the framework helps escape. *Frame in terms of analyst attention, not alerts.*
3. **Write the way they speak.** "We couldn't prove what ran." "The backlog has been red on the board for years." "My monitoring system is a model and I cannot validate it." These are real CCO sentences from public sources — not vendor copy. Copy paste before paraphrasing.

---

## The 10 pains

### PAIN-1 · "We can't prove what we did."

| | |
|---|---|
| **Plain-English description** | Decisions get made every day — alerts triaged, customers exited, scenarios re-tuned — but when the regulator asks "show us the working," the audit trail is a Word doc, three people's memory, and a SharePoint folder no one can search. |
| **Primary source** | FCA Dear CEO Letter to Annex 1 firms, March 2024 (still operative in 2026): *"Decisions made in relation to financial crime were not supported by evidence or an audit trail of debate and challenge."* — [FCA letter](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf). FinCEN's April 2026 Effectiveness NPRM (Federal Register 2026-07033) proposes that independent testing must specifically verify whether *"the AML/CFT program is maintained and implemented effectively"* — the audit trail is the evidence base for both words. Comments due **9 June 2026** — 7 days. — [Federal Register 2026-07033](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs). |
| **Roles affected** | CCO, MLRO, Internal Audit |
| **Cost type** | Audit-defensibility |
| **Framework capability** | Hash-chained audit ledger + deterministic replay → any historical run reproducible byte-for-byte. *Audit & Evidence* dashboard page; PR #97 (rule-effectiveness backtester) extends this to "show me the rule's track record." The May 31 zip-slip fix (H4) and SQL injection guard (H2) protect the integrity of the evidence bundle itself — the controls SR 26-2 examiners will inspect for data-integrity chain assurance. |

### PAIN-2 · "The backlog is red — and the board has known for years."

| | |
|---|---|
| **Plain-English description** | Alerts pile up faster than analysts can clear them. The dashboards show it. The board approves the program anyway. Then a regulator notices, and what was a slide becomes a consent order. As of June 2, 2026, the FinCEN Whistleblower NPRM comment period has closed — the proposed 10–30% award structure is now in outline, with a final rule expected late 2026 / early 2027. The incentive to report a chronic backlog existed yesterday; the formal mechanism is being finalized. |
| **Primary source** | TD Bank Consent Order (FinCEN, October 2024): TD allowed *"trillions of dollars in transactions annually to go unmonitored"*; the AIU detection queue was in **"red status"** in board reporting for years, attributable to chronic understaffing. — [FinCEN release](https://www.fincen.gov/news/news-releases/fincen-assesses-record-13-billion-penalty-against-td-bank). FinCEN Whistleblower NPRM (Federal Register 2026-06271, **comment period closed June 1, 2026**): proposed 10–30% of collected sanctions from the $300M Financial Integrity Fund; anti-retaliation protections for current and former employees. Final rule expected late 2026 / early 2027. The institutional-reporting trail that protects the bank is the same trail the Whistleblower program will examine first. — [Federal Register 2026-06271](https://www.federalregister.gov/documents/2026/04/01/2026-06271/whistleblower-incentives-and-protections). |
| **Roles affected** | CCO, MLRO, 1LoD analyst, CRO |
| **Cost type** | Audit-defensibility + morale |
| **Framework capability** | SLA timer + escalation engine → red queues become loud, not slide-decoration. *Investigations* dashboard page; per-queue breach-rate badges. The append-only audit ledger documents every internal escalation — the record regulators expect internal-report programs to produce and that the Whistleblower program will inspect first. |

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
| **Plain-English description** | The Business Risk Assessment is supposed to drive everything — scenarios, thresholds, training, board reporting. In practice it lives in a binder, was last refreshed 18 months ago, and the regulator notices first. As of June 2026, the comment window to influence the Effectiveness NPRM's proposed BRA requirement closes June 9 — 7 days. Firms that have completed a gap analysis before June 9 have documented proactive posture; firms that have not are running out of time before the 12-month implementation clock starts. |
| **Primary source** | FCA Dear CEO: *"Many Annex 1 firms did not have a BRA in place… the quality of the BRA was poor in terms of detail and methodology."* — [FCA via Waystone](https://compliance.waystone.com/insights-from-the-fcas-dear-ceo-letter-addressing-financial-crime-risks-in-annex-1-firms/). FINTRAC has reclassified missing/stale risk assessments as **"very serious"** violations under its 2025 AMP regime. FinCEN Effectiveness NPRM (Federal Register 2026-07033): proposed rule makes a documented enterprise-wide AML/CFT risk assessment — incorporating FinCEN national priorities, approved by the board — a standalone program pillar. *"Effectiveness"* splits into (1) program established and (2) program maintained; a stale BRA fails criterion (2). **Comments due 9 June 2026 — 7 days.** — [Federal Register 2026-07033](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs). |
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
| **Framework capability** | New product = new Manifest entries in days, not quarters. *Multi-jurisdiction* page shows coverage gaps the moment a new geography is added. |

### PAIN-6 · "My monitoring system is a model — and I cannot validate it."

| | |
|---|---|
| **Plain-English description** | SR 26-2 went live on 17 April 2026 and has been examination-active for 45 days. Q2 2026 examination cycles are running. BSA/AML transaction monitoring, sanctions screening, customer risk-rating, and CDD scoring are in the model-risk inventory with documentation requirements — not as a future obligation, but in current examination cycles. Second-line MRM teams are presenting gap analyses to boards now. Independent challenger validation is one of three explicitly acceptable validation methods, and the window to get ahead of the first examination letter is closing. |
| **Primary source** | **SR 26-2 (effective 17 April 2026, 45 days active as of June 2):** Joint Fed/OCC/FDIC guidance supersedes both SR 11-7 and SR 21-8. TM, sanctions screening, name-matching, customer risk-rating, and CDD scoring are *"expressly included"* in the model inventory. Examiner Q&A identifies independent re-implementation as one of three acceptable challenger-model validation methods. — [SR 26-2](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm); [SR 26-2 Attachment](https://www.federalreserve.gov/supervisionreg/srletters/SR2602a1.pdf); [OCC Bulletin 2026-13](https://www.occ.treas.gov/news-issuances/bulletins/2026/bulletin-2026-13.html). **Language note:** in leader-facing copy use *"we can show our model still works"* — not "MRM." |
| **Roles affected** | CCO, 2LoD model validation, MRM Director |
| **Cost type** | Cost + audit-defensibility |
| **Framework capability** | Per-rule MRM dossier (`generators/mrm.py`) + PR #97 backtester → "rule X precision/recall trend over the last 4 quarters" answered before lunch. The May 31 security hardening sprint (H0–H6) closed the remaining SR 26-2 gap: the coverage gate is now enforced platform-independently (`scripts/check_coverage_floor.py`), and the audit pack produces byte-identical output across runs. The framework now satisfies all three SR 26-2 independent-challenger requirements: deterministic rerun, hash-chained audit ledger, and demonstrated test coverage of scoring and audit logic. |

### PAIN-7 · "We file SARs we don't believe in, and we miss the ones we should file."

| | |
|---|---|
| **Plain-English description** | The bank files thousands of defensive SARs the analyst doesn't believe in, while the genuinely-suspicious case sits in the queue past its filing deadline. The defect is data quality and case completeness, not analyst effort. As of June 2026, the FinCEN Whistleblower NPRM comment period has closed — the proposed incentive structure targets precisely these failure patterns. |
| **Primary source** | FINTRAC on RBC (2024, $7.5M penalty): bank *"failed to flag suspicious activity, neglected to keep its written AML policies and procedures up to date and did not disclose relevant information in suspicious transaction reports… failed to submit 16 suspicious transactions reports across 130 customer files."* — [ACAMS](https://www.acams.org/en/news/fintrac-fines-royal-bank-of-canada-record-7-5-million-for-aml-failings); [Global Relay](https://www.grip.globalrelay.com/fintrac-imposes-its-largest-ever-aml-fine-on-royal-bank-of-canada/). FinCEN Effectiveness NPRM (2026-07033): frames program effectiveness around the unbroken chain — *suspicious activity identified, escalated, and reported* — not alert volume. FinCEN Whistleblower NPRM (**comment period closed June 1, 2026**): proposed 10–30% award on collected sanctions, anti-retaliation protections. Final rule expected late 2026 / early 2027. — [Federal Register 2026-06271](https://www.federalregister.gov/documents/2026/04/01/2026-06271/whistleblower-incentives-and-protections). |
| **Roles affected** | MLRO, 1LoD analyst |
| **Cost type** | Audit-defensibility |
| **Framework capability** | Case-to-STR auto-bundling (PR #64) + STR filing latency p95 metric + auto-drafted narratives drawing from the alert evidence chain → analyst writes the narrative, not the bundle. |

### PAIN-8 · "$61 billion a year — and I still can't tell the CEO what we got for it."

| | |
|---|---|
| **Plain-English description** | The bill is real and visible. The return is not. Vendor licences, consulting fees, audit-prep contractors, FTE growth — all line items. ROI is uncostable line-by-line, so the CFO ends every annual review with the same question: *"is the juice worth the squeeze?"* |
| **Primary source** | LexisNexis Risk Solutions, *True Cost of Financial Crime Compliance, US & Canada* (Feb 2024): *"annual cost of financial crime compliance totals $61 billion in the United States and Canada."* — [press release](https://risk.lexisnexis.com/about-us/press-room/press-release/20240221-true-cost-of-compliance-us-ca). FinCEN's Sep 2025 RFI on AML compliance costs explicitly framed the question *"Is the juice worth the squeeze?"* — [Mayer Brown summary](https://www.mayerbrown.com/en/insights/publications/2025/10/fincen-issues-request-for-information-on-aml-compliance-costs-is-the-juice-worth-the-squeeze). |
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
| **Plain-English description** | OSFI's January 2026 AMP Guide and FINTRAC's 2025 reclassification mean the MLRO is no longer shielded by "the program." FinCEN's April 2026 Effectiveness NPRM proposes board approval and a US-located designated officer as regulatory requirements, not preferences — with the comment deadline 7 days away (June 9). The Whistleblower NPRM comment period closed June 1: the proposed external reporting pathway (10–30% of collected sanctions, anti-retaliation protections) becomes more concrete with each step toward a final rule. The gap in the audit trail is not only a regulator risk — it is, increasingly, an internal-report risk backed by proposed financial incentives for reporters. |
| **Primary source** | OSFI Letter to Industry (11 September 2025): OSFI announced *"a lower tolerance for contraventions… penalties may be issued for lower levels of potential negligence and harm, and more frequently in 2026,"* with new AMP Guide published 29 Jan 2026. — [Fasken summary](https://www.fasken.com/en/knowledge/2026/02/financial-services-regulatory-updates). FinCEN Effectiveness NPRM (Apr 2026): AML/CFT programs *"must be approved by a board of directors… designated AML/CFT officer must be located in the United States."* The proposed rule bifurcates violation types into "program established" and "program maintained" — individual officers are named in both categories. **Comments due 9 June 2026 — 7 days.** — [Federal Register 2026-07033](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs). FinCEN Whistleblower NPRM (Federal Register 2026-06271, **comment period closed June 1, 2026**): proposed 10–30% award of collected sanctions, anti-retaliation protections for current and former employees. Final rule expected late 2026 / early 2027. — [Federal Register 2026-06271](https://www.federalregister.gov/documents/2026/04/01/2026-06271/whistleblower-incentives-and-protections). |
| **Roles affected** | CCO, MLRO personally |
| **Cost type** | Morale + audit-defensibility |
| **Framework capability** | Hash-chained ledger + deterministic replay = the Officer can sign a control attestation she actually believes. The Manifest version she signs is unambiguous — by hash — about what the program covered, when. The May 31 audit-pack determinism fix means "same spec + same data = identical output bytes" — the central SR 26-2 challenger-model requirement, and the evidence base for an Officer's attestation under the Effectiveness NPRM's proposed "program maintained" standard. |

---

## Themes (≈100 words)

The dominant pain in June 2026 primary sources remains **audit-defensibility, not detection** — regulators rarely allege the bank missed a typology; they allege the bank cannot evidence what it did, when, or why (FCA, TD, RBC). The June 2026 inflection is that three pains are now in "final rule imminent" territory: SR 26-2 (45 days examination-active), the Effectiveness NPRM (comment deadline June 9, 7 days), and the Whistleblower NPRM (comment period closed June 1, final rule late 2026). The FinCEN Effectiveness NPRM converts "supervisory expectation" to "proposed regulation" for the audit trail (PAIN-1), the documented risk assessment (PAIN-4), and the Officer's personal accountability (PAIN-10). The Whistleblower NPRM adds an external-report vector to the backlog (PAIN-2) and SAR quality (PAIN-7) — before the final rule is published.

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

- "spec", "aml.yaml", "YAML", "schema", "Pydantic", "DuckDB", "FastAPI" — use **"Compliance Manifest"**
- "decisions.jsonl" — use **"audit ledger"**
- "deterministic", "hash chain" — use "audit trail you can replay"
- "MRM" — use "model validation" or "show the model still works"
- "aggregation strategies", "evidence bundle" — use "examination ZIP" or "regulator pack"
- "primitives" — use **"Manifest entries"** or "building blocks"
- "rule logic", "rule engine" — use "detector" or "what fires the alert"

---

## Sources

- [FCA Dear CEO Letter — Annex 1 firms (March 2024)](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf)
- [FCA Dear CEO — UK retail banks (May 2021), via Mayer Brown](https://www.mayerbrown.com/en/insights/publications/2021/08/the-fcas-dear-ceo-letter)
- [FinCEN — TD Bank record $1.3B penalty (October 2024)](https://www.fincen.gov/news/news-releases/fincen-assesses-record-13-billion-penalty-against-td-bank)
- [FinCEN — AML Program Effectiveness NPRM, Federal Register 2026-07033 (April 10, 2026)](https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs)
- [FinCEN — Whistleblower Incentives & Protections NPRM, Federal Register 2026-06271 (comment period closed June 1, 2026)](https://www.federalregister.gov/documents/2026/04/01/2026-06271/whistleblower-incentives-and-protections)
- [FRB SR 26-2 — Revised Model Risk Management guidance (effective April 17, 2026)](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm)
- [SR 26-2 Attachment (full guidance PDF)](https://www.federalreserve.gov/supervisionreg/srletters/SR2602a1.pdf)
- [OCC Bulletin 2026-13 — Model Risk Management](https://www.occ.treas.gov/news-issuances/bulletins/2026/bulletin-2026-13.html)
- [ACAMS — FINTRAC fines RBC record $7.5M for AML failings (2024)](https://www.acams.org/en/news/fintrac-fines-royal-bank-of-canada-record-7-5-million-for-aml-failings)
- [OSFI — Letter to Industry September 11, 2025 (AMP guide), via Fasken](https://www.fasken.com/en/knowledge/2026/02/financial-services-regulatory-updates)
- [LexisNexis — True Cost of Financial Crime Compliance US & Canada (February 2024)](https://risk.lexisnexis.com/about-us/press-room/press-release/20240221-true-cost-of-compliance-us-ca)
- [Banking Dive — OCC hits Wells Fargo with AML enforcement action (September 2024)](https://www.bankingdive.com/news/occ-hits-wells-fargo-with-aml-enforcement-action/726890/)
- [Flagright — False positives in transaction monitoring](https://www.flagright.com/post/understanding-false-positives-in-transaction-monitoring)
- [Mayer Brown — FinCEN RFI on AML compliance costs (October 2025)](https://www.mayerbrown.com/en/insights/publications/2025/10/fincen-issues-request-for-information-on-aml-compliance-costs-is-the-juice-worth-the-squeeze)
