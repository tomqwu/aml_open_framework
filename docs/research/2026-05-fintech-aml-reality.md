# 10 AML Realities a FinTech / EMI / MSB / VASP MLRO Lives With — May 2026

*Date: 2026-05-25 · Audience: FinTech / EMI / MSB / VASP MLRO. Companion to [`2026-05-aml-process-pain.md`](2026-05-aml-process-pain.md) (Tier-1 bank lens). Previous edition: [`2026-04-fintech-aml-reality.md`](./2026-04-fintech-aml-reality.md).*

## What changed between April and May 2026

Two entirely new compliance obligations landed since the April edition:

1. **GENIUS Act NPRM (April 8)** — FinCEN and OFAC jointly proposed treating permitted payment stablecoin issuers (PPSIs) as financial institutions under the Bank Secrecy Act, requiring full BSA-program equivalents and a mandatory OFAC-specific sanctions compliance program. For stablecoin issuers, this is the first time AML and sanctions compliance are a hard regulatory requirement. Comments due **June 9, 2026**.

2. **AUSTRAC Tranche 2 enforcement begins July 1, 2026.** Australian lawyers, accountants, real-estate agents, and dealers in precious metals and stones (DPMS) face enforceable AML/CTF Act obligations from July 1. AUSTRAC's posture favours enforceable undertakings for first-cycle non-compliance at firms with documented good-faith programs — which means the program you can evidence before July 1 is the difference between an EU and a penalty.

Additionally, **SR 26-2 became operative on April 17**, which is relevant to fintech MLROs who manage TM scenarios or CDD scoring models — they are now in scope as "model risk" alongside credit models.

The eight realities from April remain valid. May adds two new ones (FINTECH-9 and FINTECH-10) because the obligations they describe did not exist in April.

---

## How to use this doc

The MLRO at a fintech is exposed in ways a Tier-1 MLRO is not: personal regulator-named risk, sponsor-bank cure notices, and Series-B due-diligence questionnaires arrive at the same desk. Each reality below is anchored in a primary source — an enforcement order, a regulator press release, or court filings — so the copy is defensible the moment a buyer asks "where did you get that?"

Three things to remember about this audience:

1. **The MLRO at a fintech is exposed in ways a Tier-1 MLRO is not.** Personal named risk, sponsor-bank cure notices, and investor diligence questionnaires arrive at the same desk. Lead with the *named* risk to the role, not the program.
2. **The sponsor bank is a regulator-by-proxy.** After Synapse's April 2024 collapse and the cascade of Federal Reserve / OCC / FDIC consent orders, the sponsor bank's risk officer can move faster than any government regulator.
3. **Speed of evidence > sophistication of detection.** What buys a fintech MLRO survival is the ability to produce — within the cure-notice window — a primary-source-cited record of every alert, decision, and exit.

---

## The 10 realities

### FINTECH-1 · "The sponsor bank's 90-day cure notice is now the operative regulator."

