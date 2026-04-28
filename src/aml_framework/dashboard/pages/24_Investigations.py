"""Investigations -- Round-6 case dashboard page (#24).

Surfaces the investigation aggregator (PR #61) + SLA timer (PR #63)
in one operator-facing view. Three sections:
  1. Backlog summary table — per-queue green/amber/red/breached counts
     with breach-rate badges (the FCA Mar 2026 Dear CEO letter view)
  2. Investigation list — every aggregated investigation with subject,
     case count, max severity, total amount, time-in-queue
  3. Investigation detail — drill into one investigation, see every
     constituent case with its live SLA status

This page works whether the operator selected per_customer_window
(default) or per_customer_per_run aggregation; the strategy is
exposed as a sidebar control.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from aml_framework.cases import (
    aggregate_investigations,
    apply_escalation,
    compute_sla_status,
    summarise_backlog,
)
from aml_framework.dashboard.components import page_header

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

page_header(
    title="Investigations",
    description=(
        "Active investigations across teams, ranked by SLA urgency. "
        "One row per subject — the unit of analyst work — with live time-in-queue."
    ),
)

spec = st.session_state.get("spec")
df_cases = st.session_state.get("df_cases", pd.DataFrame())

if spec is None or df_cases.empty:
    st.warning("No cases loaded. Run the engine via the Alert Queue page first.")
    st.stop()

# Convert DataFrame back to list-of-dicts for the aggregator (it operates
# on raw case dicts, not pandas — keeps it usable from non-dashboard code).
cases = df_cases.to_dict(orient="records")

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### Investigation grouping")
    strategy = st.selectbox(
        "Strategy",
        options=["per_customer_window", "per_customer_per_run", "per_case"],
        index=0,
        help=(
            "How to roll per-alert cases into investigations. "
            "per_customer_window groups by (customer, 30-day bucket); "
            "per_customer_per_run groups all of one customer's run cases; "
            "per_case keeps singletons."
        ),
    )
    use_now = st.toggle(
        "Evaluate SLA against now()",
        value=False,
        help=(
            "Off → use the engine's as_of timestamp (deterministic). "
            "On → use the current wall-clock time (closer to a live ops view)."
        ),
    )

as_of = (
    datetime.now(tz=timezone.utc).replace(tzinfo=None)
    if use_now
    else st.session_state.get("as_of") or datetime.now()
)

# ---------------------------------------------------------------------------
# Compute investigations + backlog
# ---------------------------------------------------------------------------

investigations = aggregate_investigations(cases, strategy=strategy)
backlog = summarise_backlog(cases, spec, as_of=as_of)

# ---------------------------------------------------------------------------
# Section 1 — backlog summary
# ---------------------------------------------------------------------------

st.subheader("Queue backlog")
st.caption(
    f"Live SLA classification per workflow queue at {as_of.isoformat(timespec='seconds')}. "
    "Green > 50% remaining · Amber 10-50% · Red < 10% · Breached ≤ 0%."
)

if backlog:
    backlog_rows = [b.to_dict() for b in backlog]
    df_backlog = pd.DataFrame(backlog_rows)
    df_backlog["breach_rate_pct"] = df_backlog["breach_rate_pct"].round(1)
    df_backlog["oldest_age_hours"] = df_backlog["oldest_age_hours"].round(1)
    st.dataframe(
        df_backlog[
            [
                "queue_id",
                "queue_sla_hours",
                "total_cases",
                "green",
                "amber",
                "red",
                "breached",
                "oldest_age_hours",
                "breach_rate_pct",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No backlog rows — workflow has no queues defined in this spec.")

# ---------------------------------------------------------------------------
# Section 2 — investigation list
# ---------------------------------------------------------------------------

st.subheader("Investigations")
st.caption(
    f"{len(investigations)} investigation(s) across {len(cases)} case(s) using `{strategy}`."
)

if not investigations:
    st.info("No investigations — no cases match the selected strategy's grouping rules.")
    st.stop()

inv_rows = []
for inv in investigations:
    inv_rows.append(
        {
            "investigation_id": inv["investigation_id"],
            "customer_id": inv["customer_id"],
            "severity": inv["severity"],
            "case_count": inv["case_count"],
            "rule_count": inv["rule_count"],
            "total_amount": float(inv["total_amount"]),
            "window_start": inv["window_start"],
            "window_end": inv["window_end"],
            "queues": ", ".join(inv["queues"]),
        }
    )
df_inv = pd.DataFrame(inv_rows)
df_inv["total_amount"] = df_inv["total_amount"].round(2)

# Sort by severity (critical first) then by total_amount.
severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
df_inv["_sev_rank"] = df_inv["severity"].map(severity_order).fillna(99)
df_inv = df_inv.sort_values(["_sev_rank", "total_amount"], ascending=[True, False]).drop(
    columns=["_sev_rank"]
)

st.dataframe(df_inv, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Section 3 — investigation detail
# ---------------------------------------------------------------------------

st.subheader("Investigation detail")
selected_id = st.selectbox(
    "Investigation",
    options=df_inv["investigation_id"].tolist(),
    help="Drill into one investigation to see constituent cases + per-case SLA.",
)
selected = next(i for i in investigations if i["investigation_id"] == selected_id)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Subject", selected["customer_id"])
c2.metric("Severity", selected["severity"])
c3.metric("Cases", selected["case_count"])
c4.metric("Total amount", f"${float(selected['total_amount']):,.2f}")

st.markdown("**Constituent cases (live SLA):**")
queue_map = {q.id: q for q in spec.workflow.queues}
case_rows = []
for case in cases:
    if case.get("case_id") not in selected["case_ids"]:
        continue
    queue = queue_map.get(case.get("queue", ""))
    if queue is None:
        continue
    status = compute_sla_status(case, queue, as_of=as_of)
    if status is None:
        continue
    escalation = apply_escalation(case, status, queue)
    case_rows.append(
        {
            "case_id": case["case_id"],
            "rule_id": case.get("rule_id", ""),
            "queue": case.get("queue", ""),
            "sla_state": status["state"],
            "time_in_queue_h": round(status["time_in_queue_hours"], 1),
            "remaining_h": round(status["time_remaining_hours"], 1),
            "escalate_to": escalation.to_queue if escalation else "",
        }
    )
if case_rows:
    df_constituent = pd.DataFrame(case_rows)
    st.dataframe(df_constituent, use_container_width=True, hide_index=True)
else:
    st.info("No constituent cases with resolvable open time.")

st.caption(
    "Investigation aggregator (PR #61), SLA timer (PR #63), and escalation policy "
    "(PR #63) compose into this single review surface."
)
