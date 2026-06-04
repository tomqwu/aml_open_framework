"""Pure helpers for the Triage Queue dashboard page.

Streamlit-free on purpose (CLAUDE.md lazy-import rule: dashboard helper
modules must not import `streamlit` at module level so they unit-test under
the `.[dev]`-only CI). All sort/format logic for the advisory N1
`priority_score` lives here; `pages/52_Triage_Queue.py` is a thin renderer.

ADVISORY: this only re-orders a view of alerts by SAR-likelihood — it never
changes an alert's disposition, queue, or open/close state.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

PRIORITY_COL = "priority_score"
EXPLANATION_COL = "priority_explanation"
SUPPRESSION_COL = "suppression"
SUPPRESSED_COL = "suppressed"
SUPPRESSION_SEGMENT_COL = "suppression_segment"

# Columns to surface in the queue table, in display order, when present.
DISPLAY_COLS = [
    PRIORITY_COL,
    "rule_id",
    "customer_id",
    "severity",
    "amount",
    "sum_amount",
    "count",
    SUPPRESSED_COL,
    SUPPRESSION_SEGMENT_COL,
]


def has_priority(df: pd.DataFrame) -> bool:
    """True when the alert frame carries at least one non-null priority_score."""
    if df is None or df.empty or PRIORITY_COL not in df.columns:
        return False
    return bool(df[PRIORITY_COL].notna().any())


def triage_view(df: pd.DataFrame) -> pd.DataFrame:
    """Scored alerts sorted by priority_score desc, with a deterministic
    (rule_id, customer_id) tiebreak. Rows without a score are dropped so the
    queue only shows what the model actually ranked."""
    scored = df[df[PRIORITY_COL].notna()].copy()
    tiebreak = [c for c in ("rule_id", "customer_id") if c in scored.columns]
    scored = scored.sort_values(
        by=[PRIORITY_COL, *tiebreak],
        ascending=[False, *([True] * len(tiebreak))],
        kind="mergesort",  # stable
    ).reset_index(drop=True)
    return scored


def has_suppression(df: pd.DataFrame) -> bool:
    """True when the alert frame carries at least one alert that went through
    the advisory suppression pass (a `suppression` dict with a non-null
    `applied` flag). Off-by-default: returns False when the column is absent."""
    if df is None or df.empty or SUPPRESSION_COL not in df.columns:
        return False
    return bool(
        df[SUPPRESSION_COL]
        .apply(lambda s: isinstance(s, dict) and s.get("applied") is not None)
        .any()
    )


def with_suppression_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of `df` with flattened advisory-suppression columns
    (`suppressed` bool, `suppression_segment` str) derived from the per-alert
    `suppression` dict. No-op copy when the column is absent. ADVISORY — these
    columns only annotate the view; nothing is removed or re-disposed."""
    out = df.copy()
    if SUPPRESSION_COL not in out.columns:
        return out
    out[SUPPRESSED_COL] = out[SUPPRESSION_COL].apply(
        lambda s: bool(s.get("applied")) if isinstance(s, dict) else False
    )
    out[SUPPRESSION_SEGMENT_COL] = out[SUPPRESSION_COL].apply(
        lambda s: s.get("segment_id") if isinstance(s, dict) else None
    )
    return out


def explanation_rows(explanation: Any) -> list[dict[str, Any]]:
    """Normalise a priority_explanation into display rows: the `bias` baseline
    first, then features ordered by absolute contribution (the biggest drivers
    on top). Returns [] for missing/empty input."""
    if not isinstance(explanation, list) or not explanation:
        return []
    bias = [e for e in explanation if e.get("feature") == "bias"]
    feats = [e for e in explanation if e.get("feature") != "bias"]
    feats.sort(key=lambda e: abs(float(e.get("contribution", 0.0))), reverse=True)
    out: list[dict[str, Any]] = []
    for e in [*bias, *feats]:
        out.append(
            {
                "feature": e.get("feature"),
                "value": round(float(e.get("value", 0.0)), 4),
                "contribution": round(float(e.get("contribution", 0.0)), 4),
            }
        )
    return out


def alert_label(row: Any) -> str:
    """Selectbox label for one scored alert: `<customer> · <rule> · <score>`."""
    cid = row.get("customer_id", "—") if hasattr(row, "get") else row["customer_id"]
    rid = row.get("rule_id", "—") if hasattr(row, "get") else row["rule_id"]
    score = float(row["priority_score"])
    return f"{cid} · {rid} · {score:.2f}"
