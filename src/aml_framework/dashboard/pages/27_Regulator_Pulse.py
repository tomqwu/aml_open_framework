"""Regulator Pulse — what's moved in the last 90 days.

The 30-event regulator-pulse research (`docs/research/2026-04-regulator-
pulse.md`) was invisible to the dashboard before this page. CCO / MLRO /
Auditor users would expect to see "what regulators just moved on that
affects this program," with each entry cross-linked to the dashboard
page that addresses it.

Source data: `dashboard/data/regulator_pulse.py` — hand-curated mirror
of the research doc. See module docstring for refresh cadence.

Layout:
- Hero: count + window + theme summary
- Filter row: regulator multi-select + sort toggle
- Event list: one expander per event with primary source + dashboard
  cross-link
- Themes section: 4 cross-cutting patterns from the research doc

This page deliberately doesn't try to replace the research doc — it's a
quick-scan operating view. The "Open in research doc" link routes the
deep reader to the full markdown on GitHub.
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

from aml_framework.dashboard.components import (
    glossary_legend,
    kpi_card_rag,
    page_header,
    tooltip_banner,
    tour_panel,
)
from aml_framework.dashboard.data.regulator_pulse import EVENTS, THEMES

page_header(
    "Regulator Pulse",
    "What's moved in the last 90 days. Every event cites the regulator's primary source — no industry briefings, no vendor analysis as the load-bearing citation.",
)

tour_panel("Regulator Pulse")
tooltip_banner(
    "Regulator Pulse",
    "30 AML / sanctions events between 2026-02-01 and today. Filter by "
    "regulator; click any entry for the source and the dashboard page "
    "that addresses it. Source data mirrors docs/research/2026-04-"
    "regulator-pulse.md — refreshed when the research doc is refreshed.",
)


def _parse_date(s: str) -> date:
    """Parse YYYY-MM-DD or YYYY-MM or YYYY into a sortable date.

    Month-precision events use day=15; year-precision events use day=15
    of the middle month. Used only for sorting; the original string is
    what gets displayed.
    """
    parts = s.split("-")
    if len(parts) == 3:
        return datetime.strptime(s, "%Y-%m-%d").date()
    if len(parts) == 2:
        return datetime.strptime(f"{s}-15", "%Y-%m-%d").date()
    return datetime.strptime(f"{s}-06-15", "%Y-%m-%d").date()


# ---------------------------------------------------------------------------
# KPI strip — count, window, regulator coverage
# ---------------------------------------------------------------------------
all_dates = [_parse_date(e["date"]) for e in EVENTS]
window_start = min(all_dates)
window_end = max(all_dates)
all_regulators = sorted({e["regulator"] for e in EVENTS})

c1, c2, c3 = st.columns(3)
with c1:
    kpi_card_rag("Events in window", len(EVENTS))
with c2:
    kpi_card_rag("Window", f"{window_start} → {window_end}")
with c3:
    kpi_card_rag("Regulators / bodies", len(all_regulators))

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Filter row
# ---------------------------------------------------------------------------
filter_col, sort_col = st.columns([3, 1])
with filter_col:
    selected_regulators = st.multiselect(
        "Filter by regulator",
        options=all_regulators,
        default=[],
        placeholder="All regulators (no filter applied)",
        help="Pick one or more regulators to narrow the timeline.",
    )
with sort_col:
    sort_order = st.radio(
        "Sort",
        options=["Newest first", "Oldest first"],
        index=0,
        horizontal=True,
    )

# Apply filter + sort
events_filtered = [
    e for e in EVENTS if not selected_regulators or e["regulator"] in selected_regulators
]
events_sorted = sorted(
    events_filtered,
    key=lambda e: _parse_date(e["date"]),
    reverse=(sort_order == "Newest first"),
)

st.caption(
    f"Showing **{len(events_sorted)}** of {len(EVENTS)} events"
    + (f" · regulator filter: {', '.join(selected_regulators)}" if selected_regulators else "")
)

# ---------------------------------------------------------------------------
# Event list
# ---------------------------------------------------------------------------
for event in events_sorted:
    expander_label = f"**{event['date']}** · {event['regulator']} — {event['headline']}"
    with st.expander(expander_label, expanded=False):
        st.markdown(f"**What changed for AML buyers**\n\n{event['for_buyers']}")
        st.markdown("")

        link_col1, link_col2 = st.columns(2)
        with link_col1:
            st.markdown(f"📄 [Primary source ↗]({event['source_url']})")
        with link_col2:
            if event["dashboard_anchor"]:
                # Streamlit doesn't expose page-key links cleanly without
                # st.page_link; fall back to a caption that names the page
                # the user can open from the sidebar.
                st.markdown(
                    f"🎯 **In this dashboard:** {event['dashboard_page']} "
                    f"— open from the sidebar to act on this event."
                )
            else:
                st.caption("_No direct dashboard equivalent — informational only._")

st.markdown("---")

# ---------------------------------------------------------------------------
# Themes — 4 cross-cutting patterns from the research doc
# ---------------------------------------------------------------------------
st.markdown("### Themes across the window")
st.caption(
    "Cross-cutting patterns from the 90-day window. "
    "Source: `docs/research/2026-04-regulator-pulse.md` Themes section."
)

theme_cols = st.columns(2)
for i, theme in enumerate(THEMES):
    with theme_cols[i % 2]:
        with st.container(border=True):
            st.markdown(f"#### {i + 1}. {theme['title']}")
            st.caption(theme["body"])

st.markdown("---")
st.caption(
    "**See also** · "
    "[Full research doc — 2026-04 regulator pulse]"
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-regulator-pulse.md)"
    " · [10 daily pain points — Tier-1 lens]"
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-aml-process-pain.md)"
    " · [FinTech AML reality — primary persona lens]"
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-fintech-aml-reality.md)"
)

st.markdown(
    glossary_legend(["MLRO", "STR", "SAR", "MRM", "FCA", "FinCEN", "AMLA", "FATF"]),
    unsafe_allow_html=True,
)