| | |
|---|---|
| **Plain-English description** | A Banking-as-a-Service sponsor bank receives a consent order from the Federal Reserve or FDIC. Within weeks, every fintech that rides on that sponsor's banking licence gets a remediation letter with a hard cure window — usually 30, 60, or 90 days — to evidence its AML program. Miss the window and the sponsor terminates. The fintech's MLRO has no appeal. |
| **Vignette** | Wednesday 9am, the sponsor bank's risk officer emails: *"Per our Federal Reserve consent order, we need your full BSA/AML program file — risk assessment, transaction-monitoring scenarios, SAR log, training records — by the 60th day. Anything missing flips the relationship to wind-down."* |
| **Primary source** | Federal Reserve cease-and-desist against Evolve Bancorp / Evolve Bank & Trust, 14 June 2024: failed to maintain *"an effective risk management framework"* for fintech partnerships; required a written plan within 90 days plus an independent third-party review. — [Federal Reserve press release](https://www.federalreserve.gov/newsevents/pressreleases/enforcement20240614a.htm). The cascade of 2024 BaaS consent orders — Blue Ridge, Lineage, Piermont, Sutton, Mode Eleven, Thread Bank — established the pattern: sponsor banks are required to inventory, risk-assess, and exit fintech partners on regulator-set timelines. — [Banking Dive running list](https://www.bankingdive.com/news/a-running-list-of-baas-banks-hit-with-consent-orders-in-2024/729121/). |
| **Roles affected** | MLRO, Head of Compliance, CEO, Engineering |
| **Cost type** | License risk |
| **Framework capability** | The Compliance Manifest *is* the program file the sponsor's risk officer is asking for. The audit ledger replays any historical run byte-for-byte; `aml audit-pack` produces the cure-notice evidence pack in hours, not weeks. |

### FINTECH-2 · "Fast growth is what the sponsor and the regulator both find first."

| | |
|---|---|
| **Plain-English description** | The fintech goes from 50,000 customers to 3 million in four years. The product team celebrates. Sanctions screening, transaction monitoring, and KYC onboarding controls do not scale at the same rate. |
| **Primary source** | FCA Final Notice against Starling Bank Limited, 27 September 2024: £28,959,426 fine. *"Starling grew from approximately 43,000 customers in 2017 to 3.6 million in 2023, however, measures to tackle financial crime did not keep pace with its growth."* The bank *"repeatedly breached a requirement not to open accounts for high-risk customers, opening over 54,000 accounts for 49,000 high-risk customers."* — [FCA press release](https://www.fca.org.uk/news/press-releases/fca-fines-starling-bank-failings-financial-crime-systems-and-controls). |
| **Roles affected** | MLRO, Head of Onboarding, Sanctions team, Board |
| **Cost type** | Compliance + license risk |
| **Framework capability** | New product + new geography = new Manifest entries in days. *Multi-Jurisdiction* dashboard page surfaces coverage gaps the moment the firm onboards in a new corridor. |

### FINTECH-3 · "The Annex 1 questionnaire is supervisory, not advisory."

| | |
|---|---|
| **Plain-English description** | The FCA's March 2024 Dear-CEO letter to Annex 1 firms — roughly 1,000 EMIs, payment institutions, money brokers, and lenders — demanded a six-month gap analysis. October 2025's follow-up questionnaire converted that demand into a supervisory tool with named-firm consequences. |
| **Primary source** | FCA Dear-CEO letter to Annex 1 firms, 5 March 2024: *"absent, inadequate or disproportionate Business Wide Risk Assessments… discrepancies between activities reported to undertake versus the activities actually undertaken… inadequate resourcing and oversight."* — [FCA letter](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf). FCA statement on financial crime risks for Annex 1 firms, 20 March 2026: MLROs at FCA-regulated banks must explicitly extend EDD frameworks to Annex 1 counterparties. — [FCA statement March 2026](https://www.fca.org.uk/news/statements/firms-must-do-proper-checks-when-dealing-unregulated-lenders). |
| **Roles affected** | MLRO, Head of Compliance, Board |
| **Cost type** | Audit-defensibility + license risk |
| **Framework capability** | The Compliance Manifest *is* the BWRA in machine-readable form. *Framework Alignment* and *Program Maturity* dashboard pages render the live BWRA from the Manifest; a stale binder becomes a live document the MLRO can hand to the FCA case officer the same day the email arrives. |

### FINTECH-4 · "VASP enforcement is now bespoke, not boilerplate."

| | |
|---|---|
| **Plain-English description** | The 2024-26 enforcement wave hits the absence of a *coherent* program: KYC onboarding, alert clearance, SAR timeliness, and PEP screening cited as one connected failure pattern. The VASP MLRO is now expected to evidence the whole chain. |
| **Primary source** | NY DFS Consent Order against Coinbase, 4 January 2023, $100M: *"failures to conduct adequate KYC due diligence at customer onboarding, timely clear alerts, timely file suspicious activity reports, conduct proper PEP and sanctions screening."* — [NY DFS press release](https://www.dfs.ny.gov/reports_and_publications/press_releases/pr202301041). FinCEN $3.5M penalty against a peer-to-peer virtual-asset platform, December 2025. — [FinCEN enforcement actions](https://www.fincen.gov/news/enforcement-actions). EU 20th Russia sanctions package (April 23, 2026): sectoral ban on transactions with any Russian CASP — VASP MLROs must now block Russian-CASP counterparties and review historical VASP-to-VASP exposure. — [EU Council press release April 23, 2026](https://www.consilium.europa.eu/en/press/press-releases/2026/04/23/russia-s-war-of-aggression-against-ukraine-20th-round-of-stern-eu-sanctions-hits-energy-military-industrial-complex-trade-and-financial-services-including-crypto/). |
| **Roles affected** | MLRO, Head of Compliance, KYC ops, SAR ops |
| **Cost type** | Audit-defensibility + license risk |
| **Framework capability** | Investigation aggregator stitches alert → KYC → sanctions → PEP → SAR into one INV-{sha256} bundle, deterministically. The SAR latency p95 metric and auto-bundled SAR ZIP close the gap NY DFS named in Coinbase. |

### FINTECH-5 · "The Travel Rule is 99 jurisdictions, four protocols, one MLRO."

| | |
|---|---|
| **Plain-English description** | FATF's revised Recommendation 16 requires originator and beneficiary information on every qualifying cross-border transfer over USD/EUR 1,000. 99 jurisdictions are at varying stages of legislation. FATF's February 2026 plenary grey-listed Kuwait and Papua New Guinea — VASP MLROs with counterparty exposure in those jurisdictions must now apply enhanced due diligence to travel-rule counterparty records from those geographies. |
| **Primary source** | FATF Recommendation 16 update, June 2025: global implementation by end-2030. — [FATF R.16 update](https://www.fatf-gafi.org/en/publications/Fatfrecommendations/update-Recommendation-16-payment-transparency-june-2025.html). FATF February 2026 Plenary: Kuwait and Papua New Guinea added to the grey list (Jurisdictions under Increased Monitoring). — [FATF February 2026 outcomes](https://www.fatf-gafi.org/en/publications/Fatfgeneral/outcomes-FATF-plenary-february-2026.html). EU AMLR 2024/1624 brings MiCA-authorised CASPs under direct AML obligations including travel-rule compliance. |
| **Roles affected** | MLRO, VASP compliance ops, Engineering integrations |
| **Cost type** | Compliance + license risk |
| **Framework capability** | ISO 20022 + Travel Rule field validator (Round 5) plus pacs.008 / pacs.009 ingestion ship as one binary. The Compliance Manifest declares the field-level requirements once; the audit ledger evidences each transmission per counterparty. |

### FINTECH-6 · "AMLR's 10 July 2027 clock is the single largest unfunded mandate in EU fintech."

| | |
|---|---|
| **Plain-English description** | EU Anti-Money Laundering Regulation 2024/1624 applies directly across all 27 Member States from 10 July 2027. AMLA's RTS consultations closed May 8, 2026 — AMLA must now submit final draft RTS to the European Commission by July 10, 2026. The window for EU fintechs to align before the standard locks is narrowing. |
| **Primary source** | AMLR 2024/1624 and AMLA 2024/1620, Official Journal 19 June 2024. AMLA consultations on CDD RTS, business-relationships RTS, and pecuniary-sanctions RTS closed; AMLA must submit final drafts to the Commission by 2026-07-10. — [AMLA consultation page](https://www.amla.europa.eu/policy/public-consultations/consultation-draft-rts-customer-due-diligence_en). AMLA direct supervision of ~40 obliged entities begins 2028; data-collection exercise for selection methodology is now underway. — [AMLA selection exercise](https://www.amla.europa.eu/amla-advances-preparations-2027-selection-exercise_en). |
| **Roles affected** | MLRO, Compliance Director, CEO, Board |
| **Cost type** | Compliance + license risk |
| **Framework capability** | Multi-jurisdiction templating ships specs for US (FinCEN), CA (FINTRAC/OSFI), EU (EBA/AMLD6 + AMLR-ready), UK (FCA/POCA). The regulation-drift watcher (`compliance/regwatch.py`) hashes every regulation reference URL and alerts on text drift — so the AMLR 10 July 2027 deadline does not become a surprise. |

### FINTECH-7 · "49 state regulators, one MSB, one Bank Secrecy Act program."

| | |
|---|---|
| **Plain-English description** | A US Money Service Business registers with FinCEN once but is licensed by up to 49 states under bespoke money-transmitter regimes. CSBS's MTMA is closing the gap — 31 states have adopted it — but the MLRO still answers to a multi-headed examiner, with each state running its own BSA/AML examination cadence. |
| **Primary source** | Coordinated multi-state enforcement against Block, Inc. / Cash App, 15 January 2025, $80M penalty by 48 state financial regulators: required Block to hire an independent consultant and correct deficiencies within 12 months. — [CSBS press release](https://www.csbs.org/newsroom/state-regulators-issue-80-million-penalty-block-inc-cash-app-bsaaml-violations). CSBS MTMA adoption: 31 states, covering 99% of reported activity. — [CSBS MTMA page](https://www.csbs.org/csbs-money-transmission-modernization-act-mtma). |
| **Roles affected** | MLRO, State licensing team, Head of Compliance |
| **Cost type** | Compliance + license risk |
| **Framework capability** | One Compliance Manifest, multiple jurisdiction-tagged audit packs (`aml audit-pack --jurisdiction US-FINCEN`, `--jurisdiction US-NY-DFS`). Deterministic re-run means any state's lookback computes from the same evidence chain. |

### FINTECH-8 · "Series-B+ AML diligence is the unfunded compliance mandate nobody warned us about."

| | |
|---|---|
| **Plain-English description** | A fintech raising a Series B (or filing an S-1) is asked for an AML program file, sanctions-screening evidence, BSA/AML training records, and per-rule effectiveness data — by an investor diligence firm or by SEC underwriters' counsel. The cost is real, the timeline is non-negotiable, and the questionnaire reads like an FCA Annex 1 letter. |
| **Primary source** | Chime's S-1 filing (2025) flagged AML compliance as a material risk factor, situating the fintech *"in the gray area between tech and finance"* with elevated regulatory exposure. — [ICLG Fintech Laws USA 2025-2026](https://iclg.com/practice-areas/fintech-laws-and-regulations/usa). LexisNexis: *"annual cost of financial crime compliance totals $61 billion in the United States and Canada."* — [LexisNexis press release](https://risk.lexisnexis.com/about-us/press-room/press-release/20240221-true-cost-of-compliance-us-ca). |
| **Roles affected** | MLRO, CEO, CFO, General Counsel |
| **Cost type** | Investor / capital risk |
| **Framework capability** | Apache 2.0, runs in the fintech's own perimeter — no vendor NDA blocking diligence disclosure. The audit ledger answers *"every change to every rule, with rationale and timestamp"* in one query. The backtester produces the false-positive trend the diligence partner is asking for. |

### FINTECH-9 · "We're a stablecoin issuer and the Bank Secrecy Act just found us."

| | |
|---|---|
| **Plain-English description** | A permitted payment stablecoin issuer has operated in a regulatory grey area between fintech and bank. The GENIUS Act NPRM proposes that ends: full BSA-program equivalents plus a mandatory OFAC sanctions compliance program under new 31 CFR Part 502. The banks that provide correspondent services to PPSIs face the same scrutiny through third-party risk channels. Comment window closes June 9, 2026. |
| **Vignette** | The PPSI's CEO forwards the April 8 Treasury press release with one line: *"Do we have a BSA program?"* The compliance lead has screening and some transaction monitoring. She does not have a board-approved risk assessment, an OFAC-specific compliance program, independent testing records, or a named US-located AML/CFT officer. She has 62 days to comment on the NPRM and, simultaneously, to build what it requires. |
| **Primary source** | FinCEN + OFAC joint NPRM: *"Permitted Payment Stablecoin Issuers AML/CFT Programs and Sanctions Compliance Programs,"* Federal Register 2026-06963, published April 10, 2026. Proposes adding PPSIs as "financial institutions" under 31 U.S.C. § 5312(a)(2), requiring full BSA-program equivalents plus a mandatory OFAC sanctions compliance program under new 31 CFR Part 502. Banks sponsoring PPSIs must update their BSA/AML third-party risk assessments. Comments due 2026-06-09. — [Federal Register 2026-06963](https://www.federalregister.gov/documents/2026/04/10/2026-06963/permitted-payment-stablecoin-issuer-anti-money-launderingcountering-the-financing-of-terrorism); [Treasury Press Release SB0435](https://home.treasury.gov/news/press-releases/sb0435); [FinCEN PPSI NPRM PDF](https://www.fincen.gov/system/files/2026-04/PPSI-AMLCFT-NPRM.pdf). |
| **Roles affected** | MLRO / AML Officer (newly designated), CEO, Legal, any sponsoring bank's BSA Officer |
| **Cost type** | License risk + audit-defensibility |
| **Framework capability** | The Compliance Manifest is the board-approved risk assessment and program file the NPRM requires. Multi-jurisdiction templating lets a PPSI Manifest reference both BSA (FinCEN) and OFAC obligations in the same file. Apache 2.0 deployment means no per-seat licence appears in the PPSI's vendor-risk register — a material simplification of the sponsor-bank due-diligence process. |

### FINTECH-10 · "AUSTRAC just made us an obliged entity. We have 37 days."

| | |
|---|---|
| **Plain-English description** | Australian lawyers, accountants, real-estate agents, and dealers in precious metals and stones become enforceable under the AML/CTF Act on July 1, 2026. AUSTRAC's stated first-cycle posture is enforceable undertakings rather than fines — but only for firms with documented, board-approved programs in place before July 1. After July 1, AUSTRAC's examination posture treats them like any other reporting entity. |
| **Vignette** | The managing partner of a Melbourne property conveyancing firm returns from a compliance conference and asks the operations manager: *"What's our AML/CTF program?"* The operations manager has a PEP check and a file note. AUSTRAC wants an enrolment, a board-approved program, a risk assessment, and compliance reports — in 37 days. |
| **Primary source** | AUSTRAC Regulatory Expectations and Priorities 2025–26: Tranche 2 reform brings lawyers, accountants, real-estate agents, and DPMS under the AML/CTF Act with mandatory enrolment and board-approved programs enforceable from 2026-07-01. *"AUSTRAC's stated posture favours enforceable undertakings over fines in the first cycle — but only for firms with documented, good-faith compliance efforts."* — [AUSTRAC: Regulatory expectations 2025–26](https://www.austrac.gov.au/amlctf-reform/austrac-regulatory-expectations-and-priorities-2025-26); [AUSTRAC AML/CTF Reform hub](https://www.austrac.gov.au/amlctf-reform). |
| **Roles affected** | Partner / Principal (personally liable under Australian law), newly-designated AML/CTF Compliance Officer, Board |
| **Cost type** | License risk + audit-defensibility |
| **Framework capability** | Multi-jurisdiction templating lets an AUSTRAC Tranche 2 firm generate a board-approved Manifest with a risk assessment anchored to the AML/CTF Act obligations in days, not weeks. `aml audit-pack --jurisdiction AU-AUSTRAC` produces the evidence pack AUSTRAC examinations require. Apache 2.0, deployable in the firm's own infrastructure — the board-approved program is owned by the firm, not a vendor cloud. |

---

## Themes (≈100 words)

For a fintech MLRO in May 2026, **the operative regulator is still whoever moves fastest** — but the threat surface has widened. The eight April realities remain: sponsor-bank cure notices, growth gaps, FCA Annex 1 supervision, VASP enforcement, Travel Rule complexity, AMLR deadline, MSB multi-state gauntlet, and investor diligence. May adds two structural shifts: the GENIUS Act NPRM turns stablecoin issuers into financial institutions overnight, and AUSTRAC Tranche 2 turns Australian professional services into a compliance market with a 37-day runway. In both cases, the operative question is unchanged: **can you prove what you have, before the window closes?**

---

## Sources

### US Federal / FinCEN / OFAC
- [Federal Reserve Evolve Bancorp consent order, June 14, 2024](https://www.federalreserve.gov/newsevents/pressreleases/enforcement20240614a.htm)
- [Banking Dive — running list of BaaS banks hit with consent orders in 2024](https://www.bankingdive.com/news/a-running-list-of-baas-banks-hit-with-consent-orders-in-2024/729121/)
- [FinCEN enforcement actions index](https://www.fincen.gov/news/enforcement-actions)
- [FinCEN + OFAC GENIUS Act NPRM — Federal Register 2026-06963](https://www.federalregister.gov/documents/2026/04/10/2026-06963/permitted-payment-stablecoin-issuer-anti-money-launderingcountering-the-financing-of-terrorism)
- [Treasury Press Release SB0435 — GENIUS Act NPRM](https://home.treasury.gov/news/press-releases/sb0435)
- [FinCEN PPSI NPRM PDF](https://www.fincen.gov/system/files/2026-04/PPSI-AMLCFT-NPRM.pdf)
- [CSBS press release: $80M Block / Cash App multistate action, January 15, 2025](https://www.csbs.org/newsroom/state-regulators-issue-80-million-penalty-block-inc-cash-app-bsaaml-violations)
- [CSBS Money Transmission Modernization Act page](https://www.csbs.org/csbs-money-transmission-modernization-act-mtma)

### NY DFS
- [NY DFS press release: $100M Coinbase settlement, January 4, 2023](https://www.dfs.ny.gov/reports_and_publications/press_releases/pr202301041)

### FCA (UK)
- [FCA Dear-CEO letter to Annex 1 firms, March 5, 2024](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf)
- [FCA press release: £29M Starling Bank fine, September 27, 2024](https://www.fca.org.uk/news/press-releases/fca-fines-starling-bank-failings-financial-crime-systems-and-controls)
- [FCA statement: Risks for firms dealing with unregulated lenders, March 20, 2026](https://www.fca.org.uk/news/statements/firms-must-do-proper-checks-when-dealing-unregulated-lenders)

### EU (AMLA / AMLR)
- [EU Regulation 2024/1620 establishing AMLA](https://eur-lex.europa.eu/eli/reg/2024/1620/oj/eng)
- [EU Regulation 2024/1624 (AMLR)](https://eur-lex.europa.eu/eli/reg/2024/1624/oj/eng)
- [AMLA — major step toward harmonised EU supervision](https://www.amla.europa.eu/amla-takes-major-step-toward-harmonised-eu-supervision_en)
- [EU Council 20th Russia sanctions package, April 23, 2026](https://www.consilium.europa.eu/en/press/press-releases/2026/04/23/russia-s-war-of-aggression-against-ukraine-20th-round-of-stern-eu-sanctions-hits-energy-military-industrial-complex-trade-and-financial-services-including-crypto/)

### FATF
- [FATF Recommendation 16 update, June 2025](https://www.fatf-gafi.org/en/publications/Fatfrecommendations/update-Recommendation-16-payment-transparency-june-2025.html)
- [FATF Plenary outcomes, February 11-13, 2026](https://www.fatf-gafi.org/en/publications/Fatfgeneral/outcomes-FATF-plenary-february-2026.html)
- [FATF Jurisdictions under Increased Monitoring, February 2026](https://www.fatf-gafi.org/en/publications/High-risk-and-other-monitored-jurisdictions/increased-monitoring-february-2026.html)

### AUSTRAC
- [AUSTRAC: Regulatory expectations and priorities 2025–26](https://www.austrac.gov.au/amlctf-reform/austrac-regulatory-expectations-and-priorities-2025-26)
- [AUSTRAC AML/CTF Reform hub](https://www.austrac.gov.au/amlctf-reform)

### Industry context
- [LexisNexis: True Cost of Financial Crime Compliance US & Canada, February 2024](https://risk.lexisnexis.com/about-us/press-room/press-release/20240221-true-cost-of-compliance-us-ca)
- [American Banker: Synapse bankruptcy puts bank-fintech partnerships on notice](https://www.americanbanker.com/news/synapse-bankruptcy-puts-bank-fintech-partnerships-on-notice)
- [ICLG: Fintech Laws and Regulations USA 2025-2026](https://iclg.com/practice-areas/fintech-laws-and-regulations/usa)
