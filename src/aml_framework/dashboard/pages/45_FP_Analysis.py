"""False-Positive Analysis — per-rule FP rate + high-FP callouts.

PR-E1 (closes #378). Read-only synthesis page that surfaces the
false-positive rate per rule so the operator can see which rules
are eating analyst time on closed-no-action dispositions. The
Pillar 7 (DS as governed augmentation) artefact the North-Star
Pillar Coverage page flags as missing.

FP rate is derived at render time from the cached `df_cases`
populated by `state.initialize_session()` — `closed_no_action`
cases divided by total cases per `rule_id`. Any queue with a
`regulator_form` set on the live spec workflow counts as an
escalated filing (true-positive proxy) — derived from the spec, not
hard-coded, so custom filing queues classify correctly. No engine
call, no spec write, no ML/clustering, no threshold sweep — those
each have their own follow-up PRs (anomaly discovery #382, threshold
sweep #379).

Universally routed (every persona sees it via TUNING_PAGES — same
idiom as NORTH_STAR_PAGES) because FP analysis
is cross-persona: analysts, MLROs, engineers, examiners, and CCOs
all ask "which rules are noisiest?" Cross-links to Rule Tuning,
Tuning Lab, and Rule Performance so the operator can jump from
"these rules need attention" → "let me tune this one".
"""

from __future__ import annotations

import json
from pathlib import Path

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
# A `closed_no_action` status counts as FP. Any queue that carries a
# `regulator_form` on the live spec counts as an escalated filing
# (true-positive proxy) — derived from the workflow, not hard-coded,
# so custom filing queues (e.g. `fraud_filing`, `ctr_filing`,
# jurisdiction-specific `fintrac_str`, etc.) classify correctly. The
# built-in STR/SAR constants in `engine/constants.py` are added as a
# safety net for specs whose queues do not yet declare a
# `regulator_form` but use the canonical ids.
#
# FP rate denominator is `total_cases` per the page contract — every
# case the rule generated, including in-flight, gets counted in the
# denominator so a noisy rule with a long queue tail can't hide its
# FP rate behind unresolved cases. In-flight cases (neither closed
# nor escalated yet) are surfaced as their own count so the operator
# sees both numbers.
# ---------------------------------------------------------------------------
_spec = st.session_state.spec
# Filing queues = any queue with `regulator_form` set. That's the
# canonical "this queue files to a regulator" marker (matches FINTRAC
# STR, FinCEN SAR, OFSI SAR, etc. — same field the regulator pack
# generator reads). Built-in STR_FILING / SAR_FILING included so a spec
# that uses the canonical ids without declaring `regulator_form` still
# classifies correctly.
_ESCALATED_STATUSES: set[str] = {Queue.STR_FILING, Queue.SAR_FILING}
for _q in _spec.workflow.queues:
    if _q.regulator_form:
        _ESCALATED_STATUSES.add(_q.id)


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
_severity_by_rule = {r.id: r.severity for r in _spec.rules}

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
    total = row["total_cases"]
    # Denominator is total cases per the page contract (header +
    # docstring): closed_no_action ÷ total cases. A rule with zero
    # cases never reaches this loop, so `total` is always positive.
    fp_rate: float | None = (row["closed_no_action"] / total) if total else None
    _records.append(
        {
            "rule_id": rule_id,
            "severity": _severity_by_rule.get(rule_id, "—"),
            "total_cases": total,
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
        f"Rules with FP rate above {_HIGH_FP_THRESHOLD:.0%} of total cases. "
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
            f"({rule['closed_no_action']} closed_no_action / "
            f"{rule['total_cases']} total cases)"
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
# `severity_col` colours the severity column with the canonical
# severity palette.
#
# FP rate is kept as a numeric 0-100 column (`fp_rate_pct`) so AG Grid
# sorts and filters it numerically — a string-percent version would
# sort lexicographically (`9.0%` would rank above `80.0%`), masking
# exactly the rules the page is meant to surface. The header label is
# the suffix that tells the reader the units.
# ---------------------------------------------------------------------------
st.markdown("### Per-rule FP rate")

# Convert the 0-1 float to a 0-100 numeric percentage and round to one
# decimal place. AG Grid renders `9.1` and `80.0` naturally; sort and
# filter both stay numeric. Null stays null so unresolved rules render
# as blank rather than zero (which would be a misleading "0% FP").
df_display = df.copy()
df_display["fp_rate_pct"] = df_display["fp_rate"].apply(
    lambda v: round(v * 100, 1) if v is not None and pd.notna(v) else None
)
df_display = df_display.drop(columns=["fp_rate"])

data_grid(
    df_display,
    key="fp_analysis_table",
    severity_col="severity",
    pinned_left=["rule_id"],
    auto_height=True,
    pagination=False,
    hint=(
        "Sorted by FP rate descending. `fp_rate_pct` = closed_no_action "
        "÷ total_cases × 100. `in_flight` = cases not yet resolved "
        "(still counted in the denominator so a noisy rule with a long "
        "queue tail can't hide its FP rate behind unresolved cases). "
        "Column is numeric — click the header to re-sort numerically."
    ),
)

# ---------------------------------------------------------------------------
# Suppression summary (#495) — advisory risk-segment de-prioritization. The
# runner emits `suppression_report.json` ONLY when risk-segmentation is
# enabled (off by default), so the file usually won't exist — handle absent
# gracefully with a one-line note. When present, surface the aggregate
# suppressed / scored counts plus the per-segment and per-rule breakdowns.
# ADVISORY: suppression de-prioritizes, it never closes an alert; the rule
# alert stays in the ledger. No customer_id in this aggregate view.
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Suppression summary")

_supp_report = None
_supp_path = Path(st.session_state.run_dir) / "suppression_report.json"
if _supp_path.exists():
    _supp_report = json.loads(_supp_path.read_text(encoding="utf-8"))

if not _supp_report or not _supp_report.get("enabled"):
    st.caption(
        "Risk segmentation is not enabled for this program — no advisory "
        "suppression ran. Add a `program.risk_segmentation` block to "
        "de-prioritize low-risk-segment alerts (advisory; never auto-closed)."
    )
else:
    st.caption(
        "⚖️ **Advisory only.** These alerts were de-prioritized for low-risk "
        "segments — they are NOT closed and remain in the ledger; an "
        "investigator can override. Counts are aggregate (no customer_id)."
    )
    _scored = int(_supp_report.get("scored_alerts", 0))
    _suppressed = int(_supp_report.get("suppressed", 0))
    _c1, _c2 = st.columns(2)
    _c1.metric("Suppressed (advisory)", _suppressed)
    _c2.metric("Scored alerts", _scored)

    _by_segment = _supp_report.get("by_segment") or {}
    _by_rule = _supp_report.get("by_rule") or {}
    if _by_segment:
        st.markdown("**By segment**")
        st.dataframe(
            pd.DataFrame([{"segment_id": k, "suppressed": v} for k, v in _by_segment.items()]),
            hide_index=True,
            use_container_width=True,
        )
    if _by_rule:
        st.markdown("**By rule**")
        st.dataframe(
            pd.DataFrame([{"rule_id": k, "suppressed": v} for k, v in _by_rule.items()]),
            hide_index=True,
            use_container_width=True,
        )
    if not _by_segment and not _by_rule:
        st.caption("Suppression ran but no alert fell below a segment threshold.")

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
