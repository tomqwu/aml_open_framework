"""AG Grid (Community tier) wrapper — replaces st.dataframe + Styler stack.

Single high-level helper ``data_grid()`` that gives every dashboard
table consistent treatment:

* Severity / RAG / risk-rating columns rendered with coloured cell
  backgrounds via AG Grid ``cellStyle`` callbacks (replacing the
  pandas Styler approach in components.py).
* Optional pinned columns (left, e.g. an ID column).
* Optional row-click drill-through with the same ``selected_<param>``
  session-state convention ``selectable_dataframe()`` uses, so
  destination pages keep working unchanged.
* Sort / filter / pagination on by default.

AG Grid Enterprise features (sparkline cells, row grouping,
master/detail) are intentionally NOT wired up — this repo ships
under Apache 2.0 and we do not require downstream deployers to buy
an AG Grid Enterprise licence.

Lazy import of ``st_aggrid`` and ``streamlit`` so unit-test CI (lean
``[dev]`` install) can import this module without the dashboard
extras.
"""

from __future__ import annotations

from typing import Any

from aml_framework.dashboard.chart_theme import (
    DNA_INK,
    DNA_INK_MUTED,
    RAG_PALETTE,
    SEVERITY_PALETTE,
)

# Customer risk-rating palette — kept here (not chart_theme) because the
# semantic vocabulary is table-only ("high/medium/low/unknown" risk).
RISK_RATING_PALETTE = {
    "high": "#dc2626",
    "medium": "#d97706",
    "low": "#16a34a",
    "unknown": DNA_INK_MUTED,
}


def _cell_style_js(palette: dict[str, str]) -> str:
    """Build an AG Grid ``cellStyle`` JsCode that maps lower-cased value
    to background + bold text. AG Grid expects the callback as a JS
    string when it crosses the streamlit-aggrid bridge.
    """
    # Build the JS object literal once at module-build time so the
    # JsCode body is plain string concatenation (no f-string at render).
    pairs = ", ".join(f"'{k}': '{v}'" for k, v in palette.items())
    return (
        "function(params) {"
        f"  var palette = {{{pairs}}};"
        "  var key = (params.value || '').toString().toLowerCase();"
        "  var color = palette[key];"
        "  if (!color) return null;"
        "  return {"
        "    'backgroundColor': color + '1a',"  # 10% alpha tint
        "    'color': color,"
        "    'fontWeight': '600',"
        "  };"
        "}"
    )


def _gradient_style_js(low: float = 0.5, high: float = 0.8, invert: bool = False) -> str:
    """JsCode for numeric cells coloured red→amber→green by threshold.

    Default direction is "high = good" (green) — for precision /
    recall / F1-style metrics where higher is healthier.

    ``invert=True`` flips to "high = bad" (red) — for risk_score /
    breach_rate-style metrics where higher is more concerning.
    Mirrors the way components.py ``metric_gradient_style()`` callers
    swapped low/high colours by hand for inverted-semantic columns.
    """
    hi_color = "#dc2626" if invert else "#16a34a"
    lo_color = "#16a34a" if invert else "#dc2626"
    return (
        "function(params) {"
        "  var v = parseFloat(params.value);"
        "  if (isNaN(v)) return null;"
        "  var color;"
        f"  if (v >= {high}) color = '{hi_color}';"
        f"  else if (v >= {low}) color = '#d97706';"
        f"  else color = '{lo_color}';"
        "  return {"
        "    'backgroundColor': color + '1a',"
        "    'color': color,"
        "    'fontWeight': '600',"
        "  };"
        "}"
    )


