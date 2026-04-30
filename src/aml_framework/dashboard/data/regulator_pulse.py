"""Regulator pulse — 30+ AML / sanctions events, 2026-02-01 → 2026-04-29.

Hand-curated mirror of `docs/research/2026-04-regulator-pulse.md`. The
research doc is the source of truth; this module is the dashboard-side
data substrate for `pages/27_Regulator_Pulse.py`.

We don't parse the markdown at runtime because:
- Stability — research doc reformatting wouldn't break the dashboard
- No new dependency (mistune / markdown-it) needed for unit-test CI
- The dashboard adds a `dashboard_page` cross-link that the research
  doc doesn't have

Update cadence
--------------
Re-curate when the research doc is refreshed. Auto-refresh out of
scope for now — the research doc is itself a deep-research-agent
output that runs on demand, not on a schedule.

Entry shape
-----------
- date              · ISO YYYY-MM-DD (or "2026-02" / "2026-03" for
  month-precision events from AMLA / AUSTRAC where the research doc
  doesn't cite a specific day)
- regulator         · short name as it appears in the research doc
- headline          · one-line summary, copied verbatim from the
  research doc's H3
- for_buyers        · 1-3 sentence "what changed for AML buyers"
  paraphrased from the research doc's expanded body
- source_url        · primary-source URL (regulator press release,
  Federal Register, SR letter, EUR-Lex, etc.). The research doc has
  multiple URLs per event; we keep the first / most authoritative.
- dashboard_page    · dashboard page that addresses the event (e.g.,
  SR 26-2 → Tuning Lab). Empty string if no direct dashboard
  equivalent — those events still appear in the timeline.
- dashboard_anchor  · file slug for the dashboard page link
"""

from __future__ import annotations

