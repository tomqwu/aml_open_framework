"""BOI Workflow — Round-8 dashboard page #25.

Process problem
---------------
The KYC analyst doing entity onboarding currently re-keys beneficial-
owner data into 3+ systems on every onboarding (CRM, AML monitoring,
FinCEN BOI return). The data drifts the moment one is edited. This
page lifts customer-360 + pKYC into a single BOI status view + one-
click FinCEN-format export — no rekeying.

What the page does
------------------
1. KPI strip: Missing / Stale / Current / Not-required counts
2. Per-customer table sorted worst-first (missing → stale → current)
3. Drill-down: pick a customer, see synthesised owners, download the
   FinCEN BOIR-shaped JSON
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from aml_framework.compliance.boi import (
    boi_summary,
    derive_boi_status_for_all,
    export_fincen_boi,
    synthesise_owners_from_customer,
)
from aml_framework.dashboard.components import (
    empty_state,
    page_header,
    selectable_dataframe,
)

page_header(
    title="BOI Workflow",
    description=(
        "Beneficial-Ownership status across reporting-company customers. "
        "One source of truth — customer-360 + pKYC + freshness window — "
        "with one-click FinCEN BOIR-shaped export. Stop re-keying owners "
        "into three systems."
    ),
)

spec = st.session_state.get("spec")
df_customers = st.session_state.get("df_customers", pd.DataFrame())
data_as_of = st.session_state.get("as_of") or datetime.now(tz=timezone.utc).replace(tzinfo=None)

if spec is None or df_customers.empty:
    st.warning("No customers loaded. Run the engine first.")
    st.stop()

with st.sidebar:
    st.markdown("### BOI freshness window")
    freshness_days = st.slider(
        "Days before a BOI is treated as stale",
        min_value=30,
        max_value=730,
        value=365,
        step=30,
        help=(
            "FinCEN's 30-day rule on ownership *changes* is event-driven. "
            "Most banks also enforce a time-driven floor — pick whichever "
            "is stricter for your jurisdiction."
        ),
    )

customers = df_customers.to_dict(orient="records")
records = derive_boi_status_for_all(customers, as_of=data_as_of, freshness_days=freshness_days)
summary = boi_summary(records)

# ---------------------------------------------------------------------------
# KPI strip
# ---------------------------------------------------------------------------

c1, c2, c3, c4 = st.columns(4)
c1.metric("Missing", summary["missing"], help="Reporting company with no BOI on file.")
c2.metric("Stale", summary["stale"], help="On file but past the freshness window.")
c3.metric("Current", summary["current"])
c4.metric("Not required", summary["not_required"])

# KPI drill — filter the per-customer table below by status. Buttons
# sit under the metric tiles and write `boi_status_filter` into session
# state; the table reads it back to scope rows. "Show all" clears.
fc1, fc2, fc3, fc4, fc5 = st.columns(5)
if fc1.button("Show missing", use_container_width=True, disabled=summary["missing"] == 0):
    st.session_state["boi_status_filter"] = "missing"
if fc2.button("Show stale", use_container_width=True, disabled=summary["stale"] == 0):
    st.session_state["boi_status_filter"] = "stale"
if fc3.button("Show current", use_container_width=True, disabled=summary["current"] == 0):
    st.session_state["boi_status_filter"] = "current"
if fc4.button("Show not-required", use_container_width=True, disabled=summary["not_required"] == 0):
    st.session_state["boi_status_filter"] = "not_required"
if fc5.button("Show all", use_container_width=True):
    st.session_state.pop("boi_status_filter", None)

# ---------------------------------------------------------------------------
# Per-customer table
# ---------------------------------------------------------------------------

active_filter = st.session_state.get("boi_status_filter")
st.subheader(f"Customers — {'filter: ' + active_filter if active_filter else 'sorted worst-first'}")
_records_for_table = [r for r in records if r.status == active_filter] if active_filter else records
df_records = pd.DataFrame([r.to_dict() for r in _records_for_table])
selectable_dataframe(
    df_records,
    key="boi_records_table",
    drill_target="pages/17_Customer_360.py",
    drill_param="customer_id",
    drill_column="customer_id",
    hint="Click any row to open the customer's 360 view (KYC + ownership + alerts).",
    use_container_width=True,
    hide_index=True,
)

# ---------------------------------------------------------------------------
# Drill-down + FinCEN export
# ---------------------------------------------------------------------------

st.subheader("Drill-down + FinCEN BOIR export")
reporting_records = [r for r in records if r.status != "not_required"]
if not reporting_records:
    empty_state(
        "No reporting-company customers in this run.",
        icon="🏢",
        detail=(
            "FinCEN BOI requirements only apply to entities with a "
            "`business_activity` field on the customer record. Try a spec "
            "that exercises the workflow — e.g. `examples/uk_bank/aml.yaml` "
            "or `examples/eu_bank/aml.yaml`."
        ),
        stop=True,
    )

selected_id = st.selectbox(
    "Customer",
    options=[r.customer_id for r in reporting_records],
    format_func=lambda cid: (
        f"{cid} — " + next(r.entity_name for r in reporting_records if r.customer_id == cid)
    ),
)
selected_record = next(r for r in reporting_records if r.customer_id == selected_id)
selected_customer = next(c for c in customers if c.get("customer_id") == selected_id)

s1, s2, s3 = st.columns(3)
s1.metric("Status", selected_record.status)
s2.metric(
    "Days since review",
    selected_record.days_since_review if selected_record.days_since_review is not None else "—",
)
s3.metric(
    "Last review",
    selected_record.last_review.date().isoformat() if selected_record.last_review else "—",
)
st.caption(selected_record.reason)

owners = synthesise_owners_from_customer(selected_customer)
st.markdown("**Beneficial owners on file (synthesised for demo):**")
st.dataframe(pd.DataFrame([o.to_dict() for o in owners]), use_container_width=True, hide_index=True)

payload = export_fincen_boi(selected_customer, owners, filing_type="initial")
st.download_button(
    "Download FinCEN BOIR JSON",
    data=json.dumps(payload, indent=2),
    file_name=f"{selected_id}_boi.json",
    mime="application/json",
    help="FinCEN-shaped payload. Wrap with the institution's filing transmission "
    "envelope before submitting.",
)
