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

import pandas as _pd_tuning
import streamlit as st

from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import (
    glossary_legend,
    kpi_card,
    line_chart,
    metric_gradient_style,
    page_header,
    scatter_chart,
)
from aml_framework.dashboard.query_params import consume_param as _consume_param
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
# Pre-select via deep link from Rule Performance / Spec Editor when
# they pass a `rule_id` query param. Falls back to the first tunable
# rule otherwise. consume_param keeps the link state one-shot so a
# refresh doesn't re-trigger.
_deep_link_rule = _consume_param("rule_id")
_default_rule_idx = tunable_rules.index(_deep_link_rule) if _deep_link_rule in tunable_rules else 0
left, right = st.columns([2, 1])
with left:
    rule_id = st.selectbox("Rule to sweep", tunable_rules, index=_default_rule_idx)
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
# Convert to DataFrame so we can attach a Styler — colour the F1 /
# precision / recall metrics red→amber→green so the MLRO can scan
# for "good" scenarios without reading every number.
_scenarios_df = _pd_tuning.DataFrame(rows)
_styled_scenarios = _scenarios_df.style
_metric_cols = [c for c in ("precision", "recall", "f1") if c in _scenarios_df.columns]
if _metric_cols:
    _styled_scenarios = _styled_scenarios.map(
        metric_gradient_style(
            low_threshold=0.5,
            high_threshold=0.8,
        ),
        subset=_metric_cols,
    )
st.dataframe(
    _styled_scenarios,
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

    # F1 → severity-token mapping for per-point colour: low F1 → red,
    # mid → amber, high → green. Mirrors the previous Plotly RAG
    # gradient with discrete band colouring (closer to AML compliance
    # convention than a continuous scale).
    def _f1_band(f1: float | None) -> str:
        if f1 is None:
            return "low"
        if f1 >= 0.8:
            return "low"  # green via severity palette ("low" severity reads green)
        if f1 >= 0.5:
            return "medium"  # amber
        return "high"  # red

    pr_df = _pd_tuning.DataFrame(
        [
            {
                "recall": r["recall"],
                "precision": r["precision"],
                "alerts": r["alerts"],
                "band": _f1_band(r["f1"]),
                # Best-F1 row gets a "★ best F1 = X.XXX" label so the
                # eye lands there first (replaces add_annotation arrow).
                "label": "",
            }
            for r in pr_rows
        ]
    )
    # Annotate the best-F1 row's `label`.
    best_idx = max(
        range(len(pr_rows)),
        key=lambda i: pr_rows[i]["f1"] if pr_rows[i]["f1"] is not None else -1,
    )
    if pr_rows[best_idx]["f1"] is not None:
        pr_df.loc[best_idx, "label"] = f"★ best F1 = {pr_rows[best_idx]['f1']:.3f}"

    scatter_chart(
        pr_df,
        x="recall",
        y="precision",
        size="alerts",
        color="band",
        label="label",
        title="Precision vs. Recall — point size = alert volume, colour = F1 band",
        height=360,
        key="tuning_lab_pr_scatter",
    )

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
        _backtest_df = _pd_tuning.DataFrame(rows)
        _styled_backtest = _backtest_df.style
        _bt_metric_cols = [c for c in ("precision", "recall", "f1") if c in _backtest_df.columns]
        if _bt_metric_cols:
            _styled_backtest = _styled_backtest.map(
                metric_gradient_style(
                    low_threshold=0.5,
                    high_threshold=0.8,
                ),
                subset=_bt_metric_cols,
            )
        st.dataframe(_styled_backtest, use_container_width=True)

        if report.drift_summary:
            st.markdown("**Drift summary** (slope = per-period change):")
            st.json(report.drift_summary)

        # Quick chart: alert volume over periods.
        chart_df = _pd_tuning.DataFrame(
            [{"period": p.period, "alerts": p.alert_count} for p in report.periods]
        )
        line_chart(
            chart_df,
            x="period",
            y="alerts",
            smooth=True,
            markers=True,
            height=300,
            key=f"tuning_lab_backtest_volume_{rule_id}",
        )

        st.download_button(
            "Download backtest_report.json",
            data=json.dumps(report.to_dict(), indent=2),
            file_name=f"{rule_id}_backtest.json",
            mime="application/json",
        )

st.markdown("---")
st.caption(
    "**See also** · "
    '[PAIN-6 — "My monitoring system is a model and I cannot validate it"]'
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-aml-process-pain.md)"
    " · [SR 26-2 (effective 2026-04-17) — what changed for AML model risk]"
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-regulator-pulse.md)"
    " · [Determinism contract in the technical deck]"
    "(https://tomqwu.github.io/aml_open_framework_demo/#/technical/deck)"
)

# Acronyms used on this page — model-validation context terms expanded
# so a non-MRM-resident leader can read along.
st.markdown(
    glossary_legend(["MRM", "2LoD", "RAG"]),
    unsafe_allow_html=True,
)
