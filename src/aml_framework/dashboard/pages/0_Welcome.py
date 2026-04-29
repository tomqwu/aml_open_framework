"""Welcome — first-screen orientation for non-technical leaders.

Process problem this addresses
------------------------------
Recent feedback: "the app is not very intuitive — what problem is being
solved and how isn't clear, and a lot of leaders don't even know what
YAML is." A CCO/MLRO who lands on the dashboard cold should understand
**what this solves** and **where to go next** within 30 seconds, without
encountering YAML/spec/hash/Pydantic. This page is that 30 seconds.

Three sections, all in plain English (no jargon):

1. "What problem does this solve?" — three short paragraphs drawing
   one PAIN-N each from docs/research/2026-04-aml-process-pain.md
2. "How does it work, in 30 seconds?" — three cards: Detect, Investigate,
   Prove. One sentence each.
3. "Where should I go next?" — persona-aware buttons that route the
   leader to their first relevant page (Audit & Evidence for Auditor;
   Investigations for MLRO; Executive Dashboard for CCO).

Operators who want today's morning status (KPIs, queue depth, alerts)
land on Executive Dashboard (page 1) — this page is orientation, not
operations.
"""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.audience import persona_description
from aml_framework.dashboard.components import glossary_legend, page_header

PAGE_TITLE = "Welcome"

page_header(
    title="What this is, and what to do next",
    description=(
        "An anti-money-laundering program you can show to your regulator "
        "without a six-week reconstruction."
    ),
)

# ---------------------------------------------------------------------------
# Section 1 — What problem does this solve?
# ---------------------------------------------------------------------------

st.markdown("### What problem does this solve?")

c1, c2, c3 = st.columns(3, gap="large")

with c1:
    st.markdown(
        """
        **You can't prove what you did.**

        Decisions get made every day — alerts triaged, customers exited,
        thresholds tuned. When the regulator asks *"show us the working,"*
        the trail is a Word doc and three people's memory.

        *(See [PAIN-1 →](https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-aml-process-pain.md#pain-1--we-cant-prove-what-we-did))*
        """
    )

with c2:
    st.markdown(
        """
        **The backlog is red on the board.**

        Alerts pile up faster than analysts can clear them. The dashboards
        show it. The board approves the program anyway. Then a regulator
        notices, and what was a slide becomes a consent order.

        *(See [PAIN-2 →](https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-aml-process-pain.md#pain-2--the-backlog-is-red--and-the-board-has-known-for-years))*
        """
    )

with c3:
    st.markdown(
        """
        **Two teams, one customer, no shared view.**

        The fraud team and the AML team open separate cases on the same
        person. Neither sees the other's evidence. The customer gets two
        contradictory letters; the regulator finds the gap.

        *(See [PAIN-9 →](https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-aml-process-pain.md#pain-9--1lod-and-2lod-dont-know-whose-risk-it-is))*
        """
    )

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 2 — How does it work, in 30 seconds?
# ---------------------------------------------------------------------------

st.markdown("### How does it work, in 30 seconds?")

d1, d2, d3 = st.columns(3, gap="large")

with d1:
    st.markdown(
        """
        #### 1. Detect
        Detectors written in plain language — readable by 1LoD,
        2LoD, and the regulator. Every detector cites the regulation
        clause that justifies it.
        """
    )

with d2:
    st.markdown(
        """
        #### 2. Investigate
        Each alert opens with the transactions, KYC, sanctions hits,
        network neighbours, and prior STRs already attached. Analyst
        writes the narrative, not the bundle.
        """
    )

with d3:
    st.markdown(
        """
        #### 3. Prove
        Every decision is sealed in a tamper-evident audit trail.
        Replay any historical run; the regulator pack is one click —
        and you can prove what happened, byte-for-byte.
        """
    )

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 3 — Where should I go next?
# ---------------------------------------------------------------------------

st.markdown("### Where should I go next?")

selected = st.session_state.get("selected_audience")
if selected:
    st.caption(f"Showing the path tailored to: **{persona_description(selected)}**")
else:
    st.caption(
        "Pick your role from the **I am a…** dropdown in the sidebar to "
        "filter the rest of the dashboard to the pages most relevant to you."
    )

