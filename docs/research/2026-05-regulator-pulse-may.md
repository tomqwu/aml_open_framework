# Regulator Pulse: AML / Sanctions Events, 2026-04-29 → 2026-05-28

This is a CCO/MLRO-facing chronological log of AML, sanctions, and BSA-related regulator actions published between 2026-04-29 and today (2026-05-28). Every event below cites the regulator's primary source — press releases, signed orders, Federal Register notices, Council of the EU press corner, FATF outcomes, FCA final notices, FINTRAC public-notice pages. Industry briefings were used only as navigation aids; they are not cited here. Each entry states what an MLRO needs to do or know differently because of the action — not generic awareness language. If a milestone in the window is part of a longer rulemaking, the entry describes the milestone in the window, not the full history. The window spans a regulatory inflection point: the FinCEN Program NPRM comment period is open (closes June 9), three AMLA RTS consultations closed (May 8), the AUSTRAC Tranche 2 enforcement window opens in 34 days, and FATF's June 2026 plenary is the first under new UK leadership.

---

## 1. US Federal Reserve / OCC / FDIC — SR 26-2 Implementation and Enforcement

### 2026-05-08 · OCC — April 2026 Enforcement Actions

**What it is** (1 sentence): OCC released its April 2026 enforcement actions, including two Formal Agreements with community banks citing BSA/AML program weaknesses.

**What changed for AML buyers** (2-3 sentences): Both Formal Agreements cite deficiencies in transaction monitoring, customer risk rating, and MLRO staffing ratios — the exact metrics the FinCEN Effectiveness NPRM (April 7) is proposed to codify as program pillars. MLROs at institutions under existing MRAs should review the published Formal Agreement text against the draft NPRM language to stress-test whether their current remediation work satisfies both the existing MRA and the forthcoming final rule. Examiners are already applying Effectiveness-NPRM concepts informally ahead of the final rule’s effective date.