EVENTS: list[dict[str, str]] = [
    # ── US Federal Reserve / OCC / FDIC — model risk + reputation risk ──
    {
        "date": "2026-02-23",
        "regulator": "Federal Reserve",
        "headline": "Proposes to codify removal of reputation risk from supervision",
        "for_buyers": (
            "Examiners can no longer downgrade an institution because a customer base 'looks bad' — "
            "only material financial risk counts. MLROs whose risk-rating models cite reputation as "
            "a factor (high-risk industry, crypto, cannabis, MSBs) should re-document those tiers "
            "around concrete BSA/sanctions risk drivers before their next exam. Comments closed 2026-04-27."
        ),
        "source_url": "https://www.federalreserve.gov/newsevents/pressreleases/bcreg20260223a.htm",
        "dashboard_page": "Risk Assessment",
        "dashboard_anchor": "6_Risk_Assessment",
    },
    {
        "date": "2026-04-07",
        "regulator": "OCC + FDIC",
        "headline": "Final rule prohibiting reputation risk in supervision",
        "for_buyers": (
            "'Debanking' of legal-but-controversial customers (firearms, crypto, payday, cannabis-adjacent) "
            "cannot be ordered or hinted at by examiners. Institutions that have used examiner pressure "
            "as cover to exit those segments must now document an actual BSA/sanctions risk basis for "
            "any exit decision. Effective 60 days after Federal Register publication."
        ),
        "source_url": "https://www.occ.gov/news-issuances/news-releases/2026/nr-ia-2026-26.html",
        "dashboard_page": "Risk Assessment",
        "dashboard_anchor": "6_Risk_Assessment",
    },
    {
        "date": "2026-04-17",
        "regulator": "Federal Reserve / OCC / FDIC",
        "headline": "SR 26-2 Revised Model Risk Management Guidance — effective today",
        "for_buyers": (
            "Transaction monitoring, sanctions screening, name-matching, customer risk-rating, and CDD "
            "scoring models are now governed under a single MRM framework alongside credit and market "
            "models — separate AML-specific MRM guidance no longer exists. Buyers must add SR-26-2-aligned "
            "model documentation (purpose, conceptual soundness, ongoing monitoring, outcome analysis, "
            "tiering) for any rule that scores or categorizes customers. The 12-month implementation "
            "tail closes April 2027."
        ),
        "source_url": "https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm",
        "dashboard_page": "Tuning Lab",
        "dashboard_anchor": "23_Tuning_Lab",
    },
    {
        "date": "2026-02-19",
        "regulator": "OCC",
        "headline": "February 2026 enforcement actions — terminations only",
        "for_buyers": (
            "Five enforcement-action terminations and zero new BSA/AML actions for the month. "
            "Useful read-across for community banks under existing BSA orders — they document what "
            "'demonstrated compliance' looks like over a 12-30 month remediation cycle."
        ),
        "source_url": "https://www.occ.treas.gov/news-issuances/news-releases/2026/nr-occ-2026-8.html",
        "dashboard_page": "",
        "dashboard_anchor": "",
    },
    {
        "date": "2026-03-18",
        "regulator": "OCC",
        "headline": "March 2026 enforcement — one prohibition, four terminations",
        "for_buyers": (
            "No new bank-level BSA/AML enforcement was published, continuing the 2026 pattern of "
            "supervisory rather than punitive activity. Insider-risk programs should note the ongoing "
            "pattern of low-dollar insider cases driving prohibition orders."
        ),
        "source_url": "https://www.occ.treas.gov/news-issuances/news-releases/2026/nr-occ-2026-15.html",
        "dashboard_page": "",
        "dashboard_anchor": "",
    },
    # ── FinCEN — Effectiveness rule, Section 311, GTOs, whistleblower ──
    {
        "date": "2026-02-13",
        "regulator": "FinCEN",
        "headline": "Launches public Whistleblower webpage",
        "for_buyers": (
            "Employees, contractors, and third parties now have a one-click route to report perceived "
            "AML or sanctions failures to Treasury, with awards of 10–30% of monetary penalties payable "
            "from the $300M Financial Integrity Fund. By the time a tip is filed externally, the audit "
            "ledger needs to show the firm took the original internal report seriously."
        ),
        "source_url": "https://www.fincen.gov/contact/office-whistleblower",
        "dashboard_page": "Audit & Evidence",
        "dashboard_anchor": "7_Audit_Evidence",
    },
    {
        "date": "2026-02-26",
        "regulator": "FinCEN",
        "headline": "Section 311 NPRM against MBaer Merchant Bank AG (Switzerland)",
        "for_buyers": (
            "First new Section 311 action in roughly three years. Correspondent banking teams must add "
            "a Section 311 monitoring control to their nested-account screening — not just SDN. "
            "Covered institutions: close any direct MBaer correspondent account, screen third-party "
            "foreign banks for MBaer exposure, apply EDD on all foreign correspondent accounts."
        ),
        "source_url": "https://home.treasury.gov/news/press-releases/sb0408",
        "dashboard_page": "Sanctions Screening",
        "dashboard_anchor": "12_Sanctions_Screening",
    },
    {
        "date": "2026-02-27",
        "regulator": "FinCEN",
        "headline": "Exemptive Relief for Minnesota fraud GTO",
        "for_buyers": (
            "Banks operating in Hennepin and Ramsey counties get breathing room to update systems but "
            "the $3,000 threshold and base reporting obligation remain. MSBs are explicitly not covered "
            "by this relief. MN-footprint banks should treat as a temporary scoping change, not a wind-down."
        ),
        "source_url": "https://www.fincen.gov/system/files/2026-01/Minnesota-Fraud-GTO-Order.pdf",
        "dashboard_page": "",
        "dashboard_anchor": "",
    },
    {
        "date": "2026-03-10",
        "regulator": "FinCEN",
        "headline": "Expanded Southwest Border Geographic Targeting Order",
        "for_buyers": (
            "MSBs in newly-covered counties must file CTRs on cash $1,000–$10,000 through 2026-09-02. "
            "Newly-covered MSBs had a 30-day onboarding window ending 2026-04-06. Bank holding companies "
            "with MSB customers in those counties should expect a sharp increase in upstream alert review."
        ),
        "source_url": "https://www.fincen.gov/news/news-releases/fincen-issues-expanded-southwest-border-geographic-targeting-order",
        "dashboard_page": "",
        "dashboard_anchor": "",
    },
    {
        "date": "2026-03-30",
        "regulator": "FinCEN",
        "headline": "Whistleblower Incentives & Protections NPRM",
        "for_buyers": (
            "Awards of 10–30% of collected sanctions create a strong financial incentive for current "
            "and former employees to report — particularly at firms with active SAR backlogs or "
            "sanctions-screening tuning gaps. Compliance teams should review their internal reporting "
            "channel KPIs and ensure escalation paths to the Board's audit committee are documented "
            "in the audit ledger. Comments due 2026-06-01."
        ),
        "source_url": "https://www.federalregister.gov/documents/2026/04/01/2026-06271/whistleblower-incentives-and-protections",
        "dashboard_page": "Audit & Evidence",
        "dashboard_anchor": "7_Audit_Evidence",
    },
    {
        "date": "2026-04-07",
        "regulator": "FinCEN + OCC + FDIC + NCUA",
        "headline": "AML/CFT Program NPRM — the 'Effectiveness Rule'",
        "for_buyers": (
            "A documented enterprise-wide AML/CFT risk assessment becomes a pillar (not just expected "
            "practice), and FinCEN national priorities must be incorporated into the program. "
            "'Effectiveness' is split into (1) program established and (2) program maintained, "
            "distinguishing technical from systemic failure. Comments due 2026-06-09; 12-month "
            "implementation period after a final rule. Expected final rule late 2026 / early 2027."
        ),
        "source_url": "https://www.federalregister.gov/documents/2026/04/10/2026-07033/anti-money-laundering-and-countering-the-financing-of-terrorism-programs",
        "dashboard_page": "Framework Alignment",
        "dashboard_anchor": "8_Framework_Alignment",
    },
    # ── EU AMLA — Single rulebook in motion ──
    {
        "date": "2026-02-09",
        "regulator": "AMLA",
        "headline": "Three draft RTS consultations open: CDD, occasional/linked transactions, pecuniary sanctions",
        "for_buyers": (
            "The CDD RTS sets EU-wide minimum data points and verification methods that will replace "
            "each member-state's local list — non-EU firms with EU subsidiaries must align before AMLR "
            "application date 2027-07-10. The pecuniary-sanctions RTS will determine how breaches are "
            "scored across member states. AMLA must submit final drafts to the Commission by 2026-07-10."
        ),
        "source_url": "https://www.amla.europa.eu/policy/public-consultations/consultation-draft-rts-customer-due-diligence_en",
        "dashboard_page": "Framework Alignment",
        "dashboard_anchor": "8_Framework_Alignment",
    },
    {
        "date": "2026-03",
        "regulator": "AMLA",
        "headline": "Data-collection exercise begins for direct-supervision selection methodology",
        "for_buyers": (
            "Cross-border financial groups operating in 6+ member states should treat the data submission "
            "as the input that determines whether they are selected for direct AMLA supervision starting "
            "January 2028 — incomplete or inconsistent data raises selection-risk."
        ),
        "source_url": "https://www.amla.europa.eu/amla-advances-preparations-2027-selection-exercise_en",
        "dashboard_page": "Framework Alignment",
        "dashboard_anchor": "8_Framework_Alignment",
    },
    {
        "date": "2026-02",
        "regulator": "AMLA",
        "headline": "Final report on RTS for risk-profile assessment and selection methodology",
        "for_buyers": (
            "The risk-profile RTS standardizes how supervisors compute inherent and residual risk for "
            "each obliged entity. MLROs should ensure their own risk-rating taxonomy can be expressed "
            "in the AMLA-defined categories or expect noise in dual reporting."
        ),
        "source_url": "https://www.amla.europa.eu/policy/regulatory-instruments_en",
        "dashboard_page": "Risk Assessment",
        "dashboard_anchor": "6_Risk_Assessment",
    },
    # ── FATF — Plenary outcomes ──
    {
        "date": "2026-02-13",
        "regulator": "FATF",
        "headline": "Plenary outcomes — Mexico City, 11–13 Feb",
        "for_buyers": (
            "Kuwait and Papua New Guinea added to the grey list. MLROs at firms with KW or PG exposure "
            "must apply EDD to natural- and legal-person customers from those jurisdictions, and update "
            "screening lists and country-risk scoring tables now. AT/IT/SG assessment-round reports "
            "scheduled for April–May 2026 publication."
        ),
        "source_url": "https://www.fatf-gafi.org/en/publications/Fatfgeneral/outcomes-FATF-plenary-february-2026.html",
        "dashboard_page": "Risk Assessment",
        "dashboard_anchor": "6_Risk_Assessment",
    },
    {
        "date": "2026-02-13",
        "regulator": "FATF",
        "headline": "Giles Thomson (UK) appointed as next FATF President",
        "for_buyers": (
            "A UK-sanctions-led presidency signals continued FATF emphasis on sanctions-evasion typologies, "
            "beneficial ownership, and Russia-related illicit-finance work. UK firms should expect tighter "
            "operational alignment between OFSI guidance and FATF outputs over the two-year term beginning "
            "2026-07-01."
        ),
        "source_url": "https://www.fatf-gafi.org/en/publications/Fatfgeneral/outcomes-FATF-plenary-february-2026.html",
        "dashboard_page": "",
        "dashboard_anchor": "",
    },
    # ── UK FCA — Annex 1 supervision and final notices ──
    {
        "date": "2026-02-23",
        "regulator": "FCA",
        "headline": "Final Notice issued to Stallion Money Limited",
        "for_buyers": (
            "One of several enforcement endpoints the FCA has produced for small payment/MSB-style "
            "firms during the window. Cancellation pattern reinforces FCA willingness to remove "
            "permission rather than fine when control failings persist at small Annex 1-adjacent firms."
        ),
        "source_url": "https://www.fca.org.uk/publication/final-notices/stallion-money-limited-2026.pdf",
        "dashboard_page": "",
        "dashboard_anchor": "",
    },
    {
        "date": "2026-03-09",
        "regulator": "FCA",
        "headline": "Final Notice cancelling Taj Exchange Ltd registration",
        "for_buyers": (
            "Confirms the FCA's pattern of using registration cancellation as a primary AML tool against "
            "small MSBs and currency exchanges, ahead of fines. Firms relying on similar registration "
            "permissions should pre-emptively confirm their MLR-2017 registration data is current."
        ),
        "source_url": "https://www.fca.org.uk/publication/decision-notices/taj-exchange-ltd-2026.pdf",
        "dashboard_page": "",
        "dashboard_anchor": "",
    },
    {
        "date": "2026-03-20",
        "regulator": "FCA",
        "headline": "Statement on financial-crime risks when dealing with Annex 1 firms",
        "for_buyers": (
            "MLROs at FCA-regulated banks must explicitly extend their EDD frameworks to Annex 1 "
            "counterparties — onboarding controls, periodic reviews, and trigger-event reviews need an "
            "'Annex 1 customer' tag. Expect supervisors to ask for evidence of post-March 2024 "
            "governance-control improvements at next inspection."
        ),
        "source_url": "https://www.fca.org.uk/news/statements/firms-must-do-proper-checks-when-dealing-unregulated-lenders",
        "dashboard_page": "Customer 360",
        "dashboard_anchor": "17_Customer_360",
    },
    {
        "date": "2026-04-01",
        "regulator": "FCA",
        "headline": "New Skilled Person Panel takes effect — 12 lots, 4-year term",
        "for_buyers": (
            "Section 166 reviews remain the FCA's primary AML enforcement-precursor tool (used in over "
            "half of recent enforcement matters). MLROs should maintain a 'ready-for-s.166' dossier — "
            "control inventory, BWRA, MI samples, training logs — because once a notice issues, the "
            "panel firm has a 4-week cold start and the firm pays."
        ),
        "source_url": "https://www.fca.org.uk/about/how-we-regulate/supervision/skilled-persons-reviews",
        "dashboard_page": "Audit & Evidence",
        "dashboard_anchor": "7_Audit_Evidence",
    },
    # ── Canada FINTRAC — AMP penalties ──
    {
        "date": "2026-02-05",
        "regulator": "FINTRAC",
        "headline": "AMP against Commerciale I.C. – Pacific Inc. ($224,235)",
        "for_buyers": (
            "Penalty appealed to Federal Court — appeals from the Tutus Money / 2024 cohort show a "
            "multi-year tail. MLROs at Canadian MSBs should treat 5-violation AMPs in the $200K range "
            "as the new floor for material PCMLTFA non-compliance."
        ),
        "source_url": "https://fintrac-canafe.canada.ca/new-neuf/nr/2026-02-05-eng",
        "dashboard_page": "",
        "dashboard_anchor": "",
    },
    {
        "date": "2026-02-05",
        "regulator": "FINTRAC",
        "headline": "AMP against TreasureMeta Corporation ($24,750)",
        "for_buyers": (
            "Single-violation AMPs in the $25K range typically reflect reporting-form or registration "
            "deficiencies. Useful baseline for benchmarking corrective-action expectations on small "
            "Canadian MSBs."
        ),
        "source_url": "https://fintrac-canafe.canada.ca/new-neuf/nr/2026-02-05-1-eng",
        "dashboard_page": "",
        "dashboard_anchor": "",
    },
    {
        "date": "2026-02-10",
        "regulator": "FINTRAC",
        "headline": "AMP against Century 21 Heritage Group Ltd. ($148,912.50)",
        "for_buyers": (
            "Real-estate sector continues to draw AMPs on a single high-impact violation type "
            "(typically receipt-of-funds records or record-keeping). Compliance teams covering real-"
            "estate originators should verify receipt-of-funds and unrepresented-party records meet "
            "PCMLTFA evidentiary standards."
        ),
        "source_url": "https://fintrac-canafe.canada.ca/pen/4-eng",
        "dashboard_page": "",
        "dashboard_anchor": "",
    },
    {
        "date": "2026-02-12",
        "regulator": "FINTRAC",
        "headline": "AMP against Manor Windsor Realty Ltd. ($107,250)",
        "for_buyers": (
            "Second real-estate AMP in the same week reinforces the sectoral focus. FINTRAC is now "
            "scoring on completeness of records, not just submission."
        ),
        "source_url": "https://fintrac-canafe.canada.ca/pen/4-eng",
        "dashboard_page": "",
        "dashboard_anchor": "",
    },
    {
        "date": "2026-03-26",
        "regulator": "FINTRAC",
        "headline": "AMP against Northern Isga Foundation ($91,162.50)",
        "for_buyers": (
            "First non-MSB / non-real-estate AMP of the window. Underlines FINTRAC's expanded "
            "enforcement posture across reporting-entity types. Charity-adjacent and foundation-"
            "structure customers should be re-tested against PCMLTFA reporting-trigger logic."
        ),
        "source_url": "https://fintrac-canafe.canada.ca/pen/4-eng",
        "dashboard_page": "",
        "dashboard_anchor": "",
    },
    # ── OFAC — Sanctions designations ──
    {
        "date": "2026-04-15",
        "regulator": "OFAC",
        "headline": "Major Iran/Hizballah designation under 'Economic Fury'",
        "for_buyers": (
            "Sanctions and trade-finance teams must immediately ingest the new SDN entries and re-screen "
            "letters of credit, vessel-tracking, bunker payments, and gold-trade counterparties. Ownership-"
            "chain dragnet (≥50% rule) should be re-run against any joint-stock counterparty in petrochemical "
            "or precious-metals trade. Secondary-sanctions exposure is real."
        ),
        "source_url": "https://home.treasury.gov/news/press-releases/sb0492",
        "dashboard_page": "Sanctions Screening",
        "dashboard_anchor": "12_Sanctions_Screening",
    },
    {
        "date": "2026-04-23",
        "regulator": "OFAC",
        "headline": "Iran EO 13902 designations — 19 entities and 19 vessels",
        "for_buyers": (
            "Trade-finance and shipping-finance teams must update vessel sanctions screening (IMO numbers, "
            "prior names) and re-run letters of credit, charter-party agreements, and P&I cover decisions. "
            "Multi-jurisdictional flag-of-convenience patterns are clearly the OFAC focus."
        ),
        "source_url": "https://www.federalregister.gov/documents/2026/04/23/2026-07897/notice-of-ofac-sanctions-actions",
        "dashboard_page": "Sanctions Screening",
        "dashboard_anchor": "12_Sanctions_Screening",
    },
    # ── EU Council — Sanctions packages ──
    {
        "date": "2026-03-16",
        "regulator": "EU Council",
        "headline": "Iran human-rights sanctions — 16 persons + 3 entities",
        "for_buyers": (
            "EU-regulated firms must immediately freeze any funds and economic resources belonging to "
            "the new listings and treat them as full-blockable persons. Total under EU Iran human-rights "
            "regime is now 263 individuals and 53 entities — sanctions screening teams should validate "
            "EU consolidated list refresh within 24 hours of publication."
        ),
        "source_url": "https://www.consilium.europa.eu/en/press/press-releases/2026/03/16/iran-council-sanctions-an-additional-16-persons-and-three-entities-over-serious-human-rights-violations/",
        "dashboard_page": "Sanctions Screening",
        "dashboard_anchor": "12_Sanctions_Screening",
    },
    {
        "date": "2026-04-23",
        "regulator": "EU Council",
        "headline": "20th sanctions package against Russia — including crypto-sector ban",
        "for_buyers": (
            "The crypto-sector ban materially extends EU sanctions reach into stablecoin and CBDC-adjacent "
            "payment rails — EU-regulated CASPs must now block any onboarding or service relationship with "
            "Russian-CASP counterparties and review historical correspondent or VASP-to-VASP exposure. Banks "
            "already under correspondent-banking pressure on Russia must extend the screening to four newly-"
            "listed banks in Kyrgyzstan, Laos, and Azerbaijan."
        ),
        "source_url": "https://www.consilium.europa.eu/en/press/press-releases/2026/04/23/russia-s-war-of-aggression-against-ukraine-20th-round-of-stern-eu-sanctions-hits-energy-military-industrial-complex-trade-and-financial-services-including-crypto/",
        "dashboard_page": "Sanctions Screening",
        "dashboard_anchor": "12_Sanctions_Screening",
    },
    {
        "date": "2026-04-23",
        "regulator": "EU Council",
        "headline": "Belarus listings under Decision 2026/503",
        "for_buyers": (
            "Sanctions teams must update Belarus-specific screening lists alongside the Russia package — "
            "the two regimes operate as a coordinated unit but use distinct legal bases, and AML teams "
            "sometimes miss the Belarus delta. Trade-finance for dual-use machinery and metals to "
            "Belarusian end-users requires renewed end-user attestations."
        ),
        "source_url": "https://www.consilium.europa.eu/en/press/press-releases/2026/04/23/russia-s-war-of-aggression-against-ukraine-20th-round-of-stern-eu-sanctions-hits-energy-military-industrial-complex-trade-and-financial-services-including-crypto/",
        "dashboard_page": "Sanctions Screening",
        "dashboard_anchor": "12_Sanctions_Screening",
    },
    # ── Australia AUSTRAC — Tranche 2 implementation ──
    {
        "date": "2026",
        "regulator": "AUSTRAC",
        "headline": "Regulatory expectations 2025–26 — Tranche 2 enforceable from 2026-07-01",
        "for_buyers": (
            "Australian DNFBPs (lawyers, accountants, real-estate agents, dealers in precious metals) "
            "need to be enrolled and have a documented AML/CTF program, board-approved, before "
            "2026-07-01. Enforceable undertakings remain AUSTRAC's primary tool: firms should expect "
            "EUs rather than fines for first-cycle non-compliance."
        ),
        "source_url": "https://www.austrac.gov.au/amlctf-reform/austrac-regulatory-expectations-and-priorities-2025-26",
        "dashboard_page": "Framework Alignment",
        "dashboard_anchor": "8_Framework_Alignment",
    },
    # ── NY DFS — Industry letters ──
    {
        "date": "2026-04-22",
        "regulator": "NY DFS",
        "headline": "Industry letter on fair-lending obligations under Exec. Law 296-a",
        "for_buyers": (
            "While not strictly AML, this letter signals DFS's intent to police credit-decisioning models — "
            "and in 2026 those models increasingly share infrastructure with AML risk-rating engines. "
            "Firms running unified customer-risk-scoring platforms should ensure model-fairness testing "
            "is documented in the same Compliance Manifest the AML team uses."
        ),
        "source_url": "https://www.dfs.ny.gov/industry_guidance/industry_letters/il20260422_fair_lending",
        "dashboard_page": "Model Performance",
        "dashboard_anchor": "13_Model_Performance",
    },
]