# Per-persona "first page to open" recommendations. Each is the page
# where the persona finds the answer to their most-felt pain in the
# fewest clicks.
NEXT_BY_PERSONA: dict[str, list[tuple[str, str, str]]] = {
    "cco": [
        (
            "Executive Dashboard",
            "Program-level health and the headline picture.",
            "1_Executive_Dashboard",
        ),
        (
            "Audit & Evidence",
            "What you'd hand a regulator if they walked in tomorrow.",
            "7_Audit_Evidence",
        ),
        (
            "Framework Alignment",
            "How this program maps to your regulator's expectations.",
            "8_Framework_Alignment",
        ),
    ],
    "vp": [
        ("Rule Performance", "Is each detector still earning its keep?", "5_Rule_Performance"),
        (
            "Comparative Analytics",
            "Compare runs side-by-side after a tuning change.",
            "19_Comparative_Analytics",
        ),
        (
            "Framework Alignment",
            "Citation and coverage map for your jurisdiction.",
            "8_Framework_Alignment",
        ),
    ],
    "director": [
        (
            "Investigations",
            "Active investigations across teams, ranked by SLA urgency.",
            "24_Investigations",
        ),
        ("Alert Queue", "Triage queue with live SLA.", "3_Alert_Queue"),
        ("Audit & Evidence", "Examination ZIP; one click to download.", "7_Audit_Evidence"),
    ],
    "manager": [
        ("Alert Queue", "What needs analyst attention now.", "3_Alert_Queue"),
        ("Investigations", "How investigations are tracking against SLA.", "24_Investigations"),
        ("Tuning Lab", "Test threshold changes before they go live.", "23_Tuning_Lab"),
    ],
    "analyst": [
        ("My Queue", "Your assigned cases, by priority.", "21_My_Queue"),
        ("Alert Queue", "Open alerts pre-attached with evidence.", "3_Alert_Queue"),
        (
            "Network Explorer",
            "Counterparty graph for the customer you're working.",
            "10_Network_Explorer",
        ),
    ],
    "auditor": [
        ("Audit & Evidence", "Replay any run; verify the chain.", "7_Audit_Evidence"),
        ("Investigations", "Drill into specific cases the run produced.", "24_Investigations"),
        ("Run History", "Every historical run, queryable.", "15_Run_History"),
    ],
    "developer": [
        ("Spec Editor", "Author and validate detectors.", "20_Spec_Editor"),
        ("Tuning Lab", "Sweep thresholds; see precision/recall.", "23_Tuning_Lab"),
        ("Run History", "Inspect any run's outputs.", "15_Run_History"),
    ],
    "pm": [
        ("Program Maturity", "Coverage gaps and where to invest next.", "2_Program_Maturity"),
        ("Transformation Roadmap", "Sequenced plan and dependencies.", "9_Transformation_Roadmap"),
        (
            "Comparative Analytics",
            "Quantify the impact of a planned change.",
            "19_Comparative_Analytics",
        ),
    ],
    "svp": [
        ("Executive Dashboard", "Headline picture for the board.", "1_Executive_Dashboard"),
        ("Program Maturity", "Where the program is on the maturity curve.", "2_Program_Maturity"),
        ("Transformation Roadmap", "Where the program is going.", "9_Transformation_Roadmap"),
    ],
    "cto": [
        ("Executive Dashboard", "Headline platform health.", "1_Executive_Dashboard"),
        (
            "Model Performance",
            "How detectors are performing in production.",
            "13_Model_Performance",
        ),
        ("Run History", "Replay any historical run; bytes match the original.", "15_Run_History"),
    ],
    "business": [
        (
            "Executive Dashboard",
            "The headline picture, no operational detail.",
            "1_Executive_Dashboard",
        ),
        ("Risk Assessment", "Where exposure concentrates.", "6_Risk_Assessment"),
    ],
}

# Default fallback when no persona is selected — show the three doors a
# typical first-time visitor most often opens.
DEFAULT_NEXT: list[tuple[str, str, str]] = [
    (
        "Executive Dashboard",
        "Program-level health and the headline picture.",
        "1_Executive_Dashboard",
    ),
    (
        "Audit & Evidence",
        "What you'd hand a regulator if they walked in tomorrow.",
        "7_Audit_Evidence",
    ),
    (
        "Investigations",
        "Active investigations across teams, ranked by SLA urgency.",
        "24_Investigations",
    ),
]

next_options = NEXT_BY_PERSONA.get(selected, DEFAULT_NEXT) if selected else DEFAULT_NEXT

cols = st.columns(len(next_options), gap="medium")
for col, (page_label, page_desc, _page_slug) in zip(cols, next_options):
    with col:
        st.markdown(f"**{page_label}**")
        st.caption(page_desc)
        # Streamlit's multi-page nav doesn't expose programmatic jumps
        # cleanly across all versions — point the leader at the sidebar
        # so they can navigate without the page reloading on click.
        st.caption("→ Open from the sidebar.")

st.markdown("---")
st.caption(
    "**Want the 5-minute pitch instead?** Open the [interactive deck]"
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/pitch/deck/index.html) "
    "— 27 slides walking the framework end-to-end. "
    "**Want the 10 daily pain points behind every page on this dashboard?** "
    "Read the [process-pain research doc]"
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-aml-process-pain.md)."
)

# Acronyms used on this page — expanded in plain English so a leader who
# doesn't know all of them sees a definition without leaving the screen.
st.markdown(
    glossary_legend(["1LoD", "2LoD", "KYC", "STR", "SLA"]),
    unsafe_allow_html=True,
)
