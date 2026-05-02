"""Executive Dashboard -- program-level KPIs and health overview.

Visual upgrade (board-pack "wow factor"): the page is what board members
open. It now leads with a Bloomberg-terminal-style trust strip (hash
chain status), then a 3-tile headline hero (the most-urgent number, with
the others demoted to a secondary KPI bar). Every KPI carries a
sparkline + delta-vs-prior-run when run-history is available. The
effectiveness funnel is rendered as both a Plotly Sankey (alerts → cases
→ STRs flow) and a Waterfall (per-stage drop-off magnitude). The radar
gets gap annotations and a 500ms fade-up reveal sweeps the page on load.

Reuses helpers in `dashboard/components.py` (terminal_block,
headline_hero, kpi_card_with_trend, kpi_card_rag, chart_layout) and
the new `dashboard/run_history.py` for sparkline data.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from aml_framework.dashboard.components import (
    RAG_COLORS,
    bar_chart,
    headline_hero,
    kpi_card_rag,
    kpi_card_with_trend,
    link_to_page,
    metric_table,
    page_header,
    radar_chart,
    sankey_chart,
    terminal_block,
    waterfall_chart,
)
from aml_framework.dashboard.run_history import (
    delta_pct,
    manifest_field_history,
    metric_value_history,
    numeric_only,
    recent_runs,
)
from aml_framework.engine.audit import AuditLedger

page_header(
    "Executive Dashboard",
    "The headline picture: how the program is doing, what needs your attention.",
)

spec = st.session_state.spec
result = st.session_state.result
df_alerts = st.session_state.df_alerts
audience = st.session_state.get("selected_audience")
run_dir = Path(st.session_state.run_dir)

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Executive Dashboard**\n\n"
        f"The engine detected **{result.total_alerts} alerts** across "
        f"**{len(spec.rules)} rules**, covering multiple AML typologies. "
        "KPI cards show program health. The RAG grid below tracks every "
        "metric with red/amber/green thresholds."
    )

# ---------------------------------------------------------------------------
# Workstream A · Trust strip — Bloomberg-terminal aesthetic at the very top
# ---------------------------------------------------------------------------
# This block is what makes the page board-pack credible. Hash chain
# verification at the top — the same trust signal as the Audit & Evidence
# page, surfaced before the headline numbers so the audience knows the
# data they're about to read is provable.
manifest = result.manifest
spec_hash = manifest.get("spec_content_hash", "")
output_hash = manifest.get("output_hash", "")
engine_version = manifest.get("engine_version", "n/a")
ts_raw = manifest.get("ts", "")
ts_short = ts_raw[:19] if ts_raw else ""

# Re-verify the audit chain on every page load — quick stat-call read,
# the result feeds the trust strip's status row.
chain_valid, chain_msg = AuditLedger.verify_decisions(run_dir)
chain_kind = "ok" if chain_valid else "bad"
chain_label = "✓ chain verified" if chain_valid else "✗ TAMPER DETECTED"

terminal_block(
    [
        ("Spec Hash", spec_hash[:16] + "…" if len(spec_hash) > 16 else (spec_hash or "—"), "hash"),
        (
            "Output Hash",
            output_hash[:16] + "…" if len(output_hash) > 16 else (output_hash or "—"),
            "hash",
        ),
        ("Engine", engine_version, ""),
        ("Run At", ts_short or "—", ""),
        ("Audit Chain", f"{chain_label} · {chain_msg}", chain_kind),
    ]
)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Workstream A · Headline hero — the 3 numbers the board sees first
# ---------------------------------------------------------------------------
# Tile 1 (largest, accent border): the most-urgent number — picked
# *automatically* from the program state, not hardcoded:
#   - SLA breaches if any
#   - else high-severity alerts requiring action
#   - else the volume of total alerts (the picture, not an alarm)
#   - else a green "all clear"
# Tiles 2 + 3: total alerts, and open cases vs SLA-at-risk count.

metrics_by_id = {m.id: m for m in result.metrics}

# Compute hero anchor metrics from data we already have.
total_alerts = result.total_alerts
open_cases = len(result.case_ids)
high_sev_rule_ids = {r.id for r in spec.rules if r.severity == "high"}
high_sev_alerts = (
    int(df_alerts[df_alerts["rule_id"].isin(high_sev_rule_ids)].shape[0])
    if not df_alerts.empty
    else 0
)

# SLA-at-risk count — hand it from the SLA metric if available, else 0.
sla_metric = metrics_by_id.get("sla_breach_pct") or metrics_by_id.get("sla_breach_rate")
sla_at_risk = (
    int(sla_metric.value) if sla_metric and isinstance(sla_metric.value, (int, float)) else 0
)

# Pick the urgent tile. The selector is intentionally simple — the
# board needs ONE number to look at, not a panel of equal weights.
if sla_at_risk > 0:
    urgent_label = "SLA Breaches"
    urgent_value = sla_at_risk
    urgent_rag = "red"
    urgent_caption = "Cases past SLA. Open Investigations to triage."
elif high_sev_alerts > 0:
    urgent_label = "High-Severity Alerts"
    urgent_value = high_sev_alerts
    urgent_rag = "amber"
    urgent_caption = f"From {len(high_sev_rule_ids)} high-severity rules. Triage from Alert Queue."
elif total_alerts > 0:
    urgent_label = "Alerts in This Run"
    urgent_value = total_alerts
    urgent_rag = None  # Neutral — alerts at this volume are the program working, not an alarm
    urgent_caption = (
        f"Across {len([r for r in spec.rules if r.status == 'active'])} active detectors."
    )
else:
    urgent_label = "All Clear"
    urgent_value = "✓"
    urgent_rag = "green"
    urgent_caption = "Zero alerts in the current run."

headline_hero(
    [
        {
            "label": urgent_label,
            "value": urgent_value,
            "rag": urgent_rag,
            "caption": urgent_caption,
        },
        {
            "label": "Total Alerts",
            "value": f"{total_alerts:,}",
            "rag": None,
            "caption": (
                f"{int(df_alerts['customer_id'].nunique()):,} distinct customers"
                if not df_alerts.empty and "customer_id" in df_alerts.columns
                else "No alerts this run"
            ),
        },
        {
            "label": "Open Cases",
            "value": f"{open_cases:,}",
            "rag": "amber" if sla_at_risk > 0 else None,
            "caption": (
                f"{sla_at_risk} SLA-at-risk · open Investigations"
                if sla_at_risk > 0
                else "Cases active in queue"
            ),
        },
    ]
)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Workstream B · Secondary KPI row with sparklines + run-deltas
# ---------------------------------------------------------------------------
# 4 facts demoted from the original 6-up: Active Rules, Typology
# Coverage, Customers Alerted, Volume Screened. Each renders the
# sparkline of its prior-run history when the run dir has siblings;
# falls back to "(no prior runs)" otherwise (no layout shift).

# Pull up to 8 prior runs (oldest → newest, current included as the
# last element) for the sparklines. Single filesystem walk; cheap.
runs = recent_runs(run_dir, n=8)

# History arrays. `manifest_field_history` reads top-level manifest
# fields; `metric_value_history` reads from metrics.json or the
# manifest.metrics array.
hist_alerts = manifest_field_history(runs, "total_alerts")
hist_coverage = metric_value_history(runs, "typology_coverage")
hist_customers = metric_value_history(runs, "distinct_customers_alerted")
hist_volume = metric_value_history(runs, "transaction_volume_usd") or metric_value_history(
    runs, "transaction_volume_cad"
)

active_rule_count = len([r for r in spec.rules if r.status == "active"])
tc = metrics_by_id.get("typology_coverage")
dc = metrics_by_id.get("distinct_customers_alerted")
tv = metrics_by_id.get("transaction_volume_usd") or metrics_by_id.get("transaction_volume_cad")

c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card_with_trend(
        "Active Rules",
        active_rule_count,
        trend_values=None,  # Active rule count is a config fact; trend doesn't add signal
    )
with c2:
    kpi_card_with_trend(
        "Typology Coverage",
        f"{tc.value * 100:.0f}%" if tc else "N/A",
        trend_values=numeric_only(hist_coverage)
        if any(v is not None for v in hist_coverage)
        else None,
        rag=tc.rag if tc else None,
        delta_pct=delta_pct(hist_coverage),
        delta_dir="higher-better",
    )
with c3:
    kpi_card_with_trend(
        "Customers Alerted",
        int(dc.value) if dc else 0,
        trend_values=numeric_only(hist_customers)
        if any(v is not None for v in hist_customers)
        else None,
        rag=dc.rag if dc else None,
        delta_pct=delta_pct(hist_customers),
        delta_dir="neutral",
    )
with c4:
    if tv:
        kpi_card_with_trend(
            "Volume Screened",
            f"${tv.value:,.0f}",
            trend_values=numeric_only(hist_volume)
            if any(v is not None for v in hist_volume)
            else None,
            rag=tv.rag,
            delta_pct=delta_pct(hist_volume),
            delta_dir="neutral",
        )
    else:
        kpi_card_with_trend("Volume Screened", "N/A")

# --- KPI drill-downs (preserved from previous layout) ---
drill_a, drill_b, _, _ = st.columns(4)
with drill_a:
    link_to_page("pages/3_Alert_Queue.py", "→ Triage alerts")
with drill_b:
    link_to_page("pages/24_Investigations.py", "→ Open investigations")

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Charts row — Alerts by Rule + RAG metrics (preserved with polish)
# ---------------------------------------------------------------------------
col_left, col_right = st.columns([3, 2])

with col_left:
    st.markdown("### Alerts by Rule")
    if not df_alerts.empty:
        sev_map = {r.id: r.severity for r in spec.rules}
        chart_df = df_alerts.groupby("rule_id").size().reset_index(name="count")
        chart_df["severity"] = chart_df["rule_id"].map(sev_map)
        chart_df = chart_df.sort_values("count", ascending=True)
        # `color="severity"` paints each rule's bar with the severity
        # palette automatically — no per-page colour map needed.
        bar_chart(
            chart_df,
            x="rule_id",
            y="count",
            color="severity",
            orientation="h",
            height=350,
            key="exec_alerts_by_rule",
        )
    else:
        st.info("No alerts generated.")

with col_right:
    st.markdown("### RAG Status")
    metric_table(result.metrics, audience=audience)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Workstream D · Bigger Program Health radar with target-gap annotations
# ---------------------------------------------------------------------------
col_radar, col_summary = st.columns([3, 2])

with col_radar:
    st.markdown("### Program Health")
    radar_metrics = [m for m in result.metrics if m.rag != "unset"][:8]
    categories = [m.name[:25] for m in radar_metrics]
    values = [{"green": 3, "amber": 2, "red": 1}.get(m.rag, 0) for m in radar_metrics]

    if categories and values:
        # Target ring at 3 (green = strongest RAG); current overlays.
        # Gap caption below the radar is the board-pack-legible reading
        # — annotations inside polar charts are universally clunky.
        indicators = [(cat, 3.5) for cat in categories]
        radar_chart(
            indicators=indicators,
            series=[("Target", [3] * len(categories)), ("Current", values)],
            height=480,
            key="exec_program_health_radar",
        )
        gaps = [(cat, 3 - v) for cat, v in zip(categories, values, strict=False) if v < 3]
        if gaps:
            gap_caption = " · ".join(f"{cat}: −{g}pt" for cat, g in gaps[:5])
            st.caption(f"**Gaps to target:** {gap_caption}")
        else:
            st.caption(f"**At target across all {len(categories)} dimensions.**")

with col_summary:
    st.markdown("### Run Summary")
    st.markdown(
        f"""
