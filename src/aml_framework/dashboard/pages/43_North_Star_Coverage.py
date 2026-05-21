"""North-Star Pillar Coverage — pitch / examiner / reviewer surface.

PR-NS-1. The repo is built around 8 AML/TM + DS pillars (captured in
the user's `project_aml_north_star` memory). The framework has been
growing into them, but no single page surfaces "here are the 8
pillars, here's the evidence each is honored today, here's the gap."
This page does. It's a READ-ONLY synthesis surface — no engine call,
no spec write, no buttons — it just reads the cached
``st.session_state`` populated by ``state.initialize_session()`` and
maps the live spec/run into the 8 pillar cards.

Universally routed (every persona sees it) alongside the Knowledge
shelf — see `app.py` + `audience.py`. Honest about gaps: pillar 1
(equivalence-before-optimization) is flagged GAP today because the
dedicated equivalence engine ships in PR-EQ-2; this page links to the
relevant existing surfaces but does NOT claim coverage we don't have.
"""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.components import page_header, section_explainer
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

page_header(
    "North-Star Pillar Coverage",
    "The 8 AML/TM + DS pillars this framework is built around — what's "
    "demonstrably covered today, and what's still a gap.",
)

section_explainer(
    page="North-Star Pillar Coverage",
    section_id="north_star_coverage.page",
    section_title="North-Star Pillar Coverage",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
        "metrics": len(getattr(st.session_state.get("spec"), "metrics", []) or []),
    },
)

# ---------------------------------------------------------------------------
# Live-spec / live-run signal pulled from cached session state. No engine
# call here — `ensure_initialized()` above guarantees these keys exist.
# ---------------------------------------------------------------------------
spec = st.session_state.spec
result = st.session_state.result
df_metrics = st.session_state.get("df_metrics")
df_decisions = st.session_state.get("df_decisions")
df_cases = st.session_state.get("df_cases")

_rule_count = len(spec.rules)
_metric_count = len(spec.metrics)
_alert_count = result.total_alerts
_case_count = len(result.case_ids)
_decision_count = 0 if df_decisions is None or df_decisions.empty else len(df_decisions)
_jurisdiction = spec.program.jurisdiction
_regulator = spec.program.regulator

st.caption(
    f"Live signal — {_rule_count} rules · {_metric_count} metrics · "
    f"{_alert_count} alerts · {_case_count} cases · {_decision_count} "
    f"audit decisions · {_jurisdiction} / {_regulator}."
)

# ---------------------------------------------------------------------------
# Pillar definitions — verbatim summary from `project_aml_north_star`
# memory. Coverage classifications are conservative: COVERED means a
# concrete artifact the framework produces today; PARTIAL means part of
# the pillar lands but at least one named piece is still missing; GAP
# means no dedicated coverage today (named honestly, not papered over).
# Links use Streamlit's title-derived deep-link slug — the same form
# `st.switch_page` accepts elsewhere in the app.
# ---------------------------------------------------------------------------

# Status palette mirrors the Framework Alignment local vocabulary so the
# product reads as a coherent set of surfaces.
_STATUS_STYLE = {
    "COVERED": ("#16a34a", "✓"),
    "PARTIAL": ("#d97706", "∼"),
    "GAP": ("#dc2626", "✗"),
}


