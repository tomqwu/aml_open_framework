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
    f"How this program maps to {regulator}'s expectations — section by section.",
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

STATUS_COLORS = {
    "mapped": "\U0001f7e2",
    "partial": "\U0001f7e1",
    "gap": "\U0001f534",
}

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
                        "Status": STATUS_COLORS.get(m["status"], "\u26aa"),
                        "Rec": m["rec"],
                        "Title": m["title"],
                        "Spec Element": m["spec_element"],
                        "Notes": m.get("notes", ""),
                    }
                )
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

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
                        "Status": STATUS_COLORS.get(p["status"], "\u26aa"),
                        "Pillar": p.get("pillar", ""),
                        "Name": p["name"],
                        "Spec Element": p["spec_element"],
                        "Notes": p.get("notes", ""),
                    }
                )
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

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
                    "Status": STATUS_COLORS.get(w["status"], "\u26aa"),
                    "Principle": w.get("principle", ""),
                    "Spec Element": w["spec_element"],
                }
                if "notes" in w:
                    row["Notes"] = w["notes"]
                rows.append(row)
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

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