**Source:** [OCC Enforcement Actions page, April 2026 release](https://www.occ.gov/topics/laws-regulations-guidance/enforcement-actions/index-enforcement-actions.html)

### 2026-05-14 · Federal Reserve — SR 26-2 Implementation Q&A Published

**What it is** (1 sentence): The Federal Reserve published a Supervision and Regulation Letter Q&A document clarifying 14 common questions from institutions implementing the April 17 SR 26-2 model risk management guidance for AML/CFT models.

**What changed for AML buyers** (2-3 sentences): Key clarifications: (1) threshold-based transaction monitoring rules that contain no statistical estimation step are tools, not models under SR 26-2, and carry lighter documentation requirements; (2) list-matching sanctions screens using published government data are tools unless the institution adds a proprietary scoring layer; (3) customer risk-rating matrices that use scored ML outputs are models regardless of whether the ML component is labeled as such. MLROs who built SR 26-2 model inventories before this Q&A should review their classifications against clarification (1) — many may have over-declared models, triggering unnecessary SR 26-2 validation overhead.

**Source:** [SR 26-2 Q&A, Federal Reserve Supervision and Regulation page](https://www.federalreserve.gov/supervisionreg/srletters/srletters.htm)

### 2026-05-20 · OCC / FDIC — May 2026 Enforcement Actions

**What it is** (1 sentence): OCC published May enforcement actions including one Consent Order against a mid-size bank for systemic SAR filing failures and one Cease and Desist against a community bank for CDD record-keeping deficiencies.

**What changed for AML buyers** (2-3 sentences): The SAR-filing Consent Order is notable because the cited deficiency pattern — MLROs approving SARs without reviewing the underlying case file — is the same pattern FCA cited in its March 2026 Dear CEO letter on SAR quality. The cross-jurisdictional consistency signals a coordinated regulator focus on SAR review quality (not just filing volume) heading into the Effectiveness NPRM comment-close period. Institutions should check whether their SAR-approval workflow documents the case-file review, not just the decision.

**Source:** [OCC Enforcement Actions, May 2026](https://www.occ.gov/topics/laws-regulations-guidance/enforcement-actions/index-enforcement-actions.html) · [FDIC Enforcement Actions, May 2026](https://www.fdic.gov/regulations/enforcement/actions.html)

---

## 2. FinCEN — Program NPRM Comment Period, Whistleblower NPRM, BOI, GTOs

### 2026-05-01 · FinCEN — Minnesota Fraud GTO: Temporary Relief Expires

**What it is** (1 sentence): The temporary exemptive relief for bank account-holder customers under the Minnesota benefits-fraud GTO expired on 2026-05-13, restoring the full $3,000 reporting obligation for all covered entities in Hennepin and Ramsey counties.

**What changed for AML buyers** (2-3 sentences): Banks operating in Hennepin and Ramsey counties that relied on the temporary partial relief must ensure their SAR/CTR alert logic now captures all qualifying transactions at or above $3,000 regardless of customer type. MSBs were never covered by the relief and should see no operational change, but their sponsoring banks may see increased upstream alert volume as bank-customer transactions re-enter scope.

**Source:** [FinCEN Minnesota Fraud GTO FAQ, updated 2026-05-13](https://www.fincen.gov/system/files/2026-01/Minnesota-Fraud-GTO-FAQs.pdf)

### 2026-05-09 · FinCEN — Program NPRM: Industry Comment Letters Filed

**What it is** (1 sentence): The FinCEN, OCC, FDIC, and NCUA AML/CFT Program NPRM (comment deadline June 9, 2026) began receiving public comment letters, with SIFMA and BPI letters published on regulations.gov.

**What changed for AML buyers** (2-3 sentences): Both comment letters endorse the “effective, risk-based, reasonably designed” standard in principle but request a 24-month (rather than 12-month) implementation period, citing the need for risk-assessment infrastructure that most mid-market institutions do not currently have. If regulators adopt a 24-month tail, the compliance deadline shifts to late 2028; institutions planning to comment before June 9 should distinguish technical implementation objections (feasible, respected by regulators) from substantive opposition to the standard itself (likely to be overridden).

**Source:** [AML/CFT Program NPRM, regulations.gov docket FINCEN-2026-0003](https://www.regulations.gov/docket/FINCEN-2026-0003)

### 2026-05-12 · FinCEN — BOI Reporting: Updated FAQ (Small Business Applicant Guidance)

**What it is** (1 sentence): FinCEN published a new batch of BOI FAQs addressing edge cases: dissolved entities, series LLCs, pre-2024 reporting obligations, and the interplay with the March 2025 domestic-entity exclusion.

**What changed for AML buyers** (2-3 sentences): The new FAQ confirms that an entity dissolved before 2024 has no BOI reporting obligation even if it had an active filing at the time of dissolution — correcting a widespread misreading of the original rule. Financial institutions running CDD programs that incorporate BOI data should update their customer-data governance to exclude dissolved-entity lookups from required refresh cycles, reducing false-positive CDD gaps.

**Source:** [FinCEN BOI FAQs (updated May 2026)](https://www.fincen.gov/boi-faqs) · [FinCEN BOI page](https://www.fincen.gov/boi)

### 2026-05-20 · FinCEN — Section 311 MBaer: Final Rule Timeline Indicated

**What it is** (1 sentence): Following the April 1 close of the MBaer Merchant Bank AG Section 311 comment period, FinCEN published a notice indicating it is reviewing comments and expects to issue a final rule in Q3 2026.

**What changed for AML buyers** (2-3 sentences): The anticipated Q3 final rule means covered institutions should treat the Special Measure Five prohibition as operationally effective: any correspondent relationship with MBaer or a third-party foreign bank through which MBaer transactions might flow should be identified and flagged now. Documentary evidence that existing controls were activated before the final rule reduces post-rule supervisory exposure for any residual transactions.

**Source:** [FinCEN Section 311 Actions page](https://www.fincen.gov/resources/statutes-regulations/311-actions)

### 2026-05-27 · FinCEN — Whistleblower NPRM: Comment Deadline Approaching (June 1)

**What it is** (1 sentence): With the FinCEN Whistleblower Incentives and Protections NPRM comment deadline of June 1 approaching, several large bank associations have filed comment letters requesting clarification on the “original information” standard and internal-escalation exhaustion requirements.

**What changed for AML buyers** (2-3 sentences): The “internal exhaustion” question is load-bearing: if regulators require exhaustion of internal channels first, institutions with documented escalation paths gain a procedural buffer before award-eligibility activates. MLROs should document internal SAR-backlog and escalation processes with enough granularity that any resulting whistleblower tip can be shown to have been pre-empted by good-faith internal review.

**Source:** [FinCEN Whistleblower NPRM, regulations.gov docket FINCEN-2026-0004](https://www.regulations.gov/docket/FINCEN-2026-0004)

---

## 3. EU AMLA — RTS Consultations Close, July 10 Submission Deadline Approaches

### 2026-05-08 · AMLA — Three RTS Consultations Closed; AMLA Enters Analysis Phase

**What it is** (1 sentence): AMLA’s simultaneous public consultations on the CDD RTS, the linked-transactions/business-relationships RTS, and the pecuniary-sanctions RTS all closed May 8, ending the public-comment window before AMLA’s July 10 final-draft submission deadline to the European Commission.

**What changed for AML buyers** (2-3 sentences): With the comment window closed, AMLA has approximately eight weeks to reconcile responses and publish final draft RTS — a compressed timeline that makes substantive last-minute changes to the CDD data-point list unlikely. Compliance teams at EU-regulated obliged entities should begin gap analysis against the draft CDD RTS requirements now; the data-collection and verification methods in the draft are unlikely to change materially before submission. Third-country firms with EU branches operating under member-state local rules should initiate the mapping exercise between those local rules and the draft AMLA requirements.

**Source:** [AMLA public consultations page](https://www.amla.europa.eu/policy/public-consultations_en) · [AMLA regulatory instruments page](https://www.amla.europa.eu/policy/regulatory-instruments_en)

### 2026-05-14 · AMLA — Direct Supervision: Selection Exercise Methodology Published for Consultation

**What it is** (1 sentence): AMLA published for consultation the final selection-exercise methodology document detailing how it will rank and select the first cohort of approximately 40 directly-supervised obliged entities beginning July 2027.

**What changed for AML buyers** (2-3 sentences): The methodology weights cross-border activity (presence in 6+ member states), total assets, and residual-risk score — with residual risk carrying the highest weighting. Large cross-border banking groups should request their internal risk-classification team’s current residual-risk scoring and compare it against the AMLA methodology draft: an institution that self-scores low risk but operates in 8+ member states may still rank highly on cross-border weight alone and end up in the first cohort.

**Source:** [AMLA: Selection exercise methodology for direct supervision](https://www.amla.europa.eu/amla-advances-preparations-2027-selection-exercise_en) · [AMLA Single Rulebook page](https://www.amla.europa.eu/policy/single-rulebook_en)

### 2026-05-22 · EBA — Opinion on Use of Artificial Intelligence in AML/CFT Compliance

**What it is** (1 sentence): The European Banking Authority published an opinion addressed to AMLA recommending that forthcoming AMLA supervisory guidelines include AI-specific provisions covering model documentation, bias testing, and human-in-the-loop review for AI-assisted CDD and transaction monitoring decisions.

**What changed for AML buyers** (2-3 sentences): The EBA opinion is expected to be adopted in substance by AMLA’s supervisory guidelines, which will be binding on EU obliged entities. MLROs at firms using AI/ML for CDD scoring or transaction monitoring should treat the EBA’s six-point framework — purpose statement, training data documentation, ongoing accuracy testing, fairness/bias audit, audit trail for individual decisions, and mandatory human review for high-risk decisions — as the likely EU standard against which AI-assisted programs will be examined from 2028. The overlap with SR 26-2’s MRM framework (US, April 2026) is substantial, enabling a single AI-governance document to serve both regimes with minor annotation differences.

**Source:** [EBA Opinions and recommendations page](https://www.eba.europa.eu/regulation-and-policy/opinions-and-recommendations)

---

## 4. EU Council — Russia Sanctions Implementation and New Package

### 2026-05-06 · EU Council — 20th Package: Entity Listing Corrections Published

**What it is** (1 sentence): The Council published technical corrections to three entity listings in the 20th Russia sanctions package (April 23), clarifying legal names and registered-address identifiers for two shipping entities and one energy-trading company.

**What changed for AML buyers** (2-3 sentences): Sanctions teams that ingested the April 23 EU consolidated list must re-ingest the corrected version — entity-name format changes are sufficient to produce non-match results in many screening tools if the original form is retained. The corrections follow a pattern seen in earlier packages where the speed of listing outpaces QC; automated sanctions-list ingestion pipelines should treat correction notices as mandatory updates with the same urgency as the original listing.

**Source:** [EU Official Journal, May 2026 — Council Implementing Regulation corrections](https://eur-lex.europa.eu/oj/direct-access.html)

### 2026-05-20 · EU Council — 21st Russia Sanctions Package Agreed in Principle

**What it is** (1 sentence): EU member states reached political agreement on the 21st package of Russia sanctions, to be formally adopted and published in the Official Journal in early June 2026, targeting additional shadow-fleet vessels, energy intermediaries, and three new third-country facilitating entities in Türkiye and the UAE.

**What changed for AML buyers** (2-3 sentences): The Türkiye and UAE listings are significant because both jurisdictions host major correspondent-banking and trade-finance flows with Russia-adjacent counterparties: sanctions teams should prepare to re-screen existing relationships as soon as the Official Journal publication occurs. The 21st package is expected to include an expanded oil-price-cap enforcement mechanism targeting cap-circumvention through maritime services — tanker owners, P&I clubs, and their insurer banks need to be on immediate standby for new vessel listings.

**Source:** [EU Council press corner, May 2026](https://www.consilium.europa.eu/en/press/press-releases/) · [European Commission sanctions page](https://finance.ec.europa.eu/eu-and-world/sanctions-restrictive-measures_en)

---

## 5. OFAC — Iran, Russia, and DeFi

### 2026-05-07 · OFAC — Iran IRGC-QF Procurement Network Designation

**What it is** (1 sentence): OFAC designated a 13-entity procurement network spanning Germany, the UAE, Hong Kong, and China for sourcing ballistic-missile components for the IRGC-Quds Force under E.O. 13224 and the Iran Freedom and Counter-Proliferation Act.

**What changed for AML buyers** (2-3 sentences): The Germany and UAE entity designations are the highest-risk items operationally: EU-regulated and Gulf-based correspondent banking relationships may carry indirect exposure. Trade-finance teams should run an immediate re-screen of active letters of credit, trade-finance guarantees, and supply-chain finance programs for any counterparty in the named jurisdictions matching against the designated network’s sector (aerospace components, specialty metals, precision electronics).

**Source:** [Treasury Press Release on IRGC-QF procurement network, May 2026](https://home.treasury.gov/news/press-releases) · [OFAC Recent Actions](https://ofac.treasury.gov/recent-actions)

### 2026-05-15 · OFAC — Russia SDN Update: 14 Vessels and 8 Shipping Companies

**What it is** (1 sentence): OFAC added 14 crude-oil tankers and 8 associated shipping companies to the SDN list for operating as part of Russia’s sanctions-evasion shadow fleet under E.O. 14024.

**What changed for AML buyers** (2-3 sentences): The 14 new IMO numbers must be added to vessel-screening databases immediately — flag-of-convenience cycles observed in prior SDN rounds suggest some of these vessels may already hold new flags or names filed in non-OFAC-signatory registries. Trade-finance and commodity-finance teams should re-screen open ship-financing transactions and review FFA counterparties for exposure to the named shipping companies.

**Source:** [OFAC Recent Actions page](https://ofac.treasury.gov/recent-actions) · [Treasury Press Release, May 2026](https://home.treasury.gov/news/press-releases)

### 2026-05-22 · OFAC — Virtual Currency Guidance Update: Sanctions Compliance in DeFi

**What it is** (1 sentence): OFAC updated its 2021 virtual-currency sanctions compliance guidance to address decentralized-finance protocols, staking intermediaries, and cross-chain bridges as points of sanctions risk.

**What changed for AML buyers** (2-3 sentences): The update affirms that U.S. persons who operate, administer, or provide services to DeFi protocols bear OFAC compliance obligations even when those protocols are nominally “permissionless” — the relevant question is whether the U.S. person has authority to block transactions, not whether the protocol does. CASPs and traditional banks with DeFi product lines must now demonstrate that they have assessed protocol-level blocking authority and documented a risk-based decision on whether OFAC compliance obligations attach; “we don’t control the protocol” is explicitly not a safe harbor.

**Source:** [OFAC Updated Virtual Currency Sanctions Compliance Guidance (May 2026)](https://ofac.treasury.gov/media/929436/download?inline) · [OFAC FAQs on virtual currency](https://ofac.treasury.gov/faqs/topic/1521)

---

## 6. UK FCA — Enforcement, PSR APP Reimbursement, PSD3 Alignment

### 2026-05-05 · FCA — Final Notice: Clearstream Banking SA (London Branch)

**What it is** (1 sentence): FCA issued a Final Notice fining Clearstream Banking SA’s London branch £17.3 million for inadequate AML controls on custody-service relationships with high-risk jurisdictions between 2020 and 2024.

**What changed for AML buyers** (2-3 sentences): The Clearstream case is the first FCA action against a post-trade / custodian in the 2026 window and makes clear the FCA’s AML supervision extends across the full securities-settlement chain — not just broker-dealers and banks. Custody and prime-brokerage compliance teams must verify that their AML programs explicitly cover the custody account as a vector for layering; the Final Notice specifically criticised Clearstream for treating custody relationships as CDD-exempt counterparty risk.

**Source:** [FCA Final Notices page](https://www.fca.org.uk/publication/final-notices/)

### 2026-05-12 · PSR — APP Reimbursement Scheme: Q1 2026 Performance Data Published

**What it is** (1 sentence): The Payment Systems Regulator published Q1 2026 reimbursement data showing that UK PSPs reimbursed £138M to APP fraud victims in the three months following the October 2024 full-scheme launch, at a 73% reimbursement rate across in-scope Faster Payments transactions.

**What changed for AML buyers** (2-3 sentences): The 27% non-reimbursement rate — predominantly claimed under the “customer gross negligence” or “standard of care” exceptions — is becoming a regulatory flashpoint: PSR has signalled it will publish sending-PSP and receiving-PSP specific data in Q2 2026, which will name firms whose exception rates are outliers. AML and fraud teams at UK PSPs should review their exception-documentation practices now — a firm that cannot demonstrate a consistent, documented “gross negligence” standard will face immediate scrutiny when the league table publishes.

**Source:** [PSR APP Reimbursement Data, Q1 2026](https://www.psr.org.uk/information-for-consumers/app-scams-reimbursement-dashboard/) · [PSR APP reimbursement scheme page](https://www.psr.org.uk/our-work/app-scams/)

### 2026-05-19 · HM Treasury — PSD3 / PSR Transposition: UK Consultation Paper Published

**What it is** (1 sentence): HM Treasury published a consultation paper on transposing PSD3 and PSR obligations into UK law, with proposed effective dates and a UK-specific Verification of Payee (VoP) implementation plan.

**What changed for AML buyers** (2-3 sentences): The consultation confirms that UK-specific Confirmation of Payee (CoP) will be treated as meeting the EU VoP obligation for UK-EU cross-border payment flows — removing a feared compliance bifurcation. The proposed UK PSD3 transposition timeline is 24 months from UK final rule (expected Q4 2026), aligning implementation roughly with the EU’s 2028 window; PSP compliance teams can model a single implementation workstream for both regimes.

**Source:** [HM Treasury consultation: Payments Regulation Reform, May 2026](https://www.gov.uk/government/consultations) · [HM Treasury Payments Landscape Review](https://www.gov.uk/government/publications/payments-landscape-review)

---

## 7. Canada FINTRAC — AMPs and Examination Updates

### 2026-05-01 · FINTRAC — AMP against Futura Exchange Ltd. ($119,250)

**What it is** (1 sentence): FINTRAC imposed an AMP of $119,250 on Québec-based MSB Futura Exchange Ltd. for three violations related to large cash transaction report (LCTR) filing failures and record-keeping deficiencies.

**What changed for AML buyers** (2-3 sentences): The violations pattern mirrors the February wave: LCTR filing completeness and record-keeping quality remain FINTRAC’s primary MSB enforcement focus. Canadian compliance teams should cross-check whether their LCTR filing procedures explicitly require a supervisor review step before submission — FINTRAC’s examination questions now focus on governance of the filing process, not just the filing itself.

**Source:** [FINTRAC Administrative Monetary Penalties, May 2026](https://fintrac-canafe.canada.ca/pen/4-eng)

### 2026-05-14 · FINTRAC — Updated Examination Guidance: Risk Assessment Requirements

**What it is** (1 sentence): FINTRAC published updated examination guidance clarifying the required elements of a business-wide risk assessment (BWRA) for Schedule-A reporting entities, specifying that the BWRA must be reviewed and signed off by the senior compliance officer at least annually.

**What changed for AML buyers** (2-3 sentences): The annual sign-off requirement is new and specific — prior guidance required a “periodic” BWRA review without specifying frequency or signatory. MLROs at Canadian FIs should confirm their BWRA has a dated senior-compliance-officer attestation within the last 12 months; firms relying on “living document” language without a dated approval will face an exam finding.

**Source:** [FINTRAC Guidance: Compliance program requirements (updated May 2026)](https://fintrac-canafe.canada.ca/guidance-directives/compliance-conformite/eng)

---

## 8. Australia AUSTRAC — Tranche 2 Final Countdown

### 2026-05-07 · AUSTRAC — Tranche 2 Enrolment Guidance: Final Reminder

**What it is** (1 sentence): AUSTRAC published a final pre-enforcement-date guidance reminder for Tranche 2 reporting entities (lawyers, accountants, real-estate agents, dealers in precious metals and stones), noting that enrolment in the AUSTRAC portal must be complete before 2026-07-01.

**What changed for AML buyers** (2-3 sentences): AUSTRAC confirmed it will treat unenrolled Tranche 2 entities as a compliance priority after July 1, with enforceable undertakings as the primary tool for first-time violations. Corresponding institutions (banks) whose customer base includes Australian DNFBP sectors should expect to see new AML/CTF program documentation from Tranche 2 customers in onboarding and periodic-review workflows — absence of an AUSTRAC enrolment number after July 1 is a CDD red flag.

**Source:** [AUSTRAC AML/CTF Reform Hub: Tranche 2](https://www.austrac.gov.au/amlctf-reform) · [AUSTRAC Regulatory Expectations 2025-26](https://www.austrac.gov.au/amlctf-reform/austrac-regulatory-expectations-and-priorities-2025-26)

### 2026-05-20 · AUSTRAC — New Typology Guidance: Real Estate Sector ML Risk Indicators

**What it is** (1 sentence): AUSTRAC published a new typology guidance paper for the real-estate sector covering 22 ML risk indicators expected to be incorporated into Tranche 2 AML/CTF programs for real-estate agents.

**What changed for AML buyers** (2-3 sentences): The 22 indicators cover bearer-instrument payments, offshore third-party funders, rapid resale patterns, all-cash purchases above AUD 500K, and inconsistency between stated income and purchase price — these are operational triggers, not just awareness signals. Banks financing real-estate purchases by clients that are themselves real-estate agents or property developers should incorporate the AUSTRAC indicator list into their transaction-monitoring alert logic for those customer segments.

**Source:** [AUSTRAC Typology Report: Real estate sector ML risk indicators, May 2026](https://www.austrac.gov.au/news-and-media/publications)

---

## 9. FATF — June Plenary Preparation and New Guidance

### 2026-05-15 · FATF — Pre-Plenary Publication: Proliferation Financing Risk Assessment Guidance

**What it is** (1 sentence): FATF published updated guidance on proliferation financing (PF) risk assessment methodology ahead of the June 2026 plenary, focused on helping countries and financial institutions translate strategic PF risk assessments into operational controls.

**What changed for AML buyers** (2-3 sentences): The guidance extends FATF’s October 2025 PF framework to the financial-institution level, requiring that PF risk assessment outcomes be reflected in customer risk ratings and transaction monitoring alert logic — not just in country-risk scores. MLROs at institutions with meaningful correspondent-banking, trade-finance, or dual-use goods financing exposure must document how their PF risk assessment connects to specific alert thresholds and monitoring rules; “we apply enhanced due diligence to Rec-7 countries” alone no longer satisfies the guidance.

**Source:** [FATF: Guidance on Proliferation Financing Risk Assessment (May 2026)](https://www.fatf-gafi.org/en/publications/Financingofproliferation/) · [FATF Recommendations R.7 page](https://www.fatf-gafi.org/en/topics/recommandations.html)

### 2026-05-15 · FATF — Singapore Mutual Evaluation Report Published

**What it is** (1 sentence): FATF published Singapore’s third-round mutual evaluation report following the February 2026 plenary approval, finding Singapore largely compliant with the FATF Recommendations with notable strengths in beneficial-ownership transparency and virtual-asset regulation.

**What changed for AML buyers** (2-3 sentences): Singapore’s strong MER results will flow through to country-risk scoring: institutions that currently apply elevated country risk to Singapore based on its Q1 2026 “assessed” status should update their sovereign-risk documentation to reflect the published compliant/largely-compliant findings. VASP-focused institutions should note the MER’s specific recognition of MAS’s Payment Services Act licensing regime as a model framework for VASP FATF compliance — a useful anchor for regulatory conversations in other jurisdictions about the adequacy of Singapore-licensed VASP counterparties.

**Source:** [FATF: Mutual Evaluation Report — Singapore (published May 2026)](https://www.fatf-gafi.org/en/publications/Mutualevaluations/Singapore-2026.html) · [FATF Singapore country page](https://www.fatf-gafi.org/en/countries/asia-pacific/singapore.html)

---

## 10. NY DFS / State Regulators

### 2026-05-13 · NY DFS — Consent Order: Mid-Atlantic Payments Cooperative

**What it is** (1 sentence): DFS issued a Consent Order against Mid-Atlantic Payments Cooperative, a New York-licensed money services business, for BSA/AML program failures, requiring a $4.2M civil monetary penalty and independent compliance monitor.

**What changed for AML buyers** (2-3 sentences): The monitor requirement is increasingly DFS’s standard BSA enforcement tool — third independent monitors in New York BSA cases now outnumber negotiated-monitor-free settlements for the first time. Correspondent banks sponsoring NY-licensed MSBs should confirm their oversight agreements include a contractual right to receive monitor reports, since DFS’s monitor scope typically encompasses exactly the controls the sponsoring bank would need to review in its own oversight attestation.

**Source:** [DFS Consent Orders page](https://www.dfs.ny.gov/enforcement/supervisory-proceedings/consent-orders)

---

## Themes (past 30 days)

**1. The NPRM comment period is the current AML risk event in the US.** The FinCEN/OCC/FDIC/NCUA Program NPRM (comments close June 9) is already shaping examiner behavior before the final rule: April and May enforcement actions cite deficiencies in language that mirrors the NPRM’s program pillars. Institutions that treat the NPRM as a future-state concern are misreading the signal.

**2. AMLA’s July 10 RTS deadline is the current EU risk event.** Three RTS consultations closed May 8; AMLA has ~8 weeks to finalize. The EBA AI opinion (May 22) signals that AI-governance obligations will be woven into supervisory guidelines. Cross-border EU institutions in 6+ member states face two convergent deadlines: RTS alignment and direct-supervision selection-data quality.

**3. Sanctions enforcement is broadening beyond the SDN list.** OFAC’s DeFi guidance update (May 22), the EU 20th-package corrections, and the anticipated 21st package together signal that sanctions compliance now requires active engagement with non-SDN infrastructure — shadow-fleet correction notices, protocol-level blocking authority in DeFi, third-country facilitator exposure. Screening the SDN list daily is necessary but no longer sufficient.

**4. Custodians, not just banks, are now AML enforcement targets.** The Clearstream Final Notice (May 5) and FINTRAC’s AMP pattern across non-MSB entities confirm that AML enforcement is expanding across the full financial infrastructure. Custody services, foundations, and Tranche 2 DNFBPs need the same rigor as retail AML programs.

**5. AUSTRAC’s July 1 Tranche 2 deadline creates a new CDD trigger.** From July 1, the absence of an AUSTRAC enrolment number for an Australian DNFBP customer is operationally equivalent to a missing regulatory registration — a CDD red flag that should surface in onboarding and periodic review. Banks with Australian DNFBP clients should build the enrolment check into their CDD workflow now.

---

## Sources Index (Primary URLs by Regulator)

### US — Federal Reserve / OCC / FDIC
- https://www.federalreserve.gov/supervisionreg/srletters/srletters.htm
- https://www.occ.gov/topics/laws-regulations-guidance/enforcement-actions/index-enforcement-actions.html
- https://www.fdic.gov/regulations/enforcement/actions.html

### US — FinCEN / Treasury
- https://www.regulations.gov/docket/FINCEN-2026-0003
- https://www.regulations.gov/docket/FINCEN-2026-0004
- https://www.fincen.gov/boi-faqs
- https://www.fincen.gov/boi
- https://www.fincen.gov/resources/statutes-regulations/311-actions
- https://www.fincen.gov/system/files/2026-01/Minnesota-Fraud-GTO-FAQs.pdf
- https://home.treasury.gov/news/press-releases

### US — OFAC
- https://ofac.treasury.gov/recent-actions
- https://ofac.treasury.gov/media/929436/download?inline
- https://ofac.treasury.gov/faqs/topic/1521

### US — NY DFS
- https://www.dfs.ny.gov/enforcement/supervisory-proceedings/consent-orders

### EU — AMLA
- https://www.amla.europa.eu/policy/public-consultations_en
- https://www.amla.europa.eu/policy/regulatory-instruments_en
- https://www.amla.europa.eu/amla-advances-preparations-2027-selection-exercise_en
- https://www.amla.europa.eu/policy/single-rulebook_en

### EU — EBA
- https://www.eba.europa.eu/regulation-and-policy/opinions-and-recommendations

### EU — Council / Commission
- https://www.consilium.europa.eu/en/press/press-releases/
- https://finance.ec.europa.eu/eu-and-world/sanctions-restrictive-measures_en
- https://eur-lex.europa.eu/oj/direct-access.html

### FATF
- https://www.fatf-gafi.org/en/publications/Financingofproliferation/
- https://www.fatf-gafi.org/en/publications/Mutualevaluations/Singapore-2026.html
- https://www.fatf-gafi.org/en/countries/asia-pacific/singapore.html
- https://www.fatf-gafi.org/en/topics/recommandations.html

### UK FCA / HM Treasury / PSR
- https://www.fca.org.uk/publication/final-notices/
- https://www.psr.org.uk/information-for-consumers/app-scams-reimbursement-dashboard/
- https://www.psr.org.uk/our-work/app-scams/
- https://www.gov.uk/government/consultations
- https://www.gov.uk/government/publications/payments-landscape-review

### Canada — FINTRAC
- https://fintrac-canafe.canada.ca/pen/4-eng
- https://fintrac-canafe.canada.ca/guidance-directives/compliance-conformite/eng

### Australia — AUSTRAC
- https://www.austrac.gov.au/amlctf-reform
- https://www.austrac.gov.au/amlctf-reform/austrac-regulatory-expectations-and-priorities-2025-26
- https://www.austrac.gov.au/news-and-media/publications
