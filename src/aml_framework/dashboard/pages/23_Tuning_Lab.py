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

import json

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
    "Test a threshold change before it goes live. See exactly which alerts you'd add or remove.",
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

# ---------------------------------------------------------------------------
# Time-series backtest — sister to the threshold sweep above.
#
# Process problem: 2LoD MLRO has to challenge "is this rule still earning
# its keep?". Tuning answers "best threshold today"; backtest answers
# "is precision/recall trending down across the last N quarters?". Both
# live on this page so the model-challenge workflow is one screen.
# ---------------------------------------------------------------------------

with st.expander("📉 Backtest this rule across historical quarters", expanded=False):
    st.markdown(
        "Replay the **current spec's thresholds** across N quarters. "
        "Use this for the SR 26-2 / OCC 2026-13 question: *is rule "
        f"`{rule_id}` precision/recall trending down over time?*"
    )

    bt_col1, bt_col2 = st.columns([1, 1])
    with bt_col1:
        n_quarters = st.slider("Quarters to replay", min_value=2, max_value=8, value=4, step=1)
    with bt_col2:
        use_labels_for_backtest = st.checkbox(
            "Use the labels CSV above for scoring",
            value=False,
            help="When checked, applies the same labels to every period. "
            "Use a per-period labels CSV via the CLI for time-varying labels.",
        )

    if st.button("Run backtest", key="run_backtest"):
        from aml_framework.engine.backtest import backtest_rule, quarters

        bt_periods = quarters(end=as_of, n=n_quarters)
        bt_labels = None
        if use_labels_for_backtest and "tuning_labels" in st.session_state:
            tl = st.session_state["tuning_labels"]
            bt_labels = lambda _p: tl  # noqa: E731 — same labels for each period

        with st.spinner(f"Replaying `{rule_id}` across {n_quarters} quarters…"):
            report = backtest_rule(spec, rule_id, bt_periods, labels_loader=bt_labels)

        st.session_state["backtest_report"] = report

    if "backtest_report" in st.session_state:
        report = st.session_state["backtest_report"]
        rows = [
            {
                "period": p.period,
                "as_of": p.as_of[:10],
                "alerts": p.alert_count,
                "precision": p.precision,
                "recall": p.recall,
                "f1": p.f1,
            }
            for p in report.periods
        ]
        st.dataframe(rows, use_container_width=True)

        if report.drift_summary:
            st.markdown("**Drift summary** (slope = per-period change):")
            st.json(report.drift_summary)

        # Quick chart: alert volume over periods.
        chart_df = [{"period": p.period, "alerts": p.alert_count} for p in report.periods]
        fig = px.line(chart_df, x="period", y="alerts", markers=True)
        fig.update_layout(**chart_layout())
        st.plotly_chart(fig, use_container_width=True)

        st.download_button(
            "Download backtest_report.json",
            data=json.dumps(report.to_dict(), indent=2),
            file_name=f"{rule_id}_backtest.json",
            mime="application/json",
        )
