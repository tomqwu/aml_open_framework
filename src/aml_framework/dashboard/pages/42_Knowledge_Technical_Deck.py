"""Knowledge · Technical Deck — engineer-and-MLRO deep-dive deck + 92-second walkthrough.

PR-U3 of the unified-product epic. The GitHub-Pages knowledge site
hosts a technical deck (CLI register: spec validation, audit-chain,
lineage) at ``docs/pitch/deck-v2/`` and a 92-second
auto-advance walkthrough video at ``docs/pitch/deck-v2/video/``. This
page surfaces both inside the native dashboard so the GH page can be
retired (PR-U4).

Structure mirrors the other Knowledge pages (33-40) and the Business
Deck (41): direct-URL-safe `ensure_initialized()`, a LITERAL
`page_header(...)`, the page-level `section_explainer(...)`, then a
body that's video+image oriented (not prose).
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from aml_framework.dashboard.components import page_header, section_explainer
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

# pages/42_*.py → parents[4] is the project root; in the container
# WORKDIR=/app and Dockerfile COPYs docs/, so /app/docs/ exists.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DECK_DIR = _REPO_ROOT / "docs" / "pitch" / "deck-v2"
_SLIDES_DIR = _DECK_DIR / "slides"
_PDF_PATH = _DECK_DIR / "aml-open-framework-v2.pdf"
_WALKTHROUGH_VIDEO = _DECK_DIR / "video" / "walkthrough.mp4"

# (file-stem, headline). Source: each slide's HTML `<title>` element,
# stripped of the " · AML Open Framework V2" suffix. Slide 03 was
# never rendered (HTML source skipped capture); slides 20-25 are
# HTML-only and absent from the captured set — keeping only the 18
# slides that have committed PNGs is intentional: nothing in this
# page can render a slide that wasn't captured at deck-build time.
_SLIDES: list[tuple[str, str]] = [
    ("01-cover", "Cover"),
    ("02-three-way-gap", "The three-way gap"),
    ("04-one-yaml-three-reviewers", "One YAML, three reviewers"),
    ("05-cli-bridge", "The CLI bridge"),
    ("06-morning-checklist", "Morning checklist"),
    ("07-new-typology", "New typology in 60s"),
    ("08-propose-change", "2LoD sign-off"),
    ("09-auditor-pack", "Auditor self-service"),
    ("10-curated-catalogue", "Curated catalogue"),
    ("11-tune-before-promote", "Tune before promote"),
    ("12-audit-hash-chain", "Audit hash-chain"),
    ("13-init-byod", "init · BYOD"),
    ("14-notify-digest", "Notify / digest"),
    ("15-multi-jurisdiction", "Multi-jurisdiction"),
    ("16-architecture", "Architecture"),
    ("17-cli-cheat-sheet", "CLI cheat-sheet"),
    ("18-by-the-numbers", "By the numbers"),
    ("19-cta", "Call to action"),
]


st.markdown(
    "The technical deck is the 18-slide CLI-register companion to the "
    "business deck — same product, different audience. It carries the "
    "spec-validation flow, the audit hash-chain proof, lineage "
    "walk-back, and the by-the-numbers slide engineers and 2LoD "
    "reviewers ask for. The **walkthrough video** at the top is a "
    "92-second auto-advance recording of every slide, mixed with "
    "background music; share it with anyone who would skim the "
    "screenshots."
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

if _PDF_PATH.exists():
    pdf_bytes = _PDF_PATH.read_bytes()
    st.download_button(
        label="📄 Download technical deck (PDF)",
        data=pdf_bytes,
        file_name="aml-open-framework-v2.pdf",
        mime="application/pdf",
        key="technical_deck_pdf_download",
    )
else:
    st.caption("PDF not bundled. Source: `docs/pitch/deck-v2/aml-open-framework-v2.pdf`.")

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
        "Source: `docs/pitch/deck-v2/slides/`."
    )
