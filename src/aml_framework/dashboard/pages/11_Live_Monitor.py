"""Live Monitor -- real-time transaction monitoring simulation.

Alert conditions are derived from the spec's aggregation_window rules:
each rule's filter and having clauses are translated into per-transaction
screening thresholds. This is NOT the full windowed engine (which requires
the complete dataset), but it applies the spec-defined filters so the
thresholds shown are real, not hardcoded.
"""

from __future__ import annotations

import time
from typing import Any

import streamlit as st

from aml_framework.dashboard.components import (
    bar_chart,
    empty_state,
    line_chart,
    page_header,
)

page_header(
    "Live Monitor",
    "Simulated real-time transaction monitoring with spec-driven alert detection.",
)

spec = st.session_state.spec
df_txns = st.session_state.df_txns

# Phase E empty-state guard — degenerate specs (zero txns / zero rules)
# previously crashed downstream pandas + plotly calls. Bail out cleanly.
if df_txns is None or df_txns.empty:
    empty_state(
        "No transaction data loaded for live monitoring.",
        icon="📭",
        detail=(
            "The Live Monitor replays a transaction stream — when the run "
            "produced zero transactions there is nothing to play back. "
            "Load a spec with sample data or wire `data_sources` in the spec."
        ),
        stop=True,
    )


def _build_screening_rules(spec_obj: Any) -> list[dict[str, Any]]:
    """Extract per-transaction screening conditions from spec rules.

    For aggregation_window rules, we use the filter conditions as the
    per-transaction screen and the having.sum_amount threshold as the
    amount trigger. For custom_sql rules, we flag transactions from
    customers already flagged by the batch engine.
    """
    screens: list[dict[str, Any]] = []
    alerted_customers = set()
    if not st.session_state.df_alerts.empty and "customer_id" in st.session_state.df_alerts.columns:
        alerted_customers = set(st.session_state.df_alerts["customer_id"].dropna().unique())

    for rule in spec_obj.rules:
        if rule.status != "active":
            continue

        if rule.logic.type == "aggregation_window":
            filt = rule.logic.filter or {}
            having = rule.logic.having or {}
            # Extract channel filter.
            channels = None
            if "channel" in filt:
                ch_val = filt["channel"]
                if isinstance(ch_val, str):
                    channels = {ch_val}
                elif isinstance(ch_val, dict) and "in" in ch_val:
                    channels = set(ch_val["in"])
            # Extract direction filter.
            direction = filt.get("direction")
            # Extract amount range from filter.
            amt_filter = filt.get("amount", {})
            amt_min = None
            if isinstance(amt_filter, dict) and "between" in amt_filter:
                amt_min = amt_filter["between"][0]
            # Extract having threshold (sum_amount).
            sum_threshold = None
            if "sum_amount" in having:
                cond = having["sum_amount"]
                if isinstance(cond, dict) and "gte" in cond:
                    sum_threshold = cond["gte"]
            # Per-transaction threshold: use sum_threshold / having.count
            # as a heuristic for "this single txn is suspicious".
            count_min = 1
            if "count" in having:
                cond = having["count"]
                if isinstance(cond, dict) and "gte" in cond:
                    count_min = cond["gte"]
            per_txn_threshold = (sum_threshold / count_min) if sum_threshold and count_min else None

            screens.append(
                {
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "severity": rule.severity,
                    "channels": channels,
                    "direction": direction,
                    "amt_min": amt_min,
                    "per_txn_threshold": per_txn_threshold,
                }
            )
        else:
            # For custom_sql/python_ref rules, flag transactions from
            # customers the batch engine already alerted on.
            screens.append(
                {
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "severity": rule.severity,
                    "alerted_customers": alerted_customers,
                    "channels": None,
                    "direction": None,
                    "amt_min": None,
                    "per_txn_threshold": None,
                }
            )
    return screens


def _check_transaction(txn: dict, screens: list[dict]) -> str | None:
    """Return the rule_id that flags this transaction, or None."""
    ch = txn.get("channel", "")
    direction = txn.get("direction", "")
    amt = float(txn.get("amount", 0))
    cid = txn.get("customer_id", "")

    for screen in screens:
        # Channel filter.
        if screen["channels"] and ch not in screen["channels"]:
            continue
        # Direction filter.
        if screen["direction"] and direction != screen["direction"]:
            continue
        # Amount minimum (from filter range like "between: [7000, 9999]").
        if screen["amt_min"] is not None and amt < screen["amt_min"]:
            continue
        # Per-transaction threshold (derived from having.sum_amount / count).
        if screen["per_txn_threshold"] is not None and amt >= screen["per_txn_threshold"]:
            return screen["rule_id"]
        # Customer-level flag from batch engine (for custom_sql rules).
        if screen.get("alerted_customers") and cid in screen["alerted_customers"]:
            if screen["per_txn_threshold"] is None:
                return screen["rule_id"]
    return None


