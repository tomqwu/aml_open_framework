"""Rule Lifecycle — per-rule status + approval-workflow placeholder (PR-A4).

Closes issue #365 ("Rule lifecycle dashboard + approval workflow"). The
examiner question we're pre-answering is "show me which rules are
running in production, which are being tuned, which are deprecated, and
who approved each transition." This page surfaces the live-spec
lifecycle state cleanly; the approval-workflow piece is rendered as an
HONEST placeholder — no signed-off-version store exists yet, so we
expose the unapproved-change badge but explicitly caption that the
backing artifact ships in a follow-up. Pillar 2 (Evidence as a
product) work.

Universally routed via `LIFECYCLE_PAGES` in `audience.py` (same idiom
as Knowledge / North-Star Coverage) — every persona sees it because
governance is cross-cutting, not persona-scoped. Read-only synthesis
surface: no engine call, no writes, no buttons that would touch the
spec.

Complements `5_Rule_Performance.py` (per-rule alert volume + detection
stats) by surfacing the *governance* attributes — status, model_tier,
validation cadence, authored intent, exclusions, risk tier — that
Rule Performance does not show. Cross-links to Spec Editor (modify
rules), Rule Performance (per-rule stats), Tuning Lab (validate
before promoting experimental → active).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aml_framework.dashboard.components import (
    data_grid,
    empty_state,
    kpi_card,
    link_to_page,
    page_footer,
    page_header,
    section_explainer,
)
from aml_framework.dashboard.state import ensure_initialized
from aml_framework.engine.audit import rule_version_hash

ensure_initialized()

page_header(
    "Rule Lifecycle",
    "Which detectors are running in production, which are being tuned, "
    "which are deprecated — plus a placeholder for the approval-workflow "
    "store that ships in a follow-up.",
)

section_explainer(
    page="Rule Lifecycle",
    section_id="rule_lifecycle.page",
    section_title="Rule Lifecycle",
    data_summary={
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
        "metrics": len(getattr(st.session_state.get("spec"), "metrics", []) or []),
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
    },
)

spec = st.session_state.spec

# Degenerate spec guard — same shape as 5_Rule_Performance.py uses for
# zero-rule specs. Without it, the KPI strip below would show all-zero
# cards and the empty data_grid would still try to compute a height
# from a length-0 frame. empty_state(..., stop=True) renders
# `page_footer()` for us before halting, per components.py.
if not spec.rules:
    empty_state(
        "This spec declares zero rules — no lifecycle to surface.",
        icon="📭",
        detail=(
            "Add rules to your spec under the `rules:` section. Each rule's "
            "`status` field (`active` / `experimental` / `deprecated`) is "
            "what this page tracks."
        ),
        stop=True,
    )

# ---------------------------------------------------------------------------
# Lifecycle KPI strip — count of rules per status. Iterates the live
# spec so the cards never drift from the rule table below.
# ---------------------------------------------------------------------------
rules = spec.rules
n_active = sum(1 for r in rules if r.status == "active")
n_experimental = sum(1 for r in rules if r.status == "experimental")
n_deprecated = sum(1 for r in rules if r.status == "deprecated")
n_total = len(rules)

st.markdown("### Lifecycle breakdown")
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Active", n_active, "#059669")
with c2:
    kpi_card("Experimental", n_experimental, "#d97706")
with c3:
    kpi_card("Deprecated", n_deprecated, "#dc2626")
with c4:
    kpi_card("Total rules", n_total, "#2563eb")

st.caption(
    "Lifecycle counts are derived live from each rule's `status` field — "
    "`active` rules are in production, `experimental` are being tuned, "
    "`deprecated` are retained for replay but no longer firing into the "
    "queue. Source of truth: the spec YAML."
)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Per-rule lifecycle table — governance attributes, deliberately
# DIFFERENT from Rule Performance (which shows alert volume + detection
# rate). Columns sorted by status (deprecated last, then experimental,
# then active) so the "rules being tuned right now" band is most
# visible in the middle of the table.
# ---------------------------------------------------------------------------

# Status sort order: deprecated last (least active), experimental in
# the middle (where the action is), active at the top (the baseline).
# Encoded as an explicit ordinal so pandas sort is stable and obvious.
_STATUS_ORDER = {"active": 0, "experimental": 1, "deprecated": 2}

# Approval-workflow placeholder. No signed-off-version store exists
# yet (deferred — see the caption below the table), so every rule's
# "approved version" is None. The badge logic below treats this as
# "unapproved" universally — that's deliberately blunt: it surfaces
# the gap rather than hiding it.
_APPROVED_VERSIONS: dict[str, str | None] = {r.id: None for r in rules}


def _truncate(text: str | None, limit: int = 80) -> str:
    """Truncate free-text fields for grid display.

    Handles None (rules without `business_intent` authored) and empty
    strings — both render as an em-dash so the column reads as
    "absent" rather than visually-empty. Bare-string truthiness is
    safe here because Rule fields are str | None, not pandas NaN.
    """
    if text is None or not text:
        return "—"
    text = str(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


rows = []
for rule in rules:
    rv = rule_version_hash(rule)
    approved = _APPROVED_VERSIONS.get(rule.id)
    # Placeholder approval check: while the approval store is
    # unimplemented, EVERY rule is "unapproved" (approved is None for
    # all rules). When the follow-up PR wires in a real store, this
    # will only flag rules whose current rule_version differs from
    # their last-approved-version. The badge name is the same now
    # so the column doesn't change shape post-wire-in.
    unapproved = approved != rv
    rows.append(
        {
            "rule_id": rule.id,
            "name": rule.name,
            "severity": rule.severity,
            "status": rule.status,
            "model_tier": rule.model_tier or "—",
            "validation_cadence_months": (
                rule.validation_cadence_months
                if rule.validation_cadence_months is not None
                else "—"
            ),
            "rule_version": rv,
            "business_intent": _truncate(getattr(rule, "business_intent", None)),
            "out_of_scope": len(getattr(rule, "out_of_scope", []) or []),
            "risk_tier": getattr(rule, "risk_tier", None) or "—",
            "approval": "⚠ unapproved" if unapproved else "✓ approved",
            "_status_order": _STATUS_ORDER.get(rule.status, 99),
        }
    )

df_rules = (
    pd.DataFrame(rows)
    .sort_values(["_status_order", "rule_id"], kind="stable")
    .drop(columns=["_status_order"])
    .reset_index(drop=True)
)

st.markdown("### Per-rule governance")
data_grid(
    df_rules,
    key="rule_lifecycle_governance_table",
    severity_col="severity" if "severity" in df_rules.columns else None,
    pinned_left=["rule_id"] if "rule_id" in df_rules.columns else None,
    height=min(35 * len(df_rules) + 60, 480),
)

st.caption(
    "**Approval workflow — placeholder.** Not yet wired — the "
    "approval-workflow follow-up will track the `rule_version` hash that "
    "2LoD signed off on, per rule. Today every row reads as `⚠ unapproved` "
    "because no signed-off-version store exists yet; once the store ships, "
    "this column will only flag rules whose current `rule_version` differs "
    "from the last-approved hash. The column name + position stay the same "
    "across the wire-in so this page's shape is stable."
)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Cross-links — three sibling pages that close the loop. Spec Editor
# is where a reviewer modifies a rule; Rule Performance is the
# complementary alert-volume / detection-rate view; Tuning Lab is the
# "validate before promoting experimental → active" stop. Routed
# through `link_to_page` so a hidden persona-target degrades to a
# caption instead of crashing the page (issue #69).
# ---------------------------------------------------------------------------
st.markdown("### Where to go next")
col_a, col_b, col_c = st.columns(3)
with col_a:
    link_to_page("pages/20_Spec_Editor.py", "Spec Editor — modify a rule")
    st.caption("Edit `status`, `business_intent`, `out_of_scope`, `risk_tier` on the spec YAML.")
with col_b:
    link_to_page("pages/5_Rule_Performance.py", "Rule Performance — per-rule stats")
    st.caption("Alert volume + detection rate per rule. Complement to this governance view.")
with col_c:
    link_to_page("pages/23_Tuning_Lab.py", "Tuning Lab — validate before promotion")
    st.caption("Sweep thresholds on `experimental` rules before promoting to `active`.")

page_footer()
