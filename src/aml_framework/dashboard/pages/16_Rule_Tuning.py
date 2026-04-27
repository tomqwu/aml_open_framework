"""Rule Tuning -- threshold what-if analysis.

Select a rule, adjust thresholds with sliders, and see the impact on
alert volume in real time. Does NOT modify the spec — shows what would
happen for review before editing the YAML.
"""

from __future__ import annotations

import duckdb
import plotly.express as px
import streamlit as st

from aml_framework.dashboard.components import chart_layout, kpi_card, page_header
from aml_framework.engine.runner import _build_warehouse
from aml_framework.generators.sql import compile_rule_sql
from aml_framework.spec.models import AggregationWindowLogic, Rule

page_header(
    "Rule Tuning",
    "Adjust detection thresholds and preview alert volume impact.",
)

spec = st.session_state.spec
data = st.session_state.data
result = st.session_state.result
as_of = st.session_state.as_of

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Rule Tuning**\n\n"
        "Select an aggregation_window rule, adjust its thresholds with "
        "sliders, and see how many alerts the modified rule would produce. "
        "Use this to find the right balance between detection and false positives."
    )

# Only aggregation_window rules can be tuned interactively.
tunable_rules = [r for r in spec.rules if r.logic.type == "aggregation_window"]

if not tunable_rules:
    st.warning("No aggregation_window rules to tune.")
    st.stop()

selected_rule_id = st.selectbox(
    "Select rule to tune",
    [r.id for r in tunable_rules],
    format_func=lambda rid: f"{rid} ({next(r.severity for r in tunable_rules if r.id == rid)})",
)

rule = next(r for r in tunable_rules if r.id == selected_rule_id)
logic = rule.logic

# Current thresholds from the spec.
st.markdown(f"### {rule.name}")
st.markdown(
    f"**Severity:** {rule.severity} | **Window:** {logic.window} | **Source:** {logic.source}"
)

st.divider()

# --- Threshold sliders ---
st.markdown("### Adjust Thresholds")
having = dict(logic.having)

adjusted_having = {}
for metric_name, cond in having.items():
    if isinstance(cond, dict):
        for op, val in cond.items():
            if isinstance(val, (int, float)):
                label = f"{metric_name} ({op})"
                current = val
                # Set slider range based on current value.
                min_val = 0
                max_val = int(current * 3) if current > 0 else 100
                step = max(1, int(current * 0.05)) if current > 10 else 1
                new_val = st.slider(
                    label,
                    min_value=min_val,
                    max_value=max_val,
                    value=int(current),
                    step=step,
                    key=f"tune_{selected_rule_id}_{metric_name}_{op}",
                )
                adjusted_having[metric_name] = {op: new_val}
            else:
                adjusted_having[metric_name] = cond
    else:
        adjusted_having[metric_name] = cond

st.divider()

# --- Run the modified rule against the warehouse ---
st.markdown("### Impact Preview")

# Build DuckDB warehouse from session data — same builder the engine uses.
con = duckdb.connect(":memory:")
_build_warehouse(con, spec, data)

# Run original rule.
original_sql = compile_rule_sql(rule, as_of=as_of, source_table=logic.source)
original_count = len(con.execute(original_sql).fetchall())

# Build modified rule (swap having thresholds).
modified_logic = AggregationWindowLogic(
    type="aggregation_window",
    source=logic.source,
    filter=logic.filter,
    group_by=list(logic.group_by),
    window=logic.window,
    having=adjusted_having,
)
modified_rule = Rule(
    id=rule.id,
    name=rule.name,
    severity=rule.severity,
    status=rule.status,
    regulation_refs=list(rule.regulation_refs),
    logic=modified_logic,
    escalate_to=rule.escalate_to,
    evidence=list(rule.evidence),
    tags=list(rule.tags),
)

try:
    modified_sql = compile_rule_sql(modified_rule, as_of=as_of, source_table=logic.source)
    modified_count = len(con.execute(modified_sql).fetchall())
except Exception as e:
    modified_count = 0
    st.error(f"Modified rule SQL error: {e}")

con.close()

# KPIs.
delta = modified_count - original_count
delta_pct = f"{delta / original_count * 100:+.0f}%" if original_count > 0 else "N/A"

c1, c2, c3 = st.columns(3)
with c1:
    kpi_card("Current Alerts", original_count, "#2563eb")
with c2:
    color = "#dc2626" if modified_count > original_count else "#059669"
    kpi_card("Modified Alerts", modified_count, color)
with c3:
    kpi_card("Change", f"{delta:+d} ({delta_pct})", "#d97706")

st.markdown("<br>", unsafe_allow_html=True)

# What-if sensitivity chart: vary the main threshold ±50%.
st.markdown("### Sensitivity Analysis")
main_metric = list(having.keys())[0] if having else None
if main_metric and isinstance(having[main_metric], dict):
    main_op = list(having[main_metric].keys())[0]
    main_val = having[main_metric][main_op]
    if isinstance(main_val, (int, float)) and main_val > 0:
        test_values = [int(main_val * f) for f in [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]]
        test_counts = []

        con2 = duckdb.connect(":memory:")
        _build_warehouse(con2, spec, data)

        for tv in test_values:
            test_having = dict(adjusted_having)
            test_having[main_metric] = {main_op: tv}
            try:
                test_logic = AggregationWindowLogic(
                    type="aggregation_window",
                    source=logic.source,
                    filter=logic.filter,
                    group_by=list(logic.group_by),
                    window=logic.window,
                    having=test_having,
                )
                test_rule = Rule(
                    id=rule.id,
                    name=rule.name,
                    severity=rule.severity,
                    regulation_refs=list(rule.regulation_refs),
                    logic=test_logic,
                    escalate_to=rule.escalate_to,
                )
                sql = compile_rule_sql(test_rule, as_of=as_of, source_table=logic.source)
                test_counts.append(len(con2.execute(sql).fetchall()))
            except Exception:
                test_counts.append(0)

        con2.close()

        fig = px.line(
            x=test_values,
            y=test_counts,
            labels={"x": f"{main_metric} threshold", "y": "Alert count"},
            markers=True,
        )
        fig.add_vline(
            x=main_val,
            line_dash="dash",
            line_color="#6b7280",
            annotation_text="Current",
        )
        st.plotly_chart(chart_layout(fig, 350), use_container_width=True)
