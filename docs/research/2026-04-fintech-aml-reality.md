# 8 AML Realities a FinTech / EMI / MSB / VASP MLRO Lives With — 2026

*Date: 2026-04-29 · Audience: FinTech / EMI / MSB / VASP MLRO. Companion to [`2026-04-aml-process-pain.md`](2026-04-aml-process-pain.md) (Tier-1 bank lens).*

## How to use this doc

This is the **style guide** for every Money Laundering Reporting Officer (MLRO) -facing word in this repository when the audience is a fintech, Electronic Money Institution (EMI), Money Service Business (MSB), or Virtual Asset Service Provider (VASP) — not a Tier-1 bank. Before you write copy aimed at a fintech MLRO, Head of Financial Crime, or Compliance Director, find the closest reality below and **borrow its plain-English phrasing**. Each reality is anchored in a primary source — a regulator-issued enforcement order, a named consent order, a regulator press release, or court filings — so the copy is defensible the moment a buyer asks "where did you get that?"

Three things to remember about this audience:

1. **The MLRO at a fintech is exposed in ways a Tier-1 MLRO is not.** Personal regulator-named risk, sponsor-bank cure notices, and Series-B due-diligence questionnaires arrive at the same desk. Lead with the *named* risk to the role, not the program.
2. **The sponsor bank is a regulator-by-proxy.** After Synapse's April 2024 collapse and the cascade of Federal Reserve / Office of the Comptroller of the Currency (OCC) / Federal Deposit Insurance Corporation (FDIC) consent orders that followed, the sponsor bank's risk officer can move faster than any government regulator — and the cure notice she sends to the fintech MLRO is the *operative* enforcement instrument for most BaaS-stack fintechs in 2026.
3. **Speed of evidence > sophistication of detection.** What buys a fintech MLRO survival is the ability to produce — within the cure-notice window — a primary-source-cited record of every alert, decision, and exit. Detection is necessary; *being able to prove it within 90 days* is what keeps the licence.

---

## The 8 realities

### FINTECH-1 · "The sponsor bank's 90-day cure notice is now the operative regulator."

