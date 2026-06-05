"""Anomaly Discovery — unsupervised z-score surface on per-customer features.

PR-E5 (closes #382). Pillar-7 work (DS as governed augmentation):
deterministic spec rules are the governed baseline; this page surfaces
candidates the rules *don't* catch by scoring each customer against the
population on simple per-customer features (count / sum / avg / unique
counterparties / cross-border ratio).

Deliberately a simple unsupervised baseline — vanilla z-score across the
population, anomaly score is the max absolute z across the available
features ("tallest peak"). No scikit-learn, no scipy, no model risk. The
goal is the *discovery surface*: high-anomaly customers NOT already in
``df_alerts`` are the candidates the spec doesn't catch — work for a
detection author to triage. Richer methods (Isolation Forest, LOF,
autoencoder) are deferred to a future ML model with its own model-risk
treatment.

Universally routed (every persona sees it) via TUNING_PAGES in
``audience.py`` — same idiom as the other Detection-&-Tuning discovery
surfaces. Sister pages: Rule Performance (per-rule view), Tuning Lab
(what-if thresholds), Customer 360 (drill-down).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from aml_framework.dashboard.components import (
    empty_state,
    link_to_page,
    page_footer,
    page_header,
    section_explainer,
)
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

page_header(
    "Anomaly Discovery",
    "Unsupervised z-score surface — customers whose feature shape stands "
    "apart from the population. Discovery candidates the spec's "
    "deterministic rules don't catch yet.",
)

# ---------------------------------------------------------------------------
# Pull cached state. `df_txns` is the substrate; `df_alerts` is the
# "already caught" set we contrast against (the discovery filter).
# ---------------------------------------------------------------------------
df_txns: pd.DataFrame = st.session_state.get("df_txns", pd.DataFrame())
df_alerts: pd.DataFrame = st.session_state.get("df_alerts", pd.DataFrame())
df_customers: pd.DataFrame = st.session_state.get("df_customers", pd.DataFrame())

section_explainer(
    page="Anomaly Discovery",
    section_id="anomaly_discovery.page",
    collapsed=True,
    section_title="Anomaly Discovery",
    data_summary={
        "n_txns": int(len(df_txns)),
        "n_customers": int(df_customers["customer_id"].nunique())
        if not df_customers.empty and "customer_id" in df_customers.columns
        else 0,
        "n_alerted_customers": int(df_alerts["customer_id"].nunique())
        if not df_alerts.empty and "customer_id" in df_alerts.columns
        else 0,
    },
)

# ---------------------------------------------------------------------------
# Empty-state guard. With no transactions there's nothing to score —
# render the affordance and bail per the bottom-page-clip contract
# (page_footer() BEFORE st.stop()).
# ---------------------------------------------------------------------------
if df_txns.empty or "customer_id" not in df_txns.columns:
    empty_state(
        "No transactions in this run — nothing to score.",
        icon="📭",
        detail=(
            "Anomaly discovery scores customers against the population "
            "on per-customer transaction features. With zero transactions "
            "the population is undefined."
        ),
        stop=True,
    )

# ---------------------------------------------------------------------------
# Per-customer feature engineering. We only build features for columns
# actually present in this run's substrate — synthetic + CSV ingestion
# carry slightly different column sets, and an optional column being
# absent should produce zero scores rather than NaN that propagates.
# ---------------------------------------------------------------------------
# Always-present features: count + sum + avg amount.
agg_spec: dict[str, tuple[str, str]] = {
    "count": ("amount", "count"),
    "sum_amount": ("amount", "sum"),
    "avg_amount": ("amount", "mean"),
}
# Optional: unique counterparties. The synthetic substrate exposes
# `counterparty_id` (per-payee linking column) and `counterparty_country`
# (ISO country). Prefer `counterparty_id` since it's the actual entity
# axis; fall back to `counterparty_country` if only that's wired.
counterparty_col: str | None = None
if "counterparty_id" in df_txns.columns:
    counterparty_col = "counterparty_id"
elif "counterparty_country" in df_txns.columns:
    counterparty_col = "counterparty_country"
if counterparty_col is not None:
    agg_spec["unique_counterparties"] = (counterparty_col, "nunique")

# Build the per-customer feature frame.
df_features = df_txns.groupby("customer_id").agg(**agg_spec).reset_index()

# Optional: cross-border ratio = fraction of txns whose
# `counterparty_country` != customer's home `country`. Requires both a
# txn-side country column AND a customer-side country column. Anything
# missing → ratio = 0 (no false signal).
has_txn_country = "counterparty_country" in df_txns.columns
has_cust_country = (
    not df_customers.empty
    and "country" in df_customers.columns
    and "customer_id" in df_customers.columns
)
if has_txn_country and has_cust_country:
    # Join the customer's home country onto each txn, then compute the
    # per-customer cross-border ratio. `pd.isna` guards so NaN home
    # countries (which can happen on partial CSV ingest) don't fabricate
    # cross-border hits.
    # Collapse duplicates before indexing. A customer feed with
    # repeated `customer_id` rows (data-quality issue) would produce a
    # non-unique index here, and `.map(home_country)` raises
    # `InvalidIndexError`. Keep the first non-null country per
    # customer instead — the cross-border feature is intentionally
    # tolerant of imperfect data, and we'd rather degrade quietly
    # than crash the page. Codex pass 12 P2 on PR-413.
    home_country = (
        df_customers[["customer_id", "country"]]
        .dropna(subset=["country"])
        .drop_duplicates(subset=["customer_id"], keep="first")
        .set_index("customer_id")["country"]
    )
    txn_home = df_txns["customer_id"].map(home_country)
    txn_cp = df_txns["counterparty_country"].astype(object)
    # A txn is "cross-border" only when both sides are known AND differ.
    is_cross = (
        (~txn_home.isna())
        & (~txn_cp.apply(pd.isna))
        & (txn_cp.astype(str).str.len() > 0)
        & (txn_home.astype(str) != txn_cp.astype(str))
    )
    cross_border_ratio = (
        pd.DataFrame({"customer_id": df_txns["customer_id"], "is_cross": is_cross.astype(float)})
        .groupby("customer_id")["is_cross"]
        .mean()
        .rename("cross_border_ratio")
    )
    df_features = df_features.merge(cross_border_ratio.reset_index(), on="customer_id", how="left")
    df_features["cross_border_ratio"] = df_features["cross_border_ratio"].fillna(0.0)
else:
    df_features["cross_border_ratio"] = 0.0


# ---------------------------------------------------------------------------
# Score each feature with a vanilla population z-score, then the
# anomaly score per customer is the max |z| across features (the
# "tallest peak"). Deliberately simple — no scikit-learn, no PCA, no
# weighting. Documented inline so a reviewer doesn't mistake this for
# the model-risk surface.
# ---------------------------------------------------------------------------
_FEATURE_COLS = [
    "count",
    "sum_amount",
    "avg_amount",
    "unique_counterparties",
    "cross_border_ratio",
]
# Restrict to features actually present (unique_counterparties is
# optional). Cast to float so std() on an integer column doesn't ever
# floor-divide. Order preserved so the displayed grid stays stable.
feature_cols = [c for c in _FEATURE_COLS if c in df_features.columns]

z_frame = pd.DataFrame(index=df_features.index)
for col in feature_cols:
    series = df_features[col].astype(float)
    # population mean + std (ddof=0). Replace 0 std with 1.0 to avoid
    # division-by-zero on degenerate features (e.g. every customer's
    # cross_border_ratio is 0 in a domestic-only data set).
    mu = series.mean()
    sigma = series.std(ddof=0)
    if not np.isfinite(sigma) or sigma == 0:
        z_frame[col] = 0.0
    else:
        z_frame[col] = (series - mu) / sigma

# Anomaly score = max absolute z across available features. NaN-safe
# in case a feature row landed NaN for any reason (it shouldn't, but
# pandas surprises are real).
df_features["anomaly_score"] = z_frame.abs().max(axis=1).fillna(0.0).astype(float)

# Discovery flag: HIGH anomaly AND NOT in df_alerts. The "no" rows are
# the discovery candidates — what the spec rules don't catch yet.
_ANOMALY_CUTOFF = 2.0
alerted_customers: set[str] = set()
if not df_alerts.empty and "customer_id" in df_alerts.columns:
    alerted_customers = set(df_alerts["customer_id"].dropna().astype(str).unique().tolist())

df_features["caught_by_rules"] = df_features["customer_id"].apply(
    lambda cid: "yes" if str(cid) in alerted_customers else "no"
)
df_features["discovery_candidate"] = (df_features["anomaly_score"] > _ANOMALY_CUTOFF) & (
    df_features["caught_by_rules"] == "no"
)

# ---------------------------------------------------------------------------
# Roll-up KPIs at the top — total customers scored, score-distribution
# histogram, count of discovery candidates.
# ---------------------------------------------------------------------------
st.markdown("### Discovery roll-up")

col_a, col_b, col_c = st.columns(3)
with col_a:
    st.metric(
        "Customers scored",
        len(df_features),
        help="Distinct customer_id values found in df_txns this run.",
    )
with col_b:
    st.metric(
        "Already caught by rules",
        int((df_features["caught_by_rules"] == "yes").sum()),
        help="Customers in df_features whose customer_id appears in df_alerts.",
    )
with col_c:
    st.metric(
        "Discovery candidates",
        int(df_features["discovery_candidate"].sum()),
        help=(
            f"High anomaly (|z| > {_ANOMALY_CUTOFF}) AND not already in "
            "df_alerts. These are the candidates the spec doesn't catch yet."
        ),
    )

st.caption(
    f"Anomaly score = max absolute population z-score across "
    f"{len(feature_cols)} per-customer feature(s): "
    f"`{'`, `'.join(feature_cols)}`. Discovery cutoff: "
    f"|z| > {_ANOMALY_CUTOFF}. Vanilla unsupervised baseline — Isolation "
    "Forest / LOF / autoencoder are deferred to a future ML model with "
    "its own model-risk lifecycle."
)

# Score-distribution histogram. We bin the anomaly score into 0.5-wide
# buckets up to a 6.0 ceiling so the long tail of extreme outliers
# collapses into the last bucket (six-sigma anything is rare enough
# that the tail doesn't deserve its own bin). `st.bar_chart` is the
# fancier-helper-free path the brief asks for.
#
# Codex P2: `pd.cut(..., right=False)` excludes the right edge, so a
# score clipped to exactly 6.0 would land outside every bin (NaN) and
# silently disappear from the chart. Nudge clipped-tail values just
# below the upper boundary so they fold into the final bin where they
# belong.
score_series = df_features["anomaly_score"].clip(lower=0.0, upper=6.0 - 1e-9)
bins = np.arange(0.0, 6.5, 0.5)
labels = [f"{bins[i]:.1f}–{bins[i + 1]:.1f}" for i in range(len(bins) - 1)]
hist = pd.cut(score_series, bins=bins, labels=labels, include_lowest=True, right=False)
hist_df = hist.value_counts().reindex(labels, fill_value=0).rename("customers").to_frame()
st.bar_chart(hist_df, use_container_width=True)

# ---------------------------------------------------------------------------
# Top-20 anomaly table. Sorted descending by anomaly score; numeric
# columns shown to two decimals so the grid stays sortable on the
# underlying float values (not on a pre-rounded string).
# ---------------------------------------------------------------------------
st.markdown("### Top 20 customers by anomaly score")

display_cols = ["customer_id", "anomaly_score", *feature_cols, "caught_by_rules"]
df_top = df_features.sort_values("anomaly_score", ascending=False).head(20)[display_cols].copy()

# Round numerics for display; keep float dtype so column sort works.
for col in ("anomaly_score", "sum_amount", "avg_amount", "cross_border_ratio"):
    if col in df_top.columns:
        df_top[col] = df_top[col].astype(float).round(2)

st.dataframe(
    df_top,
    # `use_container_width` is the Streamlit ≥1.39 spelling that this
    # project's `[dashboard]` extra declares. The newer `width="stretch"`
    # only landed in a later release. Codex pass on PR-413.
    use_container_width=True,
    hide_index=True,
    column_config={
        "customer_id": st.column_config.TextColumn("Customer", help="Customer ID"),
        "anomaly_score": st.column_config.NumberColumn(
            "Anomaly score",
            help="Max absolute population z-score across the per-customer feature set.",
            format="%.2f",
        ),
        "count": st.column_config.NumberColumn("Txn count"),
        "sum_amount": st.column_config.NumberColumn("Sum amount", format="%.2f"),
        "avg_amount": st.column_config.NumberColumn("Avg amount", format="%.2f"),
        "unique_counterparties": st.column_config.NumberColumn("Distinct counterparties"),
        "cross_border_ratio": st.column_config.NumberColumn(
            "Cross-border ratio",
            help="Fraction of txns where counterparty country != customer home country.",
            format="%.2f",
        ),
        "caught_by_rules": st.column_config.TextColumn(
            "Caught by rules",
            help=(
                "'yes' = this customer already has at least one spec-rule alert "
                "this run. 'no' = discovery candidate — the spec rules don't "
                "catch this customer yet."
            ),
        ),
    },
)

st.caption(
    "Numeric columns are sortable. Customers with `caught_by_rules = no` "
    "and high anomaly score are the discovery candidates — open Customer "
    "360 for the per-customer view, then decide whether to add a new "
    "rule (Spec Editor) or tune existing thresholds (Tuning Lab)."
)

# ---------------------------------------------------------------------------
# Cross-links. Discovery candidates land here; the operator's next step
# is one of: drill into a specific customer (Customer 360), check
# rule-side coverage (Rule Performance), or run a what-if before
# committing a threshold change (Tuning Lab).
# ---------------------------------------------------------------------------
st.markdown("### Next step")
nc_a, nc_b, nc_c = st.columns(3)
with nc_a:
    link_to_page("pages/17_Customer_360.py", "Customer 360 — per-customer drill-down")
with nc_b:
    link_to_page("pages/5_Rule_Performance.py", "Rule Performance — current coverage")
with nc_c:
    link_to_page("pages/23_Tuning_Lab.py", "Tuning Lab — threshold what-if")

page_footer()
