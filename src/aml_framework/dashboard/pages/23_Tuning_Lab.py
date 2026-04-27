"""Tuning Lab — sweep rule thresholds + preview alert deltas + download patch.

This page is the UI surface for `engine/tuning.py` (PR #50). MLRO picks
a rule that has a `tuning_grid` declared, optionally uploads labels for
precision/recall scoring, and the page renders the per-scenario table
plus a precision/recall scatter when labels are present. The chosen
scenario can be downloaded as a YAML spec patch the operator merges
into `aml.yaml` to promote.

Audit defensibility: a `tuning_run` event is appended to the current
session's run dir whenever the page runs a sweep, so every threshold
consideration is part of the audit trail.
"""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import chart_layout, kpi_card, page_header
from aml_framework.dashboard.tuning_state import (
    best_scenario,
    parse_labels_csv,
    render_spec_patch,
    rules_with_tuning_grid,
    scenarios_to_table,
)
from aml_framework.engine.tuning import sweep_rule

PAGE_TITLE = "Tuning Lab"

page_header(
    PAGE_TITLE,
    "Sweep rule thresholds, preview alert deltas + precision/recall, "
    "download a YAML spec patch to promote a candidate scenario.",
)
show_audience_context(PAGE_TITLE)

spec = st.session_state.spec
data = st.session_state.data
as_of = st.session_state.as_of
run_dir = st.session_state.run_dir

tunable_rules = rules_with_tuning_grid(spec)
if not tunable_rules:
    st.warning(
        "No rules in this spec declare a `tuning_grid`. Add one under a "
        "rule (e.g. `tuning_grid: { logic.having.count: [{gte: 2}, "
        "{gte: 5}] }`) to enable threshold sweeps for it."
    )
    st.stop()

# --- Selectors ---
left, right = st.columns([2, 1])
with left:
    rule_id = st.selectbox("Rule to sweep", tunable_rules, index=0)
with right:
    audit_writeback = st.checkbox(
        "Append `tuning_run` event to audit ledger",
        value=True,
        help="Records this sweep in the current run's decisions.jsonl.",
    )

st.markdown("##### Optional: labels CSV for precision/recall scoring")
labels_file = st.file_uploader(
    "CSV with columns `customer_id,is_true_positive`",
    type=["csv"],
    help="When provided, every scenario gets precision/recall/F1 scored against the labels.",
)

labels = None
if labels_file is not None:
    try:
        labels = parse_labels_csv(labels_file.read().decode("utf-8"))
        st.caption(f"Loaded {len(labels)} labels.")
    except Exception as exc:
        st.error(f"Failed to parse labels CSV: {exc}")

# --- Run sweep ---
run = sweep_rule(
    spec,
    rule_id,
    data,
    as_of=as_of,
    labels=labels,
    audit_run_dir=run_dir if audit_writeback else None,
)

# --- KPIs ---
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Baseline alerts", run.baseline.alert_count, "#2563eb")
with c2:
    kpi_card("Scenarios", run.grid_size, "#7c3aed")
with c3:
    looser = sum(1 for s in run.scenarios if s.alert_count > run.baseline.alert_count)
    kpi_card("More-alert scenarios", looser, "#d97706")
with c4:
    tighter = sum(1 for s in run.scenarios if s.alert_count < run.baseline.alert_count)
    kpi_card("Fewer-alert scenarios", tighter, "#16a34a")

# --- Best-F1 callout when labels supplied ---
if labels is not None:
    best_idx = best_scenario(run, metric="f1")
    if best_idx is not None:
        best = run.scenarios[best_idx]
        st.success(
            f"**Best F1**: precision={best.precision:.3f}, recall={best.recall:.3f}, "
            f"F1={best.f1:.3f}  ·  parameters: `{best.parameters}`"
        )

# --- Scenario table ---
st.markdown("##### Scenarios")
rows = scenarios_to_table(run)
st.dataframe(
    rows,
    use_container_width=True,
    hide_index=True,
    height=min(35 * len(rows) + 38, 500),
)

# --- Precision/recall scatter (only when labels present) ---
if labels is not None and any(s.precision is not None for s in run.scenarios):
    st.markdown("##### Precision–Recall scatter")
    pr_rows = [
        {
            "precision": s.precision,
            "recall": s.recall,
            "f1": s.f1,
            "alerts": s.alert_count,
            "params": str(s.parameters),
        }
        for s in run.scenarios
        if s.precision is not None and s.recall is not None
    ]
    fig = px.scatter(
        pr_rows,
        x="recall",
        y="precision",
        size="alerts",
        color="f1",
        hover_data=["params"],
        color_continuous_scale="Viridis",
        range_x=[0, 1.05],
        range_y=[0, 1.05],
    )
    fig.update_layout(xaxis_title="Recall", yaxis_title="Precision")
    st.plotly_chart(chart_layout(fig, 360), use_container_width=True)

# --- Promote a scenario ---
st.markdown("##### Promote a scenario to a spec patch")
options = [
    f"#{i}  ·  alerts={s.alert_count}  ·  Δ={s.alert_count - run.baseline.alert_count:+d}"
    + (f"  ·  F1={s.f1:.3f}" if s.f1 is not None else "")
    for i, s in enumerate(run.scenarios)
]
chosen_idx = st.selectbox(
    "Choose a scenario",
    list(range(len(options))),
    format_func=lambda i: options[i],
)
chosen = run.scenarios[chosen_idx]
patch_yaml = render_spec_patch(rule_id, chosen.parameters)
st.code(patch_yaml, language="yaml")
st.download_button(
    "Download spec patch",
    data=patch_yaml,
    file_name=f"{rule_id}_tuned_patch.yaml",
    mime="text/yaml",
)