| | |
|---|---|
| **Plain-English description** | A Banking-as-a-Service sponsor bank receives a consent order from the Federal Reserve or FDIC. Within weeks, every fintech that rides on that sponsor's banking licence gets a remediation letter with a hard cure window — usually 30, 60, or 90 days — to evidence its Anti-Money-Laundering (AML) program. Miss the window and the sponsor terminates. The fintech's MLRO has no appeal. |
| **Vignette** | Wednesday 9am, the sponsor bank's risk officer emails our MLRO: *"Per our Federal Reserve consent order, we need your full BSA/AML program file — risk assessment, transaction-monitoring scenarios, SAR log, training records — by the 60th day. Anything missing flips the relationship to wind-down."* The MLRO has six weeks to assemble what should already exist. |
| **Primary source** | Federal Reserve cease-and-desist order against Evolve Bancorp / Evolve Bank & Trust, 14 June 2024: bank failed to maintain *"an effective risk management framework"* for fintech partnerships and had AML/Bank Secrecy Act (BSA) and Office of Foreign Assets Control (OFAC) deficiencies; required a written plan within 90 days plus an independent third-party review of the Open Banking Division. — [Federal Reserve press release](https://www.federalreserve.gov/newsevents/pressreleases/enforcement20240614a.htm); [consent order PDF](https://www.federalreserve.gov/newsevents/pressreleases/files/enf20240614a1.pdf). The cascade of 2024 BaaS consent orders — Blue Ridge (OCC, 24 Jan 2024), Lineage (FDIC, 30 Jan 2024), Piermont (FDIC, 27 Feb 2024 — *"failed to report suspicious activity since September 2022"*), Sutton (FDIC, 27 Feb 2024), Mode Eleven (Fed, 28 Mar 2024), Thread Bank (FDIC, 21 May 2024) — established the pattern: sponsor banks are now required to inventory, risk-assess, and exit fintech partners on regulator-set timelines. — [Banking Dive running list](https://www.bankingdive.com/news/a-running-list-of-baas-banks-hit-with-consent-orders-in-2024/729121/). The Synapse Financial Technologies bankruptcy (Chapter 11, 22 April 2024) froze ~$265M of end-user funds and made every sponsor's third-party risk function the single most aggressive enforcement vector against fintechs. — [American Banker](https://www.americanbanker.com/news/synapse-bankruptcy-puts-bank-fintech-partnerships-on-notice). |
| **Roles affected** | MLRO, Head of Compliance, CEO (relationship owner), Engineering (data-pull deadline) |
| **Cost type** | License risk |
| **Framework capability** | The Compliance Manifest *is* the program file the sponsor's risk officer is asking for — risk assessment, every detector, every threshold, every regulation citation in one machine-readable artefact. The audit ledger replays any historical run byte-for-byte; the per-rule Model Risk Management dossier (`generators/mrm.py`) plus the regulator examination ZIP (`aml audit-pack`) produce the cure-notice evidence pack in hours, not weeks. |

### FINTECH-2 · "Fast growth is what the sponsor and the regulator both find first."

| | |
|---|---|
| **Plain-English description** | The fintech goes from 50,000 customers to 3 million in four years. The product team celebrates. Sanctions screening, transaction monitoring, and Know-Your-Customer (KYC) onboarding controls do not scale at the same rate. The first time anyone notices is when a regulator opens 54,000 high-risk accounts in the audit sample. |
| **Vignette** | Friday 4pm, the head of growth shares the new-user dashboard in Slack: *"3.6M and counting!"* Monday morning, the FCA's Annex 1 questionnaire arrives asking how many of those accounts were opened in breach of the bank's own high-risk-customer requirement. |
| **Primary source** | Financial Conduct Authority (FCA) Final Notice against Starling Bank Limited, 27 September 2024: £28,959,426 fine for financial-crime control failings 1 December 2019 – 30 November 2023. *"Starling grew from approximately 43,000 customers in 2017 to 3.6 million in 2023, however, measures to tackle financial crime did not keep pace with its growth."* The bank *"repeatedly breached a requirement not to open accounts for high-risk customers, opening over 54,000 accounts for 49,000 high-risk customers between September 2021 and November 2023,"* and its sanctions-screening system had only screened against *"a fraction of the names on the Consolidated List since 2017."* — [FCA press release](https://www.fca.org.uk/news/press-releases/fca-fines-starling-bank-failings-financial-crime-systems-and-controls); [Final Notice PDF](https://www.fca.org.uk/publication/final-notices/starling-bank-limited-2024.pdf); [K&L Gates analysis](https://www.klgates.com/Lessons-on-Effective-Financial-Crime-Controls-The-Starling-Bank-Example-11-4-2024). |
| **Roles affected** | MLRO, Head of Onboarding, Sanctions team, Board |
| **Cost type** | Compliance + license risk |
| **Framework capability** | New product + new geography = new Manifest entries in days. *Multi-Jurisdiction* dashboard page surfaces coverage gaps the moment the firm onboards in a new corridor; high-risk-customer detectors are first-class, not Excel. The hash-chained audit ledger gives the MLRO a defensible answer to *"when did you know?"* — the question Starling could not answer. |

### FINTECH-3 · "The Annex 1 questionnaire is supervisory, not advisory."

| | |
|---|---|
| **Plain-English description** | The FCA's March 2024 Dear-CEO letter to Annex 1 firms — roughly 1,000 EMIs, payment institutions, money brokers, and lenders — demanded a six-month gap analysis. October 2025's follow-up questionnaire converted that demand into a supervisory tool with named-firm consequences. The MLRO at a UK EMI now has to evidence the Business-Wide Risk Assessment (BWRA), not just hold one. |
| **Vignette** | The FCA case officer's email is two lines: *"Please attach your BWRA, your gap analysis, and your remediation plan. We will set a follow-up call."* The MLRO has a binder. The binder is 18 months old. |
| **Primary source** | FCA Dear-CEO letter to Annex 1 firms, 5 March 2024: identified *"absent, inadequate or disproportionate Business Wide Risk Assessments (BWRAs) and poorly documented methodology underpinning the risk assessment,"* alongside discrepancies between *"activities reported to undertake versus the activities actually undertaken,"* and *"inadequate resourcing and oversight of financial crime issues and requirements."* Firms required to complete a gap analysis by summer 2024. — [FCA letter PDF](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf); [DLA Piper summary](https://www.dlapiper.com/en/insights/publications/2024/04/fca-issues-warning-to-ceos-to-improve-anti-money-laundering-controls); [DWF analysis](https://dwfgroup.com/en/news-and-insights/insights/2024/3/fca-warns-annex-1-firms-over-common-failings-in-financial-crime-controls). October 2025: questionnaire phase, characterised as *"a shift from advisory guidance to supervisory intervention"* — [VinciWorks summary](https://vinciworks.com/blog/annexe-i-firms-under-fire-the-fcas-aml-crackdown-enters-a-new-phase/) (industry context only). |
| **Roles affected** | MLRO, Head of Compliance, Board |
| **Cost type** | Audit-defensibility + license risk |
| **Framework capability** | The Compliance Manifest *is* the BWRA in machine-readable form — every detector cites the regulation it answers, every threshold has a rationale, every change is in the audit ledger. *Framework Alignment* and *Program Maturity* dashboard pages render the live BWRA from the Manifest; a stale binder becomes a live document the MLRO can hand to the FCA case officer the same day the email arrives. |

### FINTECH-4 · "VASP enforcement is now bespoke, not boilerplate."

| | |
|---|---|
| **Plain-English description** | The first wave of crypto enforcement (2022-23) hit transaction monitoring and sanctions screening as separate failures. The 2024-26 wave hits the absence of a *coherent* program: KYC onboarding, alert clearance, suspicious-activity-report timeliness, and politically-exposed-person (PEP) screening cited as one connected failure pattern. The VASP MLRO is now expected to evidence the whole chain. |
| **Vignette** | The New York Department of Financial Services (NY DFS) examiner's request list runs four pages. Half of it is timestamps: *when* did the alert fire, *when* was it cleared, *when* was the SAR filed, *when* did the customer pass KYC. The exchange has the events. It does not have them in one ordered ledger. |
| **Primary source** | NY DFS Consent Order against Coinbase, 4 January 2023, $100M (still the operative VASP precedent in 2026): *"failures to conduct adequate Know Your Customer (KYC) due diligence at customer onboarding, timely clear alerts identified by Coinbase's transaction monitoring systems, timely file suspicious activity reports, conduct proper politically exposed person (PEP) and sanctions screening."* — [NY DFS press release](https://www.dfs.ny.gov/reports_and_publications/press_releases/pr202301041); [Consent Order PDF](https://www.dfs.ny.gov/system/files/documents/2023/01/ea20230104_coinbase.pdf). NY DFS Consent Order against Robinhood Crypto, 2 August 2022, $30M: BSA/AML program *"inadequately staffed; failed to timely transition from a manual transaction monitoring system that was inadequate for RHC's size, customer profiles, and transaction volumes."* — [NY DFS press release](https://www.dfs.ny.gov/reports_and_publications/press_releases/pr202208021); [Consent Order PDF](https://www.dfs.ny.gov/system/files/documents/2024/08/ea20220801_robinhood_crypto.pdf). FinCEN $3.5M penalty against a peer-to-peer virtual-asset platform, 9 December 2025, for willful BSA violations — [FinCEN enforcement actions](https://www.fincen.gov/news/enforcement-actions). |
| **Roles affected** | MLRO, Head of Compliance, KYC ops, SAR ops |
| **Cost type** | Audit-defensibility + license risk |
| **Framework capability** | Investigation aggregator stitches alert → KYC → sanctions → PEP → SAR into one INV-{sha256} bundle, deterministically. The Suspicious Activity Report (SAR) latency p95 metric and the auto-bundled SAR ZIP (network Mermaid + narrative + manifest) close the gap NY DFS named in Coinbase. *Audit & Evidence* page produces the four-page examiner request list in one click. |

### FINTECH-5 · "The Travel Rule is 99 jurisdictions, four protocols, one MLRO."

| | |
|---|---|
| **Plain-English description** | The Financial Action Task Force (FATF)'s revised Recommendation 16 (June 2025 plenary, end-2030 implementation deadline) requires originator and beneficiary information on every qualifying cross-border transfer over USD/EUR 1,000. 99 jurisdictions are at varying stages of legislation; only ~21% of assessed jurisdictions are fully compliant. There is no single protocol — TRUST, TRISA, Shyft, Sumsub VASP, OpenVASP and proprietary solutions all coexist. The VASP MLRO has to bridge them. |
| **Vignette** | Counterparty exchange uses TRUST. Our exchange uses TRISA. Originator information arrives as a JSON blob in a webhook, not as a standardised message. The MLRO needs to evidence that the field-level transmission happened on time, in full, and was logged. |
| **Primary source** | FATF Recommendation 16 update, June 2025 plenary: *"changes... to the FATF standard, also referred to as the 'Travel Rule' in the context of virtual assets, were agreed by members at the FATF's June 2025 Plenary meeting"* with global implementation by end-2030. — [FATF Recommendation 16 update](https://www.fatf-gafi.org/en/publications/Fatfrecommendations/update-Recommendation-16-payment-transparency-june-2025.html); [FATF Best Practices Travel Rule Supervision PDF](https://www.fatf-gafi.org/content/dam/fatf-gafi/recommendations/Best-Practices-Travel-Rule-Supervision.pdf); [FATF targeted update on virtual assets / VASPs 2025](https://www.fatf-gafi.org/en/publications/Fatfrecommendations/targeted-update-virtual-assets-vasps-2025.html). EU side: AMLR 2024/1624 brings all MiCA-authorised crypto-asset service providers under direct AML obligations, including travel-rule compliance under the Transfer of Funds Regulation. — [Regulation 2024/1624 (EUR-Lex)](https://eur-lex.europa.eu/eli/reg/2024/1624/oj/eng); [Jones Day analysis](https://www.jonesday.com/en/insights/2025/07/crypto-assets-casps-and-amlcft-compliance-the-new-european-regulatory-landscape-under-mica-and-amlr). |
| **Roles affected** | MLRO, VASP compliance ops, Engineering integrations |
| **Cost type** | Compliance + license risk |
| **Framework capability** | ISO 20022 + Travel Rule field validator (Round 5) plus pacs.008 / pacs.009 ingestion ship as one binary; webhook adapters for Notabene and Sumsub are in `integrations/`. The Compliance Manifest declares the field-level requirements once; the audit ledger evidences each transmission per counterparty. The MLRO can answer *"did the originator name go out, and when?"* without leaving the framework. |

### FINTECH-6 · "AMLR's 10 July 2027 clock is the single largest unfunded mandate in EU fintech."

| | |
|---|---|
| **Plain-English description** | EU Anti-Money Laundering Regulation (AMLR) 2024/1624 applies directly across all 27 Member States from 10 July 2027 — no national transposition. The EU Anti-Money Laundering Authority (AMLA) takes operational form 1 July 2025, with direct supervision of ~40 high-risk obliged entities from 2028. EMIs, payment institutions, and crypto-asset service providers are all in scope. Every EU fintech MLRO is now on a 14-month preparation runway. |
| **Vignette** | The board asks: *"what does AMLR mean for our roadmap?"* The MLRO knows it means a single rulebook, harmonised customer due diligence, mandatory risk assessment methodology, and AMLA's selection criteria looming over any cross-border firm. There is no national regulator to ask for an extension. |
| **Primary source** | EU Regulation 2024/1620 (AMLA) and 2024/1624 (AMLR), published in the Official Journal of the EU 19 June 2024. AMLA *"will begin operations on 1 July 2025"*; from 2028 it will *"directly supervise up to 40 selected obliged entities, with eligibility hinging on operating in six or more Member States and exhibiting high residual risk."* AMLR *"will apply directly from 10 July 2027."* AMLR scope expressly includes *"crypto-asset service providers as defined in the Markets in Crypto-Assets Regulation, and credit intermediaries for mortgage and consumer credits that are not financial institutions."* — [Regulation 2024/1620 (EUR-Lex)](https://eur-lex.europa.eu/eli/reg/2024/1620/oj/eng); [Regulation 2024/1624 (EUR-Lex)](https://eur-lex.europa.eu/eli/reg/2024/1624/oj/eng); [AMLA — major step toward harmonised EU supervision](https://www.amla.europa.eu/amla-takes-major-step-toward-harmonised-eu-supervision_en); [EUR-Lex AMLA legal-content summary](https://eur-lex.europa.eu/EN/legal-content/summary/authority-for-anti-money-laundering-and-countering-the-financing-of-terrorism.html). |
| **Roles affected** | MLRO, Compliance Director, CEO (cross-border footprint), Board |
| **Cost type** | Compliance + license risk |
| **Framework capability** | Multi-jurisdiction templating ships specs for US (FinCEN), CA (FINTRAC/OSFI), EU (EBA/AMLD6 + AMLR-ready), UK (FCA/POCA). Adapt to new Member-State implementing acts in days by editing the Manifest. The regulation-drift watcher (`compliance/regwatch.py`) hashes every regulation reference URL in every shipped Manifest and alerts on text drift — so the AMLR 10 July 2027 deadline does not become a surprise. |

### FINTECH-7 · "49 state regulators, one MSB, one Bank Secrecy Act program."

| | |
|---|---|
| **Plain-English description** | A US Money Service Business (MSB) registers with FinCEN once but is licensed by up to 49 states under bespoke money-transmitter regimes. The Conference of State Bank Supervisors (CSBS) Money Transmission Modernization Act (MTMA) is closing the gap — 31 states have adopted it in full or part, covering 99% of reported activity — but the MLRO still answers to a multi-headed examiner, with each state running its own BSA/AML examination cadence. State enforcement now runs in parallel with FinCEN. |
| **Vignette** | Lead-state Massachusetts examiners arrive at the MSB's Boston office. Two weeks later, California Department of Financial Protection and Innovation requests a different cut of the same data. The MLRO has the underlying records — but the formats, sample sizes, and lookback windows are all different. |
| **Primary source** | Coordinated multi-state enforcement against Block, Inc. / Cash App, 15 January 2025, $80M penalty by 48 state financial regulators (lead states: Arkansas, California, Massachusetts, Florida, Maine, Texas, Washington): *"financial services firms are required to perform due diligence on customers, including verifying customer identities, reporting suspicious activity, and applying appropriate controls for high-risk accounts"*; required Block to *"hire an independent consultant to review its BSA/AML program... submit a report within 9 months... correct any deficiencies within 12 months."* — [CSBS press release](https://www.csbs.org/newsroom/state-regulators-issue-80-million-penalty-block-inc-cash-app-bsaaml-violations); [California DFPI press release](https://dfpi.ca.gov/press_release/california-joins-80-million-enforcement-action-against-block-inc-cash-app-for-bsa-aml-violations/). CSBS Money Transmission Modernization Act adoption tracker: *"thirty-one states have enacted the law in full or in part. Money transmitters licensed in at least one state that has already adopted the MTMA collectively account for 99% of reported money transmission activity."* — [CSBS MTMA page](https://www.csbs.org/csbs-money-transmission-modernization-act-mtma); [CSBS state adoption legislation tracker](https://www.csbs.org/state-pending-enacted-mtma-legislation); [CSBS February 2026 legislative update PDF](https://www.csbs.org/sites/default/files/external-link-files/MTMA%20legislative%20update%20February%202026.pdf). FinCEN $42M total resolution against BGS USA (Brink's Global Services), February 2025, for facilitating $800M of cross-border transfers for unregistered MSBs — [FinCEN enforcement actions](https://www.fincen.gov/news/enforcement-actions). |
| **Roles affected** | MLRO, State licensing team, Head of Compliance |
| **Cost type** | Compliance + license risk |
| **Framework capability** | One Compliance Manifest, multiple jurisdiction-tagged audit packs (`aml audit-pack --jurisdiction US-FINCEN`, `--jurisdiction US-NY-DFS`, etc.). Deterministic re-run means California's lookback and Massachusetts' lookback compute from the same evidence chain — no spreadsheet reconciliation. The Compliance Manifest's `regulation_ref` lets the MLRO trace any control to its FinCEN, MTMA, or state-specific obligation. |

### FINTECH-8 · "Series-B+ AML diligence is the unfunded compliance mandate nobody warned us about."

| | |
|---|---|
| **Plain-English description** | A fintech raising a Series B (or filing an S-1) is asked for an AML program file, sanctions-screening evidence, BSA/AML training records, and per-rule effectiveness data — by an investor diligence firm or by SEC underwriters' counsel. The cost of this diligence is real, the timeline is non-negotiable, and the diligence questionnaire reads like an FCA Annex 1 letter. |
| **Vignette** | The lead investor's compliance partner sends a 47-question diligence questionnaire on Friday, due Wednesday. The MLRO needs the BWRA, the false-positive rate trend over four quarters, the sanctions-screening match logs, and a list of every rule change in the last 18 months — with rationales and approval dates. |
| **Primary source** | Chime's S-1 filing (2025) flagged AML compliance as a material risk factor, situating the fintech *"in the gray area between tech and finance"* with elevated regulatory exposure. — [ICLG Fintech Laws and Regulations USA 2025-2026](https://iclg.com/practice-areas/fintech-laws-and-regulations/usa); industry context, [Wolters Kluwer BSA/AML 2025-2026 expert insights](https://www.wolterskluwer.com/en/expert-insights/bsa-aml-in-2025-2026). The cost-floor is anchored by LexisNexis Risk Solutions, *True Cost of Financial Crime Compliance, US & Canada* (Feb 2024): *"annual cost of financial crime compliance totals $61 billion in the United States and Canada,"* with *"78% of small financial institutions"* witnessing higher labor-cost increases than mid/large counterparts (63%); cost distribution averages *"57% labor, 40% technology, 3% other."* — [LexisNexis press release](https://risk.lexisnexis.com/about-us/press-room/press-release/20240221-true-cost-of-compliance-us-ca); [PRNewswire summary](https://www.prnewswire.com/news-releases/study-reveals-annual-cost-of-financial-crime-compliance-totals-61-billion-in-the-united-states-and-canada-302064989.html). |
| **Roles affected** | MLRO, CEO, CFO, General Counsel |
| **Cost type** | Investor / capital risk |
| **Framework capability** | Apache 2.0, runs in the fintech's own perimeter — no per-seat licence, no vendor NDA blocking diligence disclosure. The audit ledger answers *"every change to every rule, with rationale and timestamp"* in one query. The per-rule effectiveness backtester (`aml backtest`) produces the false-positive trend the diligence partner is asking for, without commissioning a vendor study. The deterministic re-run guarantee means an investor's third-party reviewer can replicate any historical run from the Compliance Manifest alone. |

---

## Themes (≈100 words)

For a fintech MLRO in 2026, **the operative regulator is whoever can move fastest** — and that is increasingly the sponsor bank, the FCA case officer, or the lead investor's diligence partner, not the federal supervisor. Across the 2024-26 enforcement record, the common thread is *evidence speed*: Starling could not show its sanctions screening covered the full Consolidated List; Coinbase could not stitch alert-to-SAR into one ordered chain; the Block multistate action turned on whether Cash App could *evidence* customer due diligence, not whether it had it. The 2027 AMLR clock and the Travel Rule's 99-jurisdiction patchwork add a structural deadline the MLRO cannot defer. Lead with **defensible speed**, not detection sophistication.

---

## Sources

### Federal Reserve / FDIC / OCC (US prudential)
- [Federal Reserve press release: Evolve Bancorp / Evolve Bank & Trust enforcement, 14 June 2024](https://www.federalreserve.gov/newsevents/pressreleases/enforcement20240614a.htm)
- [Federal Reserve Evolve cease-and-desist order PDF](https://www.federalreserve.gov/newsevents/pressreleases/files/enf20240614a1.pdf)
- [Banking Dive — running list of BaaS banks hit with consent orders in 2024](https://www.bankingdive.com/news/a-running-list-of-baas-banks-hit-with-consent-orders-in-2024/729121/)

### FinCEN (US federal AML)
- [FinCEN enforcement actions index](https://www.fincen.gov/news/enforcement-actions)
- [FinCEN TD Bank Consent Order, October 2024 (PDF)](https://www.fincen.gov/system/files/enforcement_action/2024-10-10/FinCEN-TD-Bank-Consent-Order-508FINAL.pdf)

### CSBS / state regulators (US state)
- [CSBS press release: $80M Block / Cash App multistate action, 15 January 2025](https://www.csbs.org/newsroom/state-regulators-issue-80-million-penalty-block-inc-cash-app-bsaaml-violations)
- [California DFPI press release: Block / Cash App](https://dfpi.ca.gov/press_release/california-joins-80-million-enforcement-action-against-block-inc-cash-app-for-bsa-aml-violations/)
- [CSBS Money Transmission Modernization Act page](https://www.csbs.org/csbs-money-transmission-modernization-act-mtma)
- [CSBS state pending/enacted MTMA legislation tracker](https://www.csbs.org/state-pending-enacted-mtma-legislation)
- [CSBS MTMA legislative update PDF, February 2026](https://www.csbs.org/sites/default/files/external-link-files/MTMA%20legislative%20update%20February%202026.pdf)

### NY DFS (US state — virtual currency)
- [NY DFS press release: $100M Coinbase settlement, 4 January 2023](https://www.dfs.ny.gov/reports_and_publications/press_releases/pr202301041)
- [NY DFS Coinbase Consent Order PDF, 4 January 2023](https://www.dfs.ny.gov/system/files/documents/2023/01/ea20230104_coinbase.pdf)
- [NY DFS press release: $30M Robinhood Crypto, 2 August 2022](https://www.dfs.ny.gov/reports_and_publications/press_releases/pr202208021)
- [NY DFS Robinhood Crypto Consent Order PDF](https://www.dfs.ny.gov/system/files/documents/2024/08/ea20220801_robinhood_crypto.pdf)

### FCA (UK)
- [FCA Dear-CEO letter to Annex 1 firms, 5 March 2024 (PDF)](https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf)
- [FCA press release: £29M Starling Bank fine, 27 September 2024](https://www.fca.org.uk/news/press-releases/fca-fines-starling-bank-failings-financial-crime-systems-and-controls)
- [FCA Starling Bank Final Notice PDF, 2024](https://www.fca.org.uk/publication/final-notices/starling-bank-limited-2024.pdf)

### EU (AMLA / AMLR)
- [EU Regulation 2024/1620 establishing AMLA (EUR-Lex)](https://eur-lex.europa.eu/eli/reg/2024/1620/oj/eng)
- [EU Regulation 2024/1624 (AMLR) (EUR-Lex)](https://eur-lex.europa.eu/eli/reg/2024/1624/oj/eng)
- [EUR-Lex legal-content summary: AMLA](https://eur-lex.europa.eu/EN/legal-content/summary/authority-for-anti-money-laundering-and-countering-the-financing-of-terrorism.html)
- [AMLA — major step toward harmonised EU supervision](https://www.amla.europa.eu/amla-takes-major-step-toward-harmonised-eu-supervision_en)

### FATF (international)
- [FATF Recommendation 16 update, June 2025](https://www.fatf-gafi.org/en/publications/Fatfrecommendations/update-Recommendation-16-payment-transparency-june-2025.html)
- [FATF Best Practices: Travel Rule Supervision, June 2025 (PDF)](https://www.fatf-gafi.org/content/dam/fatf-gafi/recommendations/Best-Practices-Travel-Rule-Supervision.pdf)
- [FATF targeted update on virtual assets / VASPs, 2025](https://www.fatf-gafi.org/en/publications/Fatfrecommendations/targeted-update-virtual-assets-vasps-2025.html)

### Industry context (supplementary, non-load-bearing)
- [LexisNexis: True Cost of Financial Crime Compliance US & Canada press release, 21 February 2024](https://risk.lexisnexis.com/about-us/press-room/press-release/20240221-true-cost-of-compliance-us-ca)
- [PRNewswire: True Cost summary, $61B US/CA](https://www.prnewswire.com/news-releases/study-reveals-annual-cost-of-financial-crime-compliance-totals-61-billion-in-the-united-states-and-canada-302064989.html)
- [American Banker: Synapse bankruptcy puts bank-fintech partnerships on notice](https://www.americanbanker.com/news/synapse-bankruptcy-puts-bank-fintech-partnerships-on-notice)
- [DLA Piper: FCA Annex 1 letter analysis](https://www.dlapiper.com/en/insights/publications/2024/04/fca-issues-warning-to-ceos-to-improve-anti-money-laundering-controls)
- [DWF: FCA Annex 1 letter analysis](https://dwfgroup.com/en/news-and-insights/insights/2024/3/fca-warns-annex-1-firms-over-common-failings-in-financial-crime-controls)
- [K&L Gates: Starling Bank £29M fine analysis](https://www.klgates.com/Lessons-on-Effective-Financial-Crime-Controls-The-Starling-Bank-Example-11-4-2024)
- [Jones Day: Crypto Assets, CASPs, and AML/CFT under MiCA and AMLR, July 2025](https://www.jonesday.com/en/insights/2025/07/crypto-assets-casps-and-amlcft-compliance-the-new-european-regulatory-landscape-under-mica-and-amlr)
- [ICLG: Fintech Laws and Regulations USA 2025-2026](https://iclg.com/practice-areas/fintech-laws-and-regulations/usa)
- [Wolters Kluwer: BSA/AML in 2025-2026 expert insights](https://www.wolterskluwer.com/en/expert-insights/bsa-aml-in-2025-2026)
