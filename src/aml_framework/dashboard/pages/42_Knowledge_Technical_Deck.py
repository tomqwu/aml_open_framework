"""Knowledge · Technical Deck — engineer/MLRO deep-dive + 92s walkthrough + PDF.

PR-U3 of the unified-product epic surfaces the GitHub-Pages
technical deck + walkthrough video natively in the dashboard.
PR-U5 (this revision) drops the PNG slide gallery — `st.image`
with `use_container_width=True` was stretching the 1920×1080
captures on wide desktops, blurring them — and switches to a
native browser PDF iframe with built-in zoom, page navigation,
full-screen, and search.
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from aml_framework.dashboard.components import page_header, section_explainer, page_footer
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

page_header("Technical Deck", "Technical deck · CLI + audit-chain walkthrough")

section_explainer(
    page="Technical Deck",
    section_id="knowledge_technical_deck.page",
    section_title="Technical Deck",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
        "metrics": len(getattr(st.session_state.get("spec"), "metrics", []) or []),
    },
)

# pages/42_*.py → parents[4] is the project root; in the
# container WORKDIR=/app and Dockerfile COPYs docs/, so
# /app/docs/ exists.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DECK_DIR = _REPO_ROOT / "docs" / "pitch" / "deck-v2"
_PDF_PATH = _DECK_DIR / "aml-open-framework-v2.pdf"
_WALKTHROUGH_VIDEO = _DECK_DIR / "video" / "walkthrough.mp4"


st.markdown(
    "The technical deck is the 18-slide CLI-register companion to "
    "the business deck — same product, different audience. It "
    "carries the spec-validation flow, the audit hash-chain proof, "
    "lineage walk-back, and the by-the-numbers slide engineers and "
    "2LoD reviewers ask for. The **walkthrough video** at the top "
    "is a 92-second auto-advance recording of every slide, mixed "
    "with background music; share it with anyone who would skim "
    "the screenshots."
)

st.markdown("<br>", unsafe_allow_html=True)

if _WALKTHROUGH_VIDEO.exists():
    st.markdown("### Walkthrough video — 92-second auto-advance")
    st.video(str(_WALKTHROUGH_VIDEO))
else:
    st.caption(
        "Walkthrough video not bundled in this install. Source: "
        "`docs/pitch/deck-v2/video/walkthrough.mp4`."
    )

st.markdown("<br>", unsafe_allow_html=True)

st.markdown("### Deck — 18 slides")

if _PDF_PATH.exists():
    pdf_bytes = _PDF_PATH.read_bytes()
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{pdf_b64}#view=FitH" '
        f'width="100%" height="780" '
        f'style="border:1px solid rgba(255,255,255,0.12);border-radius:8px;">'
        f"</iframe>",
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)
    st.download_button(
        label="📄 Download technical deck (PDF)",
        data=pdf_bytes,
        file_name="aml-open-framework-v2.pdf",
        mime="application/pdf",
        key="technical_deck_pdf_download",
    )
else:
    st.caption("PDF not bundled. Source: `docs/pitch/deck-v2/aml-open-framework-v2.pdf`.")

page_footer()
