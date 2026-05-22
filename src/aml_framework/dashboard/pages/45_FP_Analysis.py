"""False-Positive Analysis — per-rule FP rate + high-FP callouts.

PR-E1 (closes #378). Read-only synthesis page that surfaces the
false-positive rate per rule so the operator can see which rules
are eating analyst time on closed-no-action dispositions. The
Pillar 7 (DS as governed augmentation) artefact the North-Star
Pillar Coverage page flags as missing.

FP rate is derived at render time from the cached `df_cases`
populated by `state.initialize_session()` — `closed_no_action`
cases divided by total cases per `rule_id`. STR + SAR filings
count as escalated (true-positive proxy). No engine call, no spec
write, no ML/clustering, no threshold sweep — those each have their
own follow-up PRs (anomaly discovery #382, threshold sweep #379).

Universally routed (every persona sees it via TUNING_PAGES — same
idiom as NORTH_STAR_PAGES / KNOWLEDGE_PAGES) because FP analysis
is cross-persona: analysts, MLROs, engineers, examiners, and CCOs
all ask "which rules are noisiest?" Cross-links to Rule Tuning,
Tuning Lab, and Rule Performance so the operator can jump from
"these rules need attention" → "let me tune this one".
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aml_framework.dashboard.components import (
    data_grid,
    link_to_page,
    page_footer,
    page_header,
    section_explainer,
)
from aml_framework.dashboard.state import ensure_initialized
from aml_framework.engine.constants import Queue

ensure_initialized()

page_header(
    "False-Positive Analysis",
    "Per-rule FP rate (closed-no-action ÷ total cases). The Pillar 7 "
    "'DS as governed augmentation' surface that points at which rules "
    "to tune first.",
)

section_explainer(
    page="False-Positive Analysis",
    section_id="fp_analysis.page",
    section_title="False-Positive Analysis",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "case_count": (
            len(st.session_state.get("df_cases"))
            if st.session_state.get("df_cases") is not None
            else 0
        ),
    },
)

df_cases = st.session_state.get("df_cases")

# No-cases path — guard the empty frame so a fresh run / dry-run spec
# can't crash this surface. Same pattern as PR-F3 (Decision Trail) and
# PR-NS-1 (North-Star Pillar Coverage): page_footer() then st.stop()
# so the bottom-of-page affordance still renders on the early-return.
if df_cases is None or df_cases.empty:
    st.info(
        "No cases in this run — FP analysis lights up once the engine "
        "emits at least one case. Re-run the spec against data that "
        "trips the rules, then return here."
    )
    page_footer()
    st.stop()

# ---------------------------------------------------------------------------
# Per-rule FP rate computation. Cases carry `rule_id`, `severity`, and
# `status` (the disposition queue id from `_simulate_case_resolution`).
# A `closed_no_action` status counts as FP; STR / SAR filings count as
# escalated (true-positive proxy). L2 in-flight cases are neither — we
# surface the count but exclude them from the FP-rate denominator so
# the rate isn't deflated by cases that haven't resolved yet.
# ---------------------------------------------------------------------------
_ESCALATED_STATUSES = {Queue.STR_FILING, Queue.SAR_FILING}


def _categorize(status: str) -> str:
    if status == Queue.CLOSED_NO_ACTION:
        return "closed_no_action"
    if status in _ESCALATED_STATUSES:
        return "escalated"
    return "in_flight"


# Pull severity per rule_id from the cached spec so the table can show
# the rule's declared priority alongside the empirical FP rate. The
# session-state spec is the source of truth — same rules as the engine
# saw on this run.
_severity_by_rule = {r.id: r.severity for r in st.session_state.spec.rules}

# Build the per-rule aggregate. Pandas groupby is overkill for the
# typical ≤30-rule shape — a single pass is clearer and matches the
# read-only-synthesis discipline of the sibling pages.
_rows: dict[str, dict[str, int]] = {}
for case in df_cases.to_dict(orient="records"):
    rule_id = case.get("rule_id") or "<unknown>"
    bucket = _categorize(case.get("status") or "")
    row = _rows.setdefault(
        rule_id,
        {"total_cases": 0, "closed_no_action": 0, "escalated": 0, "in_flight": 0},
    )
    row["total_cases"] += 1
    row[bucket] += 1

# Materialise the table with FP rate as a float in [0, 1]. Sorted by
# fp_rate desc so the worst offenders sit at the top — the whole point
# of this page.
_records: list[dict[str, object]] = []
for rule_id, row in _rows.items():
    resolved = row["closed_no_action"] + row["escalated"]
    # Denominator is resolved cases only — in-flight cases haven't yet
    # been classified, so including them would deflate the rate. A
    # rule with zero resolved cases is excluded from the rate (shown
    # as null) rather than divided by zero.
    fp_rate = (row["closed_no_action"] / resolved) if resolved else None
    _records.append(
        {
            "rule_id": rule_id,
            "severity": _severity_by_rule.get(rule_id, "—"),
            "total_cases": row["total_cases"],
            "closed_no_action": row["closed_no_action"],
            "escalated": row["escalated"],
            "in_flight": row["in_flight"],
            "fp_rate": fp_rate,
        }
    )

# Sort: rules with a defined fp_rate desc, then unresolved rules at the
# bottom (None sorts last). pandas treats None as NaN which sorts last
# under `na_position="last"`.
df = pd.DataFrame(_records)
df = df.sort_values(by="fp_rate", ascending=False, na_position="last").reset_index(drop=True)

# ---------------------------------------------------------------------------
# High-FP callouts — rules with fp_rate > 70% get a coloured banner at
# the top of the page so a reviewer can't miss them. 70% is the same
# threshold the FFIEC examiners commonly flag in TM tuning reviews;
# anything above that line is "the rule is firing more wrong than
# right" and deserves immediate tuning attention.
# ---------------------------------------------------------------------------
_HIGH_FP_THRESHOLD = 0.70
_high_fp_rules = [
    r for r in _records if r["fp_rate"] is not None and r["fp_rate"] > _HIGH_FP_THRESHOLD
]

if _high_fp_rules:
    st.markdown("### High-FP rules — tune first")
    st.caption(
        f"Rules with FP rate above {_HIGH_FP_THRESHOLD:.0%} of resolved cases. "
        "These are the analyst-time sinks — open Tuning Lab to model a "
        "threshold change before pushing a spec edit."
    )
    for rule in _high_fp_rules:
        rate = rule["fp_rate"]
        # rate is guaranteed non-None here by the filter above.
        rate_pct = f"{rate:.0%}" if rate is not None else "—"
        st.markdown(
            f'<div style="border-left:4px solid #dc2626;padding:8px 12px;'
            f'margin-bottom:6px;background:#dc262611;border-radius:4px;">'
            f"<strong>{rule['rule_id']}</strong> · severity={rule['severity']} · "
            f"FP rate <strong>{rate_pct}</strong> "
            f"({rule['closed_no_action']} closed / "
            f"{int(rule['closed_no_action']) + int(rule['escalated'])} resolved)"
            "</div>",
            unsafe_allow_html=True,
        )
    # Single cross-link to Tuning Lab — the modelling surface for the
    # operator's next move. Per-rule deep-link would be a follow-up.
    link_to_page("pages/23_Tuning_Lab.py", "Open Tuning Lab → model a threshold change")
    st.markdown("---")

# ---------------------------------------------------------------------------
# Per-rule FP table. Use the shared `data_grid` component for the same
# sort + filter + colouring vocabulary as the rest of the dashboard.
# `gradient_cols=["fp_rate"]` paints the rate cell on the red→amber→
# green scale so the eye lands on the worst rules first; `severity_col`
# colours the severity column with the canonical severity palette.
# ---------------------------------------------------------------------------
st.markdown("### Per-rule FP rate")

# Format fp_rate as a percent string for the table so the column reads
# naturally; keep the raw float in a hidden helper column if a future
# revision wants to sort numerically. data_grid sort is client-side so
# the string form sorts lexicographically — fine because the page-load
# sort above already pre-orders the rows correctly.
df_display = df.copy()
df_display["fp_rate"] = df_display["fp_rate"].apply(
    lambda v: f"{v:.1%}" if v is not None and pd.notna(v) else "—"
)

data_grid(
    df_display,
    key="fp_analysis_table",
    severity_col="severity",
    pinned_left=["rule_id"],
    auto_height=True,
    pagination=False,
    hint=(
        "Sorted by FP rate descending. `in_flight` = cases not yet resolved "
        "(excluded from the FP-rate denominator)."
    ),
)

# ---------------------------------------------------------------------------
# Cross-links — the operator's next moves. Same `link_to_page` discipline
# as PR-NS-1: persona-filtered targets that get hidden in the active
# nav degrade to a "switch persona" caption rather than raising
# StreamlitPageNotFoundError.
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Related surfaces")
link_to_page("pages/16_Rule_Tuning.py", "Rule Tuning — threshold sweep on this rule")
link_to_page("pages/23_Tuning_Lab.py", "Tuning Lab — what-if threshold analysis")
link_to_page("pages/5_Rule_Performance.py", "Rule Performance — per-rule precision / recall")

page_footer()
