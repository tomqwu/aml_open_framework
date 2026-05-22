"""Knowledge · Competitive Landscape — ported from the static research site.

PR-U2 of the unified-product epic. Native Streamlit rendering of
``docs/pitch/landing/research/competitive-positioning.html``. Structure
mirrors 33_Knowledge_Architecture.py — see that file for the pattern
rationale (ensure_initialized → literal page_header → section_explainer
→ generated-substrate body; STATIC_PAGES-exempt reference page).
"""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.components import page_header, section_explainer, page_footer
from aml_framework.dashboard.data import research
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

page_header("Competitive Landscape", "Competitive positioning · April 2026")

section_explainer(
    page="Competitive Landscape",
    section_id="knowledge_competitive_positioning.page",
    section_title="Competitive Landscape",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
        "metrics": len(getattr(st.session_state.get("spec"), "metrics", []) or []),
    },
)

research.render_body("competitive-positioning")

page_footer()