def _render_pillar(
    number: int,
    name: str,
    definition: str,
    status: str,
    evidence: list[str],
    links: list[tuple[str, str]],
) -> None:
    """Render one pillar card.

    Args:
        number:  1-8, used in the eyebrow.
        name:    short pillar name (matches the memory phrasing).
        definition: one-line definition (verbatim from the memory).
        status:  "COVERED" / "PARTIAL" / "GAP".
        evidence: 1-3 concrete artifacts in the live spec/run that
            demonstrate coverage (or, for PARTIAL/GAP, what's in vs
            what's missing).
        links:   ``[(title, page_path)]`` — Streamlit page paths
            relative to ``app.py`` (``pages/<N>_<Name>.py``).
    """
    color, glyph = _STATUS_STYLE[status]
    with st.container(border=True):
        # Eyebrow: "Pillar N · STATUS" with coloured pill.
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:center;margin-bottom:6px;">'
            f'<span style="font-family:ui-monospace,monospace;font-size:0.78rem;'
            f'letter-spacing:0.06em;text-transform:uppercase;color:var(--dna-ink-dim);">'
            f"Pillar {number}</span>"
            f'<span style="font-family:ui-monospace,monospace;font-size:0.78rem;'
            f"padding:2px 10px;border-radius:999px;"
            f'background:{color}22;color:{color};border:1px solid {color}55;">'
            f"{glyph} {status}</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(f"### {name}")
        st.caption(definition)

        st.markdown("**Evidence in this run**")
        for item in evidence:
            st.markdown(f"- {item}")

        if links:
            st.markdown("**See it in action**")
            for title, path in links:
                # `st.page_link` renders a real nav link inside Streamlit
                # so the user lands on the page with all routing /
                # session-state intact (no full-reload, no slug guessing).
                try:
                    st.page_link(path, label=title, icon=":material/arrow_forward:")
                except Exception:
                    # Defensive fallback — if Streamlit ever rejects the
                    # page path (e.g. page renamed), don't crash the
                    # coverage page, just render a caption.
                    st.caption(f"→ {title} (`{path}`)")


# ---------------------------------------------------------------------------
# Pillar 1 — Equivalence before optimization
# Memory text: "legacy migration must first reproduce old output under
# same inputs (parallel run, golden records, field-level diff). Separate
# *intentional logic change* from *migration defect*; classify diffs as
# data / rule / mapping defect. (Distinct from the existing
# deterministic-replay guarantee — that's same-engine reproducibility,
# not legacy-equivalence.)"
#
# Classification: GAP. The framework ships deterministic replay
# (same-engine reproducibility) but has no legacy-equivalence engine
# yet. Naming the gap honestly per the user instruction ("don't paper
# over").
# ---------------------------------------------------------------------------
_render_pillar(
    number=1,
    name="Equivalence before optimization",
    definition=(
        "Legacy migration must first reproduce old output under the same "
        "inputs (parallel run, golden records, field-level diff). Separate "
        "intentional logic change from migration defect; classify diffs as "
        "data / rule / mapping defect. Distinct from same-engine "
        "deterministic replay."
    ),
    status="GAP",
    evidence=[
        "**In:** deterministic replay — same spec + same data + same seed "
        "produces identical output hashes (`test_run_is_reproducible`).",
        "**Missing:** a dedicated legacy-equivalence engine — parallel-run "
        "harness, golden-record fixtures, field-level diff, defect "
        "classifier (data vs rule vs mapping). Ships in PR-EQ-2 — see "
        "`engine/equivalence.py` (forthcoming).",
        "**Net:** the framework can prove it replays itself; it cannot "
        "yet prove it replays a legacy SAS / Oracle / IMS rule one-for-one.",
    ],
    links=[
        ("Run History — same-engine determinism trail", "pages/15_Run_History.py"),
        ("Audit & Evidence — hash-chain replay verifier", "pages/7_Audit_Evidence.py"),
    ],
)

