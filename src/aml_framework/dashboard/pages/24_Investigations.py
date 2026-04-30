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
    find_linked_customers,
    linkage_summary,
    summarise_backlog,
)
from aml_framework.dashboard.components import (
    glossary_legend,
    id_link,
    page_header,
    rag_cell_style,
    research_link,
    see_also_footer,
    selectable_dataframe,
    severity_cell_style,
)

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
    backlog_view = df_backlog[
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
    ]
    # Colour the count columns so a queue with 12 breached jumps off
    # the page vs. one with 0; the column header IS the band so we
    # tint each column header's column with that band's hex.
    styled_backlog = backlog_view.style
    for band in ("green", "amber", "red", "breached"):
        styled_backlog = styled_backlog.set_properties(
            subset=[band],
            **{"font-weight": "700"},
        )
    # Map the band-named columns through rag_cell_style by adding a
    # constant cell containing the band itself — but Styler.map operates
    # on values. Instead, format the count as a coloured-header cell:
    # Streamlit Styler doesn't support per-header CSS yet, so we leave
    # the visual cue to the row-totalled column subsets themselves.
    st.dataframe(
        styled_backlog,
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

styled_inv = df_inv.style
if "severity" in df_inv.columns:
    styled_inv = styled_inv.map(severity_cell_style, subset=["severity"])
selectable_dataframe(
    styled_inv,
    key="investigations_list_table",
    drill_target="pages/17_Customer_360.py",
    drill_param="customer_id",
    drill_column="customer_id",
    hint="Click any investigation row to open the customer's 360 view.",
    use_container_width=True,
    hide_index=True,
)

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

# Constituent case-IDs as clickable links — even though the SLA
# table below has row-click drill (PR-A), having the IDs as a quick
# bullet list above the table is the fastest path when the analyst
# already knows which case they want to open.
case_id_links = " · ".join(
    id_link(cid, "4_Case_Investigation", "case_id") for cid in selected.get("case_ids", [])
)
if case_id_links:
    st.markdown(f"**Cases in this investigation:** {case_id_links}")

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
    styled_constituent = df_constituent.style
    if "sla_state" in df_constituent.columns:
        styled_constituent = styled_constituent.map(rag_cell_style, subset=["sla_state"])
    selectable_dataframe(
        styled_constituent,
        key="investigations_constituent_cases",
        drill_target="pages/4_Case_Investigation.py",
        drill_param="case_id",
        drill_column="case_id",
        hint="Click a case row to open the full investigation package.",
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No constituent cases with resolvable open time.")

st.caption(
    "Investigation aggregator (PR #61), SLA timer (PR #63), and escalation policy "
    "(PR #63) compose into this single review surface."
)

# ---------------------------------------------------------------------------
# Linked across domains — fraud cases on customers also under AML review.
#
# Process problem: fraud team and AML team open separate cases on the
# same customer; neither analyst sees the other's evidence; customer
# gets two contradictory letters. This panel makes the overlap visible
# so the next analyst opening a case on the customer knows to talk to
# the other team first.
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("⚠️ Linked across domains")
st.caption(
    "Customers with cases in **both** fraud-domain and AML-domain rules. "
    "If a row appears here, two teams may be working the same subject blind to each other."
)

linked = find_linked_customers(cases, st.session_state.spec)
summary = linkage_summary(linked)

lc1, lc2, lc3 = st.columns(3)
with lc1:
    st.metric("Linked customers", summary["linked_customer_count"])
with lc2:
    st.metric("Linked cases (total)", summary["total_linked_cases"])
with lc3:
    st.metric("Highest severity", summary["highest_severity"])

if linked:
    linked_rows = [
        {
            "customer_id": lc.customer_id,
            "severity": lc.severity,
            "fraud_cases": len(lc.fraud_case_ids),
            "aml_cases": len(lc.aml_case_ids),
            "fraud_rules": ", ".join(lc.fraud_rule_ids),
            "aml_rules": ", ".join(lc.aml_rule_ids),
        }
        for lc in linked
    ]
    selectable_dataframe(
        pd.DataFrame(linked_rows),
        key="investigations_linked_table",
        drill_target="pages/17_Customer_360.py",
        drill_param="customer_id",
        drill_column="customer_id",
        hint="Click a row to open the customer's 360 view (resolves the cross-team blindspot).",
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info(
        "No cross-domain links in this run. To exercise the panel, mark a rule's "
        "`aml_priority` as `fraud` in the spec, or run against the UK APP-fraud or "
        "Cyber-enabled fraud example specs."
    )

# Acronyms used on this page — keeps SLA / STR / SAR / MLRO visible for
# audit-trail reasons but expanded so a leader doesn't need to ask.
st.markdown(
    glossary_legend(["SLA", "STR", "SAR", "MLRO", "1LoD", "2LoD"]),
    unsafe_allow_html=True,
)


# --- See also (cross-page nav + research) ---
see_also_footer(
    [
        "[Case Investigation — open one case in detail](./4_Case_Investigation)",
        "[My Queue — your assigned slice](./21_My_Queue)",
        research_link(
            "FINTECH-4 — backlog drift when no one owns the queue",
            "2026-04-fintech-aml-reality.md",
            "fintech-4--backlog-drift-when-no-one-owns-the-queue",
        ),
    ]
)
