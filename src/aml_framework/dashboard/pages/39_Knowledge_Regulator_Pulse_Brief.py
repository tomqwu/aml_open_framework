"""Knowledge · Regulator Pulse Brief — ported from the static research site.

PR-U2 of the unified-product epic. Native Streamlit rendering of
``docs/pitch/landing/research/regulator-pulse.html``. Structure mirrors
33_Knowledge_Architecture.py — see that file for the pattern rationale.
This is the narrative 90-day brief; the operational Regulator Pulse
(page 27) is the filterable event log built on the same research.
"""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.components import page_header, section_explainer
from aml_framework.dashboard.data import research
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

page_header("Regulator Pulse Brief", "Regulator pulse · 90-day log")

section_explainer(
    page="Regulator Pulse Brief",
    section_id="knowledge_regulator_pulse.page",
    section_title="Regulator Pulse Brief",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
        "metrics": len(getattr(st.session_state.get("spec"), "metrics", []) or []),
    },
)

research.render_body("regulator-pulse")
