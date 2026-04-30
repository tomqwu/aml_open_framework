"""FinTech Cockpit — 1-MLRO operating surface.

The FinTech / EMI / VASP MLRO is the persona the landing page calls
"★ Primary platform" since 2026-04-29 (PR #136). She runs a 1-person
AML program. Her operative regulator on most days is **the sponsor
bank's risk officer**, who can issue a 30/60/90-day cure-notice that
is faster than any government-supervisor enforcement path.

This page is what she opens first.

Three sections:

1. **Cure-notice timer** — date-of-receipt input, computes 30/60/90-day
   deadlines, traffic-light status. The post-Synapse / Evolve cascade
   of 2024 sponsor-bank consent orders made this the default fintech
   AML emergency.

2. **8 FinTech realities** — the 8 FINTECH-N entries from
   `docs/research/2026-04-fintech-aml-reality.md` rendered as cards,
   each with the primary regulator source + the dashboard page that
   addresses it.

3. **Cure-notice evidence pack** — single-button download that bundles
   detector inventory + alert volumes + case dispositions + audit-trail
   integrity + sanctions evidence into one ZIP. The pack the sponsor
   bank's risk officer actually asks for.

Source for the realities: docs/research/2026-04-fintech-aml-reality.md
(8 FINTECH-N entries, primary-source regulator citations on every one).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from aml_framework.dashboard.components import (
    glossary_legend,
    kpi_card_rag,
    page_header,
    tooltip_banner,
    tour_panel,
)

page_header(
    "FinTech Cockpit",
    "1-MLRO operating surface. Sponsor-bank cure-notice timer · 8 FinTech realities · evidence pack on one button.",
)

tour_panel("FinTech Cockpit")
tooltip_banner(
    "FinTech Cockpit",
    "The post-Synapse / Evolve sponsor-bank cascade of 2024 made cure "
    "notices the default fintech AML emergency. This page tracks the "
    "deadline and produces the evidence pack the sponsor bank actually "
    "asks for.",
)

result = st.session_state.result
spec = st.session_state.spec
manifest = result.manifest
df_decisions = st.session_state.df_decisions

# ---------------------------------------------------------------------------
# Section 1 — Cure-notice timer
# ---------------------------------------------------------------------------
# Sponsor banks issue cure notices with 30 / 60 / 90-day windows after
# receiving their own consent order from the Federal Reserve / OCC /
# FDIC. The MLRO needs an evidence pack inside the window or the
# relationship flips to wind-down. The Evolve consent order (Fed,
# 14 June 2024) is the canonical reference — it required a written plan
# within 90 days plus an independent third-party review.

st.markdown("### Sponsor-bank cure-notice timer")
st.caption(
    "Date of receipt → countdown to 30 / 60 / 90-day deadlines. "
    "Standard windows from 2024 BaaS consent-order cascade — Federal "
    "Reserve Evolve order (14 Jun 2024), OCC Blue Ridge (24 Jan 2024), "
    "FDIC Piermont (27 Feb 2024)."
)

col_a, col_b = st.columns([1, 2])
with col_a:
    receipt_date = st.date_input(
        "Cure-notice received on",
        value=date.today(),
        max_value=date.today(),
        help="The day the sponsor bank's risk officer's email arrived.",
    )
    sla_days = st.selectbox(
        "Cure window",
        options=[30, 60, 90],
        index=2,
        help="30 / 60 / 90 days — Evolve consent order set the 90-day reference.",
    )
with col_b:
    deadline = receipt_date + timedelta(days=sla_days)
    days_remaining = (deadline - date.today()).days

    if days_remaining < 0:
        rag = "red"
        label_text = f"Window closed {abs(days_remaining)} days ago"
        urgency = "OVERDUE"
    elif days_remaining <= 14:
        rag = "red"
        label_text = f"{days_remaining} days remaining"
        urgency = "RED"
    elif days_remaining <= 30:
        rag = "amber"
        label_text = f"{days_remaining} days remaining"
        urgency = "AMBER"
    else:
        rag = "green"
        label_text = f"{days_remaining} days remaining"
        urgency = "GREEN"

    timer_col1, timer_col2, timer_col3 = st.columns(3)
    with timer_col1:
        kpi_card_rag("Receipt date", str(receipt_date))
    with timer_col2:
        kpi_card_rag("Cure-window deadline", str(deadline), rag=rag)
    with timer_col3:
        kpi_card_rag(label_text, urgency, rag=rag)

st.caption(
    "Sources: [Federal Reserve Evolve consent order, 14 Jun 2024]"
    "(https://www.federalreserve.gov/newsevents/pressreleases/files/enf20240614a1.pdf) · "
    "[Banking Dive — running list of BaaS consent orders 2024]"
    "(https://www.bankingdive.com/news/a-running-list-of-baas-banks-hit-with-consent-orders-in-2024/729121/) · "
    "[FINTECH-1 in research]"
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-fintech-aml-reality.md)"
)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 2 — 8 FinTech realities
# ---------------------------------------------------------------------------
# Each entry is a primary-source-anchored reality from
# docs/research/2026-04-fintech-aml-reality.md. Cards link to the
# dashboard page that addresses the reality, so the MLRO can move from
# "what's the pain" to "what do I do about it" in one click.

st.markdown("### 8 realities a fintech MLRO lives with")
st.caption(
    "Each anchored in a 2024-26 regulator-issued enforcement order or "
    "named consent order. Card → dashboard page that addresses it."
)

REALITIES: list[dict[str, str]] = [
    {
        "num": "01",
        "title": "Sponsor-bank's cure notice is now the operative regulator",
        "summary": "30/60/90-day windows. No appeal. Evidence-speed > detection sophistication.",
        "source": "FRB Evolve consent order · 14 Jun 2024",
        "source_url": "https://www.federalreserve.gov/newsevents/pressreleases/files/enf20240614a1.pdf",
        "addresses": "Audit & Evidence",
        "addresses_help": "Evidence pack on one CLI / one button.",
    },
    {
        "num": "02",
        "title": "Fast growth is what the sponsor and regulator both find first",
        "summary": "Growth outpaces controls. Sanctions screening covers a fraction of the list.",
        "source": "FCA Final Notice · Starling Bank £29M · 27 Sep 2024",
        "source_url": "https://www.fca.org.uk/publication/final-notices/starling-bank-limited-2024.pdf",
        "addresses": "Tuning Lab",
        "addresses_help": "Threshold sweeps + precision/recall before promotion.",
    },
    {
        "num": "03",
        "title": "The Annex 1 questionnaire is supervisory, not advisory",
        "summary": "BWRA must be evidenced — not just held. 18-month-old binder doesn't count.",
        "source": "FCA Dear-CEO letter · 5 Mar 2024",
        "source_url": "https://www.fca.org.uk/publication/correspondence/dear-ceo-letter-action-response-common-control-failings-anti-money-laundering-frameworks.pdf",
        "addresses": "Framework Alignment",
        "addresses_help": "Live BWRA rendered from the Manifest.",
    },
    {
        "num": "04",
        "title": "VASP enforcement is now bespoke, not boilerplate",
        "summary": "KYC + alert + sanctions + PEP + SAR cited as one connected failure pattern.",
        "source": "NY DFS Coinbase · $100M · 4 Jan 2023",
        "source_url": "https://www.dfs.ny.gov/system/files/documents/2023/01/ea20230104_coinbase.pdf",
        "addresses": "Investigations",
        "addresses_help": "INV-grouping stitches alert → KYC → SAR.",
    },
    {
        "num": "05",
        "title": "Travel Rule is 99 jurisdictions, four protocols, one MLRO",
        "summary": "FATF R.16 update Jun 2025 · USD/EUR 1,000 threshold · multi-protocol bridging.",
        "source": "FATF R.16 update · Jun 2025",
        "source_url": "https://www.fatf-gafi.org/en/publications/Fatfrecommendations/update-Recommendation-16-payment-transparency-june-2025.html",
        "addresses": "Spec Editor",
        "addresses_help": "ISO 20022 + Travel Rule field validator declared in Manifest.",
    },
    {
        "num": "06",
        "title": "AMLR's 10 July 2027 clock is the largest unfunded mandate in EU fintech",
        "summary": "AMLR 2024/1624 applies directly · no national transposition · 14-month runway.",
        "source": "EU Regulation 2024/1624 · published 19 Jun 2024",
        "source_url": "https://eur-lex.europa.eu/eli/reg/2024/1624/oj/eng",
        "addresses": "Framework Alignment",
        "addresses_help": "Multi-jurisdiction templates · AMLR-ready evidence.",
    },
    {
        "num": "07",
        "title": "49 state regulators, one MSB, one BSA program",
        "summary": "FinCEN once · CSBS MTMA in 31 states · multi-headed examiner.",
        "source": "CSBS Block / Cash App · $80M · 15 Jan 2025",
        "source_url": "https://www.csbs.org/newsroom/state-regulators-issue-80-million-penalty-block-inc-cash-app-bsaaml-violations",
        "addresses": "Audit & Evidence",
        "addresses_help": "Jurisdiction-tagged audit packs from one Manifest.",
    },
    {
        "num": "08",
        "title": "Series-B+ AML diligence is the unfunded compliance mandate",
        "summary": "Investor diligence questionnaire reads like an FCA Annex 1 letter. 47 questions, 5-day deadline.",
        "source": "Chime S-1 (2025) · LexisNexis True Cost · Feb 2024",
        "source_url": "https://risk.lexisnexis.com/about-us/press-room/press-release/20240221-true-cost-of-compliance-us-ca",
        "addresses": "Run History",
        "addresses_help": "Every change to every rule, with rationale and timestamp.",
    },
]

# Render in 2-column grid (4 rows of 2)
for i in range(0, len(REALITIES), 2):
    pair = REALITIES[i : i + 2]
    cols = st.columns(2)
    for col, item in zip(cols, pair, strict=False):
        with col:
            with st.container(border=True):
                st.markdown(
                    f"**FINTECH-{item['num']}** · _{item['source']}_",
                    help=item["source_url"],
                )
                st.markdown(f"#### {item['title']}")
                st.caption(item["summary"])
                st.markdown(f"→ Addresses: **{item['addresses']}** · _{item['addresses_help']}_")
                st.markdown(
                    f"[Primary source ↗]({item['source_url']})  ·  "
                    f"[FINTECH-{item['num']} in research ↗]"
                    "(https://github.com/tomqwu/aml_open_framework/blob/main/"
                    "docs/research/2026-04-fintech-aml-reality.md"
                    f"#fintech-{item['num'].lstrip('0') or '0'}--)"
                )

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 3 — Cure-notice evidence pack
# ---------------------------------------------------------------------------
# Reuses the existing build_audit_pack generator (Round-7 PR #78). The
# substance is identical to what FINTRAC examiners ask for — rule
# inventory + alert volumes + case dispositions + audit-trail integrity
# + sanctions evidence — which is also what a sponsor-bank risk officer
# under a Federal Reserve / OCC / FDIC consent order asks for. Section
# maps differ; the MVP ships with the FINTRAC section maps and a clear
# label noting future jurisdictions are one config away.

st.markdown("### Cure-notice evidence pack")
st.caption(
    "One-CLI / one-button bundle: detector inventory + alert volumes + "
    "case dispositions + audit-trail integrity + sanctions evidence + "
    "manifest with file-by-file SHA-256. Same shape as FINTRAC pre-exam "
    "pack (Round-7 PR #78) — sponsor-bank flavour shipping with FINTRAC "
    "section maps as the v1 reference template."
)

try:
    from aml_framework.generators.audit_pack import build_audit_pack

    _run_dir = Path(st.session_state.run_dir)

    _cases: list[dict] = []
    _cases_dir = _run_dir / "cases"
    if _cases_dir.exists():
        for _f in sorted(_cases_dir.glob("*.json")):
            _cases.append(json.loads(_f.read_text(encoding="utf-8")))

    _decisions: list[dict] = []
    _dec_path = _run_dir / "decisions.jsonl"
    if _dec_path.exists():
        for _line in _dec_path.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line:
                _decisions.append(json.loads(_line))

    _pack_bytes = build_audit_pack(
        spec,
        _cases,
        _decisions,
        jurisdiction="CA-FINTRAC",  # MVP — see note above
    )

    _kpi_a, _kpi_b, _kpi_c = st.columns(3)
    with _kpi_a:
        kpi_card_rag("Detectors in inventory", len(spec.rules))
    with _kpi_b:
        kpi_card_rag("Cases captured", len(_cases))
    with _kpi_c:
        kpi_card_rag("Decisions logged", len(_decisions))

    st.download_button(
        "📥 Cure-notice evidence pack (ZIP)",
        data=_pack_bytes,
        file_name=f"{spec.program.name.replace(' ', '_')}_cure_notice_evidence.zip",
        mime="application/zip",
        type="primary",
        help="Same substance as the FINTRAC pre-exam pack — what a "
        "sponsor-bank risk officer asks for, on one button. CLI: "
        "`aml audit-pack <spec> --jurisdiction CA-FINTRAC`.",
    )
except Exception as _e:  # noqa: BLE001
    st.caption(f"Evidence pack unavailable: {_e}")

# ---------------------------------------------------------------------------
# See also — research links
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption(
    "**See also** · "
    "[FinTech AML reality — 8 realities, full research]"
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-fintech-aml-reality.md)"
    " · [Regulator pulse — what's moved in the last 90 days]"
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-regulator-pulse.md)"
    " · [Competitive positioning — buyer-archetype matrix]"
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-competitive-positioning.md)"
)

st.markdown(
    glossary_legend(["MLRO", "STR", "SAR", "SLA", "MRM", "FCA", "BSA"]),
    unsafe_allow_html=True,
)
