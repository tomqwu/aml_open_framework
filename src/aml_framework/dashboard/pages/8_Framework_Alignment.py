"""Framework Alignment — jurisdiction-aware regulatory mapping."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aml_framework.dashboard.components import (
    citation_link,
    data_grid,
    page_header,
    research_link,
    see_also_footer,
    tooltip_banner,
    tour_panel,
)
from aml_framework.dashboard.data_layer import get_framework_tabs

# Framework-status palette — local vocabulary ("✓ Mapped" / "∼ Partial" /
# "✗ Gap"). Routes through data_grid's palette_cols= seam.
FRAMEWORK_STATUS_PALETTE = {
    "✓ mapped": "#16a34a",
    "∼ partial": "#d97706",
    "✗ gap": "#dc2626",
}

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


tour_panel("Framework Alignment")
if jurisdiction == "CA":
    tooltip_banner(
        "Framework Alignment (Canada)",
        "This view maps the spec to FATF Recommendations, PCMLTFA's 5 pillars "
        "(PCMLTFR s.71), and OSFI Guideline B-8 expectations for federally "
        "regulated financial institutions. Green = fully mapped, yellow = "
        "partially mapped, red = gap requiring remediation.",
    )
else:
    tooltip_banner(
        "Framework Alignment",
        "This view maps the spec to international and domestic regulatory "
        "standards. Green = fully mapped, yellow = partially mapped, red = gap.",
    )


STATUS_LABELS = {
    "mapped": "✓ Mapped",
    "partial": "∼ Partial",
    "gap": "✗ Gap",
}

# Status-text → colour map preserved for the design-fix guard test
# (`test_dashboard_design_fixes::TestFrameworkStatusLabels::
#   test_status_labels_carry_color_via_styler`). The colours
# themselves now flow through FRAMEWORK_STATUS_PALETTE on data_grid.
_STATUS_TEXT_COLORS = {
    "✓ Mapped": "#16a34a",
    "∼ Partial": "#d97706",
    "✗ Gap": "#dc2626",
}


def _render_table(rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    # Stable key per tab — tab labels include jurisdiction, so a hash
    # of the first row's Regulation column keeps keys distinct across
    # tabs without collision.
    key_suffix = str(rows[0].get("Regulation", id(rows))) if rows else "empty"
    data_grid(
        df,
        key=f"framework_alignment_{hash(key_suffix) & 0xFFFFFF}",
        palette_cols={"Status": FRAMEWORK_STATUS_PALETTE} if "Status" in df.columns else None,
        pinned_left=["Regulation"] if "Regulation" in df.columns else None,
        height=min(35 * len(df) + 60, 500),
    )
    # Citation-link companion view: if any cell contains markdown of
    # the form `[label](url)` (which `citation_link()` emits when the
    # source data carries a URL), render a clickable markdown table
    # below so the URLs become live links. st.dataframe renders the
    # markdown as plain text; st.markdown renders it as HTML. Skipped
    # silently when no row carries a link.
    has_link = any(isinstance(v, str) and "](http" in v for row in rows for v in row.values())
    if has_link:
        with st.expander("Click-through citations (rendered as links)", expanded=False):
            st.markdown(df.to_markdown(index=False), unsafe_allow_html=True)


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
                # If the data carries a `url` for this recommendation,
                # the Title cell becomes a clickable link via citation_link.
                # When no URL is on file the helper falls back to plain text.
                rows.append(
                    {
                        "Status": STATUS_LABELS.get(m["status"], "? Unknown"),
                        "Rec": m["rec"],
                        "Title": citation_link(m["title"], m.get("url")),
                        "Spec Element": m["spec_element"],
                        "Notes": m.get("notes", ""),
                    }
                )
            _render_table(rows)

        elif tab_def["type"] == "pillars":
            if jurisdiction == "CA":
                st.caption(
                    "PCMLTFR s.71 requires 5 pillars for a Canadian AML/ATF compliance "
                    "program. Each pillar maps to Manifest entries."
                )
            else:
                st.caption(
                    "The BSA requires 5 pillars (with a 6th proposed in April 2026). "
                    "Each pillar maps to Manifest entries."
                )
            rows = []
            for p in data:
                rows.append(
                    {
                        "Status": STATUS_LABELS.get(p["status"], "? Unknown"),
                        "Pillar": p.get("pillar", ""),
                        # Pillar Name becomes a clickable citation when
                        # the data layer carries a `url` for this pillar.
                        "Name": citation_link(p["name"], p.get("url")),
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


# --- See also (cross-page nav + research) ---
see_also_footer(
    [
        "[Spec Editor — propose changes that close gaps](./20_Spec_Editor)",
        "[Transformation Roadmap — phased plan](./9_Transformation_Roadmap)",
        "[Regulator Pulse — FinCEN AML Effectiveness NPRM](./27_Regulator_Pulse)",
        research_link(
            "PAIN-3 — gaps you found 6 months ago, still uncovered",
            "2026-04-aml-process-pain.md",
            "pain-3--gaps-you-found-six-months-ago-still-uncovered",
        ),
    ]
)
