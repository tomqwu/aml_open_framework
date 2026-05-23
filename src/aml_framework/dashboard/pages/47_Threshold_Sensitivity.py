"""Threshold Sensitivity — per-rule sweep curves at a glance.

PR-E2 (closes #379). Read-only synthesis page that renders, for every
`aggregation_window` rule in the spec with a numeric `having`
threshold, a small sensitivity curve showing how the alert count moves
as the threshold is varied at ``{0.5, 0.75, 1.0, 1.25, 1.5, 2.0}`` × the
spec value. The Pillar 7 ("DS as governed augmentation") companion to
the FP Analysis page (PR-E1) and the interactive Tuning Lab
(page 23) / Rule Tuning (page 16) surfaces.

Where this sits in the tuning stack:

- **Rule Tuning** (page 16): interactive sliders for ONE rule;
  per-threshold what-if + a single sensitivity chart for the picked
  rule. Pre-PR-E2 the only "see the curve" surface.
- **Tuning Lab** (page 23): full sweep + precision/recall scoring +
  spec-patch download for ONE rule at a time. The deep tuning surface.
- **Threshold Sensitivity** (this page, PR-E2): the *roll-up* — every
  tunable rule's curve at a glance, with the spec value pinned and
  high-sensitivity rules flagged. The "which rules should I look at
  first?" entry point that links into Tuning Lab + Rule Tuning.

Compute model: rules are detected by ``logic.type ==
"aggregation_window"`` + a numeric ``having[metric][op]`` constraint
(``gte`` / ``gt`` / ``lte`` / ``lt``). For each tunable rule the page
builds a modified Rule with the swapped threshold and runs
``compile_rule_sql`` against a single shared DuckDB warehouse
(``_build_warehouse`` from ``engine/runner.py``) — the same pattern
the existing Rule Tuning page uses. No spec write, no audit-ledger
event (those are Tuning Lab's job — this is a pure preview).
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from aml_framework.dashboard.components import (
    kpi_card,
    line_chart,
    link_to_page,
    page_footer,
    page_header,
    section_explainer,
)
from aml_framework.dashboard.state import ensure_initialized
from aml_framework.engine.runner import _build_warehouse, _harden_duckdb
from aml_framework.generators.sql import compile_rule_sql
from aml_framework.spec.models import AggregationWindowLogic, Rule

ensure_initialized()

page_header(
    "Threshold Sensitivity",
    "Per-rule sweep curves at a glance — how alert volume moves as each "
    "tunable rule's threshold shifts around the spec value.",
)

section_explainer(
    page="Threshold Sensitivity",
    section_id="threshold_sensitivity.page",
    section_title="Threshold Sensitivity",
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

spec = st.session_state.spec
data = st.session_state.data
as_of = st.session_state.as_of


# ---------------------------------------------------------------------------
# Discover tunable rules.
#
# A rule is "tunable for this surface" when its logic is
# `aggregation_window` AND its `having` dict carries at least one
# numeric op constraint (`gte`/`gt`/`lte`/`lt` with an int/float value).
# `bool` is explicitly excluded — Python treats `True/False` as int
# subclasses and a `bool` having value almost certainly means the spec
# author intended an equality flag, not a sweepable threshold.
# ---------------------------------------------------------------------------
_SWEEP_OPS = ("gte", "gt", "lte", "lt")
# Multipliers around the spec value. Six points — symmetric across the
# spec value so the curve reads as "what does ±50% / ±25% buy me?"
_MULTIPLIERS: tuple[float, ...] = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
# High-sensitivity threshold: when ±25% of the spec value moves the
# alert count by ≥50% in either direction, flag the rule. The chosen
# multipliers map cleanly to the spec value's neighborhood; the 50%
# delta is the empirical "the curve is steep here" line used by the
# Tuning Lab + Rule Tuning sister pages.
_HIGH_SENSITIVITY_DELTA = 0.50


def _first_numeric_threshold(having: dict) -> tuple[str, str, int | float] | None:
    """Return ``(metric, op, value)`` for the first sweepable threshold.

    Mirrors the Rule Tuning page's "main_metric" picker: scan the
    ``having`` dict for the first metric whose op is one of
    ``gte/gt/lte/lt`` and whose value is a finite, non-bool number.
    Returns ``None`` when no sweepable threshold is present (e.g. the
    rule's having clause is purely categorical, or the value is bool).

    The returned value keeps the spec's numeric type — `float(val)`
    would demote integer count thresholds and lose the type signal the
    sweep loop uses to decide rounding policy. Domain-specific
    rounding (integer-coerce for `count`-shaped metrics, leave amount
    /ratio thresholds alone) is applied in the sweep loop via
    `_is_count_metric`. Codex pass 2 + pass 3 caught the divergence
    when this picker stripped the type and when the rounding was
    applied uniformly.
    """
    for metric, cond in having.items():
        if not isinstance(cond, dict):
            continue
        for op, val in cond.items():
            if op not in _SWEEP_OPS:
                continue
            # `bool` is an int subclass; exclude it explicitly.
            if isinstance(val, bool):
                continue
            if not isinstance(val, (int, float)):
                continue
            # NaN / inf would produce nonsensical multiplied thresholds;
            # `pd.isna` covers NaN and `float('inf')` checks separately.
            if pd.isna(val):
                continue
            if val in (float("inf"), float("-inf")):
                continue
            # Preserve int vs float — see docstring. `float` stays
            # `float`, `int` stays `int` (not promoted to float).
            return metric, op, val
    return None


# Build the list once so the KPI roll-up and the per-rule sweep loop
# read from the same source.
_tunable: list[tuple[Rule, str, str, int | float]] = []
for rule in spec.rules:
    logic = rule.logic
    if not isinstance(logic, AggregationWindowLogic):
        continue
    picked = _first_numeric_threshold(logic.having)
    if picked is None:
        continue
    metric, op, val = picked
    _tunable.append((rule, metric, op, val))


if not _tunable:
    # Empty-state — every other dashboard page that may hit a no-data
    # branch uses this exact `info + page_footer + st.stop` shape so
    # the bottom-of-page affordance still renders on the early-return.
    # See `tests/test_dashboard_page_footer.py::test_st_stop_is_preceded_by_page_footer`.
    st.info(
        "No `aggregation_window` rules with a numeric `having` threshold "
        "in this spec — nothing to sweep. Add a rule like "
        "`logic: { type: aggregation_window, having: { count: { gte: 3 } } }` "
        "and reload to see its sensitivity curve here."
    )
    page_footer()
    st.stop()


# ---------------------------------------------------------------------------
# Run every sweep against a single shared DuckDB warehouse.
#
# Building the warehouse is O(rows) per call and the page may render
# six SQL runs × N tunable rules; share the connection across the loop
# rather than rebuilding the tables once per rule (the existing Rule
# Tuning page builds twice for the same reason — once would be enough).
# ---------------------------------------------------------------------------
con = duckdb.connect(":memory:")
# Match `run_spec()`: lock extensions + external access OFF before we
# interpolate spec-derived filter/group expressions into SQL. Codex
# pass 9 P2 on PR-413.
_harden_duckdb(con)
_build_warehouse(con, spec, data)


def _alerts_at(rule: Rule, logic: AggregationWindowLogic, having: dict) -> int:
    """Return the alert-row count for ``rule`` with ``having`` swapped in.

    Uses ``compile_rule_sql`` against the shared warehouse — same path
    the engine takes — so the sweep counts are apples-to-apples with
    the live run's totals. On SQL failure (e.g. an oddly-shaped having
    clause the engine doesn't accept), return -1 so the caller can
    drop the point without poisoning the chart with a misleading
    zero.
    """
    swapped = AggregationWindowLogic(
        type="aggregation_window",
        source=logic.source,
        filter=logic.filter,
        group_by=list(logic.group_by),
        window=logic.window,
        having=having,
    )
    swapped_rule = Rule(
        id=rule.id,
        name=rule.name,
        severity=rule.severity,
        status=rule.status,
        regulation_refs=list(rule.regulation_refs),
        logic=swapped,
        escalate_to=rule.escalate_to,
        evidence=list(rule.evidence),
        tags=list(rule.tags),
    )
    try:
        sql = compile_rule_sql(swapped_rule, as_of=as_of, source_table=logic.source)
        return len(con.execute(sql).fetchall())
    except Exception:
        return -1


# ---------------------------------------------------------------------------
# Per-rule sweep — collected first so the KPI roll-up at the top can
# count high-sensitivity rules without re-running every sweep twice.
# ---------------------------------------------------------------------------
_results: list[dict] = []


def _is_count_metric(name: str) -> bool:
    """True for count-style having metrics (integer-only domain).

    Count metrics carry an integer domain in DuckDB — `COUNT(*) >= 2.25`
    rounds up to `>= 3` and the 0.75× sweep point would collapse onto
    the baseline. Only `count`-shaped metrics get integer coercion;
    amount / average / ratio metrics keep their full numeric type so
    the 1.0× baseline matches the spec value exactly and the
    multiplied points stay distinct from one another.

    The match is conservative — exactly `count` or a `*_count` suffix
    so a future `count_distinct_customer` style metric also classifies
    correctly without picking up `discount` or similar.
    """
    return name == "count" or name.endswith("_count")


for rule, metric, op, spec_val in _tunable:
    logic = rule.logic
    # Sweep math. Two cases — see `_is_count_metric` docstring above:
    #   1. count-style metrics: integer domain; round multiplied values
    #      to nearest integer (1.0× == spec_val exactly).
    #   2. Everything else (sum_amount / avg_amount / ratios / scores):
    #      keep the full numeric value the multiplier produces — no
    #      rounding, no clamping. The 1.0× baseline is then exactly the
    #      spec value (engine SQL == rule's actual threshold) and the
    #      ±25% points are exactly `spec_val * 0.75` / `spec_val * 1.25`.
    #
    # No `max(1, ...)` clamp — a spec is free to author `count: {gt: 0}`
    # and the sweep should respect that at 0.5× (= 0), not silently
    # clamp to 1. The chart will simply show alerts at that threshold.
    metric_is_count = _is_count_metric(metric)

    def _swept(
        mult: float, _is_count: bool = metric_is_count, _v: int | float = spec_val
    ) -> int | float:
        raw = _v * mult
        if _is_count:
            # Integer domain — `round` nudges floating-point drift
            # (e.g. 3 * 0.75 = 2.25 → 2) while keeping the 1.0× row
            # exactly == spec_val.
            return int(round(raw))
        # Amount / ratio / score domain — pass the value through
        # unrounded so the 1.0× baseline equals the spec value
        # exactly for both `sum_amount: {gte: 999}` (int) and
        # `avg_amount: {gte: 100.125}` (float). Display formatting
        # is handled at chart-render time, separately from the SQL
        # value (codex pass 3).
        return raw

    # `sweep_points` carries `(multiplier, swept_threshold_value, alert_count)`
    # — the swept value is recorded so the chart's x-axis renders the
    # actual numeric threshold (the value the operator would land in the
    # spec) rather than recomputing it later, which kept the engine SQL
    # and the chart label in sync after codex flagged the original
    # divergence (codex pass 1).
    sweep_points: list[tuple[float, float | int, int]] = []
    for mult in _MULTIPLIERS:
        swept_val = _swept(mult)
        # Rebuild the having dict with the swapped threshold; all other
        # constraints in `having` (e.g. `sum_amount` when we're sweeping
        # `count`) are preserved so the sweep isolates a single axis.
        swapped_having: dict = {}
        for m, c in logic.having.items():
            if m == metric and isinstance(c, dict):
                swapped_having[m] = {**c, op: swept_val}
            else:
                swapped_having[m] = c
        alerts = _alerts_at(rule, logic, swapped_having)
        if alerts >= 0:
            sweep_points.append((mult, swept_val, alerts))

    # Compute the baseline (spec-value) alert count so the sensitivity
    # flag has a denominator. Sweep at mult=1.0 is the baseline.
    baseline = next((a for m, _v, a in sweep_points if m == 1.0), None)

    # Mark a rule high-sensitivity when ±25% threshold change moves the
    # alert count by ≥_HIGH_SENSITIVITY_DELTA. Use `pd.isna` to keep
    # the truthiness check safe against any future NaN escape (codex
    # caught this exact pattern on PR-F3 pass 2 — DataFrame columns can
    # carry NaN, plain Python None / int from this function cannot, but
    # the explicit guard keeps the contract obvious to readers).
    #
    # Two paths to "high sensitivity":
    #   1. Non-zero baseline: classic ratio test — abs change at ±25%
    #      ÷ baseline ≥ 50%.
    #   2. Zero baseline that goes non-zero at ±25%: the operator
    #      cares MORE about this case (a small spec edit creates queue
    #      volume from nothing). Codex pass 2 caught the original guard
    #      classifying these rules as Stable.
    high_sensitivity = False
    if baseline is not None and not pd.isna(baseline):
        nearby = [a for m, _v, a in sweep_points if m in (0.75, 1.25)]
        if nearby:
            if baseline > 0:
                max_delta = max(abs(a - baseline) / baseline for a in nearby)
                high_sensitivity = max_delta >= _HIGH_SENSITIVITY_DELTA
            else:
                # baseline == 0 — any non-zero nearby count is a steep
                # transition out of the quiet zone, so flag it.
                high_sensitivity = any(a > 0 for a in nearby)

    _results.append(
        {
            "rule": rule,
            "metric": metric,
            "op": op,
            "spec_val": spec_val,
            "sweep_points": sweep_points,
            "baseline": baseline,
            "high_sensitivity": high_sensitivity,
        }
    )

con.close()


# ---------------------------------------------------------------------------
# KPI roll-up — total tunable rules + how many are high-sensitivity.
# ---------------------------------------------------------------------------
_high_count = sum(1 for r in _results if r["high_sensitivity"])
_low_count = len(_results) - _high_count

c1, c2, c3 = st.columns(3)
with c1:
    kpi_card("Tunable rules", len(_results), "#2563eb")
with c2:
    kpi_card("High-sensitivity rules", _high_count, "#dc2626")
with c3:
    kpi_card("Stable rules", _low_count, "#16a34a")

st.caption(
    "**High-sensitivity** rules show ≥50% alert-volume change at ±25% of "
    "the spec threshold — the curve is steep at the current operating "
    "point, so a small spec edit moves the queue load a lot. Stable rules "
    "are forgiving in the same neighbourhood."
)

st.markdown("---")

# ---------------------------------------------------------------------------
# Per-rule sensitivity curves.
#
# Each rule gets a small line chart with its 6 sweep points. A
# matching annotation row beneath the chart calls out the spec value +
# baseline alert count + sensitivity classification, so a reader can
# scan the page without hovering each line.
# ---------------------------------------------------------------------------
st.markdown("### Per-rule sensitivity curves")

for entry in _results:
    rule = entry["rule"]
    metric = entry["metric"]
    op = entry["op"]
    spec_val = entry["spec_val"]
    sweep_points = entry["sweep_points"]
    baseline = entry["baseline"]
    high_sensitivity = entry["high_sensitivity"]

    badge_color = "#dc2626" if high_sensitivity else "#16a34a"
    badge_text = "HIGH SENSITIVITY" if high_sensitivity else "STABLE"

    with st.container(border=True):
        # Eyebrow row — rule id + severity + sensitivity badge so the
        # operator can scan the page top-to-bottom and home in on the
        # red badges without reading each chart.
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:center;margin-bottom:6px;">'
            f'<span style="font-family:ui-monospace,monospace;font-size:0.78rem;'
            f'letter-spacing:0.06em;text-transform:uppercase;color:var(--dna-ink-dim);">'
            f"Rule · {rule.id} · {rule.severity}</span>"
            f'<span style="font-family:ui-monospace,monospace;font-size:0.78rem;'
            f"padding:2px 10px;border-radius:999px;"
            f'background:{badge_color}22;color:{badge_color};border:1px solid {badge_color}55;">'
            f"{badge_text}</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(f"#### {rule.name}")

        # One-line context strip — what's being swept + where the spec
        # currently sits + what we observed at the spec value. Render
        # the spec value with its native type so a float threshold (e.g.
        # `avg_amount: {gte: 100.50}`) reads as `100.50`, not `100`.
        baseline_str = "—" if baseline is None else f"{baseline} alerts"
        st.caption(
            f"Sweeping `{metric}` ({op}) — spec value `{spec_val}`, "
            f"baseline {baseline_str}. Window {rule.logic.window}, "
            f"source `{rule.logic.source}`."
        )

        if not sweep_points:
            st.warning(
                "Sweep produced no valid points for this rule — the "
                "engine rejected every swapped-threshold SQL. Open Tuning "
                "Lab for a detailed run."
            )
            continue

        # Build the chart frame. Plot the absolute threshold value on the
        # x-axis (the value that would land in the spec, not the
        # multiplier). Use the same swept value the SQL run used so the
        # chart and the engine never disagree on what's being shown.
        rows: list[dict] = []
        for mult, swept_val, alerts in sweep_points:
            rows.append(
                {
                    "threshold": swept_val,
                    "alerts": alerts,
                    "label": f"{mult:.2f}×",
                }
            )
        chart_df = pd.DataFrame(rows).sort_values("threshold").reset_index(drop=True)
        line_chart(
            chart_df,
            x="threshold",
            y="alerts",
            smooth=True,
            markers=True,
            title=f"Alert count vs. {metric}",
            height=260,
            key=f"threshold_sens_{rule.id}",
        )


st.markdown("---")

# ---------------------------------------------------------------------------
# Cross-links — the natural next destinations from this overview.
# Routed through `link_to_page` so persona-filtered targets degrade
# cleanly when hidden (same pattern as the North-Star Coverage page).
# ---------------------------------------------------------------------------
st.markdown("### See also")
link_to_page("pages/23_Tuning_Lab.py", "→ Tuning Lab (interactive sweep + scoring)")
link_to_page("pages/16_Rule_Tuning.py", "→ Rule Tuning (slider what-if)")
link_to_page("pages/5_Rule_Performance.py", "→ Rule Performance (per-rule alerts)")

page_footer()
