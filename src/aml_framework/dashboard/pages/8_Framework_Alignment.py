"""Framework Alignment — FATF, FinCEN BSA, and Wolfsberg mapping."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aml_framework.dashboard.components import page_header
from aml_framework.dashboard.data_layer import (
    FATF_MAPPING,
    FINCEN_BSA_PILLARS,
    WOLFSBERG_MAPPING,
)

page_header(
    "Framework Alignment",
    "Mapping spec primitives to FATF Recommendations, FinCEN BSA Pillars, and Wolfsberg Principles.",
)

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo — Framework Alignment**\n\n"
        "This view shows how the spec-driven framework maps to international "
        "and domestic regulatory standards. Green = fully mapped, yellow = "
        "partially mapped, red = gap. The April 2026 FinCEN proposed rule "
        "adds a 6th BSA pillar (formalized risk assessment) — we've included it."
    )

STATUS_COLORS = {
    "mapped": "\U0001f7e2",
    "partial": "\U0001f7e1",
    "gap": "\U0001f534",
}

tab1, tab2, tab3 = st.tabs(["FATF Recommendations", "FinCEN BSA Pillars", "Wolfsberg Principles"])

with tab1:
    st.subheader("FATF 40 Recommendations — Key Mappings")
    st.caption(
        "The FATF Recommendations are the global AML/CFT standard. "
        "Below are the recommendations most relevant to this framework."
    )
    rows = []
    for m in FATF_MAPPING:
        rows.append({
            "Status": STATUS_COLORS.get(m["status"], "\u26aa"),
            "Rec": m["rec"],
            "Title": m["title"],
            "Spec Element": m["spec_element"],
            "Notes": m.get("notes", ""),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Summary stats
    mapped = sum(1 for m in FATF_MAPPING if m["status"] == "mapped")
    partial = sum(1 for m in FATF_MAPPING if m["status"] == "partial")
    gaps = sum(1 for m in FATF_MAPPING if m["status"] == "gap")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Fully Mapped", mapped)
    with c2:
        st.metric("Partially Mapped", partial)
    with c3:
        st.metric("Gaps", gaps)

with tab2:
    st.subheader("FinCEN BSA Program Pillars")
    st.caption(
        "The BSA requires 5 pillars (with a 6th proposed in April 2026). "
        "Each pillar maps to spec primitives that provide automated compliance."
    )
    rows = []
    for p in FINCEN_BSA_PILLARS:
        rows.append({
            "Status": STATUS_COLORS.get(p["status"], "\u26aa"),
            "Pillar": p["pillar"],
            "Name": p["name"],
            "Spec Element": p["spec_element"],
            "Notes": p.get("notes", ""),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    mapped = sum(1 for p in FINCEN_BSA_PILLARS if p["status"] == "mapped")
    partial = sum(1 for p in FINCEN_BSA_PILLARS if p["status"] == "partial")
    gaps = sum(1 for p in FINCEN_BSA_PILLARS if p["status"] == "gap")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Fully Mapped", mapped)
    with c2:
        st.metric("Partially Mapped", partial)
    with c3:
        st.metric("Gaps", gaps)

with tab3:
    st.subheader("Wolfsberg Group Principles")
    st.caption(
        "The Wolfsberg Group (13 global banks) publishes AML/CFT principles "
        "widely referenced by regulators as industry benchmarks."
    )
    rows = []
    for w in WOLFSBERG_MAPPING:
        rows.append({
            "Status": STATUS_COLORS.get(w["status"], "\u26aa"),
            "Principle": w["principle"],
            "Spec Element": w["spec_element"],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    mapped = sum(1 for w in WOLFSBERG_MAPPING if w["status"] == "mapped")
    partial = sum(1 for w in WOLFSBERG_MAPPING if w["status"] == "partial")
    gaps = sum(1 for w in WOLFSBERG_MAPPING if w["status"] == "gap")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Fully Mapped", mapped)
    with c2:
        st.metric("Partially Mapped", partial)
    with c3:
        st.metric("Gaps", gaps)
