"""Executive Dashboard -- program-level KPIs and health overview."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from aml_framework.dashboard.components import (
    SEVERITY_COLORS,
    chart_layout,
    kpi_card,
    link_to_page,
    metric_table,
    page_header,
)

page_header(
    "Executive Dashboard",
    "Program-level KPIs, alert summary, and compliance health at a glance.",
)

spec = st.session_state.spec
result = st.session_state.result
df_alerts = st.session_state.df_alerts
audience = st.session_state.get("selected_audience")

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Executive Dashboard**\n\n"
        f"The engine detected **{result.total_alerts} alerts** across "
        f"**{len(spec.rules)} rules**, covering multiple AML typologies. "
        "KPI cards show program health. The RAG grid below tracks every "
        "metric with red/amber/green thresholds."
    )

# --- KPI tiles ---
metrics_by_id = {m.id: m for m in result.metrics}

c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    kpi_card("Total Alerts", result.total_alerts, "#dc2626")
with c2:
    kpi_card("Open Cases", len(result.case_ids), "#d97706")
with c3:
    active = len([r for r in spec.rules if r.status == "active"])
    kpi_card("Active Rules", active, "#2563eb")
with c4:
    tc = metrics_by_id.get("typology_coverage")
    kpi_card("Typology Coverage", f"{tc.value * 100:.0f}%" if tc else "N/A", "#059669")
with c5:
    dc = metrics_by_id.get("distinct_customers_alerted")
    kpi_card("Customers Alerted", int(dc.value) if dc else 0, "#7c3aed")
with c6:
    # Find the volume metric by checking common ids
    tv = metrics_by_id.get("transaction_volume_usd") or metrics_by_id.get("transaction_volume_cad")
    if tv:
        unit = spec.program.jurisdiction
        kpi_card("Volume Screened", f"${tv.value:,.0f}", "#0891b2")
    else:
        kpi_card("Volume Screened", "N/A", "#6b7280")

# --- KPI drill-downs ---
# Streamlit metric-style cards aren't natively clickable, so each
# clickable KPI gets a follow-up `st.page_link` row beneath the cards.
# Pattern matches Alert Queue / Customer 360 — link_to_page writes the
# session-state mirror for any drill-state we need on the destination.
drill_total, drill_cases, _, _, _, _ = st.columns(6)
with drill_total:
    link_to_page("pages/3_Alert_Queue.py", "→ Triage alerts")
with drill_cases:
    link_to_page("pages/24_Investigations.py", "→ Open investigations")

st.markdown("<br>", unsafe_allow_html=True)

# --- Charts row ---
col_left, col_right = st.columns([3, 2])

with col_left:
    st.markdown("### Alerts by Rule")
    if not df_alerts.empty:
        sev_map = {r.id: r.severity for r in spec.rules}
        chart_df = df_alerts.groupby("rule_id").size().reset_index(name="count")
        chart_df["severity"] = chart_df["rule_id"].map(sev_map)
        chart_df = chart_df.sort_values("count", ascending=True)
        fig = px.bar(
            chart_df,
            y="rule_id",
            x="count",
            color="severity",
            orientation="h",
            color_discrete_map=SEVERITY_COLORS,
            labels={"rule_id": "", "count": "Alerts"},
        )
        fig.update_layout(yaxis_title="", showlegend=True, legend_title_text="")
        st.plotly_chart(chart_layout(fig, 350), use_container_width=True)
    else:
        st.info("No alerts generated.")

with col_right:
    st.markdown("### RAG Status")
    metric_table(result.metrics, audience=audience)

st.markdown("<br>", unsafe_allow_html=True)

# --- Bottom row: Radar + summary ---
col_radar, col_summary = st.columns([3, 2])

with col_radar:
    st.markdown("### Program Health")
    categories = [m.name[:25] for m in result.metrics if m.rag != "unset"][:8]
    values = []
    colors_list = []
    for m in result.metrics:
        if m.rag == "unset" or len(values) >= 8:
            continue
        score = {"green": 3, "amber": 2, "red": 1}.get(m.rag, 0)
        values.append(score)
        colors_list.append(m.rag)

    if categories and values:
        fig = go.Figure()
        fig.add_trace(
            go.Scatterpolar(
                r=values + [values[0]],
                theta=categories + [categories[0]],
                fill="toself",
                name="Current",
                line=dict(color="#2563eb", width=2),
                fillcolor="rgba(37, 99, 235, 0.15)",
            )
        )
        fig.add_trace(
            go.Scatterpolar(
                r=[3] * (len(categories) + 1),
                theta=categories + [categories[0]],
                fill="toself",
                name="Target",
                line=dict(color="#16a34a", width=1, dash="dot"),
                fillcolor="rgba(22, 163, 74, 0.05)",
            )
        )
        fig.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 3.5], showticklabels=False),
                bgcolor="rgba(0,0,0,0)",
            ),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.15, x=0.5, xanchor="center"),
        )
        st.plotly_chart(chart_layout(fig, 400), use_container_width=True)

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

        import json
        from pathlib import Path

        run_dir = st.session_state.run_dir
        cases = []
        cases_dir = Path(run_dir) / "cases"
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
# Effectiveness Funnel (FinCEN April 2026 NPRM + AMLA RTS 2026-07-10)
# ---------------------------------------------------------------------------
# Both FinCEN's NPRM and AMLA's RTS treat alert→case→STR conversion as
# the canonical effectiveness measure. The funnel computation lives in
# `metrics/outcomes.py` (Round-7 PR #75); this section surfaces it for
# SVP/CCO consumption and offers a one-click AMLA RTS JSON download.

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("### Effectiveness Funnel")
st.caption(
    "Alert → case → STR conversion + per-rule precision (when labels supplied). "
    "Same numbers FinCEN's April 2026 NPRM and AMLA's RTS (due 2026-07-10) treat "
    "as the canonical effectiveness measure."
)

# Load cases + decisions from the audit ledger run dir.
try:
    import json as _json
    from pathlib import Path as _Path

    from aml_framework.metrics.outcomes import compute_outcomes, format_amla_rts_json

    _run_dir = _Path(st.session_state.run_dir)
    _cases: list[dict] = []
    _cases_dir = _run_dir / "cases"
    if _cases_dir.exists():
        for _f in sorted(_cases_dir.glob("*.json")):
            _cases.append(_json.loads(_f.read_text(encoding="utf-8")))
    _decisions: list[dict] = []
    _dec_path = _run_dir / "decisions.jsonl"
    if _dec_path.exists():
        for _line in _dec_path.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line:
                _decisions.append(_json.loads(_line))

    _report = compute_outcomes(_cases, _decisions, spec_program=spec.program.name)

    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        kpi_card("Alerts", _report.total_alerts, "#dc2626")
    with fc2:
        kpi_card("Cases", _report.total_cases, "#d97706")
    with fc3:
        kpi_card("STR filed", _report.total_str_filed, "#7c3aed")
    with fc4:
        kpi_card("Alert → STR", f"{_report.alert_to_str_pct}%", "#16a34a")

    # Per-rule funnel breakdown.
    if _report.rules:
        import pandas as _pd

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

    # AMLA RTS JSON download — uses minimal metadata; operators editing
    # for real submission should use `aml outcomes-pack` CLI which
    # accepts --lei / --home-state / --period-start / --period-end.
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