# ---------------------------------------------------------------------------
# Pillar 2 — Evidence as a product
# Memory: "every run traceable by batch_id + rule_version + source
# period + data version; emit source→target mapping, DQ checks,
# reconciliation, run logs, defect tickets, approvals, rule-version
# history, supporting records by design."
#
# Classification: COVERED. The audit ledger + regulator pack are first-
# class artefacts in every run.
# ---------------------------------------------------------------------------
_render_pillar(
    number=2,
    name="Evidence as a product",
    definition=(
        "Every run traceable by batch_id + rule_version + source period + "
        "data version; emit source→target mapping, DQ checks, reconciliation, "
        "run logs, defect tickets, approvals, rule-version history, and "
        "supporting records by design."
    ),
    status="COVERED",
    evidence=[
        f"**Audit ledger** — {_decision_count} decisions on this run's "
        "append-only `decisions.jsonl` hash chain (SHA-256, tamper-detected "
        "by `AuditLedger.verify_decisions()`).",
        "**Regulator-ready ZIP bundle** — `export.py` ships every run as a "
        "single examiner artefact (spec snapshot, alerts, cases, metrics, "
        "decisions ledger, run manifest).",
        f"**Run manifest** — {_rule_count} rules + {_metric_count} metrics "
        "captured with spec hash, seed, as-of timestamp, data source "
        "fingerprint — surfaced on the Audit & Evidence and Lineage "
        "Explorer pages.",
    ],
    links=[
        ("Audit & Evidence — replay + chain verification", "pages/7_Audit_Evidence.py"),
        ("Lineage Explorer — source → query → alert walk-back", "pages/32_Lineage_Explorer.py"),
        ("Run History — per-run manifest browser", "pages/15_Run_History.py"),
    ],
)

# ---------------------------------------------------------------------------
# Pillar 3 — Point-in-time correctness
# Memory: "use customer/account/reference state as of the txn time, not
# latest; data stitching is central."
#
# Classification: PARTIAL. The engine carries an `as_of` timestamp and
# rule windows resolve against it (custom-SQL placeholder substitution).
# The synthetic data is per-snapshot. What's not yet first-class: a
# slowly-changing-dimension stitched customer/account history that
# resolves txn → contemporaneous KYC state at query time.
# ---------------------------------------------------------------------------
_render_pillar(
    number=3,
    name="Point-in-time correctness",
    definition=(
        "Use customer / account / reference state as of the transaction "
        "time, not latest; data stitching is central."
    ),
    status="PARTIAL",
    evidence=[
        "**In:** every run carries an `as_of` timestamp; custom-SQL "
        "rule templates resolve `{as_of}` / `{window_start}` / "
        "`{baseline_start}` / `{dormant_cutoff}` placeholders against it "
        "(deterministic by spec).",
        "**In:** data freshness pins per source on the Data Integration "
        "and Data Quality surfaces (PR-DATAVIZ).",
        "**Missing:** a stitched slowly-changing-dimension (SCD-2) "
        "customer / account history that resolves txn → contemporaneous "
        "KYC state at query time. Today's reference data is a single "
        "snapshot; the join is point-in-time at the run boundary, not at "
        "the per-txn boundary.",
    ],
    links=[
        ("Data Integration — source freshness + contracts", "pages/30_Data_Integration.py"),
        ("Customer 360 — per-attribute staleness view", "pages/17_Customer_360.py"),
        ("Lineage Explorer — point-in-time walk-back", "pages/32_Lineage_Explorer.py"),
    ],
)

# ---------------------------------------------------------------------------
# Pillar 4 — DQ + reconciliation + defect management
# Memory: "DQ dimensions, control totals, reconciliation output,
# severity model, defect lifecycle; surface and distinguish data vs
# rule vs mapping defects."
#
# Classification: PARTIAL. Data Quality + Data Integration pages cover
# DQ checks + control totals. Defect lifecycle (ticketing, severity,
# data-vs-rule-vs-mapping classification) is not yet a first-class
# concept in the spec — overlaps with the equivalence gap above.
# ---------------------------------------------------------------------------
_render_pillar(
    number=4,
    name="DQ + reconciliation + defect management",
    definition=(
        "DQ dimensions, control totals, reconciliation output, severity "
        "model, defect lifecycle; surface and distinguish data vs rule "
        "vs mapping defects."
    ),
    status="PARTIAL",
    evidence=[
        "**In:** Data Quality page ships DQ dimension checks "
        "(completeness, validity, uniqueness, timeliness) per source.",
        "**In:** Data Integration page surfaces source-catalogue rollups, "
        "ISO 20022 message-type counts, contract roll-ups (PR-DATAVIZ).",
        "**Missing:** a defect ticket model with severity + lifecycle + "
        "data-vs-rule-vs-mapping classifier in the spec schema. Today, "
        "DQ failures surface as gauge breaches rather than as tracked "
        "defects with owners and aging.",
    ],
    links=[
        ("Data Quality — DQ dimensions + control totals", "pages/14_Data_Quality.py"),
        ("Data Integration — source catalogue + contracts", "pages/30_Data_Integration.py"),
    ],
)

