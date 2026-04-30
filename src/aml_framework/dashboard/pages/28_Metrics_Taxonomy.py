"""Metrics Taxonomy — browseable catalogue of every metric the spec declares.

Sister page to `18_Typology_Catalogue.py` (which catalogues rules /
typologies). The Metrics Taxonomy gives senior personas — CCO, MLRO,
PM, Auditor — a single screen that answers:

  - What metrics does this program track?
  - Grouped by which 5 categories (operational / effectiveness /
    risk / regulatory / delivery)?
  - With what targets + RAG bands? Owned by whom?
  - And what's the metric's current live value + RAG status?

Without this page, operators read YAML to inspect the metrics block.
The FinCEN AML Effectiveness NPRM and AMLA RTS both pressure programs
to declare what they measure for effectiveness — this view turns the
spec's `metrics:` block into a defendable artifact.

Page layout (mirrors the Typology Catalogue's accordion-of-cards
pattern, plus the PR-A through PR-H polish: filters, RAG colour,
see-also footer):

  1. KPI strip — total / categories / with-targets / owners assigned
  2. Filters — category × audience × formula × "only with targets"
  3. Per-category accordion of metric cards with live RAG colour
  4. See-also footer (Executive Dashboard / Comparative Analytics
     / Spec Editor / FinCEN AML Effectiveness NPRM)
"""

from __future__ import annotations

import yaml
import streamlit as st

from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import (
    KPI_NEUTRAL_BORDER,
    RAG_COLORS,
    empty_state,
    glossary_legend,
    kpi_card_rag,
    page_header,
    research_link,
    see_also_footer,
)

PAGE_TITLE = "Metrics Taxonomy"

page_header(
    PAGE_TITLE,
    "What this program measures — by category, owner, target, and live RAG. "
    "The defendable counterpart to the Typology Catalogue.",
)
show_audience_context(PAGE_TITLE)

spec = st.session_state.spec
result = st.session_state.result

# ---------------------------------------------------------------------------
# Empty-state guard — a spec with zero metrics is rare but valid (e.g.,
# a brand-new spec being authored). Halt cleanly with actionable detail.
# ---------------------------------------------------------------------------

if not spec.metrics:
    empty_state(
        "This spec declares zero metrics — nothing to catalogue.",
        icon="📐",
        detail=(
            "Add a `metrics:` block to your spec. Each metric needs an "
            "`id`, `name`, `category` (operational/effectiveness/risk/"
            "regulatory/delivery), `audience`, and a `formula` (count / "
            "sum / ratio / coverage / sql). See `docs/specs/metrics.md` "
            "for the schema and `examples/canadian_schedule_i_bank/"
            "aml.yaml` for a worked example."
        ),
        stop=True,
    )

# ---------------------------------------------------------------------------
# Live-value lookup — map metric.id → MetricResult so cards can show the
# current value + RAG band when the engine has computed it.
# ---------------------------------------------------------------------------

metrics_by_id = {m.id: m for m in result.metrics}

# ---------------------------------------------------------------------------
# Section 1 — KPI strip
# ---------------------------------------------------------------------------

categories_used = sorted({m.category for m in spec.metrics})
with_targets = sum(1 for m in spec.metrics if m.target or m.thresholds)
owners_assigned = sum(1 for m in spec.metrics if m.owner)
total = len(spec.metrics)


# RAG: green if every metric has a target / owner; amber if some; red
# if none. Mirrors PR-B's "fact vs assessment" colour discipline —
# total + categories are facts (neutral), with-targets + owners-assigned
# carry an assessment of program completeness.
def _completeness_rag(present: int, n: int) -> str | None:
    if n == 0:
        return None
    if present == n:
        return "green"
    if present == 0:
        return "red"
    return "amber"


k1, k2, k3, k4 = st.columns(4)
with k1:
    kpi_card_rag("Total metrics", total)
with k2:
    kpi_card_rag("Categories used", f"{len(categories_used)} / 5")
with k3:
    kpi_card_rag(
        "With targets",
        f"{with_targets} / {total}",
        rag=_completeness_rag(with_targets, total),
    )