def data_grid(
    df: Any,
    *,
    key: str,
    severity_col: str | None = None,
    rag_col: str | None = None,
    risk_col: str | None = None,
    gradient_cols: list[str] | None = None,
    gradient_low: float = 0.5,
    gradient_high: float = 0.8,
    gradient_invert: bool = False,
    palette_cols: dict[str, dict[str, str]] | None = None,
    pinned_left: list[str] | None = None,
    pinned_right: list[str] | None = None,
    drill_target: str | None = None,
    drill_param: str | None = None,
    drill_column: str | None = None,
    height: int = 400,
    fit_columns: bool = True,
    pagination: bool = True,
    page_size: int = 25,
    hint: str | None = None,
) -> dict[str, Any]:
    """Render a pandas DataFrame as an AG Grid Community table.

    Drop-in upgrade for ``st.dataframe(df, ...)`` and
    ``selectable_dataframe(df, ...)`` — same row-click drill-through
    contract, plus colour-coded severity / RAG / risk cells, pinned
    columns, sort + filter + pagination.

    Args:
        df: pandas DataFrame.
        key: required Streamlit widget key.
        severity_col: optional column name to colour with severity palette.
        rag_col: optional column to colour with RAG / SLA palette.
        risk_col: optional column to colour with risk-rating palette.
        gradient_cols: optional list of numeric columns to colour with
            the red→amber→green metric gradient.
        gradient_low / gradient_high: gradient thresholds (defaults
            mirror components.py ``metric_gradient_style``).
        palette_cols: optional ``{column_name: {value: hex_color}}``
            map for columns whose vocabulary doesn't match severity /
            RAG / risk-rating (e.g. case-status ``new/reviewed/snoozed``,
            workflow queues ``l1_aml_analyst/l2_investigator/...``,
            SLA states ``OVERDUE/Resolved/N/A``). Lookup is
            case-insensitive on the value.
        pinned_left / pinned_right: column names to pin to the left
            or right of the grid.
        drill_target: relative page path
            (e.g. ``"pages/17_Customer_360.py"``).
        drill_param: query-param name (e.g. ``"customer_id"``).
        drill_column: column holding the drill value.
        height: grid height in pixels.
        fit_columns: auto-size columns to fit the grid width.
        pagination: enable pagination.
        page_size: rows per page when pagination is on.
        hint: optional caption above the grid.

    Returns:
        The streamlit-aggrid response dict (selected_rows, data, etc.) —
        same shape as ``selectable_dataframe`` returns ``event``.
        Drill-through paths call ``st.switch_page`` and never return.
    """
    import streamlit as st
    from st_aggrid import AgGrid, GridOptionsBuilder, JsCode  # type: ignore[import-not-found]

    if hint:
        st.caption(hint)

    builder = GridOptionsBuilder.from_dataframe(df)
    builder.configure_default_column(
        sortable=True,
        filterable=True,
        resizable=True,
        editable=False,
    )

    # Coloured cells via cellStyle JsCode — Community-tier feature.
    if severity_col and severity_col in df.columns:
        builder.configure_column(severity_col, cellStyle=JsCode(_cell_style_js(SEVERITY_PALETTE)))
    if rag_col and rag_col in df.columns:
        builder.configure_column(rag_col, cellStyle=JsCode(_cell_style_js(RAG_PALETTE)))
    if risk_col and risk_col in df.columns:
        builder.configure_column(risk_col, cellStyle=JsCode(_cell_style_js(RISK_RATING_PALETTE)))
    for col in gradient_cols or []:
        if col in df.columns:
            builder.configure_column(
                col,
                cellStyle=JsCode(_gradient_style_js(gradient_low, gradient_high, gradient_invert)),
            )
    for col_name, palette in (palette_cols or {}).items():
        if col_name in df.columns:
            # Lower-case keys so the JS lookup is case-insensitive on
            # the cell value (matches _cell_style_js behaviour).
            normalised = {k.lower(): v for k, v in palette.items()}
            builder.configure_column(col_name, cellStyle=JsCode(_cell_style_js(normalised)))

    for col in pinned_left or []:
        if col in df.columns:
            builder.configure_column(col, pinned="left")
    for col in pinned_right or []:
        if col in df.columns:
            builder.configure_column(col, pinned="right")

    if pagination:
        builder.configure_pagination(paginationAutoPageSize=False, paginationPageSize=page_size)

    if drill_target and drill_param and drill_column:
        builder.configure_selection(selection_mode="single", use_checkbox=False)

    grid_options = builder.build()
    # Brand-aligned styling — set via ag-theme CSS variables. AG Grid's
    # "balham" theme is the closest neutral starting point; we override
    # accent + header colours to match the dashboard's cream/ink/orange
    # palette.
    grid_options["headerHeight"] = 36
    grid_options["rowHeight"] = 32

    response = AgGrid(
        df,
        gridOptions=grid_options,
        height=height,
        fit_columns_on_grid_load=fit_columns,
        allow_unsafe_jscode=True,  # required for cellStyle JsCode
        theme="balham",
        key=key,
        custom_css={
            ".ag-header": {
                "background-color": "#f7f4ec !important",
                "border-bottom": "1px solid #e6e1d3 !important",
            },
            ".ag-header-cell-text": {
                "color": DNA_INK + " !important",
                "font-family": "Inter, system-ui, sans-serif !important",
                "font-weight": "600 !important",
                "font-size": "12px !important",
                "letter-spacing": "0.02em !important",
            },
            ".ag-row": {
                "border-color": "#e6e1d3 !important",
            },
            ".ag-row-hover": {
                "background-color": "#fef3e8 !important",
            },
            ".ag-cell": {
                "font-family": "Inter, system-ui, sans-serif !important",
                "font-size": "12px !important",
                "color": DNA_INK + " !important",
            },
        },
    )

    # Drill-through wiring: mirrors selectable_dataframe()'s contract.
    if drill_target and drill_param and drill_column:
        selected = response.get("selected_rows")
        # streamlit-aggrid 1.x returns either a list[dict] or a DataFrame
        # depending on data_return_mode — normalise.
        rows: list[dict[str, Any]]
        if selected is None:
            rows = []
        elif hasattr(selected, "to_dict"):
            rows = selected.to_dict("records")
        else:
            rows = list(selected)
        if rows:
            value = rows[0].get(drill_column)
            if value is not None and str(value).strip():
                st.session_state[f"selected_{drill_param}"] = str(value)
                st.switch_page(drill_target)

    return response
