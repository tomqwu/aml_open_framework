"""Shared UI components for the AML dashboard."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from aml_framework.metrics.engine import MetricResult

# ---------------------------------------------------------------------------
# Color system
# ---------------------------------------------------------------------------
RAG_COLORS = {
    "green": "#16a34a",
    "amber": "#d97706",
    "red": "#dc2626",
    "unset": "#6b7280",
}

SEVERITY_COLORS = {
    "critical": "#7c3aed",
    "high": "#dc2626",
    "medium": "#d97706",
    "low": "#16a34a",
}

CHART_TEMPLATE = "plotly_white"
CHART_PALETTE = ["#2563eb", "#7c3aed", "#db2777", "#d97706", "#059669", "#6b7280"]

# SLA band colors — mirrors the cases/sla.py state vocabulary
# (green / amber / red / breached). Centralised here so per-page color
# dicts can be deleted in Phase E.
SLA_BAND_COLORS = {
    "green": "#16a34a",
    "amber": "#d97706",
    "red": "#dc2626",
    "breached": "#7c2d12",  # dark red — distinct from red so a glance separates them
    "unknown": "#6b7280",
}

# Customer risk-rating colors — semantically distinct from severity
# (severity ranks an *alert*; risk_rating ranks a *customer*) but uses
# the same hex-code spectrum. Centralising here lets pages call
# risk_color() instead of redeclaring `{"high": "#dc2626", ...}` inline.
RISK_RATING_COLORS = {
    "high": "#dc2626",
    "medium": "#d97706",
    "low": "#16a34a",
    "unknown": "#6b7280",
}


# ---------------------------------------------------------------------------
# CSS Theme
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
/* Load deck fonts via @import inside <style> — Streamlit's markdown
 * parser treats top-level <link> tags as unsafe HTML and breaks
 * rendering. @import works reliably inside the style block. */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,600&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* ---- Deck DNA tokens (PR-M) ----
 * Lifted from docs/pitch/landing/index.html so the dashboard reads as a
 * sibling to the deck + research site instead of a separate product. */
:root {
    --dna-display: 'Source Serif 4', Georgia, serif;
    --dna-body:    'Inter', -apple-system, system-ui, sans-serif;
    --dna-mono:    'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
    --dna-ink:     #0f172a;
    --dna-ink-2:   #475569;
    --dna-ink-faint: #94a3b8;
    --dna-rule:    rgba(15, 23, 42, 0.10);
    --dna-tech-bg: #0a0e1a;
    --dna-tech-panel: #0f172a;
    --dna-cyan:    #67e8f9;
}

/* ---- Global ---- */
.block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
/* Apply Inter narrowly. Two hard constraints learned the wrong way
 * (PR-M iteration):
 *  1. Don't touch the sidebar — Streamlit's nav uses Material Symbols
 *     icon font; if our font-family wins on icon spans, icon NAMES
 *     render as text ("today" "dashboard" "speed" etc.).
 *  2. Don't use wildcards like `[class*="st-"]` — same problem,
 *     plus they trample widget chrome.
 * Target the main panel's text containers explicitly. */
body { font-family: var(--dna-body); }
[data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] p,
[data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] li,
[data-testid="stAppViewContainer"] [data-testid="stCaptionContainer"],
[data-testid="stAppViewContainer"] .stTextInput input,
[data-testid="stAppViewContainer"] .stTextArea textarea,
[data-testid="stAppViewContainer"] .stSelectbox div[role="combobox"],
[data-testid="stAppViewContainer"] .stButton button {
    font-family: var(--dna-body) !important;
}
code, pre, .terminal-block, [data-testid="stCode"] code,
[data-testid="stMarkdownContainer"] code {
    font-family: var(--dna-mono) !important;
}

/* ---- Hide Streamlit Cloud chrome ----
 * Compliance dashboards are shipped through tenants' own infrastructure;
 * the public "Deploy" button + 3-dot menu look unprofessional in that
 * context and confuse non-technical users (e.g. CCOs reviewing on tablets).
 */
.stDeployButton,
[data-testid="stToolbar"],
[data-testid="stStatusWidget"] { display: none !important; }

/* ---- Sidebar (deck DNA: tech panel) ---- */
section[data-testid="stSidebar"] {
    background: var(--dna-tech-bg);
    border-right: 1px solid rgba(148, 163, 184, 0.15);
}
section[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    font-size: 0.88rem;
    line-height: 1.5;
}
section[data-testid="stSidebar"] hr {
    border-color: rgba(148, 163, 184, 0.15) !important;
}
/* Cyan accent dot above the sidebar header — deck signature.
 * Pure CSS, no per-page wiring needed. */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]::before {
    content: '';
    display: block;
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--dna-cyan);
    box-shadow: 0 0 8px var(--dna-cyan);
    margin: 0 0 14px 4px;
}

/* ---- KPI metric cards ---- */
[data-testid="stMetricValue"] {
    font-size: clamp(1.2rem, 2.2vw, 1.8rem) !important;
    font-weight: 700 !important;
    color: #1e293b !important;
    /* Prevent mid-number wraps like "$843,3<br>88" when the card column
       narrows but the value is still single-line-renderable. */
    white-space: nowrap !important;
    overflow: hidden;
    text-overflow: ellipsis;
}
[data-testid="stMetricLabel"] {
    font-size: 0.8rem !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #64748b !important;
}
div[data-testid="stMetric"] {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1rem 1.2rem 0.8rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

/* ---- Page headers (deck DNA: serif h1, tighter scale) ---- */
.main h1, [data-testid="stAppViewContainer"] h1 {
    font-family: var(--dna-display) !important;
    font-weight: 600 !important;
    color: var(--dna-ink) !important;
    font-size: clamp(28px, 3.4vw, 44px) !important;
    line-height: 1.15 !important;
    letter-spacing: -0.01em !important;
    text-wrap: pretty;
}
h2 {
    font-family: var(--dna-display) !important;
    font-weight: 500 !important;
    color: #1e293b !important;
    letter-spacing: -0.005em;
}
h3 {
    font-family: var(--dna-body) !important;
    font-weight: 600 !important;
    color: #334155 !important;
}

/* Eyebrow + 32px rule pattern — rendered by page_header() (PR-M).
 * Mono uppercase label with a horizontal accent line under it, the
 * same signature the deck uses on every section break. */
.dna-eyebrow {
    display: flex;
    align-items: center;
    gap: 14px;
    font-family: var(--dna-mono);
    font-size: 11px;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--dna-ink-faint);
    margin: 4px 0 8px 0;
}
.dna-eyebrow::after {
    content: '';
    flex: 0 0 32px;
    height: 1px;
    background: var(--dna-ink-faint);
    opacity: 0.55;
}
.dna-eyebrow .dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--dna-cyan);
    box-shadow: 0 0 6px var(--dna-cyan);
}

/* ---- Tables ---- */
[data-testid="stDataFrame"] {
    border-radius: 8px;
    overflow: hidden;
}

/* ---- Tabs ---- */
button[data-baseweb="tab"] {
    font-weight: 600 !important;
}

/* ---- Cards (via HTML) ---- */
.metric-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.2rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

/* ---- Terminal block (Audit & Evidence — PR 4) ----
 * The hash chain + decision log lives on Audit & Evidence and is the
 * page auditors trust most. Render hashes in mono so they're scannable
 * + copyable without ambiguity (0/O, 1/l/I, etc), and lean the page
 * toward a Bloomberg-terminal vocabulary instead of SaaS-card. */
.terminal-block {
    background: #0f172a;
    color: #e2e8f0;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 1rem 1.2rem;
    font-family: "JetBrains Mono", "SF Mono", "Menlo", "Consolas", monospace;
    font-size: 0.85rem;
    line-height: 1.6;
    overflow-x: auto;
    white-space: nowrap;
}
.terminal-block .row {
    display: flex;
    gap: 1.5rem;
    align-items: baseline;
}
.terminal-block .key {
    color: #94a3b8;
    text-transform: uppercase;
    font-size: 0.72rem;
    letter-spacing: 0.05em;
    min-width: 6.5rem;
}
.terminal-block .value {
    color: #f1f5f9;
}
.terminal-block .value.hash {
    color: #67e8f9;  /* cyan-300 — distinguishes hashes from human text */
}
.terminal-block .value.ok { color: #86efac; }    /* green-300 */
.terminal-block .value.warn { color: #fde68a; }  /* amber-300 */
.terminal-block .value.bad { color: #fca5a5; }   /* red-300 */
.metric-card-accent {
    border-left: 4px solid #2563eb;
}
.metric-card h4 { margin: 0 0 0.3rem 0; color: #0f172a; }
.metric-card .value {
    font-size: clamp(1.4rem, 2.4vw, 2rem);
    font-weight: 700;
    color: #0f172a;
    margin: 0.2rem 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.metric-card .label {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #64748b;
}
.rag-dot {
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 50%;
    margin-right: 6px;
}

/* ---- Mobile responsiveness (issue #66) ----
 * Streamlit defaults assume wide desktop viewports; without these
 * overrides the dashboard horizontal-scrolls on phones and the
 * sidebar takes ~90% of the screen when expanded.
 *
 * Breakpoints chosen to match common device widths:
 *   <768px  → tablets / large phones
 *   <480px  → phones
 */

/* Tighten container padding on tablets and below */
@media (max-width: 768px) {
    .block-container {
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
        padding-top: 1rem !important;
        max-width: 100vw !important;
    }
    /* Stack columns vertically — Streamlit's CSS grid keeps them
       horizontal until ~640px, which is too aggressive for our
       4-column KPI rows. Force stacking earlier. */
    [data-testid="stHorizontalBlock"] {
        flex-direction: column !important;
    }
    [data-testid="stHorizontalBlock"] > [data-testid="column"] {
        width: 100% !important;
        flex: 1 1 100% !important;
    }
    /* Smaller KPI value font so 4-up KPI cards don't truncate when stacked */
    [data-testid="stMetricValue"] {
        font-size: 1.4rem !important;
    }
    /* Compress headers */
    h1 { font-size: 1.5rem !important; }
    h2 { font-size: 1.25rem !important; }
    h3 { font-size: 1.1rem !important; }
    /* Make tables horizontally scroll inside their container,
       not blow out the page width */
    [data-testid="stDataFrame"] {
        overflow-x: auto !important;
    }
    /* Plotly chart heights — desktop defaults overflow vertically
       on small screens; cap at 60vh so charts fit + leave room for
       the legend */
    [data-testid="stPlotlyChart"] > div {
        height: auto !important;
        max-height: 60vh;
    }
}

/* Phone-specific: tighten further + auto-hide sidebar handle width */
@media (max-width: 480px) {
    .block-container {
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    /* Sidebar width when expanded — reduce so users can still see
       page content underneath when the sidebar is opened */
    section[data-testid="stSidebar"] {
        width: 85vw !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.2rem !important;
    }
}

/* Touch-target sizing — Apple HIG + Material Design both call for
 * a 44x44pt minimum tap target. Streamlit defaults are too small
 * for fingers on phones. */
@media (max-width: 768px) {
    button, [role="button"], a {
        min-height: 44px;
    }
    /* Selectbox / multiselect inputs */
    [data-baseweb="select"] {
        min-height: 44px;
    }
}
</style>
"""


