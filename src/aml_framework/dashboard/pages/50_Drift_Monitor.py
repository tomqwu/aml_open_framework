"""Drift Monitor — per-scorer input/output drift across recent runs.

PR-E3 (issue #380, [E3][epic]). Pillar 7 (DS as governed augmentation).

Read-only synthesis surface — no engine call, no spec write. For each
`python_ref` scorer the framework runs, this page reads the per-rule
alert artefacts from the most recent stored runs (via
`aml_framework.api.db.list_runs()` + `get_run_alerts()`), computes a
count-based drift signal per scorer, and surfaces high-drift scorers
with a Tuning Lab cross-link.

NOTE — drift here is intentionally count-based: a scorer whose alert
count last-run was >2× or <0.5× the median of prior runs is flagged
"high drift". Richer statistical drift (KS test / PSI / Wasserstein on
feature distributions) is deferred to a future ML scoring epic — that
work requires capturing the model's input feature vector per alert,
which the current alert payload doesn't carry. See the deferred-work
note inline.

Universally routed (every persona sees it) via `TUNING_PAGES` —
mirrors the Knowledge / North-Star idiom in `app.py`. NOT in
`AUDIENCE_PAGES` so the per-persona MAX_PAGES_PER_PERSONA cap is
preserved.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from statistics import median

import pandas as pd
import streamlit as st

from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import (
    empty_state,
    kpi_card,
    line_chart,
    link_to_page,
    page_footer,
    page_header,
    section_explainer,
    see_also_footer,
)
from aml_framework.dashboard.data_grid import data_grid
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

page_header(
    "Drift Monitor",
    "Per-scorer alert-volume drift across recent runs — surfaces "
    "python_ref scorers whose output materially diverges from their "
    "recent baseline.",
)
show_audience_context("Drift Monitor")

section_explainer(
    page="Drift Monitor",
    section_id="drift_monitor.page",
    collapsed=True,
    section_title="Drift Monitor",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
        "metrics": len(getattr(st.session_state.get("spec"), "metrics", []) or []),
        "case_count": (
            len(st.session_state.get("df_cases"))
            if st.session_state.get("df_cases") is not None
            else 0
        ),
    },
)

# -----------------------------------------------------------------------
# Model-risk report (#497) — advisory model-inventory monitoring.
# Rendered FIRST, before any python_ref/persistence early-return, because
# the report reads `model_risk_report.json` from the run dir and is
# independent of whether the spec has python_ref scorers — a rule-only
# spec with `program.model_risk_monitoring.enabled` must still see it
# (otherwise the no-python_ref `st.stop()` below would hide it). The
# runner emits the file ONLY when `program.model_risk_monitoring.enabled`
# (off by default), so it usually won't exist — handle absent/disabled
# gracefully with a one-line note (the common case). Mirrors page 45's
# run-dir artifact read (`45_FP_Analysis.py:263`):
# `Path(st.session_state.run_dir) / "<file>.json"`. ADVISORY: a lens over
# the model inventory — it never blocks a run or changes a model.
# Aggregate-only (model_key/owner are config, not PII).
# -----------------------------------------------------------------------
st.subheader("Model-risk report")

_mr_report = None
_mr_path = Path(st.session_state.run_dir) / "model_risk_report.json"
if _mr_path.exists():
    _mr_report = json.loads(_mr_path.read_text(encoding="utf-8"))

if not _mr_report or not _mr_report.get("enabled"):
    st.info(
        "Model-risk monitoring is not enabled — add `program.model_risk_monitoring` to the spec."
    )
else:
    _mr_n_models = int(_mr_report.get("n_models", 0))
    _mr_n_high = int(_mr_report.get("n_high_drift", 0))
    section_explainer(
        page="Drift Monitor",
        section_id="drift.model_risk",
        section_title="Model-risk report",
        data_summary={
            "n_models": _mr_n_models,
            "n_high_drift": _mr_n_high,
        },
    )
    st.caption(
        "Advisory monitoring (SR 11-7 / OSFI E-23) — a lens over the model "
        "inventory; never blocks a run or changes a model."
    )
    _mc1, _mc2 = st.columns(2)
    _mc1.metric("Models monitored", _mr_n_models)
    _mc2.metric("High-drift models", _mr_n_high)
    _mr_entries = _mr_report.get("entries") or []
    if _mr_entries:
        # Preserve JSON order — the engine sorts high-drift-first.
        st.dataframe(
            pd.DataFrame(
                _mr_entries,
                columns=[
                    "model_key",
                    "kind",
                    "tier",
                    "owner",
                    "current_alerts",
                    "prior_alerts",
                    "drift",
                    "drift_ratio",
                    "cadence_months",
                ],
            ),
            hide_index=True,
            use_container_width=True,
        )

st.markdown("---")

spec = st.session_state.spec
result = st.session_state.result

# Find python_ref rules — these are the ML scorers the page monitors.
# Restrict to status=="active": the engine itself skips non-active rules
# (`engine/runner.py:938`) so a deprecated scorer would always emit zero
# alerts in the current run, which the drift classifier would then
# misread as a downward outlier vs. its historical baseline. Mirrors
# the engine's own filter so drift only fires on scorers that actually
# ran. (Codex P2.)
ml_rules = [r for r in spec.rules if r.logic.type == "python_ref" and r.status == "active"]

# Load recent stored runs from the persistence layer. `list_runs()` is
# the canonical enumerate-runs idiom (Run History + Comparative
# Analytics use it). Defensive: when the API isn't reachable (no
# DATABASE_URL on a dashboard-only local launch, Cosmos misconfig,
# etc.) we fall back to current-session-only.
#
# Scope stored runs to the CURRENT spec_path so drift baselines aren't
# polluted by runs that came from a different spec / different ruleset.
# A scorer might not exist on an older spec — without this filter a
# brand-new scorer would have an all-zero prior baseline drawn from
# runs that pre-date it, and its first real-run count would always
# flag HIGH DRIFT. spec_path is the cheapest comparable key (already
# returned by `list_runs()`); a strict spec_content_hash filter would
# need a per-run `get_run()` lookup that's not worth the round trip.
# Codex P1.
# Multi-tenant safety: same posture as Experiment Tracking (PR-E4).
# Without `tenant_id` scoping, Bank A's drift baseline could evict
# (or be polluted by) Bank B's runs — `list_runs()` returns the 50 most
# recent across tenants. Codex pass 2 on PR-413.
_active_tenant = st.session_state.get("active_tenant")
_active_tenant_id = _active_tenant.id if _active_tenant is not None else None

_persistence_error: str | None = None
try:
    from aml_framework.api.db import get_run_alerts as _get_run_alerts_fn
    from aml_framework.api.db import init_db, list_runs

    init_db()
    # Pull a larger window so cross-spec runs in the tenant's history
    # don't crowd the current spec out of the default cap of 50. The
    # spec-suffix filter below narrows back to this spec. Codex pass
    # 13 P2 on PR-413.
    stored_runs = list_runs(tenant_id=_active_tenant_id, limit=500)

    def get_run_alerts(run_id: str):
        return _get_run_alerts_fn(run_id, tenant_id=_active_tenant_id)
except Exception as _exc:
    # Two distinct failure modes: persistence is not configured at all
    # (sqlite default, no rows yet) vs. configured backend is
    # misconfigured / unreachable (Postgres DSN typo, Cosmos endpoint
    # down, network blip). Codex passes 9+10 P2 on PR-413: surface
    # the second case explicitly so operators don't confuse an outage
    # with "no stored history yet". Both Postgres (`DATABASE_URL`)
    # and Cosmos (`COSMOS_ENDPOINT`) backends are supported by the
    # API layer — gate on either being set.
    stored_runs = []
    get_run_alerts = None  # type: ignore[assignment]
    if os.environ.get("DATABASE_URL") or os.environ.get("COSMOS_ENDPOINT"):
        _persistence_error = f"{type(_exc).__name__}: {_exc}"

if _persistence_error:
    st.error(
        "⚠️  Drift-history backend is unavailable — falling back to "
        "current-session only. Stored baselines and historical drift "
        "ratios will appear empty until persistence is restored.\n\n"
        f"`{_persistence_error}`"
    )


def _spec_key(p: str) -> str:
    """Normalize a spec_path for cross-source equality.

    The dashboard launches with an absolute path
    (`/.../aml_open_framework/examples/foo/aml.yaml`) but API-persisted
    runs store the request's relative `spec_path`
    (`examples/foo/aml.yaml`). Both share the SAME suffix relative to
    the repo root, so a tail-match comparison works for arbitrary
    layouts — `examples/<dir>/aml.yaml`, `specs/foo.yaml`, anywhere.

    Codex passes 3+5 on PR-413: the previous fixed last-3-segments
    rule was right for the canonical `examples/` shape but dropped
    runs whose spec lives at a different depth (e.g. top-level
    `specs/foo.yaml`).

    Codex pass 14 on PR-413: API callers may post a spec path with a
    leading `./` (accepted by `_safe_spec_path` and stored verbatim).
    Strip any leading `./` segments so they normalize to the same
    suffix as an absolute path.
    """
    norm = (p or "").replace("\\", "/").lstrip("/")
    while norm.startswith("./"):
        norm = norm[2:]
    return norm


def _specs_match(a: str, b: str) -> bool:
    """True when two spec_path strings refer to the same file.

    Either one may be absolute or relative; suffix-equal under
    normalized slashes counts as a match. Symmetric: `endswith` either
    direction so absolute-vs-relative and absolute-vs-absolute both
    work.

    Codex pass 9 P2: refuse to match when one side is a bare basename
    (`aml.yaml`) — that would collide with every spec sharing the
    filename. Require the SHORT side to contain at least one path
    separator so the suffix carries actual directory context.
    """
    a_norm = _spec_key(a)
    b_norm = _spec_key(b)
    if not a_norm or not b_norm:
        return False
    if a_norm == b_norm:
        return True
    # The shorter side must carry directory context — a bare filename
    # would suffix-match unrelated specs sharing the same basename.
    short = a_norm if len(a_norm) <= len(b_norm) else b_norm
    if "/" not in short:
        return False
    return a_norm.endswith("/" + b_norm) or b_norm.endswith("/" + a_norm)


_current_spec_path_raw = str(st.session_state.spec_path)
_scoped_runs = [
    r for r in stored_runs if _specs_match(str(r.get("spec_path", "")), _current_spec_path_raw)
]

# Cap at last 10 runs to keep the page snappy. `list_runs()` returns
# DESC by created_at; reverse for chronological X-axis on the line chart.
RECENT_RUN_CAP = 10
recent_runs = list(reversed(_scoped_runs[:RECENT_RUN_CAP]))


def _no_data_path(reason: str) -> None:
    """Helper — render an empty-state and exit cleanly.

    Codex pattern: `page_footer()` BEFORE `st.stop()` so the bottom-of-
    page affordance renders on the early-return path (otherwise
    `test_st_stop_is_preceded_by_page_footer` fails).
    """
    empty_state(
        reason,
        icon="📉",
        detail=(
            "Drift monitoring needs either a python_ref scorer in the spec "
            "AND ≥1 persisted run, or the current session must include "
            "a python_ref scorer. Run a few jobs (`aml run` or `POST "
            "/runs`) — each persisted execution feeds this surface."
        ),
    )
    page_footer()
    st.stop()


if not ml_rules:
    _no_data_path("No python_ref scorers in this spec.")

if not recent_runs and not result.alerts:
    _no_data_path("No persisted runs and no current-session alerts available.")

# -----------------------------------------------------------------------
# Per-scorer per-run summary stats. Read the alert list for each
# (run_id, rule_id) pair from the persistence layer; the current
# session run is appended as the rightmost point so the latest signal
# is always visible (Run History uses the same "current session is the
# anchor" idiom).
#
# Stats kept intentionally minimal — count + mean of any numeric score
# field if present. Tolerant of missing score fields: a scorer that
# only emits categorical evidence (no `score` / `risk_score` /
# `confidence` field) still gets a count-only signal. Don't crash on
# empty alert lists either — a scorer that fired zero alerts in a run
# is a legitimate signal, not a bug.
# -----------------------------------------------------------------------

_SCORE_FIELDS = ("score", "risk_score", "confidence")


def _alert_score(alert: dict) -> float | None:
    """Pick the first present numeric score field on an alert payload,
    or None if no recognisable score exists. Be tolerant of dict-shaped
    values (the python_ref scorer occasionally wraps numerics in
    `{"value": X, "unit": ...}` — see `_scalar_amount` in
    13_Model_Performance.py for the same defensive pattern). Returns
    None for non-numeric values so the caller can skip them rather
    than poison the mean."""
    for k in _SCORE_FIELDS:
        if k not in alert:
            continue
        v = alert[k]
        if isinstance(v, dict):
            for nested in ("value", "score"):
                if nested in v:
                    try:
                        return float(v[nested])
                    except (TypeError, ValueError):
                        return None
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _summarise(alerts: list[dict]) -> tuple[int, float | None]:
    """Return (alert_count, mean_score_or_None). Empty list → (0, None)."""
    count = len(alerts)
    if not alerts:
        return 0, None
    scores = [s for s in (_alert_score(a) for a in alerts) if s is not None]
    if not scores:
        return count, None
    return count, sum(scores) / len(scores)


# Build per-rule timeline: list of (run_label, count, mean_score)
# rows, ordered chronologically. Each row's mean_score may be None;
# the caller must guard before charting.
per_rule_timeline: dict[str, list[dict]] = {r.id: [] for r in ml_rules}

# Stored-run history (oldest → newest among the last RECENT_RUN_CAP).
# Per-run we ONLY append a timeline point for rules that the stored
# run actually produced a row for. A missing `rule_id` key means the
# scorer didn't exist on the spec used by that run (rules added since
# then) — treating that as "0 alerts" would draw a false baseline of
# zero priors and flag the scorer HIGH DRIFT on its first real run.
# A genuine zero-alert run still persists a row (the engine writes an
# empty list to `run_alerts` when the rule ran but matched nothing —
# `engine/runner.py` populates `result.alerts[rule.id] = []` and the
# API store_run() persists every key in that dict). So presence in
# `by_rule` is the right "did this rule run" signal. Codex P1.
_lookup_failures: list[str] = []
if get_run_alerts is not None:
    for run in recent_runs:
        run_id = run.get("run_id", "")
        try:
            run_alert_rows = get_run_alerts(run_id)
        except Exception as _alert_exc:
            # Track the failure so it's surfaced to the operator
            # instead of silently degrading the baseline. Skip THIS
            # run entirely — don't include it in any rule's timeline,
            # so `runs_analyzed` reflects what actually contributed
            # data. Codex pass 7 on PR-413.
            _lookup_failures.append(f"{run_id[:12]}: {type(_alert_exc).__name__}")
            continue
        # `get_run_alerts` returns [{rule_id, alerts}, ...]; index by rule.
        by_rule: dict[str, list[dict]] = {}
        for row in run_alert_rows:
            by_rule[row["rule_id"]] = row.get("alerts") or []
        # Compact run label for the X-axis — first 8 chars of run_id is
        # enough to distinguish runs without crowding the axis.
        label = (run_id[:8] + "…") if len(run_id) > 8 else (run_id or "?")
        for rule in ml_rules:
            if rule.id not in by_rule:
                # Rule wasn't on the spec that produced this run — skip
                # rather than fabricate a zero prior. See block comment
                # above.
                continue
            count, mean_score = _summarise(by_rule[rule.id])
            per_rule_timeline[rule.id].append(
                {
                    "run": label,
                    "run_id": run_id,
                    "count": count,
                    "mean_score": mean_score,
                }
            )

# Current session run as the rightmost anchor — same idiom as Run
# History. result.alerts is the in-memory dict {rule_id: [alert,...]}.
for rule in ml_rules:
    count, mean_score = _summarise(result.alerts.get(rule.id, []) or [])
    per_rule_timeline[rule.id].append(
        {
            "run": "current",
            "run_id": "current_session",
            "count": count,
            "mean_score": mean_score,
        }
    )


# -----------------------------------------------------------------------
# Drift flag — last-run alert count vs median of priors. >2× OR <0.5×
# the prior median is flagged "high drift". Skips scorers with <2
# total data points (need at least 1 prior + 1 current to compare).
#
# Limit of approach (documented inline so a reviewer doesn't think
# we missed it): this is a coarse alert-volume drift signal, NOT a
# statistical input-distribution drift (KS / PSI / Wasserstein). The
# alert payload doesn't carry the model's full input feature vector
# today; richer distribution-level drift ships with the future ML
# scoring epic that will persist feature snapshots per alert.
# -----------------------------------------------------------------------

DRIFT_HIGH_MULTIPLIER = 2.0
DRIFT_LOW_MULTIPLIER = 0.5


def _drift_classify(timeline: list[dict]) -> tuple[str, float | None, float | None]:
    """Return (status, last_count, prior_median).

    status ∈ {"high", "normal", "insufficient_data"}. `prior_median`
    is None when status == "insufficient_data".
    """
    if len(timeline) < 2:
        return "insufficient_data", None, None
    last = timeline[-1]["count"]
    priors = [t["count"] for t in timeline[:-1]]
    # `statistics.median` raises on empty; the `< 2` guard above
    # already excludes that path.
    prior_med = float(median(priors))
    if prior_med == 0:
        # If the scorer was silent on all prior runs, treat any fire
        # in the latest run as drift (>0 from 0). Avoids a divide-by-
        # zero while still surfacing the new signal.
        return ("high" if last > 0 else "normal", float(last), prior_med)
    ratio = last / prior_med
    if ratio >= DRIFT_HIGH_MULTIPLIER or ratio <= DRIFT_LOW_MULTIPLIER:
        return "high", float(last), prior_med
    return "normal", float(last), prior_med


drift_rows = []
for rule in ml_rules:
    status, last_count, prior_med = _drift_classify(per_rule_timeline[rule.id])
    drift_rows.append(
        {
            "rule_id": rule.id,
            "model_id": rule.logic.model_id,
            "model_version": rule.logic.model_version,
            "status": status,
            "last_count": last_count,
            "prior_median": prior_med,
        }
    )

high_drift = [r for r in drift_rows if r["status"] == "high"]

# -----------------------------------------------------------------------
# Roll-up KPIs
# -----------------------------------------------------------------------
# runs_analyzed counts what actually contributed — recent_runs already
# excludes runs whose alert lookup failed (see `_lookup_failures` above).
# +1 for the current in-memory session. Codex pass 7 on PR-413.
runs_analyzed = len(recent_runs) - len(_lookup_failures) + 1
c1, c2, c3 = st.columns(3)
with c1:
    kpi_card("python_ref scorers", len(ml_rules), "#2563eb")
with c2:
    # Red when any scorer is flagged — a meaningful at-a-glance signal.
    kpi_card("High-drift scorers", len(high_drift), "#dc2626" if high_drift else "#16a34a")
with c3:
    kpi_card("Runs analyzed", runs_analyzed, "#7c3aed")

if _lookup_failures:
    st.warning(
        f"⚠️  {len(_lookup_failures)} stored run(s) failed alert lookup and "
        "were excluded from the drift baseline. Showing details below; "
        "the drift status reflects only runs whose data could be read."
    )
    with st.expander(f"Show {len(_lookup_failures)} excluded run(s)", expanded=False):
        for failure in _lookup_failures:
            st.caption(f"• {failure}")

st.markdown("<br>", unsafe_allow_html=True)

# -----------------------------------------------------------------------
# High-drift surface (top of page when present) — pulls scorers
# requiring attention out of the per-rule grid below so the analyst
# can act without scrolling.
# -----------------------------------------------------------------------
if high_drift:
    st.markdown("### High-drift scorers")
    st.caption(
        f"These {len(high_drift)} scorer(s) have a last-run alert count "
        f"≥{DRIFT_HIGH_MULTIPLIER:g}× or ≤{DRIFT_LOW_MULTIPLIER:g}× the median "
        "of prior runs. Open Tuning Lab to investigate the threshold / "
        "feature-distribution context."
    )
    high_df = pd.DataFrame(
        [
            {
                "Rule": r["rule_id"],
                "Model": f"{r['model_id']} v{r['model_version']}",
                "Last count": int(r["last_count"]) if r["last_count"] is not None else 0,
                "Prior median": (
                    round(r["prior_median"], 2) if r["prior_median"] is not None else 0.0
                ),
            }
            for r in high_drift
        ]
    )
    data_grid(
        high_df,
        key="drift_high_drift_table",
        pinned_left=["Rule"] if "Rule" in high_df.columns else None,
        auto_height=True,
    )
    link_to_page(
        "pages/23_Tuning_Lab.py",
        "→ Open Tuning Lab to investigate threshold / feature drift",
    )
    st.markdown("<br>", unsafe_allow_html=True)

# -----------------------------------------------------------------------
# Per-scorer alert-count timeline. One small chart per python_ref
# rule. Pandas-NaN-safe: `mean_score` may be None for runs where the
# scorer didn't emit a score (or emitted no alerts) — the chart only
# uses `count`, so the NaN cells don't affect rendering.
# -----------------------------------------------------------------------
st.markdown("### Per-scorer alert volume over recent runs")

if runs_analyzed < 2:
    # Only one data point — line chart is meaningless. Surface as info
    # rather than render an empty axis (Codex P2 pattern from Run History).
    st.info(
        "Only one run has been analysed so far — drift trends need at least "
        "2 runs. Persist additional runs (via `aml run` or the API) to "
        "populate the timeline."
    )
else:
    for rule in ml_rules:
        timeline = per_rule_timeline[rule.id]
        timeline_df = pd.DataFrame(timeline)
        status = next(r["status"] for r in drift_rows if r["rule_id"] == rule.id)
        # Status pill mirrors Tuning Lab's vocabulary so the cross-link
        # reads coherently.
        pill_color = {
            "high": "#dc2626",
            "normal": "#16a34a",
            "insufficient_data": "#9ca3af",
        }[status]
        pill_label = {
            "high": "HIGH DRIFT",
            "normal": "STABLE",
            "insufficient_data": "INSUFFICIENT DATA",
        }[status]
        st.markdown(
            f"#### {rule.id} — {rule.logic.model_id} v{rule.logic.model_version} "
            f"<span style='font-family:ui-monospace,monospace;font-size:0.72rem;"
            f"padding:2px 8px;border-radius:999px;background:{pill_color}22;"
            f"color:{pill_color};border:1px solid {pill_color}55;'>"
            f"{pill_label}</span>",
            unsafe_allow_html=True,
        )

        # If literally every value is zero, surface that and skip the
        # chart — an all-zero line reads as a chart bug, not as "scorer
        # has been silent." Empty-list scorers (no alerts in any run)
        # would hit this path.
        if timeline_df["count"].sum() == 0:
            st.caption("This scorer fired no alerts in any analysed run.")
            continue

        line_chart(
            timeline_df,
            x="run",
            y="count",
            title=f"{rule.id} — alert count per run",
            height=240,
            key=f"drift_timeline_{rule.id}",
        )

st.markdown("<br>", unsafe_allow_html=True)

# -----------------------------------------------------------------------
# Deferred-work note — honest about what this signal does NOT cover so
# reviewers don't read "Drift Monitor" as "ML monitoring is solved here."
# -----------------------------------------------------------------------
with st.expander("What this signal does — and does NOT — cover"):
    st.markdown(
        "**Today:** alert-volume drift only. A scorer's last-run count is "
        f"compared against the median of its prior recent runs (last "
        f"{RECENT_RUN_CAP}). >{DRIFT_HIGH_MULTIPLIER:g}× or "
        f"<{DRIFT_LOW_MULTIPLIER:g}× ⇒ HIGH DRIFT.\n\n"
        "**Deferred (future ML scoring epic):** statistical "
        "distribution-level drift (Kolmogorov-Smirnov, Population "
        "Stability Index, Wasserstein) on the scorer's input feature "
        "vector. That work requires capturing the feature snapshot per "
        "alert; the current `python_ref` alert payload doesn't carry "
        "it. When that lands, this page gains a per-scorer KS / PSI "
        "panel alongside the existing count-based signal."
    )

# -----------------------------------------------------------------------
# See-also cross-links — pillar-7 navigation hub. Drift Monitor sits
# between Model Performance (per-scorer analytics this-run) and Tuning
# Lab (threshold what-if). Run History anchors the timeline.
# -----------------------------------------------------------------------
see_also_footer(
    [
        "[Model Performance — per-scorer this-run analytics](./Model_Performance)",
        "[Tuning Lab — threshold what-if analysis](./Tuning_Lab)",
        "[Run History — full run-by-run manifest browser](./Run_History)",
    ]
)

page_footer()
