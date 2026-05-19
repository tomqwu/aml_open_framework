"""Knowledge · FinTech AML Reality — ported from the static research site.

PR-U2 of the unified-product epic. Native Streamlit rendering of
``docs/pitch/landing/research/fintech.html``. Structure mirrors
33_Knowledge_Architecture.py — see that file for the pattern rationale.
"""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.components import page_header, section_explainer
from aml_framework.dashboard.data import research
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

page_header("FinTech AML Reality", "FinTech reality · 2026 edition")

section_explainer(
    page="FinTech AML Reality",
    section_id="knowledge_fintech.page",
    section_title="FinTech AML Reality",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
        "metrics": len(getattr(st.session_state.get("spec"), "metrics", []) or []),
    },
)

research.render_body("fintech")
