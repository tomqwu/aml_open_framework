# Chart Library Migration — Per-page Audit

Scope deliverable for the PR-CHART series. Lists every chart and table
call site in the dashboard, mapped to its target wrapper helper from
`dashboard/charts.py` and `dashboard/data_grid.py` (built in PR-CHART-1).

PR-CHART-2 (pilot) consumes rows 11_Live_Monitor + 3_Alert_Queue.
PR-CHART-3 (charts batch) consumes the remaining 11 chart pages.
PR-CHART-4 (tables batch) consumes the remaining 17 table pages.

## Chart pages — 13 total

| Page | Plotly call(s) | Target helper | Notes |
|---|---|---|---|
| 11_Live_Monitor | `go.Figure` + `go.Scatter` (line); `go.Figure` + `go.Bar` | `line_chart()`, `bar_chart()` | Pilot for PR-CHART-2. Live-update chart placeholder via key. |
| 3_Alert_Queue | `px.bar`, `px.pie` | `bar_chart()`, `pie_chart(donut=True)` | Pilot for PR-CHART-2. |
| 1_Executive_Dashboard | `px.bar`, `go.Scatterpolar` (radar), `go.Sankey`, custom waterfall | `bar_chart()`, `radar_chart()`, `sankey_chart()`, `waterfall_chart()` | Heaviest page — 4 chart types. |
| 4_Case_Investigation | `px.scatter`, `go.Sankey` | `scatter_chart()`, `sankey_chart()` | |
| 17_Customer_360 | `px.bar`, `px.pie` | `bar_chart()`, `pie_chart()` | |
| 19_Comparative_Analytics | `go.Bar`, `go.Pie`, `go.Bar` | `bar_chart()`, `pie_chart()`, `bar_chart()` | Three charts side-by-side. |
| 21_My_Queue | `px.bar`, `px.pie`, `px.histogram` | `bar_chart()`, `pie_chart()`, `bar_chart(...)` (binned) | Histogram → bar via pre-binning in page. |
| 23_Tuning_Lab | `px.scatter`, `px.line` | `scatter_chart()`, `line_chart()` | F1 sweep + alert volume timeline. |
| 9_Transformation_Roadmap | `px.timeline` (Gantt) | `timeline_chart()` | Custom-series Gantt — only consumer of `timeline_chart()`. |
| 16_Rule_Tuning | `px.line` | `line_chart()` | |
| 13_Model_Performance | `px.histogram` | `bar_chart(...)` (pre-binned) | Score distribution. |
| 2_Program_Maturity | `go.Scatterpolar` | `radar_chart()` | Single radar — large height (520px). |
| 5_Rule_Performance | `px.bar`, `px.pie` | `bar_chart()`, `pie_chart()` | |
| 6_Risk_Assessment | `px.pie`, `px.bar` ×2, `px.imshow` (heatmap) | `pie_chart()`, `bar_chart()`, `bar_chart()`, `heatmap_chart()` | Four charts. |

**Coverage check**: every Plotly call in `pages/` maps to a curated
helper. The escape hatch `echarts_chart(option)` is unused — good
signal that the curated vocabulary is complete.

## Table pages — 19 total

Triage pages (drill-through, severity / risk colouring) get the rich
treatment via `data_grid(..., severity_col=..., risk_col=...,
drill_target=..., drill_param=..., drill_column=...)`. Read-only
pages get the light treatment (pinned + sort/filter only).

### Triage tables (rich treatment)

| Page | Current call | Target |
|---|---|---|
| 3_Alert_Queue | `selectable_dataframe` | `data_grid(severity_col="severity", drill_target=...)` |
| 21_My_Queue | `selectable_dataframe` | `data_grid(severity_col="severity", drill_target=...)` |
| 24_Investigations | `st.dataframe` (formerly selectable) | `data_grid(rag_col="sla_state", drill_target=...)` |
| 25_BOI_Workflow | `selectable_dataframe` | `data_grid(rag_col="status", drill_target=...)` |
| 17_Customer_360 (alerts) | `st.dataframe` | `data_grid(severity_col="severity", risk_col="risk_rating")` |
| 4_Case_Investigation (alerts) | `st.dataframe` | `data_grid(severity_col="severity")` |

### Read-only tables (light treatment)

| Page | Current call | Target |
|---|---|---|
| 7_Audit_Evidence | `st.dataframe` (event log) | `data_grid(rag_col="event_type", pinned_left=["timestamp"])` |
| 15_Run_History | `st.dataframe` | `data_grid(pinned_left=["run_id"])` |
| 8_Framework_Alignment | `st.dataframe` | `data_grid(pinned_left=["regulation"])` |
| 12_Sanctions_Screening | `st.dataframe` | `data_grid(severity_col="match_severity")` |
| 14_Data_Quality | `st.dataframe` | `data_grid(rag_col="rag")` |
| 29_AI_Assistant | `st.dataframe` (transcript) | `data_grid(pinned_left=["timestamp"])` |
| 10_Network_Explorer | `st.dataframe` | `data_grid(severity_col="severity")` |
| 6_Risk_Assessment | `st.dataframe` | `data_grid(rag_col="rag")` |
| 1_Executive_Dashboard | `st.dataframe` (metric table via `metric_table()`) | `data_grid(rag_col="RAG")` — refactor `metric_table()` to call `data_grid` |
| 31_Information_Sharing | `st.dataframe` | `data_grid(pinned_left=["partner"])` |
| 13_Model_Performance | `st.dataframe` (metrics) | `data_grid(gradient_cols=["precision","recall","f1"])` |
| 5_Rule_Performance | `st.dataframe` | `data_grid(gradient_cols=["precision","recall"])` |
| 23_Tuning_Lab | `st.dataframe` (scenarios) | `data_grid(gradient_cols=["f1","precision","recall"])` |
| 19_Comparative_Analytics | `st.dataframe` (run summary) | `data_grid(pinned_left=["run_id"])` |

## Helper inventory built in PR-CHART-1

`dashboard/charts.py`:

- `bar_chart()` — vertical / horizontal / stacked / per-bar semantic colour
- `line_chart()` — single + multi-series, smooth, optional area fill
- `area_chart()` — convenience for `line_chart(area=True)`
- `pie_chart()` — donut by default
- `scatter_chart()` — bubble support via `size=`
- `radar_chart()` — multi-series polar
- `heatmap_chart()` — matrix with cream → burnt-orange ramp
- `sankey_chart()` — flow diagram with adjacency emphasis
- `funnel_chart()` — outcomes funnel (alerts → cases → STR)
- `gauge_chart()` — RAG dial with custom bands
- `timeline_chart()` — custom-series Gantt over time axis
- `waterfall_chart()` — pos/neg deltas via stacked transparent placeholder
- `echarts_chart()` — escape hatch (raw option dict)

`dashboard/data_grid.py`:

- `data_grid()` — AG Grid Community wrapper, replaces both
  `st.dataframe` + Styler stack and `selectable_dataframe()`. Wires
  severity / RAG / risk-rating / metric-gradient cell colours via
  JsCode callbacks. Mirrors `selectable_dataframe`'s drill-through
  contract (`selected_<param>` session-state convention).

`dashboard/chart_theme.py`:

- `echarts_theme()` — ECharts theme dict from brand DNA tokens
  (cream `#f7f4ec` / ink `#1c1f26` / burnt-orange `#a44b30`)
- `severity_color()` / `rag_color()` — semantic colour resolvers
