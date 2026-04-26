"""XGBoost risk scorer — real ML model trained on synthetic data.

Trains an XGBoost classifier to predict whether a customer is a planted
positive (suspicious) based on transaction features. Falls back to the
heuristic scorer if xgboost is not installed.

Callable signature for python_ref:
    func(con: duckdb.DuckDBPyConnection, as_of: datetime) -> list[dict]
"""

from __future__ import annotations

import logging
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger("aml.models.xgboost")

_MODEL_DIR = Path(__file__).parent / "trained"
_MODEL_PATH = _MODEL_DIR / "xgboost_risk_model.pkl"


def _extract_features(con: duckdb.DuckDBPyConnection, as_of: datetime) -> list[dict[str, Any]]:
    """Extract per-customer features from the DuckDB warehouse."""
    window_start = as_of - timedelta(days=30)
    sql = """
    SELECT
        customer_id,
        COUNT(*) AS txn_count,
        SUM(amount) AS total_amount,
        AVG(amount) AS avg_amount,
        COALESCE(STDDEV_SAMP(amount), 0) AS stddev_amount,
        COUNT(DISTINCT channel) AS channel_count,
        COUNT(DISTINCT CAST(booked_at AS DATE)) AS active_days
    FROM txn
    WHERE booked_at >= $1
      AND booked_at <  $2
    GROUP BY customer_id
    HAVING COUNT(*) >= 3
    """
    rows = con.execute(sql, [window_start, as_of]).fetchall()
    cols = [d[0] for d in con.description]
    return [dict(zip(cols, r)) for r in rows]


def train_model(
    con: duckdb.DuckDBPyConnection,
    as_of: datetime,
    positive_customers: set[str] | None = None,
) -> Any:
    """Train an XGBoost model on the current warehouse data.

    positive_customers: customer IDs known to be suspicious (planted positives).
    If None, uses C0001-C0008 as the default positive set.
    """
    try:
        import xgboost as xgb
    except ImportError:
        logger.warning("xgboost not installed — skipping model training")
        return None

    if positive_customers is None:
        positive_customers = {f"C{i:04d}" for i in range(1, 9)}

    features = _extract_features(con, as_of)
    if not features:
        return None

    feature_cols = [
        "txn_count",
        "total_amount",
        "avg_amount",
        "stddev_amount",
        "channel_count",
        "active_days",
    ]
    X = [[float(f.get(c, 0)) for c in feature_cols] for f in features]
    y = [1 if f["customer_id"] in positive_customers else 0 for f in features]

    model = xgb.XGBClassifier(
        n_estimators=50,
        max_depth=3,
        learning_rate=0.1,
        use_label_encoder=False,
        eval_metric="logloss",
        verbosity=0,
    )
    model.fit(X, y)

    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with _MODEL_PATH.open("wb") as f:
        pickle.dump({"model": model, "feature_cols": feature_cols}, f)

    # Write a hash file so we can verify integrity before loading.
    import hashlib

    model_hash = hashlib.sha256(_MODEL_PATH.read_bytes()).hexdigest()
    _MODEL_PATH.with_suffix(".sha256").write_text(model_hash, encoding="utf-8")

    logger.info("XGBoost model trained and saved to %s", _MODEL_PATH)
    return model


def xgboost_risk_scorer(
    con: duckdb.DuckDBPyConnection,
    as_of: datetime,
) -> list[dict[str, Any]]:
    """Score customers using the trained XGBoost model.

    Falls back to the heuristic scorer if xgboost is not available.
    """
    try:
        import xgboost  # noqa: F401
    except ImportError:
        from aml_framework.models.scoring import heuristic_risk_scorer

        logger.info("xgboost not installed — falling back to heuristic scorer")
        return heuristic_risk_scorer(con, as_of)

    # Train on-the-fly if no saved model exists.
    if not _MODEL_PATH.exists():
        model = train_model(con, as_of)
        if model is None:
            from aml_framework.models.scoring import heuristic_risk_scorer

            return heuristic_risk_scorer(con, as_of)

    # Verify model integrity before loading.
    import hashlib

    hash_path = _MODEL_PATH.with_suffix(".sha256")
    if hash_path.exists():
        expected = hash_path.read_text(encoding="utf-8").strip()
        actual = hashlib.sha256(_MODEL_PATH.read_bytes()).hexdigest()
        if actual != expected:
            logger.error("Model file integrity check failed — possible tampering")
            from aml_framework.models.scoring import heuristic_risk_scorer

            return heuristic_risk_scorer(con, as_of)

    with _MODEL_PATH.open("rb") as f:
        saved = pickle.load(f)  # noqa: S301
    model = saved["model"]
    feature_cols = saved["feature_cols"]

    features = _extract_features(con, as_of)
    if not features:
        return []

    X = [[float(f.get(c, 0)) for c in feature_cols] for f in features]
    probas = model.predict_proba(X)[:, 1]

    alerts: list[dict[str, Any]] = []
    window_start = as_of - timedelta(days=30)
    for feat, proba in zip(features, probas):
        if proba >= 0.5:
            alerts.append(
                {
                    "rule_id": "xgboost_risk_scorer",
                    "customer_id": feat["customer_id"],
                    "sum_amount": float(feat["total_amount"]),
                    "count": int(feat["txn_count"]),
                    "risk_score": round(float(proba), 4),
                    "window_start": window_start,
                    "window_end": as_of,
                }
            )
    return alerts
