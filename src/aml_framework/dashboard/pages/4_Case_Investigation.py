"""Case Investigation -- entity profile, transaction timeline, flow diagram."""

from __future__ import annotations

from datetime import datetime, timezone

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from aml_framework.cases.aggregator import aggregate_investigations
from aml_framework.cases.sla import apply_escalation, compute_sla_status
from aml_framework.cases.str_bundle import bundle_investigation_to_str
from aml_framework.dashboard.components import (
    chart_layout,
    citation_link,
    empty_state,
    page_header,
    risk_color,
    severity_color,
    sla_band_color,
    tooltip_banner,
    tour_panel,
)
from aml_framework.dashboard.query_params import consume_param
from aml_framework.engine.constants import Event, Queue


def _record_action(run_dir, case: dict, event: str, disposition: str) -> None:
    """Write a decision to the audit ledger, update case file, and sync session state."""
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    import pandas as pd

    from aml_framework.engine.audit import AuditLedger

    run_dir_path = Path(run_dir)
    ts = datetime.now(tz=timezone.utc)
    decision = {
        "event": event,
        "case_id": case["case_id"],
        "rule_id": case.get("rule_id", ""),
        "queue": case.get("queue", ""),
        "disposition": disposition,
        "source": "dashboard_ui",
    }
    AuditLedger.append_to_run_dir(run_dir_path, decision, ts=ts)

    # Update case file on disk.
    case_path = run_dir_path / "cases" / f"{case['case_id']}.json"
    if case_path.exists():
        case_data = json.loads(case_path.read_bytes())
        case_data["status"] = disposition
        case_data["resolved_at"] = ts.isoformat()
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
        new_row = pd.DataFrame([{"ts": ts.isoformat(), **decision}])
        st.session_state.df_decisions = pd.concat(
            [st.session_state.df_decisions, new_row],
            ignore_index=True,
        )

    st.success(f"Decision recorded: **{event}** -> {disposition}")
    st.caption(f"Written to {(run_dir_path / 'decisions.jsonl').name} and synced to session.")


page_header(
    "Case Investigation",
    "Deep-dive into individual cases with entity profile, transaction timeline, and evidence.",
)

spec = st.session_state.spec
result = st.session_state.result
df_cases = st.session_state.df_cases
df_customers = st.session_state.df_customers
df_txns = st.session_state.df_txns

tour_panel("Case Investigation")
tooltip_banner(
    "Case Investigation",
    "Select a case to see the full investigation package: entity profile, "
    "triggering transactions highlighted on a timeline, regulation citations, "
    "and evidence requested.",
)

if df_cases.empty:
    empty_state(
        "No cases in this run.",
        icon="📭",
        detail="Run the engine via the Alert Queue page or `aml run` first.",
        stop=True,
    )

# --- Case selector ---
# Pre-select via deep link from Alert Queue / Customer 360 / Investigations.
# `consume_param` clears the link state so a refresh doesn't keep re-triggering it.
case_ids = sorted(df_cases["case_id"].tolist())
deep_link_case = consume_param("case_id")
default_idx = case_ids.index(deep_link_case) if deep_link_case in case_ids else 0
selected_case = st.selectbox("Select case", case_ids, index=default_idx)
case = df_cases[df_cases["case_id"] == selected_case].iloc[0].to_dict()

# --- Header banner ---
sev = case.get("severity", "")
sev_color = severity_color(sev)
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

# --- SLA timer + STR bundle download row ---
# The two operator-facing affordances analyst needs at a glance:
#   1. Where this case sits against its queue's SLA (from cases/sla.py)
#   2. One-click STR submission package (from cases/str_bundle.py)
queue_map = {q.id: q for q in spec.workflow.queues}
queue_obj = queue_map.get(case.get("queue", ""))
as_of = st.session_state.get("as_of") or datetime.now(tz=timezone.utc).replace(tzinfo=None)
sla_status = compute_sla_status(case, queue_obj, as_of=as_of) if queue_obj else None

