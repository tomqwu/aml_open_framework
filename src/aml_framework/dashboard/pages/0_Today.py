"""Today — per-persona priorities surface (PR 3 of design review).

The pre-PR-3 default landing was Executive Dashboard for everyone, which
was identical for analysts, auditors, and SVPs. This page renders 3
priority cards scoped to ``selected_audience``, each linking into the
destination page where the user can act on the signal.

The card-builder logic lives in ``aml_framework.dashboard.today`` so it
runs without streamlit (unit-test CI image only installs ``.[dev]``).
"""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import (
    kpi_card_rag,
    link_to_page,
)
from aml_framework.dashboard.today import build_cards_for_audience

audience = st.session_state.get("selected_audience")
spec = st.session_state.spec
result = st.session_state.result
df_alerts = st.session_state.df_alerts
df_cases = st.session_state.get("df_cases")

# ---------------------------------------------------------------------------
# Landing-style hero (PR-P) — mirrors docs/pitch/landing/index.html so the
# entrance page feels like the marketing site's first frame, not a generic
# Streamlit dashboard. Three regions: eyebrow → serif headline → meta row.
# ---------------------------------------------------------------------------
_program = spec.program.name.replace("_", " ").title()
_jurisdiction = spec.program.jurisdiction
_regulator = spec.program.regulator

st.markdown(
    f"""
<div class="dna-hero">
  <div class="dna-hero-eyebrow">
    <span class="dna-hero-dot"></span>
    Today &middot; {_jurisdiction} &middot; {_regulator}
  </div>
  <h1 class="dna-hero-title">An AML program you can <em>show</em>,<br>not just describe.</h1>
  <p class="dna-hero-lede">
    {_program}. {len(spec.rules)} detection rules · {result.total_alerts} alerts · {len(result.case_ids)} cases on this run.
    Pick up where the program is right now &mdash; the priorities below adapt to your role.
  </p>
</div>
""",
    unsafe_allow_html=True,
)

show_audience_context("Today")

if not audience:
    st.info(
        "**Tip:** pick an **Audience view** in the sidebar to see the "
        "3-card priority view tailored to your role. Showing the generic "
        "view below."
    )

cards = build_cards_for_audience(audience, spec, result, df_alerts, df_cases)

cols = st.columns(3)
for col, card in zip(cols, cards):
    with col:
        kpi_card_rag(card.label, card.value, rag=card.rag)
        st.caption(card.hint)
        link_to_page(card.target_page, card.cta)

# A tighter "what changed since last run?" hook lives below the cards
# and pulls the latest two run-history entries when available. Falls
# back to silence if there's only one run on disk — so the page never
# pretends there's a delta when there isn't.
st.divider()

run_history = st.session_state.get("run_history", [])
if len(run_history) >= 2:
    latest, previous = run_history[-1], run_history[-2]
    delta_alerts = (latest.get("total_alerts", 0) or 0) - (previous.get("total_alerts", 0) or 0)
    delta_cases = (latest.get("cases_opened", 0) or 0) - (previous.get("cases_opened", 0) or 0)
    direction_alerts = "↑" if delta_alerts > 0 else "↓" if delta_alerts < 0 else "→"
    direction_cases = "↑" if delta_cases > 0 else "↓" if delta_cases < 0 else "→"
    st.caption(
        f"vs. previous run: alerts {direction_alerts} {abs(delta_alerts)}, "
        f"cases {direction_cases} {abs(delta_cases)}"
    )
else:
    st.caption(
        "First run on record — no delta to show. Run history accumulates as "
        "the engine is invoked across days."
    )
