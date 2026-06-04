"""Start — the first-run front door. One sentence, one button, then a live
4-beat Golden Thread (alert -> case -> audit) over a real planted case.

Full-canvas: it does NOT depend on the sidebar, so it works on a phone even
while the broader nav loads. The 44 pages stay out of sight until the final
beat. ADVISORY/orientation surface only — reads cached run data, changes
nothing.
"""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard import golden_thread as gt
from aml_framework.dashboard.components import (
    page_footer,
    page_header,
    section_explainer,
)
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

# Direction-C: suppress the visible eyebrow/title/caption chrome so the
# ink hero band (injected below on the hero screen) is the FIRST visible
# block — no doubled "Start here" H1. `render_chrome=False` still mounts
# the AI-assistant hook and satisfies the page_header source-guard test
# (same opt-out 0_Today.py uses). The old in-canvas `mobile_menu(...)`
# ☰ expander is removed: the new persistent bottom tab bar is the mobile
# nav now, so it was redundant clutter.
page_header(
    "Start here",
    "An anti-money-laundering program you can show your regulator — without a six-week reconstruction.",
    render_chrome=False,
)


def _records(key: str) -> list[dict]:
    df = st.session_state.get(key)
    if df is None or getattr(df, "empty", True):
        return []
    return df.to_dict("records")


def _audit_summary() -> dict:
    result = st.session_state.get("result")
    manifest = getattr(result, "manifest", {}) or {}
    return {"decisions_hash": manifest.get("decisions_hash", "—"), "reproducible": True}


beats = gt.build_beats(_records("df_alerts"), _records("df_cases"), _audit_summary())
st.session_state.setdefault("gt_beat", -1)  # -1 = hero (pre-tour) screen
idx = st.session_state["gt_beat"]


def _go(i: int) -> None:
    st.session_state["gt_beat"] = i


if idx < 0:
    # Hero screen — Direction C landing: an ink full-bleed hero band with
    # reverse-type wordmark + serif H1 (cream, rust *show*), three stat
    # cards (Rules / Alerts / Cases from the live cached run), then the
    # rust "Show me it's real" CTA. Injected as HTML so it reads great on
    # a phone (and acceptably on desktop). The `page_header()` above runs
    # with `render_chrome=False` (mounts the AI hook + satisfies the
    # source-guard test, but draws no visible title) so THIS band is the
    # first visible block — no doubled "Start here" heading.
    _spec = st.session_state.get("spec")
    _result = st.session_state.get("result")
    _n_rules = len(getattr(_spec, "rules", []) or [])
    _n_alerts = int(getattr(_result, "total_alerts", 0) or 0)
    _n_cases = len(_records("df_cases"))
    st.markdown(
        f"""
<div class="dna-start-hero">
  <div class="dna-start-hbar">
    <span class="dna-start-dot"></span>
    <span class="dna-start-wordmark">AML Open Framework</span>
  </div>
  <h1 class="dna-start-h1">An AML program you can <em>show</em>.</h1>
  <p class="dna-start-lede">Not just describe — shown to your regulator
     without a six-week reconstruction.</p>
</div>
<div class="dna-start-stats">
  <div class="dna-start-stat"><div class="dna-start-n">{_n_rules}</div>
     <div class="dna-start-l">Rules</div></div>
  <div class="dna-start-stat"><div class="dna-start-n">{_n_alerts}</div>
     <div class="dna-start-l">Alerts</div></div>
  <div class="dna-start-stat"><div class="dna-start-n">{_n_cases}</div>
     <div class="dna-start-l">Cases</div></div>
</div>
""",
        unsafe_allow_html=True,
    )
    st.button("▶  Show me it's real", type="primary", on_click=_go, args=(0,))
    st.page_link("pages/0_Today.py", label="Skip to the app →")
    page_footer()
    st.stop()

section_explainer(
    page="Start here",
    section_id="start.page",
    section_title="Start here",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
    },
)

beat = beats[min(idx, len(beats) - 1)]
st.subheader(beat["title"])
st.write(beat["narration"])

if beat["panel_kind"] == gt.PANEL_ALERT:
    a = beat["payload"]
    st.write(f"**Customer:** {a.get('customer_id', '—')}")
    st.json({k: a.get(k) for k in ("rule_id", "severity", "sum_amount", "count", "priority_score")})
elif beat["panel_kind"] == gt.PANEL_CASE:
    if beat["payload"]:
        st.json(beat["payload"])
    else:
        st.info("Case assembly view — open the matching case in Case Investigation.")
elif beat["panel_kind"] == gt.PANEL_AUDIT:
    st.json(beat["payload"])
    st.caption("Verify it yourself: `aml verify-decisions` re-hashes the ledger.")
elif beat["panel_kind"] == gt.PANEL_EMPTY:
    st.info("Load an example spec with planted activity to see the full story.")

# Controls.
if beat["panel_kind"] == gt.PANEL_DOORS:
    st.page_link("pages/0_Today.py", label="Explore for my role →")
    st.page_link("pages/3_Alert_Queue.py", label="Browse all tools →")
    st.button("↻ Replay the tour", on_click=_go, args=(-1,))
elif beat["panel_kind"] != gt.PANEL_EMPTY and idx < len(beats) - 1:
    st.button("Next →", type="primary", on_click=_go, args=(idx + 1,))
    st.button("Skip to the end →", on_click=_go, args=(len(beats) - 1,))
else:
    st.button("↻ Replay the tour", on_click=_go, args=(-1,))

page_footer()