sla_col, escalate_col, bundle_col = st.columns([2, 2, 2])
with sla_col:
    if sla_status is not None:
        band = sla_status["state"]
        band_color = sla_band_color(band)
        st.markdown(
            f'<div style="background:{band_color}15; border-left:4px solid {band_color}; '
            f'padding:0.6rem 1rem; border-radius:6px;">'
            f'<div style="font-size:0.7rem; text-transform:uppercase; letter-spacing:0.05em; '
            f'color:#64748b;">SLA</div>'
            f'<div style="font-size:1.1rem; font-weight:700; color:{band_color};">'
            f"{band.upper()} · {sla_status['time_remaining_hours']:.1f}h remaining"
            f"</div>"
            f'<div style="font-size:0.75rem; color:#64748b;">'
            f"Due {sla_status['due_at'].strftime('%Y-%m-%d %H:%M')}"
            f"</div></div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("SLA: not computable (no opened_at on alert)")

with escalate_col:
    escalation = (
        apply_escalation(case, sla_status, queue_obj)
        if (sla_status is not None and queue_obj is not None)
        else None
    )
    if escalation is not None:
        st.markdown(
            f'<div style="background:#fff7ed; border-left:4px solid #ea580c; '
            f'padding:0.6rem 1rem; border-radius:6px;">'
            f'<div style="font-size:0.7rem; text-transform:uppercase; '
            f'letter-spacing:0.05em; color:#9a3412;">Escalation recommended</div>'
            f'<div style="font-size:1rem; font-weight:600; color:#9a3412;">'
            f"→ {escalation.to_queue}</div>"
            f'<div style="font-size:0.75rem; color:#7c2d12;">'
            f"Reason: {escalation.reason.replace('_', ' ')}</div></div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("Escalation: none recommended")

with bundle_col:
    # One-click STR submission ZIP — bundles narrative + goAML XML +
    # Mermaid network diagram + manifest.json (file-by-file SHA-256).
    # `aggregate_investigations([case], strategy="per_case")` wraps the
    # single case as a one-element investigation so the bundler signature
    # matches its multi-case use cases on Investigations page #24.
    try:
        invs = aggregate_investigations([case], strategy="per_case")
        if invs:
            bundle_bytes = bundle_investigation_to_str(
                invs[0],
                cases=[case],
                spec=spec,
                customers=df_customers.to_dict(orient="records"),
                transactions=df_txns.to_dict(orient="records"),
            )
            st.download_button(
                "📥 STR submission ZIP",
                data=bundle_bytes,
                file_name=f"{case['case_id']}_str_bundle.zip",
                mime="application/zip",
                help="Self-contained ZIP: narrative.txt + goAML XML + "
                "Mermaid network diagram + manifest.json with SHA-256 per file. "
                "Same shape as Investigations page download.",
                use_container_width=True,
            )
    except Exception as e:  # noqa: BLE001 — bundle gen must never crash the page
        st.caption(f"STR bundle unavailable: {e}")

# --- Entity Profile + Alert Details ---
col_profile, col_alert = st.columns(2)

customer_id = case.get("alert", {}).get("customer_id", "")
customer_row = df_customers[df_customers["customer_id"] == customer_id]

with col_profile:
    st.markdown("### Entity Profile")
    if not customer_row.empty:
        c = customer_row.iloc[0]
        cust_risk_color = risk_color(c["risk_rating"])
        st.markdown(
            f'<div class="metric-card">'
            f'<div style="font-size:1.1rem; font-weight:600;">{c["full_name"]}</div>'
            f'<div style="font-size:0.85rem; color:#64748b; margin:0.3rem 0 0.8rem;">'
            f"{c['customer_id']} &middot; {c['country']}</div>"
            f'<div><span style="font-size:0.78rem; color:#64748b;">Risk Rating</span><br>'
            f'<span style="color:{cust_risk_color}; font-weight:700;">{c["risk_rating"].upper()}</span>'
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
            cite_md = citation_link(ref["citation"], ref.get("url"))
            st.markdown(f"- **{cite_md}**: {ref['description']}")

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

    # Save narrative to case file.
    import json
    from datetime import datetime as _dt_case
    from pathlib import Path

    case_path = Path(st.session_state.run_dir) / "cases" / f"{case['case_id']}.json"
    if case_path.exists():
        case_data = json.loads(case_path.read_bytes())
        case_data["narrative_draft"] = narrative
        case_data["narrative_generated_at"] = _dt_case.now().isoformat()
        case_path.write_bytes(
            json.dumps(case_data, indent=2, sort_keys=True, default=str).encode("utf-8")
        )
        st.caption("Narrative saved to case file.")

# --- Case Action Buttons ---
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("### Case Actions")
st.caption("Actions write to the immutable audit ledger (decisions.jsonl).")

run_dir = st.session_state.run_dir
case_status = case.get("status", "open")

if "closed" in case_status or case_status in (Queue.STR_FILING, Queue.SAR_FILING):
    st.success(f"Case already resolved: **{case_status}**")
else:
    col_a1, col_a2, col_a3, col_a4 = st.columns(4)

    with col_a1:
        if st.button("Escalate to L2", use_container_width=True):
            _record_action(run_dir, case, Event.ESCALATED, Queue.L2_INVESTIGATOR)
    with col_a2:
        filing_q = Queue.STR_FILING if jurisdiction == "CA" else Queue.SAR_FILING
        if st.button(f"File {filing_label}", type="primary", use_container_width=True):
            _record_action(run_dir, case, f"escalated_to_{filing_label.lower()}", filing_q)
    with col_a3:
        if st.button("Close - No Action", use_container_width=True):
            _record_action(run_dir, case, Event.CLOSED, Queue.CLOSED_NO_ACTION)
    with col_a4:
        if st.button("Request EDD", use_container_width=True):
            _record_action(run_dir, case, "edd_requested", "edd_review")