# Executive font scale — applied for SVP / CTO / VP / Director / CCO
# audiences. These users typically read from larger displays in meeting
# contexts and want bigger numbers without leaning in. ~20-30% scale-up
# on KPI values, headers, and metric labels; tables stay at base size to
# avoid breaking layouts that already pack a lot of columns.
EXECUTIVE_AUDIENCES = frozenset({"svp", "vp", "director", "cto", "cco"})

EXECUTIVE_CSS = """
<style>
[data-testid="stMetricValue"] {
    font-size: 2.4rem !important;
}
[data-testid="stMetricLabel"] {
    font-size: 1rem !important;
}
[data-testid="stMetricDelta"] {
    font-size: 1.1rem !important;
}
.metric-card .value { font-size: 2.8rem !important; }
.metric-card .label { font-size: 1rem !important; }
.metric-card h4 { font-size: 1.3rem !important; }
h1 { font-size: 2.4rem !important; }
h2 { font-size: 1.9rem !important; }
h3 { font-size: 1.5rem !important; }
/* Body text up one notch — readable from across a conference table */
.block-container [data-testid="stMarkdownContainer"] p {
    font-size: 1.05rem !important;
    line-height: 1.6 !important;
}
.block-container [data-testid="stCaptionContainer"] {
    font-size: 0.95rem !important;
}

/* Page-load fade-up — applied via .animate-on-load class on hero +
 * KPI cards. 500ms one-shot, no infinite loop. Delays cascade so the
 * sections reveal sequentially (like a board deck slide in).
 *
 * Stays subtle on purpose — board-pack credible, not slop.
 */
@keyframes fadeUp {
    0%   { opacity: 0; transform: translateY(8px); }
    100% { opacity: 1; transform: translateY(0); }
}
.animate-on-load { animation: fadeUp 0.5s ease-out both; }
.animate-on-load:nth-child(1) { animation-delay: 0ms; }
.animate-on-load:nth-child(2) { animation-delay: 80ms; }
.animate-on-load:nth-child(3) { animation-delay: 160ms; }
@media (prefers-reduced-motion: reduce) {
    .animate-on-load { animation: none; }
}
</style>
"""