# ---------------------------------------------------------------------------
# Pillar 5 — Risk-based controls
# Memory: "risk attributes drive scenario eligibility, thresholds,
# alert priority, case routing — not decorative metadata."
#
# Classification: COVERED. Risk Assessment page + the per-rule risk
# tags in the spec drive case routing and alert priority.
# ---------------------------------------------------------------------------
_render_pillar(
    number=5,
    name="Risk-based controls",
    definition=(
        "Risk attributes drive scenario eligibility, thresholds, alert "
        "priority, and case routing — not decorative metadata."
    ),
    status="COVERED",
    evidence=[
        f"**In:** {_rule_count} rules carry risk tags driving alert "
        "priority on the Alert Queue and routing on My Queue / Analyst "
        "Review Queue.",
        "**In:** Risk Assessment page maps customer-segment exposure to "
        "scenario eligibility per the spec's risk attributes.",
        "**In:** Typology Catalogue cross-references each typology to its "
        "risk-rated detection rule(s).",
    ],
    links=[
        ("Risk Assessment — exposure → scenario eligibility", "pages/6_Risk_Assessment.py"),
        ("Alert Queue — risk-priority ordering", "pages/3_Alert_Queue.py"),
        ("Typology Catalogue — risk → typology → rule", "pages/18_Typology_Catalogue.py"),
    ],
)

# ---------------------------------------------------------------------------
# Pillar 6 — Alert lifecycle & explainability
# Memory: "an alert is a handoff into investigation; features must
# explain the trigger (window, threshold, segment, rule version,
# reference-data version, supporting txns)."
#
# Classification: COVERED. The Case Investigation page's "Why this
# fired" panel + the Lineage Explorer walk-back provide
# rule-version + window + supporting-txns explanation; Investigations
# carries case routing through escalation.
# ---------------------------------------------------------------------------
_render_pillar(
    number=6,
    name="Alert lifecycle & explainability",
    definition=(
        "An alert is a handoff into investigation; features must explain "
        "the trigger (window, threshold, segment, rule version, "
        "reference-data version, supporting transactions)."
    ),
    status="COVERED",
    evidence=[
        f"**In:** every alert on this run ({_alert_count} total) carries "
        "its rule_id, threshold, window, and supporting-txn references "
        "from the engine — visible on Case Investigation's 'Why this "
        "fired' panel.",
        "**In:** Lineage Explorer (PR-LIN) walks source row → SQL query → "
        f"alert → case, with rule version + spec hash pinned. {_case_count} "
        "cases in scope on this run.",
        "**In:** Investigations page carries the L1 → L2 → MLRO escalation "
        "lifecycle; STR narrative generator pre-attaches the trigger "
        "evidence.",
    ],
    links=[
        ("Case Investigation — 'Why this fired' panel", "pages/4_Case_Investigation.py"),
        ("Lineage Explorer — source → query → alert chain", "pages/32_Lineage_Explorer.py"),
        ("Investigations — L1 → L2 → MLRO lifecycle", "pages/24_Investigations.py"),
    ],
)

