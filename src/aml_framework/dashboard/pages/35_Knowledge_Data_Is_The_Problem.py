"""Knowledge · Data Is The Problem — ported from the static research site.

PR-U2 of the unified-product epic. Native Streamlit rendering of
``docs/pitch/landing/research/data-problem.html``. Structure mirrors
33_Knowledge_Architecture.py — see that file for the pattern rationale.
"""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.components import page_header, section_explainer, page_footer
from aml_framework.dashboard.data import research
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

page_header("Data Is The Problem", "Whitepaper · 2026 edition")

section_explainer(
    page="Data Is The Problem",
    section_id="knowledge_data_problem.page",
    section_title="Data Is The Problem",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
        "metrics": len(getattr(st.session_state.get("spec"), "metrics", []) or []),
    },
)

research.render_body("data-problem")

page_footer()
