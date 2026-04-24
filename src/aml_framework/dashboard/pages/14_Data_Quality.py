"""Data Quality -- contract validation, freshness SLAs, column statistics."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aml_framework.dashboard.components import kpi_card, page_header
from aml_framework.dashboard.audience import show_audience_context

page_header(
    "Data Quality",
    "Data contract compliance, quality check results, and column-level statistics.",
)
show_audience_context("Data Quality")

spec = st.session_state.spec
data = st.session_state.data
as_of = st.session_state.as_of

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Data Quality**\n\n"
        "Each data contract declares columns, types, freshness SLAs, and quality "
        "checks (not_null, unique). This page executes those checks against the "
        "actual data and reports violations."
    )

# --- Execute quality checks ---
total_checks = 0
total_passed = 0
total_violations = 0
contract_results: list[dict] = []

for contract in spec.data_contracts:
    rows = data.get(contract.id, [])
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    n_rows = len(df)

    # Freshness check.
    freshness_ok = True
    freshness_note = "N/A"
    if contract.freshness_sla and not df.empty:
        ts_cols = [c.name for c in contract.columns if c.type == "timestamp"]
        for ts_col in ts_cols:
            if ts_col in df.columns:
                latest = pd.to_datetime(df[ts_col]).max()
                if latest is not pd.NaT:
                    age_hours = (
                        as_of - latest.to_pydatetime().replace(tzinfo=None)
                    ).total_seconds() / 3600
                    freshness_note = f"{age_hours:.1f}h (SLA: {contract.freshness_sla})"
                    sla_val = int(contract.freshness_sla[:-1])
                    sla_unit = contract.freshness_sla[-1]
                    sla_hours = sla_val * {"s": 1 / 3600, "m": 1 / 60, "h": 1, "d": 24}[sla_unit]
                    if age_hours > sla_hours:
                        freshness_ok = False
                    break

    # Quality checks.
    check_results: list[dict] = []
    for qc in contract.quality_checks:
        for check_type, fields in qc.items():
            total_checks += 1
            if check_type == "not_null":
                for field in fields:
                    if field in df.columns:
                        nulls = int(df[field].isna().sum())
                        passed = nulls == 0
                        if passed:
                            total_passed += 1
                        else:
                            total_violations += 1
                        check_results.append(
                            {
                                "Check": f"not_null({field})",
                                "Status": "PASS" if passed else "FAIL",
                                "Detail": f"{nulls} nulls" if nulls else "0 nulls",
                            }
                        )
            elif check_type == "unique":
                for field in fields:
                    if field in df.columns:
                        dupes = int(df[field].duplicated().sum())
                        passed = dupes == 0
                        if passed:
                            total_passed += 1
                        else:
                            total_violations += 1
                        check_results.append(
                            {
                                "Check": f"unique({field})",
                                "Status": "PASS" if passed else "FAIL",
                                "Detail": f"{dupes} duplicates" if dupes else "0 duplicates",
                            }
                        )

    contract_results.append(
        {
            "contract_id": contract.id,
            "source": contract.source,
            "rows": n_rows,
            "columns": len(contract.columns),
            "freshness_sla": contract.freshness_sla or "N/A",
            "freshness_status": "OK" if freshness_ok else "BREACH",
            "freshness_detail": freshness_note,
            "checks": check_results,
        }
    )

# --- KPIs ---
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Contracts", len(spec.data_contracts), "#2563eb")
with c2:
    kpi_card("Quality Checks", total_checks, "#7c3aed")
with c3:
    kpi_card("Passed", total_passed, "#059669")
with c4:
    kpi_card("Violations", total_violations, "#dc2626" if total_violations > 0 else "#059669")

st.markdown("<br>", unsafe_allow_html=True)

# --- Contract overview ---
st.markdown("### Contract Overview")
overview = pd.DataFrame(
    [
        {
            "Contract": r["contract_id"],
            "Source": r["source"],
            "Rows": r["rows"],
            "Columns": r["columns"],
            "Freshness SLA": r["freshness_sla"],
            "Freshness": r["freshness_status"],
        }
        for r in contract_results
    ]
)


def _status_color(val):
    if val == "BREACH":
        return "color: #dc2626; font-weight: 700;"
    if val == "OK":
        return "color: #059669; font-weight: 700;"
    return ""


st.dataframe(
    overview.style.map(_status_color, subset=["Freshness"]),
    use_container_width=True,
    hide_index=True,
)

st.markdown("<br>", unsafe_allow_html=True)

# --- Per-contract details ---
for cr in contract_results:
    contract = next(c for c in spec.data_contracts if c.id == cr["contract_id"])
    df = pd.DataFrame(data.get(cr["contract_id"], []))

    with st.expander(f"**{cr['contract_id']}** — {cr['rows']} rows, {cr['columns']} columns"):
        # Quality check results.
        if cr["checks"]:
            st.markdown("**Quality Checks**")
            checks_df = pd.DataFrame(cr["checks"])

            def _check_color(val):
                if val == "FAIL":
                    return "color: #dc2626; font-weight: 700;"
                if val == "PASS":
                    return "color: #059669; font-weight: 700;"
                return ""

            st.dataframe(
                checks_df.style.map(_check_color, subset=["Status"]),
                use_container_width=True,
                hide_index=True,
            )

        # Column schema.
        st.markdown("**Column Schema**")
        col_rows = []
        for col in contract.columns:
            col_info = {
                "Name": col.name,
                "Type": col.type,
                "Nullable": col.nullable,
                "PII": col.pii,
            }
            # Add basic stats if data exists.
            if col.name in df.columns:
                series = df[col.name]
                col_info["Non-Null"] = int(series.notna().sum())
                col_info["Unique"] = int(series.nunique())
            col_rows.append(col_info)
        st.dataframe(pd.DataFrame(col_rows), use_container_width=True, hide_index=True)

        # Freshness detail.
        st.markdown(f"**Freshness:** {cr['freshness_detail']}")
