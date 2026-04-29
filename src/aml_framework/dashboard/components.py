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
/* ---- Global ---- */
.block-container { padding-top: 1.5rem; padding-bottom: 1rem; }

/* ---- Hide Streamlit Cloud chrome ----
 * Compliance dashboards are shipped through tenants' own infrastructure;
 * the public "Deploy" button + 3-dot menu look unprofessional in that
 * context and confuse non-technical users (e.g. CCOs reviewing on tablets).
 */
.stDeployButton,
[data-testid="stToolbar"],
[data-testid="stStatusWidget"] { display: none !important; }

/* ---- Sidebar ---- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
}
section[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    font-size: 0.88rem;
    line-height: 1.5;
}
section[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.12) !important;
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

/* ---- Page headers ---- */
h1 { font-weight: 700 !important; color: #0f172a !important; }
h2 { font-weight: 600 !important; color: #1e293b !important; }
h3 { font-weight: 600 !important; color: #334155 !important; }

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
    """Consistent page header."""
    st.markdown(f"# {title}")
    if description:
        st.caption(description)
    st.divider()


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
    """Render a styled KPI card with colored left border."""
    st.markdown(
        f"""<div class="metric-card" style="border-left: 4px solid {accent_color};">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
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
