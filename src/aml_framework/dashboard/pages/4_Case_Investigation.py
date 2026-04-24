"""Case Investigation -- entity profile, transaction timeline, flow diagram."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from aml_framework.dashboard.components import chart_layout, page_header


def _record_action(run_dir, case: dict, event: str, disposition: str) -> None:
    """Write a decision to the audit ledger, update case file, and sync session state."""
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    import pandas as pd

    decisions_path = Path(run_dir) / "decisions.jsonl"
    decision = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "event": event,
        "case_id": case["case_id"],
        "rule_id": case.get("rule_id", ""),
        "queue": case.get("queue", ""),
        "disposition": disposition,
        "source": "dashboard_ui",
    }
    with decisions_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(decision, sort_keys=True, separators=(",", ":")) + "\n")

    # Update case file on disk.
    case_path = Path(run_dir) / "cases" / f"{case['case_id']}.json"
    if case_path.exists():
        case_data = json.loads(case_path.read_bytes())
        case_data["status"] = disposition
        case_data["resolved_at"] = decision["ts"]
        case_path.write_bytes(
            json.dumps(case_data, indent=2, sort_keys=True, default=str).encode("utf-8")
        )

    # Cascade: update session state so other pages reflect the change.
    if "df_cases" in st.session_state and not st.session_state.df_cases.empty:
        mask = st.session_state.df_cases["case_id"] == case["case_id"]
        if mask.any():
            st.session_state.df_cases.loc[mask, "status"] = disposition

    # Add decision to session decisions DataFrame.
    if "df_decisions" in st.session_state:
        new_row = pd.DataFrame([decision])
        st.session_state.df_decisions = pd.concat(
            [st.session_state.df_decisions, new_row],
            ignore_index=True,
        )

    st.success(f"Decision recorded: **{event}** -> {disposition}")
    st.caption(f"Written to {decisions_path.name} and synced to session.")


page_header(
    "Case Investigation",
    "Deep-dive into individual cases with entity profile, transaction timeline, and evidence.",
)

spec = st.session_state.spec
result = st.session_state.result
df_cases = st.session_state.df_cases
df_customers = st.session_state.df_customers
df_txns = st.session_state.df_txns

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Case Investigation**\n\n"
        "Select a case to see the full investigation package: entity profile, "
        "triggering transactions highlighted on a timeline, regulation citations, "
        "and evidence requested."
    )

if df_cases.empty:
    st.warning("No cases in this run.")
    st.stop()

# --- Case selector ---
case_ids = sorted(df_cases["case_id"].tolist())
selected_case = st.selectbox("Select case", case_ids)
case = df_cases[df_cases["case_id"] == selected_case].iloc[0].to_dict()

# --- Header banner ---
sev = case.get("severity", "")
sev_colors = {"high": "#dc2626", "medium": "#d97706", "low": "#16a34a", "critical": "#7c3aed"}
sev_color = sev_colors.get(sev, "#6b7280")
st.markdown(
    f'<div style="background:linear-gradient(135deg, {sev_color}18, {sev_color}08); '
    f'border-left:4px solid {sev_color}; border-radius:8px; padding:1rem 1.5rem; margin-bottom:1rem;">'
    f'<span style="font-size:0.78rem; text-transform:uppercase; letter-spacing:0.05em; '
    f'color:{sev_color}; font-weight:700;">{sev} severity</span><br>'
    f'<span style="font-size:1.1rem; font-weight:600; color:#0f172a;">'
    f"{case.get('rule_name', case.get('rule_id', ''))}</span><br>"
    f'<span style="font-size:0.85rem; color:#475569;">'
    f"Queue: {case.get('queue', '')} &middot; Status: {case.get('status', '')}</span>"
    f"</div>",
    unsafe_allow_html=True,
)

# --- Entity Profile + Alert Details ---
col_profile, col_alert = st.columns(2)

customer_id = case.get("alert", {}).get("customer_id", "")
customer_row = df_customers[df_customers["customer_id"] == customer_id]

with col_profile:
    st.markdown("### Entity Profile")
    if not customer_row.empty:
        c = customer_row.iloc[0]
        risk_color = {"high": "#dc2626", "medium": "#d97706", "low": "#16a34a"}.get(
            c["risk_rating"], "#6b7280"
        )
        st.markdown(
            f'<div class="metric-card">'
            f'<div style="font-size:1.1rem; font-weight:600;">{c["full_name"]}</div>'
            f'<div style="font-size:0.85rem; color:#64748b; margin:0.3rem 0 0.8rem;">'
            f"{c['customer_id']} &middot; {c['country']}</div>"
            f'<div><span style="font-size:0.78rem; color:#64748b;">Risk Rating</span><br>'
            f'<span style="color:{risk_color}; font-weight:700;">{c["risk_rating"].upper()}</span>'
            f"</div>"
            f'<div style="margin-top:0.5rem;"><span style="font-size:0.78rem; color:#64748b;">'
            f"Onboarded</span><br>{str(c['onboarded_at'])[:10]}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption(f"Customer {customer_id} not found.")

with col_alert:
    st.markdown("### Alert Details")
    alert_data = case.get("alert", {})
    amt = float(alert_data.get("sum_amount", 0))
    count = alert_data.get("count", "N/A")
    w_start = str(alert_data.get("window_start", ""))[:10]
    w_end = str(alert_data.get("window_end", ""))[:10]
    st.markdown(
        f'<div class="metric-card">'
        f'<div style="display:flex; gap:2rem; margin-bottom:0.8rem;">'
        f'<div><span style="font-size:0.78rem; color:#64748b;">Amount</span><br>'
        f'<span style="font-size:1.4rem; font-weight:700;">${amt:,.2f}</span></div>'
        f'<div><span style="font-size:0.78rem; color:#64748b;">Transactions</span><br>'
        f'<span style="font-size:1.4rem; font-weight:700;">{count}</span></div>'
        f"</div>"
        f'<div><span style="font-size:0.78rem; color:#64748b;">Window</span><br>'
        f"{w_start} to {w_end}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Regulation references
    refs = case.get("regulation_refs", [])
    if refs:
        st.markdown("**Regulation References**")
        for ref in refs:
            st.markdown(f"- **{ref['citation']}**: {ref['description']}")

st.markdown("<br>", unsafe_allow_html=True)

# --- Transaction Timeline ---
st.markdown("### Transaction Timeline")
if customer_id and not df_txns.empty:
    cust_txns = df_txns[df_txns["customer_id"] == customer_id].copy()
    if not cust_txns.empty:
        cust_txns["booked_at"] = cust_txns["booked_at"].astype(str)
        cust_txns["signed_amount"] = cust_txns.apply(
            lambda r: r["amount"] if r["direction"] == "in" else -r["amount"], axis=1
        )
        fig = px.scatter(
            cust_txns,
            x="booked_at",
            y="signed_amount",
            color="channel",
            size=cust_txns["amount"].abs(),
            hover_data=["txn_id", "direction", "amount", "channel"],
            labels={"booked_at": "Date", "signed_amount": "Amount (signed)"},
            color_discrete_map={
                "cash": "#d97706",
                "wire": "#2563eb",
                "ach": "#7c3aed",
                "card": "#6b7280",
                "eft": "#0891b2",
            },
        )
        w_start_full = alert_data.get("window_start")
        w_end_full = alert_data.get("window_end")
        if w_start_full and w_end_full:
            fig.add_vrect(
                x0=str(w_start_full),
                x1=str(w_end_full),
                fillcolor="rgba(220, 38, 38, 0.08)",
                line=dict(color="rgba(220, 38, 38, 0.4)", width=1),
                annotation_text="Alert Window",
                annotation_position="top left",
                annotation_font_size=11,
            )
        fig.update_layout(xaxis_title="", yaxis_title="Amount ($)")
        st.plotly_chart(chart_layout(fig, 380), use_container_width=True)
    else:
        st.caption("No transactions found for this customer.")

st.markdown("<br>", unsafe_allow_html=True)

# --- Channel Flow Sankey ---
st.markdown("### Transaction Flow by Channel")
if customer_id and not df_txns.empty:
    cust_txns = df_txns[df_txns["customer_id"] == customer_id].copy()
    if not cust_txns.empty:
        flow = (
            cust_txns.groupby(["channel", "direction"])
            .agg(total=("amount", "sum"), count=("txn_id", "count"))
            .reset_index()
        )

        labels = [customer_id]
        channels = flow["channel"].unique().tolist()
        labels.extend(channels)

        sources, targets_list, values, link_colors = [], [], [], []
        channel_colors = {
            "cash": "#d97706",
            "wire": "#2563eb",
            "ach": "#7c3aed",
            "card": "#6b7280",
            "eft": "#0891b2",
        }
        for _, row in flow.iterrows():
            ch_idx = labels.index(row["channel"])
            base_color = channel_colors.get(row["channel"], "#94a3b8")
            if row["direction"] == "in":
                sources.append(ch_idx)
                targets_list.append(0)
            else:
                sources.append(0)
                targets_list.append(ch_idx)
            values.append(float(row["total"]))
            # Convert hex to rgba for Plotly compatibility.
            r, g, b = int(base_color[1:3], 16), int(base_color[3:5], 16), int(base_color[5:7], 16)
            link_colors.append(f"rgba({r},{g},{b},0.25)")

        fig = go.Figure(
            go.Sankey(
                node=dict(
                    label=labels,
                    pad=20,
                    thickness=25,
                    color=["#2563eb"] + [channel_colors.get(c, "#94a3b8") for c in channels],
                ),
                link=dict(source=sources, target=targets_list, value=values, color=link_colors),
            )
        )
        st.plotly_chart(chart_layout(fig, 320), use_container_width=True)

# --- Evidence Requested ---
st.markdown("### Evidence Requested")
evidence = case.get("evidence_requested", [])
if evidence:
    cols = st.columns(min(len(evidence), 3))
    for i, item in enumerate(evidence):
        with cols[i % len(cols)]:
            st.markdown(
                f'<div class="metric-card" style="text-align:center; padding:0.8rem;">'
                f'<span style="font-size:0.85rem;">{item.replace("_", " ").title()}</span>'
                f"</div>",
                unsafe_allow_html=True,
            )
else:
    st.caption("No evidence items specified.")

# --- STR/SAR Narrative Generator ---
st.markdown("<br>", unsafe_allow_html=True)
jurisdiction = spec.program.jurisdiction
filing_label = "STR" if jurisdiction == "CA" else "SAR"
st.markdown(f"### Generate {filing_label} Narrative")

if st.button(f"Generate {filing_label} Draft", type="primary"):
    from aml_framework.generators.narrative import generate_str_narrative

    cust_dict = customer_row.iloc[0].to_dict() if not customer_row.empty else None
    cust_txns_list = []
    if customer_id and not df_txns.empty:
        cust_txns_list = df_txns[df_txns["customer_id"] == customer_id].to_dict("records")

    narrative = generate_str_narrative(
        case=case,
        customer=cust_dict,
        transactions=cust_txns_list,
        jurisdiction=jurisdiction,
    )
    st.code(narrative, language="text")

# --- Case Action Buttons ---
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("### Case Actions")
st.caption("Actions write to the immutable audit ledger (decisions.jsonl).")

run_dir = st.session_state.run_dir
case_status = case.get("status", "open")

if "closed" in case_status or case_status in ("str_filing", "sar_filing"):
    st.success(f"Case already resolved: **{case_status}**")
else:
    col_a1, col_a2, col_a3, col_a4 = st.columns(4)

    with col_a1:
        if st.button("Escalate to L2", use_container_width=True):
            _record_action(run_dir, case, "escalated", "l2_investigator")
    with col_a2:
        filing_q = "str_filing" if jurisdiction == "CA" else "sar_filing"
        if st.button(f"File {filing_label}", type="primary", use_container_width=True):
            _record_action(run_dir, case, f"escalated_to_{filing_label.lower()}", filing_q)
    with col_a3:
        if st.button("Close - No Action", use_container_width=True):
            _record_action(run_dir, case, "closed", "closed_no_action")
    with col_a4:
        if st.button("Request EDD", use_container_width=True):
            _record_action(run_dir, case, "edd_requested", "edd_review")
