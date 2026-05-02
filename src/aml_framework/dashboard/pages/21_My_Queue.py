"""My Queue -- analyst personal dashboard with assigned cases and workload."""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from aml_framework.cases.sla import compute_sla_status
from aml_framework.dashboard.components import (
    bar_chart,
    empty_state,
    kpi_card,
    link_to_page,
    page_header,
    pie_chart,
    selectable_dataframe,
)

page_header(
    "My Queue",
    "Personal analyst dashboard — your assigned cases, workload, and activity.",
)

spec = st.session_state.spec
df_cases = st.session_state.df_cases
df_decisions = st.session_state.df_decisions

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- My Queue**\n\n"
        "This is your personal work queue. Select your analyst queue to see "
        "assigned cases, track your SLA compliance, and review recent activity."
    )

if df_cases.empty:
    empty_state(
        "No cases in this run.",
        icon="📭",
        detail="Run the engine to generate cases for your queue.",
        stop=True,
    )

# --- Queue selector ---
queues = sorted(spec.workflow.queues, key=lambda q: q.id)
queue_ids = [q.id for q in queues]
selected_queue = st.selectbox(
    "Select your queue",
    queue_ids,
    index=0,
    help="Choose the queue you're assigned to.",
)

queue_obj = next((q for q in queues if q.id == selected_queue), None)

# Filter cases to this queue.
my_cases = df_cases[df_cases["queue"] == selected_queue].copy()
open_cases = my_cases[~my_cases["status"].isin(["closed_no_action", "closed"])]
resolved_cases = my_cases[
    my_cases["status"].isin(["closed_no_action", "closed"])
    | my_cases["status"].str.contains("filing", na=False)
]

# --- Personal KPIs ---
st.markdown("<br>", unsafe_allow_html=True)
c1, c2, c3, c4 = st.columns(4)

total_assigned = len(my_cases)
total_open = len(open_cases)
total_resolved = len(resolved_cases)

# SLA compliance from decisions.
sla_compliance = "N/A"
if not df_decisions.empty and "within_sla" in df_decisions.columns:
    my_decisions = df_decisions[df_decisions["queue"] == selected_queue]
    sla_rows = my_decisions[my_decisions["within_sla"].notna()]
    if not sla_rows.empty:
        pct = sla_rows["within_sla"].astype(bool).mean() * 100
        sla_compliance = f"{pct:.0f}%"

with c1:
    kpi_card("Assigned", total_assigned, "#2563eb")
    # KPI drill: clicking the page-link sets a queue filter on Case
    # Investigation so the analyst lands on a pre-filtered list rather
    # than scrolling the full case table.
    if total_assigned:
        link_to_page(
            "pages/4_Case_Investigation.py",
            "→ Open in Case Investigation",
            queue_filter=selected_queue,
        )
with c2:
    kpi_card("Open", total_open, "#d97706" if total_open > 0 else "#059669")
    if total_open:
        link_to_page(
            "pages/4_Case_Investigation.py",
            f"→ {total_open} open · drill in",
            queue_filter=selected_queue,
            status_filter="open",
        )
with c3:
    kpi_card("Resolved", total_resolved, "#059669")
    if total_resolved:
        link_to_page(
            "pages/4_Case_Investigation.py",
            f"→ {total_resolved} resolved",
            queue_filter=selected_queue,
            status_filter="resolved",
        )
with c4:
    kpi_card("SLA Compliance", sla_compliance, "#7c3aed")
    # SLA breaches are the high-leverage drill here — when the SLA % is
    # below 100, lead the analyst straight to the breached cases.
    if sla_compliance != "N/A" and sla_compliance != "100%":
        link_to_page(
            "pages/4_Case_Investigation.py",
            "→ SLA breaches",
            queue_filter=selected_queue,
            sla_filter="breached",
        )

# --- SLA info ---
if queue_obj:
    st.caption(f"Queue SLA: {queue_obj.sla} | Next queues: {', '.join(queue_obj.next or ['—'])}")

st.markdown("<br>", unsafe_allow_html=True)

# --- Open cases table (with live SLA) ---
st.markdown("### Open Cases")
if not open_cases.empty:
    display_cols = ["case_id", "rule_id", "severity", "status"]
    # Add alert amount if available.
    if "alert" in open_cases.columns:
        open_cases = open_cases.copy()
        open_cases["amount"] = open_cases["alert"].apply(
            lambda a: f"${float(a.get('sum_amount', 0)):,.2f}" if isinstance(a, dict) else "—"
        )
        open_cases["customer"] = open_cases["alert"].apply(
            lambda a: a.get("customer_id", "") if isinstance(a, dict) else ""
        )
        display_cols = ["case_id", "customer", "rule_id", "severity", "amount", "status"]

    # Live SLA state per case — compute_sla_status returns None when the
    # case has no resolvable opened_at, so we fall back to "—" rather than
    # silently misclassifying as "breached".
    as_of = st.session_state.get("as_of") or datetime.now(tz=timezone.utc).replace(tzinfo=None)

    def _sla_state(row: dict) -> str:
        if queue_obj is None:
            return "—"
        status = compute_sla_status(row, queue_obj, as_of=as_of)
        if status is None:
            return "—"
        return status["state"]

    def _sla_remaining(row: dict) -> str:
        if queue_obj is None:
            return ""
        status = compute_sla_status(row, queue_obj, as_of=as_of)
        if status is None:
            return ""
        return f"{status['time_remaining_hours']:.1f}h"

    # Pass each row as a dict so the helpers see the same shape they
    # accept on the Investigations page.
    case_records = open_cases.to_dict(orient="records")
    open_cases["sla_state"] = [_sla_state(r) for r in case_records]
    open_cases["sla_remaining"] = [_sla_remaining(r) for r in case_records]
    display_cols = display_cols + ["sla_state", "sla_remaining"]

    available_cols = [c for c in display_cols if c in open_cases.columns]
    selectable_dataframe(
        open_cases[available_cols],
        key="myqueue_open_cases_table",
        drill_target="pages/4_Case_Investigation.py",
        drill_param="case_id",
        drill_column="case_id",
        hint="Click any row to open the case in Case Investigation.",
        use_container_width=True,
        hide_index=True,
        height=min(35 * len(open_cases) + 38, 400),
    )
    # Caption documents the SLA band column for the analyst — they'll
    # learn it once and look for it on every queue.
    st.caption(
        "SLA bands: green > 50% remaining · amber 10-50% · red < 10% · breached ≤ 0%. "
        "Computed live from `cases/sla.py`."
    )