| | |
|---|---|
| **Program** | {spec.program.name} |
| **Jurisdiction** | {spec.program.jurisdiction} |
| **Regulator** | {spec.program.regulator} |
| **Rules executed** | {len(spec.rules)} |
| **Total alerts** | {result.total_alerts} |
| **Cases opened** | {len(result.case_ids)} |
| **Metrics computed** | {len(result.metrics)} |
| **Reports generated** | {len(result.reports)} |
"""
    )

    # Export report download.
    audience_sel = st.session_state.get("selected_audience") or "svp"
    matching_reports = [(rid, md) for rid, md in result.reports.items() if audience_sel in rid]
    if matching_reports:
        rid, md = matching_reports[0]
        st.download_button(
            f"Download {rid} report",
            md,
            f"{rid}.md",
            "text/markdown",
            use_container_width=True,
        )

    # Board PDF export.
    if st.button("Generate Board PDF", use_container_width=True):
        from aml_framework.dashboard.maturity import compute_maturity_scores
        from aml_framework.generators.board_pdf import generate_board_pdf

        cases = []
        cases_dir = run_dir / "cases"
        if cases_dir.exists():
            for f in sorted(cases_dir.glob("*.json")):
                cases.append(json.loads(f.read_bytes()))

        maturity = compute_maturity_scores(spec)
        pdf_bytes = generate_board_pdf(
            spec=spec,
            metrics=[m.to_dict() for m in result.metrics],
            cases=cases,
            maturity_scores=maturity,
        )
        st.download_button(
            "Download Board PDF",
            pdf_bytes,
            f"{spec.program.name.replace(' ', '_')}_board_report.pdf",
            "application/pdf",
            use_container_width=True,
        )

# ---------------------------------------------------------------------------
# Workstream C · Effectiveness Funnel — Sankey (flow) + Waterfall (drop-off)
# ---------------------------------------------------------------------------
# Both FinCEN's NPRM and AMLA's RTS treat alert→case→STR conversion as
# the canonical effectiveness measure. Replaces the old 4-card flat
# funnel: Sankey shows the FLOW (where volume goes), Waterfall shows
# the DROP-OFF magnitude per stage. Same data, two views.

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("### Effectiveness Funnel")
st.caption(
    "Alert → case → STR conversion + per-rule precision (when labels supplied). "
    "Same numbers FinCEN's April 2026 NPRM and AMLA's RTS (due 2026-07-10) treat "
    "as the canonical effectiveness measure. Sankey shows flow; Waterfall shows drop-off."
)

try:
    from aml_framework.metrics.outcomes import compute_outcomes, format_amla_rts_json

    _cases: list[dict] = []
    _cases_dir = run_dir / "cases"
    if _cases_dir.exists():
        for _f in sorted(_cases_dir.glob("*.json")):
            _cases.append(json.loads(_f.read_text(encoding="utf-8")))
    _decisions: list[dict] = []
    _dec_path = run_dir / "decisions.jsonl"
    if _dec_path.exists():
        for _line in _dec_path.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line:
                _decisions.append(json.loads(_line))

    _report = compute_outcomes(_cases, _decisions, spec_program=spec.program.name)

    # Fan-out the 4 stages: alerts → cases opened → cases with STR
    # filed → cases closed-no-action. Drop-offs in amber are the
    # false-positive surface.
    n_alerts = _report.total_alerts
    n_cases = _report.total_cases
    n_str = _report.total_str_filed
    n_closed = sum(r.closed_no_action for r in _report.rules)
    # The "alert → case" drop-off includes alerts that never made it
    # into a case (filtered by aggregation strategy).
    alerts_no_case = max(n_alerts - n_cases, 0)
    cases_pending = max(n_cases - n_str - n_closed, 0)

    # Funnel KPI strip — same 4-card row as before, kept for the
    # numbers-at-a-glance audience. Sankey/Waterfall are below.
    pct = _report.alert_to_str_pct or 0
    if pct >= 10:
        funnel_rag = "green"
    elif pct >= 5:
        funnel_rag = "amber"
    elif pct > 0:
        funnel_rag = "red"
    else:
        funnel_rag = None
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        kpi_card_rag("Alerts", n_alerts)
    with fc2:
        kpi_card_rag("Cases", n_cases)
    with fc3:
        kpi_card_rag("STR filed", n_str)
    with fc4:
        kpi_card_rag("Alert → STR", f"{_report.alert_to_str_pct}%", rag=funnel_rag)

    funnel_left, funnel_right = st.columns(2)

    with funnel_left:
        st.markdown("##### Sankey · alert → case → STR flow")
        # Node order:
        #   0  Alerts
        #   1  Cases opened
        #   2  Filtered (no case)
        #   3  STR filed
        #   4  Closed-no-action
        #   5  Pending
        if n_alerts > 0:
            # Sankey nodes carry the count in the label so the funnel
            # tells its own story; edges connect alerts → cases → STR
            # plus the drop-off branches (filtered / closed / pending).
            nodes = [
                f"Alerts ({n_alerts:,})",
                f"Cases ({n_cases:,})",
                f"Filtered ({alerts_no_case:,})",
                f"STR filed ({n_str:,})",
                f"Closed · no action ({n_closed:,})",
                f"Pending ({cases_pending:,})",
            ]
            edges = [
                (nodes[0], nodes[1], float(max(n_cases, 1))),
                (nodes[0], nodes[2], float(alerts_no_case)),
                (nodes[1], nodes[3], float(n_str)),
                (nodes[1], nodes[4], float(n_closed)),
                (nodes[1], nodes[5], float(cases_pending)),
            ]
            # ECharts sankey throws "Sankey is a DAG, the original data
            # has cycle!" when fed zero-value edges (e2e bug caught on
            # PR #189). Strip them and only render nodes with at least
            # one connecting edge.
            edges = [(s, t, v) for s, t, v in edges if v > 0]
            connected_nodes = {n for s, t, _ in edges for n in (s, t)}
            kept_nodes = [n for n in nodes if n in connected_nodes]
            sankey_chart(
                nodes=kept_nodes,
                edges=edges,
                title="Alert → case → STR flow",
                height=360,
                key="exec_funnel_sankey",
            )
        else:
            st.caption("_No alerts in this run — Sankey will populate once detectors fire._")

    with funnel_right:
        st.markdown("##### Waterfall · drop-off per stage")
        if n_alerts > 0:
            # Waterfall: start at total alerts, subtract each drop-off
            # stage, end at STR filed. The waterfall_chart helper
            # handles pos/neg colouring + transparent placeholder
            # stacking so the bars "float" off the running total.
            labels = ["Alerts", "→ Filtered", "→ Closed", "→ Pending", "STR filed"]
            deltas = [
                float(n_alerts),
                -float(alerts_no_case),
                -float(n_closed),
                -float(cases_pending),
                float(n_str),
            ]
            waterfall_chart(
                labels=labels,
                deltas=deltas,
                title="Drop-off per stage",
                pos_color=RAG_COLORS["green"],
                neg_color=RAG_COLORS["amber"],
                height=360,
                key="exec_funnel_waterfall",
            )
        else:
            st.caption("_No alerts in this run — Waterfall will populate once detectors fire._")

    # Per-rule funnel breakdown (compact dataframe).
    if _report.rules:
        import pandas as _pd

        st.markdown("##### Per-rule precision + SLA breach rate")
        _rule_rows = [
            {
                "rule_id": r.rule_id,
                "alerts": r.alerts,
                "cases": r.cases_opened,
                "str_filed": r.str_filed,
                "closed": r.closed_no_action,
                "pending": r.pending,
                "sla_breach_%": r.sla_breach_rate_pct,
                "precision": "—" if r.precision is None else f"{r.precision:.2f}",
            }
            for r in _report.rules
        ]
        st.dataframe(
            _pd.DataFrame(_rule_rows),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No rules fired yet — run the engine to populate the funnel.")

    # AMLA RTS JSON download (preserved).
    _amla_payload = format_amla_rts_json(
        _report,
        program_metadata={
            "lei": "",
            "obliged_entity_type": "credit_institution",
            "home_member_state": spec.program.jurisdiction or "",
            "reporting_period_start": "",
            "reporting_period_end": "",
        },
    )
    st.download_button(
        "📥 AMLA RTS JSON (draft 2026-02)",
        data=_amla_payload,
        file_name=f"{spec.program.name.replace(' ', '_')}_amla_rts.json",
        mime="application/json",
        help="Same shape FinCEN narrative effectiveness pack uses. "
        "For production submission, run `aml outcomes-pack` CLI to "
        "set LEI + reporting period explicitly.",
    )
except Exception as _e:  # noqa: BLE001 — funnel must never crash the dashboard
    st.caption(f"Funnel unavailable: {_e}")