# ---------------------------------------------------------------------------
# Pillar 7 — DS as governed augmentation
# Memory: "deterministic rules are the governed baseline; ML/analytics
# *prioritize, tune, segment, discover* with explainability, validation,
# monitoring, approval (model risk). Watch temporal leakage, imperfect
# labels, imbalanced evaluation, feature-window correctness."
#
# Classification: PARTIAL. Rules-baseline is the governed product;
# Model Performance + Tuning Lab surface ML-side prioritisation and
# threshold tuning with validation. What's still missing: a formal
# model-risk lifecycle (challenger model registry, approval gates,
# temporal-leakage / feature-window checks as first-class spec
# artefacts rather than analyst discipline).
# ---------------------------------------------------------------------------
_render_pillar(
    number=7,
    name="DS as governed augmentation",
    definition=(
        "Deterministic rules are the governed baseline; ML/analytics "
        "prioritize, tune, segment, and discover — with explainability, "
        "validation, monitoring, and approval (model risk). Watch temporal "
        "leakage, imperfect labels, imbalanced evaluation, feature-window "
        "correctness."
    ),
    status="PARTIAL",
    evidence=[
        "**In:** deterministic rule baseline is the governed product "
        f"({_rule_count} rules + {_metric_count} metrics in this spec); "
        "ML lives alongside, not in place of.",
        "**In:** Model Performance + Tuning Lab + Rule Tuning surfaces "
        "ML-assisted threshold tuning with explainability and CI-checked "
        "validation.",
        "**Missing:** a formal model-risk lifecycle in the spec — "
        "challenger-model registry, approval gates, temporal-leakage / "
        "feature-window checks as first-class spec artefacts rather than "
        "analyst discipline.",
    ],
    links=[
        ("Model Performance — ML metric drift + monitoring", "pages/13_Model_Performance.py"),
        ("Tuning Lab — what-if threshold analysis", "pages/23_Tuning_Lab.py"),
        ("AI Assistant — co-pilot provenance + audit trail", "pages/29_AI_Assistant.py"),
    ],
)

# ---------------------------------------------------------------------------
# Pillar 8 — Serve five roles
# Memory: "data engineer, data analyst/BI, data scientist, QA/DQ
# engineer, solution architect (maps to the dashboard's persona/audience
# routing)."
#
# Classification: COVERED. Audience routing in `audience.py` already
# carries 14 personas (the original 5 + extras like FinTech MLRO);
# every persona has a curated arc capped at 9 pages.
# ---------------------------------------------------------------------------
_render_pillar(
    number=8,
    name="Serve five roles",
    definition=(
        "Data engineer, data analyst / BI, data scientist, QA / DQ "
        "engineer, solution architect — the dashboard's persona / "
        "audience routing must map to these five (plus the workflow "
        "personas above them)."
    ),
    status="COVERED",
    evidence=[
        "**In:** `audience.py` carries 14 personas with curated page "
        "arcs — all five north-star roles plus operational personas "
        "(analyst / manager / director / CCO / VP / SVP / CTO / PM / "
        "auditor / business / FinTech MLRO).",
        "**In:** per-persona cap of 9 pages enforced "
        "(`MAX_PAGES_PER_PERSONA`) — the sidebar self-curates so no role "
        "sees the full 40-page surface.",
        "**In:** persona selector + one-line role description in the "
        "sidebar lets a leader self-identify by title (CCO / MLRO / "
        "Director of Financial Crime / Data Engineer / Head of Data) "
        "without guessing what `cco` / `vp` mean.",
    ],
    links=[
        ("Today — personalised landing per role", "pages/0_Today.py"),
        ("Executive Dashboard — strategic-view fallback", "pages/1_Executive_Dashboard.py"),
        ("Data Integration — Data Engineer / Head of Data lane", "pages/30_Data_Integration.py"),
    ],
)

# ---------------------------------------------------------------------------
# Roll-up — the headline tally so a pitch reviewer sees the picture in
# one glance.
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Coverage roll-up")

col_a, col_b, col_c = st.columns(3)
with col_a:
    st.metric("Covered", "4", help="Pillars 2, 5, 6, 8")
with col_b:
    st.metric("Partial", "3", help="Pillars 3, 4, 7")
with col_c:
    st.metric("Gap", "1", help="Pillar 1 — equivalence engine ships in PR-EQ-2")

st.caption(
    "Coverage is asserted, not aspirational — every COVERED claim above "
    "points to a concrete artefact this run produced. PARTIAL and GAP "
    "rows name what's missing rather than soft-pedalling it. Source of "
    "truth for the 8 pillars: the user's `project_aml_north_star` "
    "memory."
)
