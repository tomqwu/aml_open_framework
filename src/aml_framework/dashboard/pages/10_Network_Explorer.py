"""Network Explorer -- interactive entity relationship graph."""

from __future__ import annotations

import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

from aml_framework.dashboard.components import kpi_card, page_header

page_header(
    "Network Explorer",
    "Entity relationship graph showing customer transaction flows and community patterns.",
)

df_txns = st.session_state.df_txns
df_customers = st.session_state.df_customers
df_alerts = st.session_state.df_alerts

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Network Explorer**\n\n"
        "Customers are nodes, transaction flows are edges. Node size reflects "
        "total volume; color reflects risk rating. Red-bordered nodes have "
        "active alerts. Fan-in patterns (many senders to one receiver) are "
        "flagged as potential funnel accounts."
    )

# --- Build graph data ---
risk_colors = {"high": "#dc2626", "medium": "#d97706", "low": "#16a34a"}
alerted_ids = set()
if not df_alerts.empty and "customer_id" in df_alerts.columns:
    alerted_ids = set(df_alerts["customer_id"].dropna().unique())

# Compute per-customer stats
cust_stats = df_txns.groupby("customer_id").agg(
    total_volume=("amount", "sum"),
    txn_count=("txn_id", "count"),
    channels=("channel", "nunique"),
).reset_index()
cust_info = df_customers.set_index("customer_id")

# Build nodes
nodes = []
for _, row in cust_stats.iterrows():
    cid = row["customer_id"]
    info = cust_info.loc[cid] if cid in cust_info.index else None
    risk = info["risk_rating"] if info is not None else "low"
    name = info["full_name"] if info is not None else cid
    vol = float(row["total_volume"])
    size = max(15, min(50, int(vol / 5000)))
    color = risk_colors.get(risk, "#6b7280")
    border = "#dc2626" if cid in alerted_ids else "#e2e8f0"
    border_width = 3 if cid in alerted_ids else 1

    nodes.append(Node(
        id=cid,
        label=cid,
        title=f"{name}\nRisk: {risk}\nVolume: ${vol:,.0f}\nTxns: {int(row['txn_count'])}",
        size=size,
        color={"background": color, "border": border},
        borderWidth=border_width,
    ))

# Build edges — connect customers who share the same channel activity pattern
# For this demo, create edges between customers in the same "channel cluster"
# by connecting customers who transact through the same rare channels
channel_users: dict[str, list[str]] = {}
for _, row in df_txns.iterrows():
    ch = row["channel"]
    cid = row["customer_id"]
    channel_users.setdefault(ch, [])
    if cid not in channel_users[ch]:
        channel_users[ch].append(cid)

# Also build direct flow edges from transaction patterns
# Group by (customer, direction) to find flow partners
edges: list[Edge] = []
edge_set: set[tuple[str, str]] = set()

# Connect alerted customers to each other (investigation network)
alerted_list = sorted(alerted_ids)
for i, c1 in enumerate(alerted_list):
    for c2 in alerted_list[i + 1:]:
        if (c1, c2) not in edge_set:
            edges.append(Edge(
                source=c1, target=c2,
                color="#dc262640", width=1, dashes=True,
                title="Co-alerted",
            ))
            edge_set.add((c1, c2))

# Connect customers sharing uncommon channels (wire, e_transfer)
for ch in ["wire", "e_transfer"]:
    users = channel_users.get(ch, [])
    for i, c1 in enumerate(users[:10]):
        for c2 in users[i + 1: i + 4]:
            if c1 != c2 and (c1, c2) not in edge_set:
                vol = float(df_txns[
                    (df_txns["customer_id"].isin([c1, c2])) & (df_txns["channel"] == ch)
                ]["amount"].sum())
                edges.append(Edge(
                    source=c1, target=c2,
                    color="#2563eb40", width=max(1, min(5, int(vol / 10000))),
                    title=f"Shared {ch}: ${vol:,.0f}",
                ))
                edge_set.add((c1, c2))

# --- KPI row ---
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Nodes", len(nodes), "#2563eb")
with c2:
    kpi_card("Edges", len(edges), "#7c3aed")
with c3:
    kpi_card("Alerted Nodes", len(alerted_ids), "#dc2626")
with c4:
    # Fan-in: customers receiving from 3+ distinct senders via wire
    fan_in_count = 0
    if not df_txns.empty:
        incoming = df_txns[df_txns["direction"] == "in"].groupby("customer_id")["channel"].count()
        fan_in_count = int((incoming >= 10).sum())
    kpi_card("Fan-In Suspects", fan_in_count, "#d97706")

st.markdown("<br>", unsafe_allow_html=True)

# --- Graph visualization ---
config = Config(
    width=1100,
    height=500,
    directed=False,
    physics=True,
    hierarchical=False,
    nodeHighlightBehavior=True,
    highlightColor="#2563eb",
    collapsible=False,
)

agraph(nodes=nodes, edges=edges, config=config)

st.markdown("<br>", unsafe_allow_html=True)

# --- Alerted customer detail ---
st.markdown("### Alerted Customers Detail")
if alerted_ids:
    detail_df = df_customers[df_customers["customer_id"].isin(alerted_ids)].merge(
        cust_stats, on="customer_id", how="left",
    )
    cols = ["customer_id", "full_name", "country", "risk_rating", "total_volume", "txn_count", "channels"]
    available = [c for c in cols if c in detail_df.columns]
    st.dataframe(detail_df[available], use_container_width=True, hide_index=True)