def apply_theme() -> None:
    """Inject custom CSS — base theme, mobile-responsive overlay (issue #66),
    and the executive font scale when an exec-tier audience is selected.

    The executive scale activates when `st.session_state["selected_audience"]`
    is in `EXECUTIVE_AUDIENCES` (SVP / CTO / VP / Director / CCO). It's
    additive — runs after the base CSS so its `!important` rules win.
    """
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    audience = st.session_state.get("selected_audience")
    if audience in EXECUTIVE_AUDIENCES:
        st.markdown(EXECUTIVE_CSS, unsafe_allow_html=True)


def responsive_plotly_config() -> dict[str, Any]:
    """Return a Plotly config dict that enables responsive resizing.

    Pass to `st.plotly_chart(fig, config=responsive_plotly_config())`.
    Plotly's `responsive: True` makes the chart re-layout when its
    container resizes — without it, charts render at their initial
    width and overflow on mobile when the user rotates or the
    sidebar collapses.
    """
    return {
        "responsive": True,
        "displayModeBar": False,  # Cleaner mobile view; users can toggle if needed
    }


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------


def page_header(title: str, description: str | None = None) -> None:
    """Consistent page header — deck DNA (PR-M).

    Renders the static-site / pitch-deck signature pattern on every
    dashboard page: small uppercase mono eyebrow + horizontal accent
    line + Source Serif h1 + Inter caption. The whole dashboard reads
    as a sibling to docs/pitch/ instead of a separate product.

    Also mounts the GenAI assistant panel in the sidebar (PR-K). The
    assistant call is wrapped in try/except so a misconfigured backend
    never crashes a page render.
    """
    # Eyebrow: persona context if a persona is selected, else "Dashboard".
    eyebrow_label = (
        f"Dashboard · {st.session_state.get('selected_audience', '').replace('_', ' ').title()}".strip(
            " ·"
        )
        if st.session_state.get("selected_audience")
        else "Dashboard"
    )
    st.markdown(
        f'<div class="dna-eyebrow"><span class="dot"></span>{eyebrow_label}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f"# {title}")
    if description:
        st.caption(description)
    st.markdown(
        '<hr style="border:none; border-top:1px solid var(--dna-rule); margin:10px 0 18px 0;">',
        unsafe_allow_html=True,
    )
    # AI assistant — present on every page via this single wire-up (PR-K).
    try:
        ai_panel(page=title)
    except Exception:  # noqa: BLE001 — assistant must NEVER crash a page render
        pass


def research_link(label: str, doc_path: str, anchor: str | None = None) -> str:
    """Return a markdown link to a research doc on GitHub.

    All research docs live under ``docs/research/`` in the main repo
    and render natively on github.com (Mermaid + tables + footnotes).
    The dashboard surfaces "See also research →" links rather than
    embedding markdown directly so the doc stays the canonical surface.

    >>> research_link("PAIN-1 — can't prove what we did", "2026-04-aml-process-pain.md", "pain-1--we-cant-prove-what-we-did")
    '[PAIN-1 — can\\'t prove what we did](https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-aml-process-pain.md#pain-1--we-cant-prove-what-we-did)'
    """
    base = "https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/"
    href = f"{base}{doc_path}"
    if anchor:
        href = f"{href}#{anchor}"
    return f"[{label}]({href})"


def id_link(id_value: str, page_path: str, param: str) -> str:
    """Return a markdown deep link for an entity ID.

    Used by table renderers that want to expose plain-text IDs (rule
    IDs, case IDs, investigation IDs, customer IDs) as clickable links
    to the destination page that owns the detail.

    Pair with a markdown-table companion view inside an expander when
    consumers use ``st.dataframe``, since that widget doesn't render
    embedded markdown — the same pattern ``citation_link`` uses.

    Args:
        id_value: the entity ID to surface (e.g. ``"C0001"``).
        page_path: relative page filename without ``pages/`` or ``.py``
            (e.g. ``"17_Customer_360"``). Streamlit's page-link URL
            convention is ``./<filename>``.
        param: query-param name the destination reads via ``read_param``.

    Returns:
        Markdown anchor of the form
        ``[id_value](./page_path?param=id_value)``.

    >>> id_link("C0001", "17_Customer_360", "customer_id")
    '[C0001](./17_Customer_360?customer_id=C0001)'
    """
    return f"[{id_value}](./{page_path}?{param}={id_value})"


def citation_link(citation: str, url: str | None = None) -> str:
    """Return a markdown link for a regulation citation, or bare text.

    Specs declare ``regulation_refs[*].url`` for some citations and not
    others. Pages should not have to branch on that — this helper does
    it once: when ``url`` is present, the citation becomes a clickable
    markdown link; otherwise the citation renders as plain text.

    The dashboard's regulation tables, citations on Case Investigation,
    and the Audit & Evidence drift table all flow through this so
    populating ``url`` in a spec instantly makes that citation
    deep-linkable wherever it appears, without per-page edits.

    >>> citation_link("31 CFR 1020.320", "https://www.ecfr.gov/...")
    '[31 CFR 1020.320](https://www.ecfr.gov/...)'
    >>> citation_link("31 CFR 1020.320", None)
    '31 CFR 1020.320'
    >>> citation_link("31 CFR 1020.320", "")
    '31 CFR 1020.320'
    """
    if not url or not str(url).strip():
        return citation
    return f"[{citation}]({url})"


def see_also_footer(items: list[str]) -> None:
    """Render the standard 'See also · ' footer block.

    Used on every page that has cross-references (other dashboard pages,
    research docs, regulator-pulse events). Each item is a pre-formatted
    markdown link string — typically a mix of ``research_link(...)``
    output and bare ``[label](url)`` for in-app pages.

    Renders a divider above so the block reads as a footer, not as
    in-flow content.
    """
    if not items:
        return
    st.markdown("---")
    st.caption("**See also** · " + " · ".join(items))


def tooltip_banner(page_title: str, body: str) -> None:
    """Render the legacy "Guided demo" tooltip-style banner.

    Used when the user picks ``Mode: Tooltip mode`` in the sidebar.
    No-ops when no banner mode is active. Preserved so we don't lose
    the per-page context strings the legacy ``guided_demo`` toggle
    provided — they still have value in tooltip-only contexts.
    """
    if st.session_state.get("guided_mode") != "tooltip":
        return
    st.info(f"**Guided · {page_title}**\n\n{body}")


def tour_panel(page_title: str) -> None:
    """Render the guided-tour navigation card at the top of a page.

    Reads tour state from ``st.session_state``. No-ops if no tour is
    active. If the active tour is on a different page, shows a quiet
    "you've drifted off the tour" hint with a back-on-track button.

    The card is intentionally heavier than the legacy ``st.info``
    banner — it carries step counter, narrative, the concrete task,
    and three action buttons (Back / Skip / Next or Finish).
    """
    from aml_framework.dashboard import tour as tour_mod

    state = st.session_state
    if not tour_mod.is_active(state):
        return

    # Tour completion state — render a "finished" card.
    if tour_mod.is_complete(state):
        _render_complete_card(page_title)
        return

    step = tour_mod.current_step(state)
    if step is None:
        return

    # If the user navigated to a page that's not the current tour step,
    # show a soft hint instead of the full panel — don't hijack the page.
    if step.page_title != page_title:
        _render_off_track_hint(step)
        return

    cur, total = tour_mod.step_position(state)
    arc_label = state.get("tour_arc", "").upper()

    # Tour panel container — slate background, cyan accent border-left.
    st.markdown(
        f"""<div style="
            background: linear-gradient(135deg, #0f172a, #1e293b);
            border: 1px solid #334155;
            border-left: 4px solid #67e8f9;
            border-radius: 12px;
            padding: 20px 28px;
            margin-bottom: 16px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.2);
        ">
        <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:10px;">
          <div style="font-family: 'JetBrains Mono', monospace; font-size: 11px;
                      letter-spacing: 0.18em; text-transform: uppercase; color: #67e8f9;">
            🗺️ {arc_label} TOUR · STEP {cur} / {total}
          </div>
          <div style="font-family: 'JetBrains Mono', monospace; font-size: 11px;
                      color: #94a3b8; letter-spacing: 0.05em;">{step.duration}</div>
        </div>
        <div style="font-size: 18px; font-weight: 700; color: #f1f5f9; margin-bottom: 8px;">
          {step.step_title}
        </div>
        <div style="font-size: 14px; line-height: 1.6; color: #cbd5e1; margin-bottom: 12px;">
          {step.narrative}
        </div>
        <div style="font-size: 13px; color: #94a3b8; padding: 10px 14px;
                    background: rgba(103, 232, 249, 0.06); border-radius: 6px;
                    border-left: 2px solid #67e8f9;">
          <b style="color: #67e8f9; font-family: 'JetBrains Mono', monospace;
                   font-size: 11px; letter-spacing: 0.12em;">TRY THIS →</b>
          <span style="margin-left: 8px;">{step.task}</span>
        </div></div>""",
        unsafe_allow_html=True,
    )

    # Navigation row. Streamlit columns for native button widgets.
    col_back, col_skip, _, col_next = st.columns([1, 1, 3, 1])
    with col_back:
        if st.button(
            "← Back",
            key=f"tour_back_{cur}",
            disabled=(cur == 1),
            use_container_width=True,
        ):
            prev = tour_mod.retreat(state)
            if prev:
                st.switch_page(prev.page_path)
    with col_skip:
        if st.button("Skip tour", key=f"tour_skip_{cur}", use_container_width=True):
            tour_mod.end(state)
            st.rerun()
    with col_next:
        is_last = cur == total
        label = "Finish ✓" if is_last else "Next →"
        if st.button(label, key=f"tour_next_{cur}", type="primary", use_container_width=True):
            nxt = tour_mod.advance(state)
            if nxt:
                st.switch_page(nxt.page_path)
            else:
                # Reached completion — rerender to show completion card.
                st.rerun()


def _render_off_track_hint(step: Any) -> None:
    """Quiet banner when user has navigated away from the active tour step."""
    st.markdown(
        f"""<div style="
            background: rgba(103, 232, 249, 0.04);
            border: 1px dashed #67e8f9;
            border-radius: 8px;
            padding: 10px 16px;
            margin-bottom: 12px;
            font-size: 13px; color: #94a3b8;
        ">
        🗺️ Tour paused — you're off the recommended path. Next stop:
        <b style="color: #67e8f9;">{step.page_title}</b> ({step.step_title}).
        </div>""",
        unsafe_allow_html=True,
    )
    if st.button(f"↩ Back on track → {step.page_title}", key="tour_resume"):
        st.switch_page(step.page_path)


def _render_complete_card(page_title: str) -> None:
    """Tour-finished card. Offers Replay / End."""
    from aml_framework.dashboard import tour as tour_mod

    state = st.session_state
    arc_id = state.get("tour_arc", "")
    arc_label = arc_id.upper()

    st.markdown(
        f"""<div style="
            background: linear-gradient(135deg, rgba(134, 239, 172, 0.1), rgba(15, 23, 42, 1));
            border: 1px solid #16a34a;
            border-radius: 12px;
            padding: 24px 28px;
            margin-bottom: 16px;
        ">
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 11px;
                    letter-spacing: 0.18em; text-transform: uppercase; color: #86efac;
                    margin-bottom: 10px;">
          ✓ {arc_label} TOUR COMPLETE
        </div>
        <div style="font-size: 22px; font-weight: 700; color: #f1f5f9; margin-bottom: 8px;">
          You've walked the canonical {arc_label.lower()} arc.
        </div>
        <div style="font-size: 14px; line-height: 1.6; color: #cbd5e1;">
          Next up: explore other personas, drill into the data, or read the
          <a href="https://github.com/tomqwu/aml_open_framework" style="color: #67e8f9;">source</a>.
        </div></div>""",
        unsafe_allow_html=True,
    )
    col_replay, col_end, _ = st.columns([1, 1, 3])
    with col_replay:
        if st.button("↻ Replay tour", key="tour_replay", use_container_width=True):
            tour_mod.start(state, arc_id)
            step = tour_mod.current_step(state)
            if step:
                st.switch_page(step.page_path)
    with col_end:
        if st.button("End tour", key="tour_end_complete", use_container_width=True):
            tour_mod.end(state)
            st.rerun()


def kpi_card(label: str, value: Any, accent_color: str = "#2563eb") -> None:
    """Render a styled KPI card with colored left border.

    Note: prefer ``kpi_card_rag`` for new code — the ``accent_color``
    parameter on this helper traditionally received decorative-rainbow
    hex codes that carried no semantic meaning, conflicting with the
    RAG + severity color systems. Existing call sites are kept so the
    migration can land page-by-page.
    """
    st.markdown(
        f"""<div class="metric-card" style="border-left: 4px solid {accent_color};">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
        </div>""",
        unsafe_allow_html=True,
    )


# Neutral border for KPI cards that *report* a value (alerts: 17, rules
# active: 9) rather than *assess* it. Slate-400 — quiet enough that the
# RAG-colored cards next to it carry the visual signal.
KPI_NEUTRAL_BORDER = "#94a3b8"


def terminal_block(rows: list[tuple[str, str, str]]) -> None:
    """Render a compact terminal-style block of key/value rows.

    Each row is a tuple ``(key, value, kind)`` where ``kind`` is one of:
      - ``"hash"``  — cyan, fixed-width truncation supported via CSS
      - ``"ok"``    — green ("verified")
      - ``"warn"``  — amber
      - ``"bad"``   — red ("tamper detected")
      - ``""`` / anything else — neutral light slate

    Pulls toward Bloomberg/FactSet aesthetic for the Audit & Evidence
    page rather than the rounded-card SaaS look used elsewhere — the
    huashu-design 120%-on-one-page recommendation.
    """
    pieces = []
    for key, value, kind in rows:
        kind_class = f" {kind}" if kind in {"hash", "ok", "warn", "bad"} else ""
        pieces.append(
            f'<div class="row"><span class="key">{key}</span>'
            f'<span class="value{kind_class}">{value}</span></div>'
        )
    st.markdown(
        '<div class="terminal-block">' + "".join(pieces) + "</div>",
        unsafe_allow_html=True,
    )


def kpi_card_rag(label: str, value: Any, rag: str | None = None) -> None:
    """Render a KPI card whose left border is bound to RAG semantics.

    Args:
        label: KPI label (uppercase rendering handled by CSS).
        value: Metric value to display.
        rag: One of ``"green"`` / ``"amber"`` / ``"red"`` / ``"breached"`` /
            ``"unset"`` / ``None``. ``None`` and ``"unset"`` both produce
            the neutral slate border (KPI is a fact, not an assessment).

    Replaces the rainbow-decorative ``kpi_card(..., accent_color=...)``
    pattern flagged in the design review. Color now carries one job:
    "this metric is in a good / warning / bad state".
    """
    if rag and rag != "unset":
        color = RAG_COLORS.get(rag) or SLA_BAND_COLORS.get(rag) or KPI_NEUTRAL_BORDER
    else:
        color = KPI_NEUTRAL_BORDER
    st.markdown(
        f"""<div class="metric-card" style="border-left: 4px solid {color};">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def headline_hero(tiles: list[dict[str, Any]]) -> None:
    """Render a 3-tile board-pack hero strip.

    The Executive Dashboard's first screen for board members. Each tile
    is a dict with:

      - ``label`` (str) — uppercase tile label
      - ``value`` (str | int) — the headline number
      - ``rag`` (str | None) — colour band; tile 1 (the urgent one) gets
        a heavier accent border, tiles 2 and 3 get the neutral kpi-card
        treatment scaled up
      - ``caption`` (str, optional) — small line under the value
        (e.g., "12 SLA-at-risk · 3 closed-no-action")
      - ``href`` (str, optional) — drill-through link rendered as a
        compact arrow under the caption

    The first tile is rendered ~1.4x the size of the others — visual
    hierarchy is the point.

    Pulls only from existing tokens (RAG_COLORS, KPI_NEUTRAL_BORDER) so
    no new colour gets invented per the design memory.
    """
    if len(tiles) != 3:
        raise ValueError("headline_hero expects exactly 3 tiles (got %d)" % len(tiles))

    # Wrapper grid: hero gets 2x the column width of secondary tiles.
    cols = st.columns([2, 1, 1])
    for col, tile, is_hero in zip(cols, tiles, [True, False, False], strict=False):
        rag = tile.get("rag")
        accent = (
            RAG_COLORS.get(rag) or SLA_BAND_COLORS.get(rag or "") if rag else KPI_NEUTRAL_BORDER
        ) or KPI_NEUTRAL_BORDER
        # Hero tile: thicker border (8px), larger value font, optional badge.
        border_w = "8px" if is_hero else "4px"
        value_fs = "3.6rem" if is_hero else "2.4rem"
        label_fs = "0.95rem" if is_hero else "0.85rem"
        caption_html = ""
        if tile.get("caption"):
            caption_html = (
                f'<div style="color:#475569;font-size:0.85rem;margin-top:0.4rem;">'
                f"{tile['caption']}</div>"
            )
        href_html = ""
        if tile.get("href"):
            href_html = (
                f'<div style="margin-top:0.5rem;"><a href="{tile["href"]}" '
                f'style="color:#2563eb;text-decoration:none;font-size:0.85rem;'
                f'font-weight:600;">{tile.get("href_label", "→ open")}</a></div>'
            )
        bg_overlay = ""
        if is_hero and rag in {"red", "amber", "green"}:
            # Subtle tint (4% opacity hex via the closing 0a) on hero only —
            # makes the urgent number unmissable without crossing into noise.
            tint_pct = "0a"  # 4% opacity
            bg_overlay = f"background: linear-gradient(180deg, {accent}{tint_pct} 0%, white 100%);"
        with col:
            st.markdown(
                f"""<div class="metric-card animate-on-load" style="border-left: {border_w} solid {accent}; {bg_overlay} padding: 1.4rem 1.5rem;">
                    <div class="label" style="font-size:{label_fs};letter-spacing:0.06em;text-transform:uppercase;color:#64748b;font-weight:600;">{tile["label"]}</div>
                    <div class="value" style="font-size:{value_fs};font-weight:700;line-height:1.05;color:#0f172a;margin-top:0.4rem;">{tile["value"]}</div>
                    {caption_html}
                    {href_html}
                </div>""",
                unsafe_allow_html=True,
            )


def kpi_card_with_trend(
    label: str,
    value: Any,
    trend_values: list[float] | None = None,
    rag: str | None = None,
    delta_pct: float | None = None,
    delta_dir: str = "neutral",
) -> None:
    """KPI card with an inline sparkline + delta-vs-prior-run string.

    Args:
        label / value / rag — same as ``kpi_card_rag``.
        trend_values: list of numeric values (oldest→newest, including
            the current run as the last element). When fewer than 2
            values are supplied the sparkline is suppressed and the
            delta slot reads "(no prior runs)".
        delta_pct: signed pct change of the current run vs the previous
            (e.g., +12.0 for "12% higher than last run"). When ``None``
            the delta string is suppressed.
        delta_dir: ``"higher-better"`` / ``"lower-better"`` / ``"neutral"``.
            Drives the colour of the sparkline + delta arrow:
              - ``higher-better``: green when delta_pct > 0, amber when < 0
              - ``lower-better``: green when delta_pct < 0, amber when > 0
              - ``neutral``: grey
    """
    if rag and rag != "unset":
        color = RAG_COLORS.get(rag) or SLA_BAND_COLORS.get(rag) or KPI_NEUTRAL_BORDER
    else:
        color = KPI_NEUTRAL_BORDER

    # Spark + delta block markup.
    spark_html = ""
    delta_html = ""
    if trend_values and len(trend_values) >= 2:
        # Inline SVG sparkline — Plotly is overkill at this size and
        # adds layout shift on first paint. The SVG is one path scaled
        # to a 100x32 viewbox; works without JS.
        vmin = min(trend_values)
        vmax = max(trend_values)
        rng = (vmax - vmin) or 1
        n = len(trend_values)
        pts = []
        for i, v in enumerate(trend_values):
            x = (i / (n - 1)) * 100
            y = 28 - ((v - vmin) / rng) * 24  # 4..28 px in a 32-px tall canvas
            pts.append(f"{x:.1f},{y:.1f}")
        spark_color = {
            "higher-better": RAG_COLORS["green"] if (delta_pct or 0) >= 0 else RAG_COLORS["amber"],
            "lower-better": RAG_COLORS["green"] if (delta_pct or 0) <= 0 else RAG_COLORS["amber"],
            "neutral": "#64748b",
        }.get(delta_dir, "#64748b")
        spark_html = (
            f'<svg viewBox="0 0 100 32" preserveAspectRatio="none" style="width:100%;height:32px;'
            f'margin-top:0.4rem;display:block;">'
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{spark_color}" '
            f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />'
            f"</svg>"
        )
        if delta_pct is not None:
            arrow = "↑" if delta_pct > 0 else ("↓" if delta_pct < 0 else "→")
            sign = "+" if delta_pct > 0 else ""
            delta_html = (
                f'<div style="color:{spark_color};font-size:0.8rem;font-weight:600;'
                f'margin-top:0.25rem;">{arrow} {sign}{delta_pct:.1f}% vs last run</div>'
            )
    else:
        delta_html = (
            '<div style="color:#94a3b8;font-size:0.78rem;margin-top:0.4rem;">(no prior runs)</div>'
        )

    st.markdown(
        f"""<div class="metric-card animate-on-load" style="border-left: 4px solid {color};">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
            {spark_html}
            {delta_html}
        </div>""",
        unsafe_allow_html=True,
    )


def rag_dot_html(rag: str) -> str:
    """Return an HTML colored dot."""
    color = RAG_COLORS.get(rag, RAG_COLORS["unset"])
    return f'<span class="rag-dot" style="background:{color};"></span>'


def severity_badge(severity: str) -> str:
    """Return an HTML badge for severity."""
    color = SEVERITY_COLORS.get(severity, "#6b7280")
    return (
        f'<span style="background:{color}; color:white; padding:2px 10px; '
        f'border-radius:12px; font-size:0.78rem; font-weight:600;">'
        f"{severity}</span>"
    )


# ---------------------------------------------------------------------------
# Color resolvers — single source of truth, replacing per-page dicts
# ---------------------------------------------------------------------------


def severity_color(severity: str) -> str:
    """Resolve a severity string to its hex color.

    Replaces the per-page `_sev_style` / `colors = {...}` dicts that
    drifted apart across pages #4, #5, #12, #17, #21, #22.
    """
    return SEVERITY_COLORS.get((severity or "").lower(), "#6b7280")


def sla_band_color(state: str) -> str:
    """Resolve a `cases/sla.py` SLA band ('green'/'amber'/'red'/'breached')
    to its hex color. Used by the SLA timer ring + backlog tables."""
    return SLA_BAND_COLORS.get((state or "").lower(), SLA_BAND_COLORS["unknown"])


def risk_color(rating: str) -> str:
    """Resolve a customer risk-rating ('high'/'medium'/'low') to its
    hex color. Replaces inline `risk_colors = {...}` dicts in pages
    #6, #10, #17, #18 (workflow audit catch — Phase E follow-up)."""
    return RISK_RATING_COLORS.get((rating or "").lower(), RISK_RATING_COLORS["unknown"])


# ---------------------------------------------------------------------------
# Pandas Styler helpers — make read-only tables carry semantic colour
# without each page redeclaring its own _highlight_X / _status_color fns
# ---------------------------------------------------------------------------


def _styled_text(color: str | None, weight: str = "700") -> str:
    """Return a Styler cell rule, or empty when colour resolution fell back
    to the neutral grey (we leave such cells uncoloured to avoid suggesting
    semantic meaning where none exists)."""
    if not color or color in (RAG_COLORS["unset"], "#6b7280"):
        return ""
    return f"color: {color}; font-weight: {weight};"


def severity_cell_style(value: Any) -> str:
    """`Styler.map` callback — returns CSS for a severity-string cell.

    Use as ``df.style.map(severity_cell_style, subset=["severity"])``.
    Values are matched case-insensitively against ``SEVERITY_COLORS``;
    unknown values render plain.
    """
    if not isinstance(value, str):
        return ""
    return _styled_text(SEVERITY_COLORS.get(value.lower()))


def rag_cell_style(value: Any) -> str:
    """`Styler.map` callback for RAG-band cells.

    Accepts ``green``/``amber``/``red``/``breached``/``unset`` (case-
    insensitive). ``unset`` renders neutral. Reuses ``RAG_COLORS`` +
    ``SLA_BAND_COLORS`` so SLA breach state is also coloured correctly
    when the column carries that vocabulary.
    """
    if not isinstance(value, str):
        return ""
    key = value.lower()
    color = RAG_COLORS.get(key) or SLA_BAND_COLORS.get(key)
    return _styled_text(color)


def metric_gradient_style(
    low_color: str = "#dc2626",  # red
    mid_color: str = "#d97706",  # amber
    high_color: str = "#16a34a",  # green
    *,
    low_threshold: float = 0.5,
    high_threshold: float = 0.8,
) -> Any:
    """Return a `Styler.map` callback that colours numeric cells red→amber→green.

    Used for precision/recall/F1 cells on Tuning Lab — values below
    ``low_threshold`` are red, above ``high_threshold`` green, in between
    amber. Designed for [0, 1] metrics; the thresholds are adjustable
    when callers want a different break point.
    """

    def _style(value: Any) -> str:
        if value is None or isinstance(value, str):
            return ""
        try:
            v = float(value)
        except (TypeError, ValueError):
            return ""
        if v >= high_threshold:
            color = high_color
        elif v >= low_threshold:
            color = mid_color
        else:
            color = low_color
        return _styled_text(color)

    return _style


def event_type_cell_style(value: Any) -> str:
    """`Styler.map` callback for audit-decision event-type cells.

    Maps the controlled vocabulary the audit ledger emits onto a small
    palette so analysts scanning the decision log can spot escalations
    + resolutions without reading every row.
    """
    if not isinstance(value, str):
        return ""
    table = {
        # Negative / escalation events — red
        "alert": "#dc2626",
        "escalate": "#dc2626",
        "snooze": "#dc2626",
        # Workflow / triage — amber
        "transition": "#d97706",
        "tuning_run": "#d97706",
        "control_review": "#d97706",
        # Closure / positive — green
        "close": "#16a34a",
        "resolve": "#16a34a",
        "filed": "#16a34a",
        "ack": "#16a34a",
        "acknowledge": "#16a34a",
    }
    return _styled_text(table.get(value.lower()))


# ---------------------------------------------------------------------------
# Empty-state helper — kills the inconsistent st.warning/info/error pattern
# ---------------------------------------------------------------------------


def empty_state(
    message: str,
    *,
    icon: str = "ℹ️",
    detail: str | None = None,
    stop: bool = False,
) -> None:
    """Render a consistent empty-state block.

    Replaces the ad-hoc `st.warning(...) + st.stop()` patterns scattered
    across pages #3, #4, #21, #24. Operators see the same shape every
    time so they learn it once.

    Args:
        message: short headline (e.g. "No alerts in this run.")
        icon: leading emoji or icon string
        detail: optional secondary line — what the operator should do next
        stop: when True, calls `st.stop()` after rendering — for pages
            that genuinely can't proceed without the missing data
    """
    body = f"### {icon} {message}"
    if detail:
        body += f"\n\n{detail}"
    st.info(body)
    if stop:
        st.stop()


# ---------------------------------------------------------------------------
# Cross-page navigation helper — query-param-based deep links
# ---------------------------------------------------------------------------


def link_to_page(
    page_path: str,
    label: str,
    **query_params: Any,
) -> None:
    """Render a Streamlit page link with optional query params.

    Wraps `st.page_link` to give us one place to format URLs consistently
    when we add deep-linking (e.g. an Alert Queue row links to
    `Customer 360` with `?customer_id=C0001`). Streamlit reads query
    params from the URL and the destination page calls
    `query_params.read_param('customer_id')` to pre-select.

    Args:
        page_path: relative page filename, e.g. "pages/17_Customer_360.py"
        label: clickable text shown to the user
        **query_params: optional URL params; written to session state via
            the `selected_*` convention so destination pages can read them
            from `st.session_state` (Streamlit's `st.page_link` doesn't
            yet pass query params natively).
    """
    if query_params:
        # Streamlit's st.page_link doesn't currently pass query params on
        # navigation, so we stash them in session state under the same
        # `selected_<key>` namespace that destination pages already use.
        for key, value in query_params.items():
            st.session_state[f"selected_{key}"] = value
    st.page_link(page_path, label=label)


def selectable_dataframe(
    df: Any,
    *,
    key: str,
    drill_target: str | None = None,
    drill_param: str | None = None,
    drill_column: str | None = None,
    hint: str | None = "Click any row to open the detail view.",
    **dataframe_kwargs: Any,
) -> Any:
    """Render a dataframe whose rows drill through to a target page on click.

    Replaces the older "selectbox-below-the-table" pattern: instead of
    repeating each row's primary key in a dropdown, the table itself is
    the picker — click a row → set ``selected_<drill_param>`` in session
    state → ``st.switch_page(drill_target)``. Built on Streamlit ≥1.34's
    ``st.dataframe(on_select="rerun", selection_mode="single-row")``.

    Args:
        df: a ``pandas.DataFrame`` or ``pandas.io.formats.style.Styler``.
            For a Styler, the underlying frame is read via ``df.data``
            so the click handler can look up the drill value.
        key: required Streamlit widget key — selection state is keyed
            by this, so two tables on the same page must use distinct keys.
        drill_target: relative page path (e.g. ``"pages/17_Customer_360.py"``).
            ``None`` disables drill-through (table is just selectable).
        drill_param: query-param name (e.g. ``"customer_id"``) used by the
            destination page's ``read_param`` / ``consume_param`` call.
        drill_column: column in the underlying frame holding the drill
            value (e.g. ``"customer_id"``). Falls back silently when the
            column is missing or the value is null.
        hint: caption shown above the table; pass ``None`` to suppress.
        **dataframe_kwargs: forwarded to ``st.dataframe`` (height,
            column_config, etc).

    Returns:
        The Streamlit selection-state object (``event``) so callers can
        inspect ``event.selection.rows`` for non-drill use cases. Drill
        navigation calls ``st.switch_page`` and never returns.
    """
    if hint and drill_target:
        st.caption(hint)

    underlying = df.data if hasattr(df, "data") else df

    event = st.dataframe(
        df,
        on_select="rerun",
        selection_mode="single-row",
        key=key,
        **dataframe_kwargs,
    )

    if not (drill_target and drill_param and drill_column):
        return event

    rows = getattr(getattr(event, "selection", None), "rows", None) or []
    if not rows:
        return event

    try:
        idx = rows[0]
        if drill_column not in underlying.columns:
            return event
        value = underlying.iloc[idx][drill_column]
    except (IndexError, KeyError, AttributeError):
        return event

    if pd.isna(value):
        return event

    # Mirror into session state under the `selected_<param>` convention
    # query_params.read_param / consume_param expect, then jump.
    st.session_state[f"selected_{drill_param}"] = str(value)
    st.switch_page(drill_target)
    return event  # unreachable; switch_page halts the script


def metric_table(metrics: list[MetricResult], audience: str | None = None) -> None:
    """Render a styled metric summary table with colored RAG dots."""
    filtered = metrics
    if audience:
        filtered = [m for m in metrics if audience in m.audience]

    if not filtered:
        st.info("No metrics for this audience.")
        return

    rows = []
    for m in filtered:
        rows.append(
            {
                "RAG": m.rag.upper() if m.rag != "unset" else "-",
                "Metric": m.name,
                "Category": m.category,
                "Value": _fmt_value(m),
                "Owner": m.owner or "\u2014",
            }
        )

    df = pd.DataFrame(rows)

    def _color_rag(val: str) -> str:
        colors = {"GREEN": "#16a34a", "AMBER": "#d97706", "RED": "#dc2626"}
        c = colors.get(val, "#94a3b8")
        return f"color: {c}; font-weight: 700;"

    styled = df.style.map(_color_rag, subset=["RAG"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


def _fmt_value(m: MetricResult) -> str:
    if m.unit == "%":
        return f"{m.value * 100:.1f}%"
    if m.unit in ("usd", "USD", "CAD", "cad"):
        return f"${m.value:,.0f}"
    if m.unit == "hours":
        return f"{m.value:.1f}h"
    if isinstance(m.value, float) and not m.value.is_integer():
        return f"{m.value:.3f}"
    return str(int(m.value)) if float(m.value).is_integer() else str(m.value)


def chart_layout(fig: Any, height: int = 380) -> Any:
    """Apply consistent chart styling."""
    fig.update_layout(
        template=CHART_TEMPLATE,
        height=height,
        margin=dict(t=30, b=30, l=20, r=20),
        font=dict(family="Inter, system-ui, sans-serif", size=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# Glossary helpers live in `dashboard/glossary.py` (a pandas/streamlit-
# free module so unit-tests CI can import them) and are re-exported here
# for backwards compatibility. Pages still do
# `from aml_framework.dashboard.components import glossary_legend`.
from aml_framework.dashboard.glossary import (  # noqa: E402,F401
    GLOSSARY,
    glossary_legend,
    glossary_term,
)


# ---------------------------------------------------------------------------
# GenAI Assistant panel — PR-K MVP
# ---------------------------------------------------------------------------
# A single `ai_panel(page=...)` call wires the sidebar widget into every
# page via `page_header()`. The widget is intentionally small: textarea,
# submit, last reply. Power-user views and the run-level audit trail
# live on the dedicated `29_AI_Assistant` page.
#
# Compliance posture:
#   - Default backend is `template` (canned scaffolding, no LLM call).
#     Operator opts into `ollama` / `openai` via `AML_AI_BACKEND` env.
#   - Every reply is logged to `ai_interactions.jsonl` in run_dir; the
#     spec's `program.ai_audit_log` flag controls whether the full
#     reply text or just a SHA-256 hash is written.
#   - Every reply is rendered with a "DRAFT — analyst review required"
#     banner. Citations (rule_id / metric_id / case_id) link back into
#     the dashboard via the deep-link convention from PR-A / PR-H.
#   - `try / except` wrap around the entire panel — a misconfigured
#     LLM never breaks the dashboard.


def ai_panel(*, page: str) -> None:
    """Render the GenAI assistant sidebar widget for this page.

    Mounted automatically by `page_header()` so every dashboard page
    inherits it. Reads run + persona + selected-entity state from
    `st.session_state`; backend is selected via the `AML_AI_BACKEND`
    environment variable (defaults to `template`).
    """
    import os

    if "ai_transcript" not in st.session_state:
        st.session_state["ai_transcript"] = {}

    backend_name = os.environ.get("AML_AI_BACKEND", "template").lower()

    with st.sidebar:
        st.markdown("---")
        # Backend pill — operator sees what's running before submitting.
        # `template` = grey (no LLM); `ollama` = green (local); `openai` = cyan (cloud).
        pill_color = {"template": "#94a3b8", "ollama": "#16a34a", "openai": "#67e8f9"}.get(
            backend_name, "#94a3b8"
        )
        st.markdown(
            f'<div style="display:flex; align-items:center; gap:8px; '
            f'margin-bottom:6px;">'
            f'<span style="width:8px; height:8px; border-radius:50%; '
            f'background:{pill_color}; box-shadow:0 0 6px {pill_color};"></span>'
            f'<span style="font-family:JetBrains Mono,monospace; font-size:11px; '
            f'letter-spacing:0.05em; text-transform:uppercase; color:#94a3b8;">'
            f"AI Assistant · {backend_name}</span></div>",
            unsafe_allow_html=True,
        )

        question_key = f"ai_question_{page}"
        question = st.text_area(
            "Ask the assistant",
            key=question_key,
            height=88,
            placeholder="e.g. why is channel_coverage_gap red on this run?",
            label_visibility="collapsed",
        )

        if backend_name == "openai":
            st.caption("⚠️ PII may be transmitted to OpenAI. Use `ollama` for on-prem inference.")

        if st.button("Ask", key=f"ai_ask_{page}", use_container_width=True):
            _handle_ai_submission(page=page, question=question, backend_name=backend_name)

        # Last reply on this page (one-shot Q&A in MVP — no multi-turn).
        last_reply = st.session_state["ai_transcript"].get(page)
        if last_reply is not None:
            _render_assistant_reply(last_reply)


def _handle_ai_submission(*, page: str, question: str, backend_name: str) -> None:
    """Build context, call backend, log to audit ledger, store reply."""
    if not question.strip():
        st.toast("Type a question first.", icon="ℹ️")
        return

    from aml_framework.assistant.factory import get_assistant
    from aml_framework.assistant.models import AssistantContext, reply_to_audit_dict

    spec = st.session_state.get("spec")
    result = st.session_state.get("result")
    df_alerts = st.session_state.get("df_alerts")
    df_cases = st.session_state.get("df_cases")
    df_decisions = st.session_state.get("df_decisions")

    context = AssistantContext(
        page=page,
        persona=st.session_state.get("selected_audience"),
        spec_name=getattr(getattr(spec, "program", None), "name", "") or "",
        spec_jurisdiction=getattr(getattr(spec, "program", None), "jurisdiction", "") or "",
        spec_regulator=getattr(getattr(spec, "program", None), "regulator", "") or "",
        rule_count=len(getattr(spec, "rules", [])) if spec else 0,
        metric_count=len(getattr(spec, "metrics", [])) if spec else 0,
        run_id=str(getattr(result, "run_id", "")) if result else "",
        alert_count=len(df_alerts) if df_alerts is not None else 0,
        case_count=len(df_cases) if df_cases is not None else 0,
        decision_count=len(df_decisions) if df_decisions is not None else 0,
        selected_customer_id=st.session_state.get("selected_customer_id"),
        selected_case_id=st.session_state.get("selected_case_id"),
        selected_rule_id=st.session_state.get("selected_rule_id"),
        selected_metric_id=st.session_state.get("selected_metric_id"),
    )

    try:
        assistant = get_assistant(backend_name)
        reply = assistant.reply(question, context)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Assistant backend `{backend_name}` failed: {exc}")
        # Always fall back to template so the panel never silent-fails.
        from aml_framework.assistant.template import TemplateBackend

        reply = TemplateBackend().reply(question, context)

    st.session_state["ai_transcript"][page] = reply

    # Audit-log every interaction. `program.ai_audit_log` decides whether
    # the full reply text or its SHA-256 hash is written. Errors are
    # swallowed — the panel must never break a page render.
    try:
        from pathlib import Path

        from aml_framework.engine.audit import AuditLedger

        run_dir = st.session_state.get("run_dir")
        if run_dir is None:
            return
        audit_mode = getattr(getattr(spec, "program", None), "ai_audit_log", "hash_only")
        row = reply_to_audit_dict(reply, full_text=(audit_mode == "full_text"))
        row["question"] = question.strip()
        AuditLedger.append_to_run_dir(
            Path(run_dir),
            {"event": "ai_interaction", **row},
            jsonl_name="ai_interactions.jsonl",
        )
    except Exception:  # noqa: BLE001
        pass


def _render_assistant_reply(reply: Any) -> None:
    """Render an AssistantReply in the sidebar.

    DRAFT banner + body + citation chips + confidence badge. Citation
    chips link back into the dashboard via the deep-link convention.
    """
    confidence_color = {"high": "#16a34a", "medium": "#d97706", "low": "#94a3b8"}.get(
        getattr(reply, "confidence", "low"), "#94a3b8"
    )

    st.markdown(
        '<div style="font-family:JetBrains Mono,monospace; font-size:10px; '
        "letter-spacing:0.08em; text-transform:uppercase; color:#dc2626; "
        'margin-top:12px; margin-bottom:6px;">DRAFT · analyst review required</div>',
        unsafe_allow_html=True,
    )
    st.markdown(reply.text)

    # Confidence + citation summary
    citation_count = len(getattr(reply, "citations", []) or [])
    metric_count = len(getattr(reply, "referenced_metric_ids", []) or [])
    case_count = len(getattr(reply, "referenced_case_ids", []) or [])
    st.markdown(
        f'<div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:8px;">'
        f'<span style="font-family:JetBrains Mono,monospace; font-size:10px; '
        f"padding:2px 6px; border-radius:3px; background:{confidence_color}22; "
        f'color:{confidence_color}; font-weight:600;">'
        f"confidence · {reply.confidence}</span>"
        f'<span style="font-family:JetBrains Mono,monospace; font-size:10px; '
        f'color:#64748b;">{citation_count} citation(s) · '
        f"{metric_count} metric(s) · {case_count} case(s)</span>"
        "</div>",
        unsafe_allow_html=True,
    )