with k4:
    kpi_card_rag(
        "Owners assigned",
        f"{owners_assigned} / {total}",
        rag=_completeness_rag(owners_assigned, total),
    )

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 2 — Filters
# ---------------------------------------------------------------------------

ALL_CATEGORIES = ["operational", "effectiveness", "risk", "regulatory", "delivery"]
ALL_FORMULAS = ["count", "sum", "ratio", "coverage", "sql"]
ALL_AUDIENCES = sorted({a for m in spec.metrics for a in m.audience})

active_audience = st.session_state.get("selected_audience")
default_audiences = (
    [active_audience] if active_audience and active_audience in ALL_AUDIENCES else ALL_AUDIENCES
)

fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 1])
with fc1:
    selected_categories = st.multiselect(
        "Filter by category",
        options=ALL_CATEGORIES,
        default=ALL_CATEGORIES,
        help="Five categories from the spec schema's MetricCategory enum.",
    )
with fc2:
    selected_audiences = st.multiselect(
        "Filter by audience",
        options=ALL_AUDIENCES,
        default=default_audiences,
        help="Defaults to the persona you picked in the sidebar.",
    )
with fc3:
    selected_formulas = st.multiselect(
        "Filter by formula type",
        options=ALL_FORMULAS,
        default=ALL_FORMULAS,
        help="count / sum / ratio / coverage / sql.",
    )
with fc4:
    only_with_targets = st.toggle(
        "Only with targets",
        value=False,
        help="Surface just the metrics that carry RAG bands.",
    )


def _passes_filter(metric) -> bool:
    if metric.category not in selected_categories:
        return False
    if not (set(metric.audience) & set(selected_audiences)):
        return False
    if metric.formula.type not in selected_formulas:
        return False
    if only_with_targets and not (metric.target or metric.thresholds):
        return False
    return True


filtered = [m for m in spec.metrics if _passes_filter(m)]

st.caption(f"Showing **{len(filtered)}** of **{total}** metrics across this spec.")

# ---------------------------------------------------------------------------
# Section 3 — Per-category accordion of cards
# ---------------------------------------------------------------------------


def _format_target(target: dict | None) -> str | None:
    """Render a target / threshold dict as a glanceable string."""
    if not target:
        return None
    parts = []
    for op, val in target.items():
        symbol = {
            "lte": "≤",
            "gte": "≥",
            "lt": "<",
            "gt": ">",
            "eq": "=",
            "between": "in",
        }.get(op, op)
        parts.append(f"{symbol} {val}")
    return ", ".join(parts)