if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Live Monitor**\n\n"
        f"Alert conditions are derived from the **{len(spec.rules)} spec rules**. "
        "Aggregation-window rules contribute per-transaction amount thresholds; "
        "custom-SQL and python_ref rules flag transactions from customers "
        "already alerted by the batch engine. Press **Start Monitoring** to begin."
    )

# Show which rules drive the screening.
with st.expander("Screening rules (derived from spec)"):
    screens = _build_screening_rules(spec)
    for s in screens:
        ch_str = ", ".join(sorted(s["channels"])) if s.get("channels") else "any"
        thr = f"${s['per_txn_threshold']:,.0f}" if s.get("per_txn_threshold") else "customer-level"
        st.markdown(
            f"- **{s['rule_id']}** ({s['severity']}) — channels: {ch_str}, threshold: {thr}"
        )

# --- Controls ---
col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([1, 1, 3])
with col_ctrl1:
    start = st.button("Start Monitoring", type="primary", use_container_width=True)
with col_ctrl2:
    stop = st.button("Stop", use_container_width=True)
with col_ctrl3:
    speed = st.select_slider(
        "Speed",
        options=["Slow", "Normal", "Fast", "Ultra"],
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
    screens = _build_screening_rules(spec)

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

        # Check against spec-derived screening rules.
        matched_rule = _check_transaction(txn, screens)
        if matched_rule:
            alerts_fired += 1
            rule_obj = next((r for r in spec.rules if r.id == matched_rule), None)
            recent_alerts.append(
                {
                    "Customer": txn["customer_id"],
                    "Rule": matched_rule,
                    "Severity": rule_obj.severity if rule_obj else "?",
                    "Amount": f"${amt:,.2f}",
                    "Channel": ch,
                }
            )

        feed_rows.append(
            {
                "Time": str(txn["booked_at"])[:19],
                "Customer": txn["customer_id"],
                "Amount": f"${amt:,.2f}",
                "Channel": ch,
                "Dir": txn["direction"],
                "Alert": matched_rule or "",
            }
        )

        if processed % 3 == 0 or i == total - 1:
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

            import pandas as pd

            # Cumulative volume — area chart inside the placeholder.
            # The placeholder's `.empty()` clears the previous render
            # and `.container()` opens a fresh DG context for the new
            # tick. We must NOT pass an explicit st_echarts `key` —
            # Streamlit registers keys globally and a stable key would
            # collide across loop iterations (StreamlitDuplicateElementId).
            # Without `key`, each tick gets its own auto-id scoped to
            # the container; cheap because the DOM only diffs the
            # canvas's data.
            volume_df = pd.DataFrame(
                {"i": list(range(len(volume_history))), "volume": volume_history}
            )
            chart_placeholder.empty()
            with chart_placeholder.container():
                line_chart(
                    volume_df,
                    x="i",
                    y="volume",
                    area=True,
                    smooth=True,
                    markers=False,
                    title="Cumulative Volume ($)",
                    height=280,
                )

            if channel_counts:
                channel_df = pd.DataFrame(
                    {
                        "channel": list(channel_counts.keys()),
                        "count": list(channel_counts.values()),
                    }
                )
                channel_placeholder.empty()
                with channel_placeholder.container():
                    bar_chart(
                        channel_df,
                        x="channel",
                        y="count",
                        orientation="h",
                        title="Channel Activity",
                        height=280,
                    )

            feed_header.markdown(f"### Transaction Feed ({processed}/{total})")
            display = pd.DataFrame(feed_rows[-15:][::-1])
            feed_placeholder.dataframe(display, use_container_width=True, hide_index=True)

            if recent_alerts:
                alert_placeholder.markdown(f"### Live Alerts ({alerts_fired})")
                alert_placeholder.dataframe(
                    pd.DataFrame(recent_alerts[-8:][::-1]),
                    use_container_width=True,
                    hide_index=True,
                )

            time.sleep(delay)

    st.session_state["monitoring_active"] = False
    st.success(
        f"Monitoring complete. {processed} transactions, {alerts_fired} alerts from spec rules."
    )

elif not st.session_state.get("monitoring_active", False):
    screens = _build_screening_rules(spec)
    rule_count = len(screens)
    st.markdown(
        f'<div style="text-align:center; padding:3rem; color:#94a3b8;">'
        f'<div style="font-size:3rem;">&#9654;</div>'
        f'<div style="font-size:1.1rem;">Press <b>Start Monitoring</b> to begin '
        f"real-time transaction replay</div>"
        f'<div style="font-size:0.85rem; margin-top:0.5rem;">'
        f"{len(df_txns)} transactions | {rule_count} screening rules from spec</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
