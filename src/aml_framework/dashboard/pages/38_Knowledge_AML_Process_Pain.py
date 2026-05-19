"""Knowledge · AML Process Pain — ported from the static research site.

PR-U2 of the unified-product epic. Native Streamlit rendering of
``docs/pitch/landing/research/process-pain.html``. Structure mirrors
33_Knowledge_Architecture.py — see that file for the pattern rationale.
"""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.components import page_header, section_explainer
from aml_framework.dashboard.data import research
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

page_header("AML Process Pain", "Style guide · 2026 edition")

section_explainer(
    page="AML Process Pain",
    section_id="knowledge_process_pain.page",
    section_title="AML Process Pain",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
        "metrics": len(getattr(st.session_state.get("spec"), "metrics", []) or []),
    },
)

research.render_body("process-pain")
