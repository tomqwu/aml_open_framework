"""Network Explorer -- entity relationship graph from real transaction flows.

Edges represent actual transaction activity patterns:
- Customers with correlated timing (transactions within 1 hour of each other)
  are connected, weighted by volume — this surfaces pass-through and layering.
- Fan-in detection counts distinct senders (customers whose outflows precede
  another customer's inflows within a time window).
"""

from __future__ import annotations

import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

from aml_framework.dashboard.components import (
    data_grid,
    empty_state,
    kpi_card_rag,
    link_to_page,
    page_header,
    risk_color,
)
from aml_framework.dashboard.audience import show_audience_context

page_header(
    "Network Explorer",
    "Entity relationship graph based on transaction flow correlations.",
)
show_audience_context("Network Explorer")

df_txns = st.session_state.df_txns
df_customers = st.session_state.df_customers
df_alerts = st.session_state.df_alerts

# Phase E empty-state guard — the network graph needs at least 2
# customers with txns to draw any edges. On degenerate specs (zero
# txns or single-customer fixture) the agraph block + groupby would
# raise; bail out cleanly with operator guidance instead.
if df_txns is None or df_txns.empty:
    empty_state(
        "No transaction data — network graph needs txns to compute edges.",
        icon="🕸️",
        detail=(
            "The Network Explorer derives edges from temporal correlations "
            "between customer txns. Without txns there is nothing to draw. "
            "Load a spec with sample data or wire `data_sources`."
        ),
        stop=True,
    )

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Network Explorer**\n\n"
        "Edges connect customers whose transactions are **temporally correlated** "
        "(within 1 hour of each other), which surfaces pass-through and layering "
        "patterns. Node size = total volume, color = risk rating, red border = "
        "active alert. Fan-in counts distinct customers whose outflows precede "
        "another's inflows."
    )

# --- Build graph data ---
alerted_ids = set()
if not df_alerts.empty and "customer_id" in df_alerts.columns:
    alerted_ids = set(df_alerts["customer_id"].dropna().unique())

# --- Filters --- (PR 5)
# Past ~25 customers the full graph becomes hairball-soup. Filters let
# the user trim to (a) only customers with active alerts + their direct
# counterparties, or (b) nodes with high fan-in degree. Both filters
# are computed before edge construction so the rendered graph stays
# legible without the agraph layout fighting itself.
fc1, fc2, fc3 = st.columns([2, 2, 1])
with fc1:
    show_alerted_only = st.toggle(
        "Show alerted nodes + counterparties only",
        value=False,
        help=(
            "Hides customers with no active alert AND no temporal "
            "correlation to an alerted customer. Surfaces the "
            "investigation-relevant subgraph."
        ),
    )
with fc2:
    min_fan_in = st.slider(
        "Minimum fan-in (correlated counterparties)",
        min_value=0,
        max_value=10,
        value=0,
        help="Filter to nodes whose temporal-correlation degree ≥ this threshold.",
    )
with fc3:
    st.caption(f"{len(df_customers)} total customers in spec")

# Per-customer stats.
cust_stats = (
    df_txns.groupby("customer_id")
    .agg(
        total_volume=("amount", "sum"),
        txn_count=("txn_id", "count"),
        channels=("channel", "nunique"),
    )
    .reset_index()
)
cust_info = df_customers.set_index("customer_id")

# Build nodes.
nodes = []
for _, row in cust_stats.iterrows():
    cid = row["customer_id"]
    info = cust_info.loc[cid] if cid in cust_info.index else None
    risk = info["risk_rating"] if info is not None else "low"
    name = info["full_name"] if info is not None else cid
    vol = float(row["total_volume"])
    size = max(15, min(50, int(vol / 5000)))
    color = risk_color(risk)
    border = "#dc2626" if cid in alerted_ids else "#e2e8f0"
    border_width = 3 if cid in alerted_ids else 1

    nodes.append(
        Node(
            id=cid,
            label=cid,
            title=f"{name}\nRisk: {risk}\nVolume: ${vol:,.0f}\nTxns: {int(row['txn_count'])}",
            size=size,
            color={"background": color, "border": border},
            borderWidth=border_width,
        )
    )

# Build edges from temporal correlation.
# Two customers are linked if one has an outflow and the other has an inflow
# within 1 hour — this is how pass-through and layering are detected.
edges: list[Edge] = []
edge_weights: dict[tuple[str, str], float] = {}

if not df_txns.empty:
    outflows = df_txns[df_txns["direction"] == "out"].sort_values("booked_at")
    inflows = df_txns[df_txns["direction"] == "in"].sort_values("booked_at")

    # For efficiency with small datasets, do a pairwise check.
    out_records = outflows[["customer_id", "booked_at", "amount"]].to_dict("records")
    in_records = inflows[["customer_id", "booked_at", "amount"]].to_dict("records")

    for out_txn in out_records:
        for in_txn in in_records:
            if out_txn["customer_id"] == in_txn["customer_id"]:
                continue
            # Check temporal proximity: inflow within 0-60 minutes after outflow.
            delta = (in_txn["booked_at"] - out_txn["booked_at"]).total_seconds()
            if 0 <= delta <= 3600:
                pair = tuple(sorted([out_txn["customer_id"], in_txn["customer_id"]]))
                vol = float(min(out_txn["amount"], in_txn["amount"]))
                edge_weights[pair] = edge_weights.get(pair, 0) + vol

    for (c1, c2), vol in edge_weights.items():
        width = max(1, min(6, int(vol / 5000)))
        both_alerted = c1 in alerted_ids and c2 in alerted_ids
        color = "rgba(220, 38, 38, 0.5)" if both_alerted else "rgba(37, 99, 235, 0.3)"
        edges.append(
            Edge(
                source=c1,
                target=c2,
                color=color,
                width=width,
                title=f"Correlated flow: ${vol:,.0f}",
            )
        )

