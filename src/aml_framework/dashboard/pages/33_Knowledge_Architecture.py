"""Knowledge · Architecture — ported from the static research site.

PR-U2 of the unified-product epic. The GitHub-Pages marketing/knowledge
site is being merged into the product so the GH page can be retired.
This page is the native Streamlit rendering of
``docs/pitch/landing/research/architecture.html``.

Structure mirrors 27_Regulator_Pulse.py exactly: `ensure_initialized()`
(direct-URL robustness), a LITERAL `page_header(...)` (the title-mining
contract in tests/test_dashboard_workflows.py), a page-level
`section_explainer(...)` (the "GenAI on every page" promise), then the
prose body — rendered from the generated `dashboard.data.research`
substrate so no whitepaper text is copy-pasted into the page. It's a
reference page, not a run view, so it carries the STATIC_PAGES exemption
(same as Regulator Pulse).
"""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.components import page_header, section_explainer
from aml_framework.dashboard.data import research
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

page_header("Architecture", "Architecture · design rationale")

section_explainer(
    page="Architecture",
    section_id="knowledge_architecture.page",
    section_title="Architecture",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
        "metrics": len(getattr(st.session_state.get("spec"), "metrics", []) or []),
    },
)

research.render_body("architecture")
