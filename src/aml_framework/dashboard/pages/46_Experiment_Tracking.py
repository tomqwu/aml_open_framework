"""Experiment Tracking — MLflow-style overview of every persisted run.

PR-E4 (closes #381). Read-only synthesis page that treats every
`run-*` record from the API persistence layer as an experiment row —
surfacing `spec_content_hash`, `seed`, `as_of`, `engine_version`,
`total_alerts`, `decisions_hash`, `dq_exceptions_hash` and friends in
a sortable table. Operators tuning thresholds or comparing spec
variants get an MLflow-style overview without standing up a separate
tracking server.

Pure read of `aml_framework.api.db.list_runs()` + `get_run()` (manifest
JSON) + `get_run_alerts()` (alert counts) — plus the current in-memory
session as one always-present row. No engine call, no spec write, no
side-effect buttons.

Universally routed (every persona sees it) via `TRACKING_PAGES`, the
same idiom as `NORTH_STAR_PAGES` / `AUDIT_TRAIL_PAGES` — see
`audience.py` + `app.py`. Complementary to Run History (per-run
detail browser) and Comparative Analytics (run-over-run trend deltas),
NOT a replacement: this page's job is the "all experiments at a
glance" sortable table.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aml_framework.dashboard.components import (
    data_grid,
    kpi_card,
    link_to_page,
    page_footer,
    page_header,
    section_explainer,
)
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

page_header(
    "Experiment Tracking",
    "Every persisted run as an MLflow-style experiment row — sortable by "
    "`spec_content_hash`, `seed`, `as_of`, alerts, and hash-chain digests.",
)

section_explainer(
    page="Experiment Tracking",
    section_id="experiment_tracking.page",
    section_title="Experiment Tracking",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
        "metrics": len(getattr(st.session_state.get("spec"), "metrics", []) or []),
    },
)


def _short(value: object, length: int = 12) -> str:
    """Return a short prefix of a hash for table-friendly display.

    Manifests can carry `None` for `dq_exceptions_hash` on pre-PR-B4
    runs, and DataFrame columns built from heterogeneous manifests
    therefore mix strings and `NaN`. NaN is truthy in Python, so a
    naive `if value:` check would render `"nan"[:12] = 'nan'` in the
    table — false data in an examiner-facing audit surface. Use the
    explicit pandas-aware guard. (Same defensive pattern PR-F3 codex
    pass 2 pinned.)
    """
    if value is None:
        return ""
    # pandas / numpy NaN is the only float that compares not-equal to itself.
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value)
    if not text:
        return ""
    return text if len(text) <= length else text[:length]


# ---------------------------------------------------------------------------
# Build one row per experiment. The current in-memory session is always
# row 0 (so the page lights up on a fresh install with no API db); any
# rows persisted via `aml api` / Docker Compose join it.
# ---------------------------------------------------------------------------
result = st.session_state.result
session_manifest = result.manifest if result is not None else {}

session_row = {
    "run_id": "current_session",
    "run_ts": st.session_state.as_of.isoformat(),
    "spec_content_hash": _short(session_manifest.get("spec_content_hash")),
    "seed": st.session_state.seed,
    "as_of": session_manifest.get("as_of", ""),
    "engine_version": session_manifest.get("engine_version", ""),
    "total_alerts": result.total_alerts if result is not None else 0,
    "total_cases": len(result.case_ids) if result is not None else 0,
    "decisions_hash": _short(session_manifest.get("decisions_hash")),
    "dq_exceptions_hash": _short(session_manifest.get("dq_exceptions_hash")),
}

# Try to load stored runs. Same defensive try/except as Run History +
# Comparative Analytics — the API persistence layer is optional, and
# the page must still render when the SQLite/Postgres path is not
# wired (or when running in a fresh container before the first run
# lands).
stored_rows: list[dict] = []
try:
    from aml_framework.api.db import get_run, get_run_alerts, init_db, list_runs

    init_db()
    for entry in list_runs():
        run_id = entry.get("run_id", "")
        # Fetch the persisted manifest for the rich fields the
        # `list_runs` projection doesn't return (it only carries
        # run_id / spec_path / seed / created_at by design).
        manifest = get_run(run_id) or {}
        # Sum total_alerts from the alerts table. `get_run_alerts`
        # returns one row per rule_id with a list of alerts; the
        # experiment-table cell is the sum across rules.
        try:
            alert_rows = get_run_alerts(run_id)
            total_alerts = sum(len(r.get("alerts") or []) for r in alert_rows)
        except Exception:
            total_alerts = 0
        stored_rows.append(
            {
                "run_id": run_id,
                "run_ts": entry.get("created_at", ""),
                "spec_content_hash": _short(manifest.get("spec_content_hash")),
                "seed": entry.get("seed"),
                "as_of": manifest.get("as_of", ""),
                "engine_version": manifest.get("engine_version", ""),
                "total_alerts": total_alerts,
                # total_cases isn't carried in the persisted manifest
                # (no `get_run_cases` mirror) — surface as empty rather
                # than fabricating a value. Run History deep-links to
                # the full per-run case list when a reviewer needs the
                # exact count.
                "total_cases": None,
                "decisions_hash": _short(manifest.get("decisions_hash")),
                "dq_exceptions_hash": _short(manifest.get("dq_exceptions_hash")),
            }
        )
except Exception:
    # Persistence layer not available — fall through with just the
    # current-session row. The empty-state path below handles the
    # "literally zero rows" edge separately.
    stored_rows = []

all_rows = [session_row] + stored_rows

# ---------------------------------------------------------------------------
# Roll-up KPIs — total experiments, distinct spec variants, total alerts
# observed across the corpus. Counted from the same `all_rows` the table
# renders so the headline numbers match exactly what the reviewer sees
# below.
# ---------------------------------------------------------------------------
_distinct_specs = {row["spec_content_hash"] for row in all_rows if row.get("spec_content_hash")}
_total_alerts_corpus = sum(int(row.get("total_alerts") or 0) for row in all_rows)

c1, c2, c3 = st.columns(3)
with c1:
    kpi_card("Total experiments", len(all_rows), "#2563eb")
with c2:
    kpi_card("Distinct spec variants", len(_distinct_specs), "#7c3aed")
with c3:
    kpi_card("Total alerts (corpus)", _total_alerts_corpus, "#dc2626")

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Empty-state path — if for any reason `all_rows` ended up empty (e.g.
# `result` was None AND the API path raised), render the canonical
# guidance + page_footer + st.stop pair. (In normal operation the
# current-session row guarantees ≥1.)
# ---------------------------------------------------------------------------
if not all_rows:
    st.info(
        "No experiments to track yet. Runs are persisted when the API is "
        "running (`aml api` or Docker Compose). Each `aml run` or "
        "`POST /runs` creates an experiment row here with spec hash, "
        "seed, alert count, and hash-chain digests."
    )
    page_footer()
    st.stop()

# ---------------------------------------------------------------------------
# Sortable experiments table — one row per run, newest first. Operators
# tuning thresholds across spec variants can sort by `spec_content_hash`
# (group experiments under the same spec) or `total_alerts` (see which
# variant moved the needle).
# ---------------------------------------------------------------------------
df = pd.DataFrame(all_rows)

# Default sort: newest run first. `run_ts` is ISO-format so a lexical
# sort matches chronological order — no parse step needed.
df = df.sort_values(by="run_ts", ascending=False).reset_index(drop=True)

# Column order chosen so the reviewer's first eye-scan covers what
# changed (spec_content_hash, seed, as_of) before the outcome columns
# (total_alerts, total_cases) and the audit-chain anchors
# (decisions_hash, dq_exceptions_hash) on the right.
_column_order = [
    "run_ts",
    "run_id",
    "spec_content_hash",
    "seed",
    "as_of",
    "engine_version",
    "total_alerts",
    "total_cases",
    "decisions_hash",
    "dq_exceptions_hash",
]
df = df[[c for c in _column_order if c in df.columns]]

data_grid(
    df,
    key="experiment_tracking_table",
    pinned_left=["run_ts", "run_id"],
    gradient_cols=["total_alerts"] if "total_alerts" in df.columns else None,
    height=420,
)

st.caption(
    "Sorted newest first. Click a column header to re-sort by spec hash, "
    "seed, alert count, etc. `current_session` is the in-memory run from "
    "this dashboard session — it doesn't require the API persistence "
    "layer to be wired."
)

# ---------------------------------------------------------------------------
# Cross-links — Experiment Tracking is the aggregate table; the
# detail surfaces live on Run History (per-run manifest browser),
# Comparative Analytics (run-over-run trend deltas), and Audit &
# Evidence (hash-chain verification). Route via `link_to_page` so
# persona-hidden targets degrade to a "switch persona" caption rather
# than raising. Same idiom as PR-NS-1 / PR-F3.
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Related surfaces")
link_to_page("pages/15_Run_History.py", "Run History — per-run manifest browser")
link_to_page(
    "pages/19_Comparative_Analytics.py", "Comparative Analytics — run-over-run trend deltas"
)
link_to_page("pages/7_Audit_Evidence.py", "Audit & Evidence — hash-chain replay verifier")

page_footer()
