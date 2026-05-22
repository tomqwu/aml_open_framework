"""Equivalence — legacy↔new alert parallel-run divergence surface.

PR-EQ-3. Closes the Pillar 1 gap on the North-Star Coverage page by
surfacing the classifier shipped in PR-EQ-2 (``engine/equivalence.py``)
as an examiner-facing dashboard surface.

Behaviour:

* When ``spec.program.legacy_reference`` is ``None``, the page shows
  an info card explaining how to opt in via the spec (with a small
  YAML snippet). This is the common case for greenfield deployments.
* When a ``LegacyReference`` is declared, the page loads the legacy
  alert CSV via ``load_legacy_alerts_csv``, calls ``classify_alerts``
  against the live run's ``result.alerts``, and surfaces:
    - 4-column KPI roll-up (MATCH / NEW_ONLY / LEGACY_ONLY / DIFF).
    - By-rule breakdown table.
    - Cell-level table (capped at 200 rows for readability).
  The classifier is pure + fast (no I/O after the CSV load); safe to
  run on every Streamlit rerun.

Routed UNIVERSALLY (every persona sees it) via
``EQUIVALENCE_PAGES`` in ``audience.py`` — same idiom as
``KNOWLEDGE_PAGES`` / ``NORTH_STAR_PAGES``. Audit-team-facing, so it's
registered under the "Audit & Reference" sidebar category.

Read-only: never writes ``legacy_reference`` back to the spec — that
edit path belongs to the Spec Editor.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from aml_framework.dashboard.components import (
    link_to_page,
    page_footer,
    page_header,
    section_explainer,
)
from aml_framework.dashboard.state import ensure_initialized
from aml_framework.engine.equivalence import (
    EquivalenceClass,
    classify_alerts,
    load_legacy_alerts_csv,
)

ensure_initialized()

page_header(
    "Equivalence",
    "Legacy↔new alert parallel-run divergence — the SR 11-7 / OSFI E-23 "
    "evidence that the new framework reproduces the legacy TM system "
    "where it should, and explains every cell where it doesn't.",
)

section_explainer(
    page="Equivalence",
    section_id="equivalence.page",
    section_title="Equivalence",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
        "legacy_reference_declared": (
            getattr(
                getattr(st.session_state.get("spec"), "program", None), "legacy_reference", None
            )
            is not None
        ),
    },
)

spec = st.session_state.spec
result = st.session_state.result
legacy_reference = spec.program.legacy_reference

# ---------------------------------------------------------------------------
# No-legacy-reference path — show how to opt in via the spec, then stop.
# This is the common case for greenfield deployments that have no legacy
# system to compare against; we surface the feature explicitly rather
# than hiding the page so the operator discovers it.
# ---------------------------------------------------------------------------
if legacy_reference is None:
    st.info(
        "**No legacy reference declared.**\n\n"
        "This program has no `program.legacy_reference` block in the spec, so "
        "the parallel-run divergence classifier has nothing to compare against. "
        "Add a block like the one below to your `aml.yaml` to enable "
        "MATCH / NEW_ONLY / LEGACY_ONLY / DIFF classification against a "
        "legacy TM system's alert export."
    )
    st.code(
        """program:
  # ... existing fields ...
  legacy_reference:
    path: data/legacy/legacy_alerts.csv     # exported from the legacy system
    format: csv
    key_columns: [customer_id, period_start, rule_id_legacy]
    # new_rule_id -> legacy_rule_id; classifier joins on this map
    rule_map:
      rapid_pass_through: MANTAS_RPT_001
      structuring_below_10k: MANTAS_STR_002
