"""Knowledge · Business Deck — board-pack walkthrough + 12 narrative slides.

PR-U3 of the unified-product epic. The GitHub-Pages knowledge site
hosts a board-style business deck + a 64-second board-video at
``docs/pitch/deck-v2/business-slides/`` and
``docs/pitch/deck-v2/board-video/``. This page surfaces both inside the
native dashboard so the GH page can be retired (PR-U4 finishes that).

Structure mirrors the other Knowledge pages (33-40): direct-URL-safe
`ensure_initialized()`, a LITERAL `page_header(...)`, the page-level
`section_explainer(...)`, then the body. The body is image+video
oriented (not prose), so unlike the research whitepaper pages there
is no `dashboard.data.research` extraction — slide PNGs and MP4s live
under `docs/` in the deployed image (Dockerfile copies the whole
`docs/` tree to `/app/docs/`), reached by walking 4 parents up from
this file.
"""

from __future__ import annotations

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

# Repo-root anchor: pages/41_*.py → parents[4] is the project root
# (src/aml_framework/dashboard/pages/<file> → src/aml_framework/dashboard
# → src/aml_framework → src → root). In the deployed container the
# Dockerfile sets WORKDIR=/app and COPYs docs/, so /app/docs/ exists at
# this path. For pip-installed wheels the docs/ tree is not bundled —
# we render a graceful caption in that case rather than crashing.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DECK_DIR = _REPO_ROOT / "docs" / "pitch" / "deck-v2"
_SLIDES_DIR = _DECK_DIR / "business-slides" / "slides"
_PDF_PATH = _DECK_DIR / "business-slides" / "aml-open-framework-business.pdf"
_BOARD_VIDEO = _DECK_DIR / "board-video" / "board-video.mp4"

# (file-stem, headline) — pinning the slide order + the human-readable
# headline that captions each panel. Sourced from the slide HTML
# `<title>` elements at build time, baked here so we don't HTML-parse
# at runtime.
_SLIDES: list[tuple[str, str]] = [
    ("01-cover", "Cover — board briefing"),
    ("02-2to1-rule", "The 2:1 rule"),
    ("03-cost", "The cost in three sizes"),
    ("04-quotes", "What leaders actually say"),
    ("05-thesis", "The thesis"),
    ("06-how-it-works", "How it works"),
    ("07-tuesday", "A Tuesday on the AML floor"),
    ("08-meetings", "The meetings that stop happening"),
    ("09-changes", "Pain → Capability map"),
    ("10-quadrant", "Where this sits in the market"),
    ("11-numbers", "By the numbers"),
    ("12-close", "Close — what we're asking for"),
]


st.markdown(
    "The business deck is a 12-slide board-pack for CCO, MLRO, and "
    "Audit Committee audiences. It pairs with the 64-second "
    "**board video** at the top — a McKinsey-style walkthrough of the "
    "thesis with no CLI register. Both artefacts live next to the "
    "framework source in `docs/pitch/deck-v2/` and ship inside the "
    "deployed container."
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

# Download buttons row — PDF for offline reading + a deep-link the
# user can paste into a meeting invite. Both target files inside the
# container; `st.download_button` streams bytes, no Streamlit static
# server config needed.
if _PDF_PATH.exists():
    pdf_bytes = _PDF_PATH.read_bytes()
    st.download_button(
        label="📄 Download business deck (PDF)",
        data=pdf_bytes,
        file_name="aml-open-framework-business.pdf",
        mime="application/pdf",
        key="business_deck_pdf_download",
    )
else:
    st.caption(
        "PDF not bundled. Source: "
        "`docs/pitch/deck-v2/business-slides/aml-open-framework-business.pdf`."
    )

st.markdown("<br>", unsafe_allow_html=True)

st.markdown("### Slides")

missing_slides: list[str] = []
for stem, headline in _SLIDES:
    img_path = _SLIDES_DIR / f"{stem}.png"
    if not img_path.exists():
        missing_slides.append(stem)
        continue
    st.markdown(f"**{stem.split('-', 1)[0]} · {headline}**")
    st.image(str(img_path), use_container_width=True)
    st.markdown("<br>", unsafe_allow_html=True)

if missing_slides:
    st.caption(
        f"Slides not bundled in this install: {', '.join(missing_slides)}. "
        "Source: `docs/pitch/deck-v2/business-slides/slides/`."
    )
