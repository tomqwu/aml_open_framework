"""Framework Alignment — jurisdiction-aware regulatory mapping."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aml_framework.dashboard.components import page_header
from aml_framework.dashboard.data_layer import get_framework_tabs

spec = st.session_state.spec
jurisdiction = spec.program.jurisdiction
regulator = spec.program.regulator

page_header(
    "Framework Alignment",
    f"Mapping spec primitives to regulatory standards for {jurisdiction} ({regulator}).",
)

st.caption(
    "Coverage status values are maintained manually and represent an "
    "initial mapping assessment. Confirm with compliance and legal counsel."
)

if st.session_state.get("guided_demo"):
    if jurisdiction == "CA":
        st.info(
            "**Guided Demo — Framework Alignment (Canada)**\n\n"
            "This view maps the spec to FATF Recommendations, PCMLTFA's 5 pillars "
            "(PCMLTFR s.71), and OSFI Guideline B-8 expectations for federally "
            "regulated financial institutions. Green = fully mapped, yellow = "
            "partially mapped, red = gap requiring remediation."
        )
    else:
        st.info(
            "**Guided Demo — Framework Alignment**\n\n"
            "This view maps the spec to international and domestic regulatory "
            "standards. Green = fully mapped, yellow = partially mapped, red = gap."
        )

STATUS_LABELS = {
    "mapped": "✓ Mapped",
    "partial": "∼ Partial",
    "gap": "✗ Gap",
}

_STATUS_TEXT_COLORS = {
    "✓ Mapped": "#16a34a",
    "∼ Partial": "#d97706",
    "✗ Gap": "#dc2626",
}


def _status_style(val: str) -> str:
    color = _STATUS_TEXT_COLORS.get(val, "")
    return f"color: {color}; font-weight: 700;" if color else ""


def _render_table(rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    if "Status" in df.columns:
        styled = df.style.map(_status_style, subset=["Status"])
        st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


framework_tabs = get_framework_tabs(jurisdiction)
tabs = st.tabs([t["label"] for t in framework_tabs])

for tab_widget, tab_def in zip(tabs, framework_tabs):
    with tab_widget:
        st.subheader(tab_def["label"])
        data = tab_def["data"]

        if tab_def["type"] == "fatf":
            st.caption(
                "The FATF Recommendations are the global AML/CFT standard. "
                "Below are the recommendations most relevant to this framework."
            )
            rows = []
            for m in data:
                rows.append(
                    {
                        "Status": STATUS_LABELS.get(m["status"], "? Unknown"),
                        "Rec": m["rec"],
                        "Title": m["title"],
                        "Spec Element": m["spec_element"],
                        "Notes": m.get("notes", ""),
                    }
                )
            _render_table(rows)

        elif tab_def["type"] == "pillars":
            if jurisdiction == "CA":
                st.caption(
                    "PCMLTFR s.71 requires 5 pillars for a Canadian AML/ATF compliance "
                    "program. Each pillar maps to spec primitives."
                )
            else:
                st.caption(
                    "The BSA requires 5 pillars (with a 6th proposed in April 2026). "
                    "Each pillar maps to spec primitives."
                )
            rows = []
            for p in data:
                rows.append(
                    {
                        "Status": STATUS_LABELS.get(p["status"], "? Unknown"),
                        "Pillar": p.get("pillar", ""),
                        "Name": p["name"],
                        "Spec Element": p["spec_element"],
                        "Notes": p.get("notes", ""),
                    }
                )
            _render_table(rows)

        elif tab_def["type"] == "principles":
            if "OSFI" in tab_def["label"]:
                st.caption(
                    "OSFI Guideline B-8 applies to federally regulated financial "
                    "institutions. These expectations are additive to FINTRAC "
                    "requirements and are assessed during OSFI examinations."
                )
            else:
                st.caption(
                    "The Wolfsberg Group (13 global banks) publishes AML/CFT "
                    "principles widely referenced by regulators as benchmarks."
                )
            rows = []
            for w in data:
                row: dict = {
                    "Status": STATUS_LABELS.get(w["status"], "? Unknown"),
                    "Principle": w.get("principle", ""),
                    "Spec Element": w["spec_element"],
                }
                if "notes" in w:
                    row["Notes"] = w["notes"]
                rows.append(row)
            _render_table(rows)

        # Summary stats for all tab types.
        mapped = sum(1 for item in data if item["status"] == "mapped")
        partial = sum(1 for item in data if item["status"] == "partial")
        gaps = sum(1 for item in data if item["status"] == "gap")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Fully Mapped", mapped)
        with c2:
            st.metric("Partially Mapped", partial)
        with c3:
            st.metric("Gaps", gaps)