def _render_metric_card(metric) -> None:
    """Render one metric as a card with RAG accent + live value strip."""
    live = metrics_by_id.get(metric.id)
    # Accent bar: live RAG when computed, else neutral grey.
    band = live.rag if live and live.rag in RAG_COLORS else None
    accent = RAG_COLORS.get(band) if band else KPI_NEUTRAL_BORDER

    audience_str = " · ".join(metric.audience)
    owner_html = (
        f'<span style="color:#0f172a;">{metric.owner}</span>'
        if metric.owner
        else f'<span style="color:{KPI_NEUTRAL_BORDER}; font-style:italic;">no owner</span>'
    )
    unit_str = f" {metric.unit}" if metric.unit else ""

    target_str = _format_target(metric.target)
    bands_html = ""
    if metric.thresholds:
        band_chips = []
        for band_name in ("green", "amber", "red"):
            cond = metric.thresholds.get(band_name)
            if cond:
                color = RAG_COLORS.get(band_name, KPI_NEUTRAL_BORDER)
                cond_str = _format_target(cond) or ""
                band_chips.append(
                    f'<span style="background:{color}18; color:{color}; '
                    f"padding:0.1rem 0.4rem; border-radius:4px; font-size:0.72rem; "
                    f'font-weight:700;">{band_name}: {cond_str}</span>'
                )
        if band_chips:
            bands_html = (
                '<div style="display:flex; gap:0.4rem; flex-wrap:wrap; margin-top:0.4rem;">'
                + "".join(band_chips)
                + "</div>"
            )

    live_html = ""
    if live is not None:
        rag_color = RAG_COLORS.get(live.rag, KPI_NEUTRAL_BORDER)
        target_met_label = ""
        if live.target_met is True:
            target_met_label = ' <span style="color:#16a34a; font-weight:700;">· on target</span>'
        elif live.target_met is False:
            target_met_label = ' <span style="color:#dc2626; font-weight:700;">· off target</span>'
        live_html = (
            f'<div style="margin-top:0.5rem; padding:0.4rem 0.6rem; background:#f8fafc; '
            f'border-radius:6px; font-size:0.85rem;">'
            f'<span style="color:#64748b; text-transform:uppercase; letter-spacing:0.04em; '
            f'font-size:0.7rem;">Current run</span><br>'
            f'<span style="font-size:1.05rem; font-weight:700; color:{rag_color};">'
            f"{live.value}{unit_str}</span>"
            f'<span style="color:{rag_color}; font-weight:700; '
            f'text-transform:uppercase; margin-left:0.5rem;">{live.rag}</span>'
            f"{target_met_label}"
            f"</div>"
        )

    desc_html = (
        f'<div style="font-size:0.85rem; color:#475569; margin:0.3rem 0;">{metric.description}</div>'
        if metric.description
        else ""
    )

    st.markdown(
        f'<div class="metric-card" style="border-left:4px solid {accent}; margin-bottom:0.6rem;">'
        f'<div style="display:flex; justify-content:space-between; align-items:baseline;">'
        f'<div style="font-weight:600; font-size:1.0rem;">{metric.name}</div>'
        f'<code style="font-size:0.78rem; color:#64748b;">{metric.id}</code>'
        f"</div>"
        f"{desc_html}"
        f'<div style="font-size:0.78rem; color:#475569;">'
        f"<strong>Owner:</strong> {owner_html} &nbsp;·&nbsp; "
        f"<strong>Audience:</strong> {audience_str} &nbsp;·&nbsp; "
        f"<strong>Formula:</strong> <code>{metric.formula.type}</code>"
        f"{f' &nbsp;·&nbsp; <strong>Target:</strong> {target_str}' if target_str else ''}"
        f"</div>"
        f"{bands_html}"
        f"{live_html}"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Formula source as a YAML block — collapsed by default, expanded
    # only when the operator wants the gory definition. Renders the
    # Pydantic model dump as YAML so spec readers recognise the shape.
    with st.expander("Formula definition (YAML)", expanded=False):
        st.code(
            yaml.safe_dump(metric.formula.model_dump(), sort_keys=False),
            language="yaml",
        )


if not filtered:
    empty_state(
        "No metrics match the current filters.",
        icon="🔍",
        detail="Loosen the category, audience, or formula filters above.",
    )
else:
    for category in ALL_CATEGORIES:
        in_cat = [m for m in filtered if m.category == category]
        if not in_cat:
            continue
        with st.expander(
            f"**{category.title()}** — {len(in_cat)} metric(s)",
            expanded=len(filtered) <= 6,
        ):
            for metric in in_cat:
                _render_metric_card(metric)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# See-also footer (PR-C pattern)
# ---------------------------------------------------------------------------

see_also_footer(
    [
        "[Executive Dashboard — metrics surfaced as headline KPIs](./1_Executive_Dashboard)",
        "[Comparative Analytics — metric trends + RAG distribution](./19_Comparative_Analytics)",
        "[Spec Editor — propose a new metric](./20_Spec_Editor)",
        research_link(
            "FinCEN AML Effectiveness NPRM — what regulators want measured",
            "2026-04-regulator-pulse.md",
            "fincen-aml-effectiveness-nprm",
        ),
    ]
)

# Acronym expansion — keeps CCO / MLRO / RAG / NPRM / RTS visible for
# the senior personas this page targets.
st.markdown(
    glossary_legend(["CCO", "MLRO", "FinCEN", "AMLA", "RAG"]),
    unsafe_allow_html=True,
)
