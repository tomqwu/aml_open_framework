"""Live Monitor -- real-time transaction monitoring simulation."""

from __future__ import annotations

import time

import plotly.graph_objects as go
import streamlit as st

from aml_framework.dashboard.components import page_header

page_header(
    "Live Monitor",
    "Simulated real-time transaction monitoring with live alert detection.",
)

df_txns = st.session_state.df_txns

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Live Monitor**\n\n"
        "Press **Start Monitoring** to replay synthetic transactions in "
        "real time. Transactions matching alert thresholds (cash > $9,000 or "
        "wire > $20,000) flash as live alerts. This simulates what a "
        "production real-time monitoring feed would look like."
    )

# --- Controls ---
col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([1, 1, 3])
with col_ctrl1:
    start = st.button("Start Monitoring", type="primary", use_container_width=True)
with col_ctrl2:
    stop = st.button("Stop", use_container_width=True)
with col_ctrl3:
    speed = st.select_slider(
        "Speed", options=["Slow", "Normal", "Fast", "Ultra"],
        value="Fast",
    )

speed_map = {"Slow": 0.5, "Normal": 0.25, "Fast": 0.1, "Ultra": 0.02}
delay = speed_map[speed]

if stop:
    st.session_state["monitoring_active"] = False

st.divider()

# --- Dashboard layout ---
kpi_cols = st.columns(4)
kpi_txn_count = kpi_cols[0].empty()
kpi_total_volume = kpi_cols[1].empty()
kpi_alert_count = kpi_cols[2].empty()
kpi_alert_rate = kpi_cols[3].empty()

st.markdown("")
chart_cols = st.columns([3, 2])
chart_placeholder = chart_cols[0].empty()
channel_placeholder = chart_cols[1].empty()

st.markdown("")
feed_header = st.empty()
feed_placeholder = st.empty()
alert_placeholder = st.empty()

if start:
    st.session_state["monitoring_active"] = True

    # Sort transactions chronologically for replay
    sorted_txns = df_txns.sort_values("booked_at").to_dict("records")
    total = len(sorted_txns)

    processed = 0
    volume = 0.0
    alerts_fired = 0
    channel_counts: dict[str, int] = {}
    volume_history: list[float] = []
    recent_alerts: list[dict] = []
    feed_rows: list[dict] = []

    for i, txn in enumerate(sorted_txns):
        if not st.session_state.get("monitoring_active", False):
            break

        processed += 1
        amt = float(txn["amount"])
        volume += amt
        ch = txn["channel"]
        channel_counts[ch] = channel_counts.get(ch, 0) + 1
        volume_history.append(volume)

        # Check for alert condition
        is_alert = (ch == "cash" and amt > 9000) or (ch == "wire" and amt > 20000)
        if is_alert:
            alerts_fired += 1
            recent_alerts.append({
                "Customer": txn["customer_id"],
                "Channel": ch,
                "Amount": f"${amt:,.2f}",
                "Type": "High Cash" if ch == "cash" else "Large Wire",
            })

        feed_rows.append({
            "Time": str(txn["booked_at"])[:19],
            "Customer": txn["customer_id"],
            "Amount": f"${amt:,.2f}",
            "Channel": ch,
            "Dir": txn["direction"],
            "Alert": "!!!" if is_alert else "",
        })

        # Update every 3 transactions to reduce flicker
        if processed % 3 == 0 or i == total - 1:
            # KPIs
            kpi_txn_count.markdown(
                f'<div class="metric-card" style="border-left:4px solid #2563eb;">'
                f'<div class="label">TRANSACTIONS</div>'
                f'<div class="value">{processed:,}</div></div>',
                unsafe_allow_html=True,
            )
            kpi_total_volume.markdown(
                f'<div class="metric-card" style="border-left:4px solid #059669;">'
                f'<div class="label">VOLUME</div>'
                f'<div class="value">${volume:,.0f}</div></div>',
                unsafe_allow_html=True,
            )
            kpi_alert_count.markdown(
                f'<div class="metric-card" style="border-left:4px solid #dc2626;">'
                f'<div class="label">ALERTS</div>'
                f'<div class="value">{alerts_fired}</div></div>',
                unsafe_allow_html=True,
            )
            rate = f"{alerts_fired / processed * 100:.1f}%" if processed > 0 else "0%"
            kpi_alert_rate.markdown(
                f'<div class="metric-card" style="border-left:4px solid #d97706;">'
                f'<div class="label">ALERT RATE</div>'
                f'<div class="value">{rate}</div></div>',
                unsafe_allow_html=True,
            )

            # Volume chart
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                y=volume_history, mode="lines",
                line=dict(color="#2563eb", width=2),
                fill="tozeroy", fillcolor="rgba(37, 99, 235, 0.1)",
            ))
            fig.update_layout(
                title="Cumulative Volume ($)",
                height=280, margin=dict(t=40, b=20, l=40, r=20),
                template="plotly_white",
                xaxis_title="Transactions", yaxis_title="",
                showlegend=False,
            )
            chart_placeholder.plotly_chart(fig, use_container_width=True)

            # Channel breakdown
            if channel_counts:
                fig2 = go.Figure(go.Bar(
                    x=list(channel_counts.values()),
                    y=list(channel_counts.keys()),
                    orientation="h",
                    marker_color=["#d97706", "#2563eb", "#7c3aed", "#6b7280", "#0891b2", "#059669"][
                        :len(channel_counts)
                    ],
                ))
                fig2.update_layout(
                    title="Channel Activity",
                    height=280, margin=dict(t=40, b=20, l=60, r=20),
                    template="plotly_white",
                    xaxis_title="Count", yaxis_title="",
                    showlegend=False,
                )
                channel_placeholder.plotly_chart(fig2, use_container_width=True)

            # Transaction feed (last 15)
            import pandas as pd

            feed_header.markdown(f"### Transaction Feed ({processed}/{total})")
            display = pd.DataFrame(feed_rows[-15:][::-1])
            feed_placeholder.dataframe(display, use_container_width=True, hide_index=True)

            # Alert feed
            if recent_alerts:
                alert_placeholder.markdown(
                    f"### Live Alerts ({alerts_fired})\n"
                )
                alert_placeholder.dataframe(
                    pd.DataFrame(recent_alerts[-8:][::-1]),
                    use_container_width=True, hide_index=True,
                )

            time.sleep(delay)

    st.session_state["monitoring_active"] = False
    st.success(f"Monitoring complete. Processed {processed} transactions, {alerts_fired} alerts fired.")

elif not st.session_state.get("monitoring_active", False):
    # Static view when not monitoring
    st.markdown(
        '<div style="text-align:center; padding:3rem; color:#94a3b8;">'
        '<div style="font-size:3rem;">&#9654;</div>'
        '<div style="font-size:1.1rem;">Press <b>Start Monitoring</b> to begin '
        'real-time transaction replay</div>'
        f'<div style="font-size:0.85rem; margin-top:0.5rem;">'
        f'{len(df_txns)} transactions ready for replay</div>'
        '</div>',
        unsafe_allow_html=True,
    )
