"""Data Quality -- contract validation, freshness SLAs, column statistics."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import (
    page_footer,
    data_grid,
    empty_state,
    kpi_card,
    page_header,
    section_explainer,
)

from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

# Local status palettes — values come from the contract / check rows.
FRESHNESS_PALETTE = {"breach": "#dc2626", "ok": "#16a34a"}
CHECK_PALETTE = {"fail": "#dc2626", "pass": "#16a34a"}

page_header(
    "Data Quality",
    "Data contract compliance, quality check results, and column-level statistics.",
)
show_audience_context("Data Quality")

section_explainer(
    page="Data Quality",
    section_id="data_quality.page",
    section_title="Data Quality",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
        "metrics": len(getattr(st.session_state.get("spec"), "metrics", []) or []),
        "case_count": (
            len(st.session_state.get("df_cases"))
            if st.session_state.get("df_cases") is not None
            else 0
        ),
    },
)


spec = st.session_state.spec
data = st.session_state.data
as_of = st.session_state.as_of

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Data Quality**\n\n"
        "Each data contract declares columns, types, freshness SLAs, and quality "
        "checks (not_null, unique, enum, regex, range). This page executes those checks "
        "against the actual data and reports violations."
    )

# --- Empty-state guard: no contracts means there's nothing to assess ---
if not spec.data_contracts:
    empty_state(
        "No data contracts defined.",
        icon="📋",
        detail=(
            "Add `data_contracts` to your spec to surface freshness SLAs, "
            "column types, and quality checks here. See "
            "`docs/specs/data-contracts.md` for the schema."
        ),
        stop=True,
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

    # Quality checks. PR-B1 (#366) extends the engine with `enum` /
    # `regex` / `range` validity checks alongside `not_null` / `unique`;
    # this page now scores all five so the KPI denominator and the
    # per-contract table stay aligned with what the engine emits.
    check_results: list[dict] = []
    for qc in contract.quality_checks:
        for check_type, fields in qc.items():
            if check_type in ("not_null", "unique"):
                if not isinstance(fields, list):
                    continue
                for field in fields:
                    if field not in df.columns:
                        continue
                    total_checks += 1
                    if check_type == "not_null":
                        nulls = int(df[field].isna().sum())
                        passed = nulls == 0
                        detail = f"{nulls} nulls" if nulls else "0 nulls"
                    else:
                        dupes = int(df[field].duplicated().sum())
                        passed = dupes == 0
                        detail = f"{dupes} duplicates" if dupes else "0 duplicates"
                    if passed:
                        total_passed += 1
                    else:
                        total_violations += 1
                    check_results.append(
                        {
                            "Check": f"{check_type}({field})",
                            "Status": "PASS" if passed else "FAIL",
                            "Detail": detail,
                        }
                    )
            elif check_type in ("enum", "regex", "range") and isinstance(fields, dict):
                for field, spec in fields.items():
                    if field not in df.columns:
                        continue
                    total_checks += 1
                    series = df[field]
                    present = series.dropna()
                    if check_type == "enum":
                        allowed = list(spec) if isinstance(spec, (list, tuple)) else []
                        bad = int((~present.isin(allowed)).sum()) if allowed else 0
                        passed = bad == 0
                        detail = f"{bad} out-of-set" if bad else "0 out-of-set"
                    elif check_type == "regex":
                        import re as _re

                        if isinstance(spec, str):
                            try:
                                pat = _re.compile(spec)
                                bad = int(
                                    sum(
                                        1
                                        for v in present
                                        if not isinstance(v, str) or pat.fullmatch(v) is None
                                    )
                                )
                            except _re.error:
                                bad = 0
                        else:
                            bad = 0
                        passed = bad == 0
                        detail = f"{bad} pattern misses" if bad else "0 pattern misses"
                    else:  # range
                        lo = spec.get("min") if isinstance(spec, dict) else None
                        hi = spec.get("max") if isinstance(spec, dict) else None

                        def _to_num(v):
                            # Mirror engine `_eval_range` / `_coerce_bound`
                            # so the dashboard scorecard agrees with
                            # `dq_exceptions.jsonl`: reject bools
                            # (a True/False in a numeric column is a
                            # defect, not 1/0), and reject non-finite
                            # values (NaN/Inf can't be compared).
                            import math as _m

                            if v is None or isinstance(v, bool):
                                return None
                            try:
                                f = float(v)
                            except (TypeError, ValueError):
                                return None
                            if not _m.isfinite(f):
                                return None
                            return f

                        lo_n = _to_num(lo)
                        hi_n = _to_num(hi)
                        bad = 0
                        for v in present:
                            nv = _to_num(v)
                            if nv is None:
                                bad += 1
                                continue
                            if lo_n is not None and nv < lo_n:
                                bad += 1
                            elif hi_n is not None and nv > hi_n:
                                bad += 1
                        passed = bad == 0
                        detail = f"{bad} out-of-range" if bad else "0 out-of-range"
                    if passed:
                        total_passed += 1
                    else:
                        total_violations += 1
                    check_results.append(
                        {
                            "Check": f"{check_type}({field})",
                            "Status": "PASS" if passed else "FAIL",
                            "Detail": detail,
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


data_grid(
    overview,
    key="data_quality_overview",
    palette_cols={"Freshness": FRESHNESS_PALETTE} if "Freshness" in overview.columns else None,
    pinned_left=["Contract"] if "Contract" in overview.columns else None,
    height=300,
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
            data_grid(
                checks_df,
                key=f"data_quality_checks_{cr['contract_id']}",
                palette_cols={"Status": CHECK_PALETTE} if "Status" in checks_df.columns else None,
                height=min(35 * len(checks_df) + 60, 250),
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
        data_grid(pd.DataFrame(col_rows), key=f"dq_{contract.id}_columns", height=300)

        # Contract compliance — check actual data matches declared schema.
        if not df.empty:
            schema_issues: list[str] = []
            for col in contract.columns:
                if col.name not in df.columns:
                    schema_issues.append(f"Missing column: **{col.name}** (declared in contract)")
                    continue
                # Type checking.
                series = df[col.name]
                if col.type == "integer" and series.notna().any():
                    non_int = series.dropna().apply(
                        lambda x: (
                            not isinstance(x, (int, float))
                            or (isinstance(x, float) and x != int(x))
                        )
                    )
                    if non_int.any():
                        schema_issues.append(
                            f"**{col.name}**: {int(non_int.sum())} values are not integers"
                        )
                if not col.nullable and series.isna().any():
                    schema_issues.append(
                        f"**{col.name}**: {int(series.isna().sum())} nulls in non-nullable column"
                    )

            # Check for undeclared columns.
            declared = {c.name for c in contract.columns}
            extra = set(df.columns) - declared
            if extra:
                schema_issues.append(f"Undeclared columns: {', '.join(sorted(extra))}")

            if schema_issues:
                st.markdown("**Contract Compliance Issues**")
                for issue in schema_issues:
                    st.markdown(f"- {issue}")
            else:
                st.markdown("**Contract Compliance:** All columns match declared schema.")

        # Freshness detail.
        st.markdown(f"**Freshness:** {cr['freshness_detail']}")

page_footer()
