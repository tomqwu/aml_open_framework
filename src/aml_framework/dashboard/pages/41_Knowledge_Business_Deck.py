"""Knowledge · Business Deck — board-pack walkthrough + 64s board video + PDF.

PR-U3 of the unified-product epic surfaces the GitHub-Pages
business deck + board video natively in the dashboard. PR-U5
(this revision) drops the PNG slide gallery — `st.image` with
`use_container_width=True` was stretching the 1920×1080 captures
to the dashboard column width on wide desktops, blurring them —
and switches to a native browser PDF iframe. Browsers render
PDFs with built-in zoom, page navigation, full-screen, and search
without any extra dashboard infrastructure (the base64 data URI
keeps the PDF inline so there's no cross-origin static-server
to wire up). The PDF is the canonical artefact anyway — operators
download it for offline reading.
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from aml_framework.dashboard.components import page_header, section_explainer
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

page_header("Business Deck", "Business deck · board-pack walkthrough")

section_explainer(
    page="Business Deck",
    section_id="knowledge_business_deck.page",
    section_title="Business Deck",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
        "metrics": len(getattr(st.session_state.get("spec"), "metrics", []) or []),
    },
)

# pages/41_*.py → parents[4] is the project root. In the deployed
# container the Dockerfile sets WORKDIR=/app and COPYs docs/, so
# /app/docs/ exists at this path. For pip-installed wheels the
# docs/ tree is not bundled — graceful caption fallback.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DECK_DIR = _REPO_ROOT / "docs" / "pitch" / "deck-v2"
_PDF_PATH = _DECK_DIR / "business-slides" / "aml-open-framework-business.pdf"
_BOARD_VIDEO = _DECK_DIR / "board-video" / "board-video.mp4"


st.markdown(
    "The business deck is the 12-slide board-pack for CCO, MLRO, "
    "and Audit Committee audiences. It pairs with the 64-second "
    "**board video** at the top — a McKinsey-style walkthrough of "
    "the thesis with no CLI register. Both artefacts live next to "
    "the framework source in `docs/pitch/deck-v2/` and ship inside "
    "the deployed container."
)

st.markdown("<br>", unsafe_allow_html=True)

if _BOARD_VIDEO.exists():
    st.markdown("### Board video — 64-second walkthrough")
    st.video(str(_BOARD_VIDEO))
else:
    st.caption(
        "Board video not bundled in this install. Source: "
        "`docs/pitch/deck-v2/board-video/board-video.mp4`."
    )

st.markdown("<br>", unsafe_allow_html=True)

st.markdown("### Deck — 12 slides")

if _PDF_PATH.exists():
    pdf_bytes = _PDF_PATH.read_bytes()
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    # Browsers render PDFs natively in iframes with built-in zoom,
    # page navigation, full-screen, search. Inlining via base64
    # data URI avoids the cross-origin / static-server wiring that
    # serving the PDF over HTTP would require.
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{pdf_b64}#view=FitH" '
        f'width="100%" height="780" '
        f'style="border:1px solid rgba(255,255,255,0.12);border-radius:8px;">'
        f"</iframe>",
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)
    # Keep the download button for offline reading + meeting-invite
    # attachment workflows.
    st.download_button(
        label="📄 Download business deck (PDF)",
        data=pdf_bytes,
        file_name="aml-open-framework-business.pdf",
        mime="application/pdf",
        key="business_deck_pdf_download",
    )
else:
    st.caption(
        "PDF not bundled in this install. Source: "
        "`docs/pitch/deck-v2/business-slides/aml-open-framework-business.pdf`."
    )