""",
        language="yaml",
    )
    st.caption(
        "Once a `legacy_reference` is declared, this page loads the CSV at "
        "render time, calls `engine.equivalence.classify_alerts(...)`, and "
        "surfaces the cell-level divergence with a per-rule rollup. The "
        "engine itself is unaffected — `legacy_reference` is metadata, never "
        "consulted at run time (determinism contract pinned by "
        "`test_legacy_reference_does_not_break_determinism_contract`)."
    )
    st.markdown("---")
    st.markdown("**Related surfaces**")
    link_to_page("pages/20_Spec_Editor.py", "Spec Editor — edit `program.legacy_reference`")
    link_to_page(
        "pages/43_North_Star_Coverage.py",
        "North-Star Pillar Coverage — Pillar 1 (Equivalence before optimization)",
    )
    page_footer()
    st.stop()

# ---------------------------------------------------------------------------
# Loaded-legacy path — read the CSV, classify, render.
# Every failure mode (missing file, missing header, missing required
# column) surfaces as a user-readable error rather than crashing the
# page. The classifier is pure and fast; safe on every rerun.
# ---------------------------------------------------------------------------
st.caption(
    f"Legacy reference: `{legacy_reference.path}` "
    f"(format={legacy_reference.format}, dataset={legacy_reference.dataset or '—'})"
)

legacy_alerts: list = []
load_error: str | None = None
legacy_path = Path(legacy_reference.path)

try:
    if not legacy_path.exists():
        load_error = (
            f"Legacy alert file not found at `{legacy_path}`. "
            "Check that the path in `program.legacy_reference.path` "
            "is reachable from the dashboard's working directory, or "
            "edit the spec to point at the live export location."
        )
    elif legacy_reference.format != "csv":
        load_error = (
            f"Legacy reference format `{legacy_reference.format}` is declared "
            "but only `csv` is supported by this surface today. Pre-convert "
            "the export to CSV, or wait for the parquet/jsonl loader."
        )
    else:
        legacy_alerts = load_legacy_alerts_csv(legacy_path)
except ValueError as exc:
    # Loader raises ValueError on missing header / missing required
    # column / malformed datetime. Surface verbatim — the messages are
    # already human-readable and tell the operator exactly what to fix.
    load_error = f"Could not parse legacy alert CSV: {exc}"

if load_error is not None:
    st.error(load_error)
    st.markdown("---")
    st.markdown("**Related surfaces**")
    link_to_page("pages/20_Spec_Editor.py", "Spec Editor — edit `program.legacy_reference`")
    link_to_page("pages/15_Run_History.py", "Run History — see the new-side alerts this run")
    page_footer()
    st.stop()

# Build the severity map once — passed to the classifier so DIFF
# detection works even when the runner doesn't inject severity onto
# the alert payload (see equivalence.py docstring for the rationale).
rule_severities = {r.id: r.severity for r in spec.rules}

report = classify_alerts(
    new_alerts=result.alerts,
    legacy_alerts=legacy_alerts,
    rule_map=legacy_reference.rule_map or {},
    rule_severities=rule_severities,
)

# ---------------------------------------------------------------------------
# Roll-up KPIs — one column per EquivalenceClass. report.counts always
# carries all four keys (classifier guarantees no .get() needed).
# ---------------------------------------------------------------------------
st.markdown("### Classification roll-up")
col_match, col_new_only, col_legacy_only, col_diff = st.columns(4)
with col_match:
    st.metric(
        "MATCH",
        report.counts[EquivalenceClass.MATCH],
        help="Both systems alerted on the same (customer, period, rule) cell with the same severity.",
    )
with col_new_only:
    st.metric(
        "NEW_ONLY",
        report.counts[EquivalenceClass.NEW_ONLY],
        help="The new framework alerted; the legacy system did not.",
    )
with col_legacy_only:
    st.metric(
        "LEGACY_ONLY",
        report.counts[EquivalenceClass.LEGACY_ONLY],
        help="The legacy system alerted; the new framework did not.",
    )
with col_diff:
    st.metric(
        "DIFF",
        report.counts[EquivalenceClass.DIFF],
        help="Both alerted but the severity differs — see the diff_reason column below.",
    )

_total_cells = sum(report.counts.values())
st.caption(
    f"{_total_cells} cells classified across "
    f"{len(report.by_rule)} rule rollups · "
    f"legacy export: {len(legacy_alerts)} rows · "
    f"new-side: {result.total_alerts} alerts."
)

# ---------------------------------------------------------------------------
# By-rule breakdown — one row per rule (new rule_id when mapped, else
# the `legacy:<id>` synthetic key the classifier emits for unmapped
# legacy rules). Sortable by default via st.dataframe.
# ---------------------------------------------------------------------------
st.markdown("### By-rule breakdown")
if report.by_rule:
    by_rule_rows = [
        {
            "rule_id": rule_id,
            "MATCH": bucket[EquivalenceClass.MATCH],
            "NEW_ONLY": bucket[EquivalenceClass.NEW_ONLY],
            "LEGACY_ONLY": bucket[EquivalenceClass.LEGACY_ONLY],
            "DIFF": bucket[EquivalenceClass.DIFF],
        }
        for rule_id, bucket in sorted(report.by_rule.items())
    ]
    st.dataframe(
        pd.DataFrame(by_rule_rows),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.caption(
        "No cells classified — both the new-side and legacy-side alert "
        "lists are empty, or no `rule_map` entries connect them."
    )

# ---------------------------------------------------------------------------
# Cell-level table — capped at 200 rows so the page stays interactive
# on large legacy exports. Operators wanting the full set should
# integrate the classifier programmatically (the engine API is the
# source of truth — this page is a viewer).
# ---------------------------------------------------------------------------
_MAX_CELL_ROWS = 200
st.markdown("### Cell-level classification")
if report.cells:
    cell_rows = [
        {
            "customer_id": cell.customer_id,
            "period_start": cell.period_start,
            "period_end": cell.period_end,
            # rule_id_new/legacy can be None on LEGACY_ONLY / unmapped
            # NEW_ONLY cells; pandas treats None as NaN in the rendered
            # table, which surfaces as a blank cell — exactly what we
            # want. Don't coerce to "" because that would hide the
            # distinction from a real empty string.
            "rule_id_new": cell.rule_id_new,
            "rule_id_legacy": cell.rule_id_legacy,
            "classification": cell.classification.value,
            "new_severity": cell.new_severity,
            "legacy_severity": cell.legacy_severity,
            "diff_reason": cell.diff_reason,
        }
        for cell in report.cells[:_MAX_CELL_ROWS]
    ]
    st.dataframe(
        pd.DataFrame(cell_rows),
        use_container_width=True,
        hide_index=True,
    )
    if len(report.cells) > _MAX_CELL_ROWS:
        st.caption(
            f"Showing the first {_MAX_CELL_ROWS} of {len(report.cells)} "
            "classified cells. For the full export, call "
            "`engine.equivalence.classify_alerts(...)` programmatically "
            "and serialise `report.cells`."
        )
else:
    st.caption("No cells to classify on this run.")

# ---------------------------------------------------------------------------
# Cross-links — Run History (new-side trail), Audit & Evidence
# (regulator-pack drill-down), Spec Editor (legacy_reference edit
# path). Routed through link_to_page so persona-filtered targets
# degrade gracefully if the active persona hides them.
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("**Related surfaces**")
link_to_page("pages/15_Run_History.py", "Run History — same-engine determinism trail")
link_to_page("pages/7_Audit_Evidence.py", "Audit & Evidence — regulator pack + replay chain")
link_to_page("pages/20_Spec_Editor.py", "Spec Editor — edit `program.legacy_reference`")
link_to_page(
    "pages/43_North_Star_Coverage.py",
    "North-Star Pillar Coverage — Pillar 1 (Equivalence before optimization)",
)

page_footer()