else:
    empty_state(
        "No open cases — queue is clear.",
        icon="✅",
        detail=(
            "All cases assigned to this queue have been resolved or "
            "escalated. Pick another queue from the selector above to "
            "see its workload."
        ),
    )

st.markdown("<br>", unsafe_allow_html=True)

# --- Workload breakdown ---
col_left, col_right = st.columns(2)

with col_left:
    st.markdown("### Cases by Severity")
    if not my_cases.empty and "severity" in my_cases.columns:
        sev_counts = my_cases["severity"].value_counts().reset_index()
        sev_counts.columns = ["severity", "count"]
        bar_chart(
            sev_counts,
            x="severity",
            y="count",
            color="severity",
            height=280,
            key="my_queue_severity_bar",
        )
    else:
        st.caption("No severity data available.")

with col_right:
    st.markdown("### Cases by Status")
    if not my_cases.empty and "status" in my_cases.columns:
        status_counts = my_cases["status"].value_counts().reset_index()
        status_counts.columns = ["status", "count"]
        pie_chart(
            status_counts,
            names="status",
            values="count",
            donut=True,
            height=280,
            key="my_queue_status_pie",
        )
    else:
        st.caption("No status data available.")

st.markdown("<br>", unsafe_allow_html=True)

# --- Recent activity ---
st.markdown("### Recent Activity")
if not df_decisions.empty:
    my_activity = df_decisions[df_decisions["queue"] == selected_queue].copy()
    if not my_activity.empty:
        display_cols = ["ts", "event", "case_id", "disposition"]
        available = [c for c in display_cols if c in my_activity.columns]
        st.dataframe(
            my_activity[available].sort_values("ts", ascending=False).head(20),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"Showing latest 20 of {len(my_activity)} decisions.")
    else:
        st.caption("No activity recorded for this queue.")
else:
    st.caption("No decisions recorded.")

# --- Resolution time distribution ---
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("### Resolution Time Distribution")
if not df_decisions.empty and "resolution_hours" in df_decisions.columns:
    my_resolved = df_decisions[
        (df_decisions["queue"] == selected_queue) & (df_decisions["resolution_hours"].notna())
    ]
    if not my_resolved.empty:
        # ECharts has no native histogram + vrect band combo. Pre-bin
        # into 15 buckets and render as a bar chart with per-bar
        # severity-keyed colour: green ≤ SLA, amber 1×-2× SLA, red > 2×.
        # The bar palette resolver in dashboard.charts maps the
        # `band` column's "low/medium/high" values to severity colours.
        import math

        import pandas as pd

        sla_hours = None
        if queue_obj:
            from aml_framework.generators.sql import parse_window

            try:
                sla_td = parse_window(queue_obj.sla)
                sla_hours = sla_td.total_seconds() / 3600
            except Exception:
                sla_hours = None

        hours = [float(h) for h in my_resolved["resolution_hours"].tolist() if h is not None]
        if hours:
            n_bins = 15
            hi = max(hours)
            lo = 0.0
            bin_width = (hi - lo) / n_bins if hi > lo else 1.0
            bins = [0] * n_bins
            for h in hours:
                if math.isnan(h):
                    continue
                idx = min(int((h - lo) / bin_width), n_bins - 1)
                bins[idx] += 1

            def _band(centre: float) -> str:
                if sla_hours is None:
                    return "medium"
                if centre <= sla_hours:
                    return "low"  # green — under SLA
                if centre <= sla_hours * 2:
                    return "medium"  # amber — 1×-2× SLA
                return "high"  # red — > 2× SLA

            centres = [(i + 0.5) * bin_width for i in range(n_bins)]
            sla_label = f" (SLA {queue_obj.sla})" if queue_obj and sla_hours is not None else ""
            res_df = pd.DataFrame(
                {
                    "bucket": [f"{c:.1f}h" for c in centres],
                    "cases": bins,
                    "band": [_band(c) for c in centres],
                }
            )
            bar_chart(
                res_df,
                x="bucket",
                y="cases",
                color="band",
                title=f"Resolution Time Distribution{sla_label}",
                height=300,
                key=f"my_queue_resolution_hist_{selected_queue}",
            )
    else:
        st.caption("No resolution data for this queue.")
else:
    st.caption("No resolution time data available.")
