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

# Codex pass 1 (P1): without a `rule_map`, every new-side alert would
# bucket as NEW_ONLY and every legacy-side alert as LEGACY_ONLY — a
# misleading "100% divergence" picture that's worse than no surface
# at all under SR 11-7 / OSFI E-23 scrutiny. Stop the render with a
# clear config message instead. Operators who legitimately want
# identity mapping (new rule_id == legacy rule_id) must declare it
# explicitly in the spec — the absence of that declaration here means
# the operator hasn't yet committed to the mapping, and the
# divergence report would mislead.
if not legacy_reference.rule_map:
    st.warning(
        "**`legacy_reference.rule_map` is empty.**\n\n"
        "Without a new-rule-id → legacy-rule-id map, the classifier "
        "cannot join cells across the two systems, and the resulting "
        "report would bucket every new alert as `NEW_ONLY` and every "
        "legacy alert as `LEGACY_ONLY` — misleading audit evidence.\n\n"
        "Add a `rule_map` to `program.legacy_reference` so the "
        "classifier knows which new rules align with which legacy "
        "rules. If the rule ids are identical across systems, declare "
        "that explicitly (e.g. `rule_map: {rapid_pass_through: "
        "rapid_pass_through}`)."
    )
    st.code(
        """program:
  legacy_reference:
    path: data/legacy/legacy_alerts.csv
    format: csv
    key_columns: [customer_id, period_start, rule_id_legacy]
    rule_map:
      rapid_pass_through: MANTAS_RPT_001
      structuring_below_10k: MANTAS_STR_002
""",
        language="yaml",
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


# Codex pass 2 (P2): the spec's `key_columns` carries the legacy
# export's native column names (e.g. the CA example declares
# `[rule_id, customer_id, window_start]`). The loader's canonical
# names are `customer_id` / `period_start` / `period_end` /
# `rule_id_legacy`. Build a translation map so the loader can read
# the export verbatim without forcing the operator to rename columns
# in the legacy system. Operators whose export already uses the
# canonical names (i.e. they renamed at export time) see an empty
# mapping and fall through unchanged. Conservative — only translates
# the well-known synonyms documented in `engine/equivalence.py` +
# `test_column_mapping_supports_spec_native_legacy_columns`.
_LEGACY_SYNONYMS: dict[str, str] = {
    # legacy-system column name → canonical loader name
    "rule_id": "rule_id_legacy",
    "window_start": "period_start",
    "window_end": "period_end",
}


def _derive_column_mapping(key_columns: list[str], csv_header: list[str]) -> dict[str, str]:
    """Build `{canonical: csv_column}` for the loader.

    Strategy (after codex passes 2/4/6 on PR-413):

    1. Honor explicit `key_columns` synonyms first — when the operator
       wrote `key_columns: [rule_id, customer_id, window_start]`, those
       are their declared legacy-system names.
    2. For any canonical column not yet mapped AND not present in the
       CSV header, fall back to the well-known synonym IF that synonym
       exists in the CSV. This catches the case where `key_columns`
       only lists 3 of the 4 canonical cells but the CSV carries the
       4th under its legacy name (e.g. CA's `key_columns` omits
       `window_end` but the CSV has it).
    3. If the canonical column is already in the CSV header, do
       nothing — the loader's default mapping reads it directly.

    This avoids both failure modes codex flagged:
    - Forcing a synonym lookup when the CSV uses canonical names.
    - Missing a synonym when `key_columns` doesn't enumerate all 4.
    """
    canonical_cols = ("customer_id", "period_start", "period_end", "rule_id_legacy")
    mapping: dict[str, str] = {}
    header_set = set(csv_header)
    # Step 1: explicit operator declarations from key_columns. Only
    # apply a synonym mapping when (a) the legacy name from
    # `key_columns` is actually present in the CSV header AND (b) the
    # canonical name is NOT already present. Without this guard,
    # canonical-header exports whose `key_columns` lists legacy names
    # would still map canonical→missing-legacy and the loader would
    # reject the file. Codex pass 11 P2 on PR-413.
    for col in key_columns:
        canonical = _LEGACY_SYNONYMS.get(col)
        if canonical is None:
            continue
        if canonical in header_set:
            continue
        if col not in header_set:
            continue
        mapping[canonical] = col
    # Step 2: fill gaps with well-known synonyms when the canonical
    # name is absent from the CSV and the synonym is present.
    legacy_for_canonical = {v: k for k, v in _LEGACY_SYNONYMS.items()}
    for canonical in canonical_cols:
        if canonical in mapping:
            continue
        if canonical in header_set:
            continue
        synonym = legacy_for_canonical.get(canonical)
        if synonym is not None and synonym in header_set:
            mapping[canonical] = synonym
    return mapping


legacy_alerts: list = []
load_error: str | None = None
legacy_path = Path(legacy_reference.path)
column_mapping: dict[str, str] = {}

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
        # Peek the CSV header so the column-mapping derivation can
        # tell whether the CSV already uses canonical names (no
        # synonym mapping needed) vs. legacy names (synonym mapping
        # required). Codex passes 4 + 6 on PR-413.
        import csv as _csv

        with legacy_path.open(newline="", encoding="utf-8") as _fh:
            _reader = _csv.reader(_fh)
            _csv_header = next(_reader, []) or []
        column_mapping = _derive_column_mapping(legacy_reference.key_columns, _csv_header)
        legacy_alerts = load_legacy_alerts_csv(
            legacy_path,
            column_mapping=column_mapping or None,
        )
except ValueError as exc:
    # Loader raises ValueError on missing header / missing required
    # column / malformed datetime. Surface verbatim — the messages are
    # already human-readable and tell the operator exactly what to fix.
    load_error = f"Could not parse legacy alert CSV: {exc}"
except OSError as exc:
    # `open()` raises `OSError` for permission-denied, directory-not-
    # file, or other I/O failures that the `legacy_path.exists()` /
    # `.is_file()` check above missed (e.g. a mount that disappears
    # between the check and the open). Surface as a configuration
    # error so the page degrades like the missing-file path instead
    # of rendering a Streamlit traceback. Codex pass 10 P3 on PR-413.
    load_error = (
        f"Could not read legacy alert CSV at `{legacy_path}`: "
        f"{type(exc).__name__}: {exc}. Verify the path resolves to a "
        "readable file and the dashboard process has permissions."
    )

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

# Filter alerts to those that carry the comparison-required fields.
# `classify_alerts` validates every alert before applying the rule_map,
# so an unmapped `custom_sql` / `python_ref` payload missing
# `customer_id` / `window_start` / `window_end` would raise and crash
# the page. Codex pass 8 on PR-413.
_REQUIRED_FIELDS = ("customer_id", "window_start", "window_end")
_dropped_per_rule: dict[str, int] = {}
filtered_alerts: dict[str, list[dict]] = {}
for rule_id, alerts in (result.alerts or {}).items():
    keep: list[dict] = []
    dropped = 0
    for a in alerts:
        if all(a.get(k) is not None for k in _REQUIRED_FIELDS):
            keep.append(a)
        else:
            dropped += 1
    if keep:
        filtered_alerts[rule_id] = keep
    if dropped:
        _dropped_per_rule[rule_id] = dropped

if _dropped_per_rule:
    total_dropped = sum(_dropped_per_rule.values())
    st.warning(
        f"⚠️  {total_dropped} alert(s) across "
        f"{len(_dropped_per_rule)} rule(s) lack the equivalence-required "
        "fields (customer_id / window_start / window_end). These are "
        "excluded from the divergence report — they're typically "
        "`custom_sql` or `python_ref` rules whose payload doesn't carry "
        "the canonical cell key. See the per-rule breakdown."
    )
    with st.expander(f"Show {len(_dropped_per_rule)} excluded rule(s)", expanded=False):
        for rid, n in sorted(_dropped_per_rule.items(), key=lambda kv: -kv[1]):
            st.caption(f"• `{rid}` — {n} alert(s) excluded")

try:
    report = classify_alerts(
        new_alerts=filtered_alerts,
        legacy_alerts=legacy_alerts,
        rule_map=legacy_reference.rule_map,
        rule_severities=rule_severities,
    )
except ValueError as _classify_exc:
    # Belt-and-suspenders — the filter above should have caught any
    # malformed alert, but if the classifier still raises (e.g. legacy
    # CSV has a row missing required fields), surface a clear page
    # rather than a Streamlit traceback.
    st.error(
        "Cannot classify equivalence: "
        f"`{type(_classify_exc).__name__}: {_classify_exc}`. Check the "
        "legacy CSV and the spec's `program.legacy_reference` declaration."
    )
    page_footer()
    st.stop()

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