THEMES: list[dict[str, str]] = [
    {
        "title": "Enforcement softens, rulemaking accelerates",
        "body": (
            "New BSA/AML cease-and-desist orders are absent from OCC's Feb–Mar releases; the FinCEN/OCC/"
            "FDIC/NCUA joint Effectiveness NPRM, the SR 26-2 model-risk rewrite, and the reputation-risk "
            "final rule represent the largest US AML-program reset since AMLA 2020."
        ),
    },
    {
        "title": "Models are now first-class compliance citizens",
        "body": (
            "SR 26-2 collapsed the BSA/AML-specific model-risk regime (SR 21-8) into the general MRM "
            "framework. Examiners will expect a model inventory that treats TM, sanctions screening, "
            "name-matching, and CDD scoring identically to credit and market models."
        ),
    },
    {
        "title": "Sanctions reach deeper into crypto and correspondent banking",
        "body": (
            "OFAC's Iran 'Economic Fury' actions and the EU's 20th-package crypto-sector ban represent "
            "a structural shift: CASP-level transaction prohibitions, RUBx and CBDC bans, and Section 311 "
            "against MBaer all extend sanctions into the rails AML programs depend on."
        ),
    },
    {
        "title": "EU AMLA shifts from talking to building",
        "body": (
            "Three RTS consultations, two final reports, and the data-collection-for-selection exercise "
            "all happened inside ten weeks. By 2026-07-10, AMLA must submit final RTS to the Commission."
        ),
    },
]