# Fan-in detection: count distinct senders (outflow customers correlated
# with a given customer's inflows).
fan_in_counts: dict[str, set[str]] = {}
for c1, c2 in edge_weights:
    fan_in_counts.setdefault(c1, set()).add(c2)
    fan_in_counts.setdefault(c2, set()).add(c1)
fan_in_suspects = {cid for cid, senders in fan_in_counts.items() if len(senders) >= 3}

# --- Apply filters (PR 5) ---
# After edges are computed we know which nodes are connected to which.
# Filtering the *node* list shrinks the visible graph; edges referencing
# filtered-out nodes are dropped automatically by agraph.
if show_alerted_only and alerted_ids:
    keep_ids = set(alerted_ids)
    # Include direct counterparties so the alerted node has context.
    for c1, c2 in edge_weights:
        if c1 in alerted_ids:
            keep_ids.add(c2)
        if c2 in alerted_ids:
            keep_ids.add(c1)
    nodes = [n for n in nodes if n.id in keep_ids]
    edges = [e for e in edges if e.source in keep_ids and e.to in keep_ids]
if min_fan_in > 0:
    keep_ids = {cid for cid, senders in fan_in_counts.items() if len(senders) >= min_fan_in}
    nodes = [n for n in nodes if n.id in keep_ids]
    edges = [e for e in edges if e.source in keep_ids and e.to in keep_ids]

# --- KPI row ---
# Alerted nodes carries an actual assessment (any alert is a state to
# notice). Fan-in suspects ≥ 3 also a signal — bind to red. Counts of
# total nodes/edges are facts.
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card_rag("Nodes", len(nodes))
with c2:
    kpi_card_rag("Flow Edges", len(edges))
with c3:
    kpi_card_rag(
        "Alerted Nodes",
        len(alerted_ids),
        rag="red" if alerted_ids else None,
    )
with c4:
    kpi_card_rag(
        "Fan-In (3+ links)",
        len(fan_in_suspects),
        rag="red" if fan_in_suspects else None,
    )

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

# --- Drill-down to Customer 360 ---
# streamlit-agraph node-click events don't reliably bubble up through
# Streamlit's component bridge in the version we depend on, so the
# pragmatic deep-link is a selectbox below the graph: pick any node + jump
# to that customer's 360 view. Defaults to the first alerted node when
# present so the most-investigation-relevant node is one click away.
node_options = [n.id for n in nodes]
if node_options:
    default_node = (
        next((n for n in node_options if n in alerted_ids), node_options[0])
        if alerted_ids
        else node_options[0]
    )
    drill_n1, drill_n2 = st.columns([3, 2])
    with drill_n1:
        drill_node = st.selectbox(
            "Drill into node",
            node_options,
            index=node_options.index(default_node),
            key="network_node_drill",
        )
    with drill_n2:
        st.write("")
        link_to_page(
            "pages/17_Customer_360.py",
            f"→ Open {drill_node} in Customer 360",
            customer_id=drill_node,
        )

st.markdown("<br>", unsafe_allow_html=True)

# --- Fan-in suspects ---
if fan_in_suspects:
    st.markdown("### Fan-In Suspects (3+ correlated counterparties)")
    suspects_df = df_customers[df_customers["customer_id"].isin(fan_in_suspects)].copy()
    if not suspects_df.empty:
        suspects_df = suspects_df.merge(cust_stats, on="customer_id", how="left")
        suspects_df["links"] = suspects_df["customer_id"].map(
            lambda cid: len(fan_in_counts.get(cid, set()))
        )
        cols = ["customer_id", "full_name", "country", "risk_rating", "total_volume", "links"]
        available = [c for c in cols if c in suspects_df.columns]
        data_grid(
            suspects_df[available],
            key="network_fan_in_suspects",
            risk_col="risk_rating" if "risk_rating" in available else None,
            pinned_left=["customer_id"] if "customer_id" in available else None,
            height=300,
        )

# --- Alerted customer detail ---
st.markdown("### Alerted Customers")
if alerted_ids:
    detail_df = df_customers[df_customers["customer_id"].isin(alerted_ids)].merge(
        cust_stats,
        on="customer_id",
        how="left",
    )
    cols = ["customer_id", "full_name", "country", "risk_rating", "total_volume", "txn_count"]
    available = [c for c in cols if c in detail_df.columns]
    data_grid(
        detail_df[available],
        key="network_alerted_customers",
        risk_col="risk_rating" if "risk_rating" in available else None,
        pinned_left=["customer_id"] if "customer_id" in available else None,
        height=300,
    )
