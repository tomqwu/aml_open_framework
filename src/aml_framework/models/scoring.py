"""Heuristic risk scorer — demonstrates the python_ref execution pipeline.

This is NOT a trained ML model. It computes a composite risk score from
behavioral features (velocity, amount deviation, channel mixing) using
SQL against the in-memory DuckDB warehouse. A production deployment would
replace this with an actual model (XGBoost, LightGBM, etc.) behind the
same callable interface.

Callable signature for python_ref:
    func(con: duckdb.DuckDBPyConnection, as_of: datetime) -> list[dict]
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import duckdb


def heuristic_risk_scorer(
    con: duckdb.DuckDBPyConnection,
    as_of: datetime,
) -> list[dict[str, Any]]:
    """Score customers on behavioral risk using transaction features."""
    window_start = as_of - timedelta(days=30)

    sql = f"""
    WITH features AS (
        SELECT
            customer_id,
            COUNT(*)                              AS txn_count,
            SUM(amount)                           AS total_amount,
            AVG(amount)                           AS avg_amount,
            STDDEV_SAMP(amount)                   AS stddev_amount,
            COUNT(DISTINCT channel)               AS channel_count,
            COUNT(DISTINCT CAST(booked_at AS DATE)) AS active_days,
            MIN(booked_at)                        AS window_start,
            MAX(booked_at)                        AS window_end
        FROM txn
        WHERE booked_at >= TIMESTAMP '{window_start.isoformat(sep=" ")}'
          AND booked_at <  TIMESTAMP '{as_of.isoformat(sep=" ")}'
        GROUP BY customer_id
        HAVING COUNT(*) >= 3
    ),
    scored AS (
        SELECT
            customer_id,
            txn_count,
            total_amount,
            -- Velocity: transactions per active day (higher = more suspicious)
            CASE WHEN active_days > 0
                 THEN LEAST(txn_count * 1.0 / active_days / 5.0, 1.0)
                 ELSE 0 END                       AS velocity_score,
            -- Amount deviation: coefficient of variation (higher = more erratic)
            CASE WHEN avg_amount > 0 AND stddev_amount IS NOT NULL
                 THEN LEAST(stddev_amount / avg_amount / 2.0, 1.0)
                 ELSE 0 END                       AS deviation_score,
            -- Channel mixing: using 3+ channels is unusual
            CASE WHEN channel_count >= 4 THEN 1.0
                 WHEN channel_count >= 3 THEN 0.7
                 WHEN channel_count >= 2 THEN 0.3
                 ELSE 0.0 END                     AS channel_score,
            window_start,
            window_end
        FROM features
    )
    SELECT
        'ml_risk_scorer'                          AS rule_id,
        customer_id,
        total_amount                              AS sum_amount,
        txn_count                                 AS count,
        velocity_score,
        deviation_score,
        channel_score,
        ROUND(
            velocity_score * 0.4
            + deviation_score * 0.3
            + channel_score * 0.3,
            4
        )                                         AS risk_score,
        window_start,
        window_end
    FROM scored
    WHERE (velocity_score * 0.4 + deviation_score * 0.3 + channel_score * 0.3) >= 0.65
    ORDER BY customer_id
    """

    rows = con.execute(sql).fetchall()
    cols = [d[0] for d in con.description] if con.description else []
    alerts = [dict(zip(cols, r)) for r in rows]
    # Emit feature_attribution so the case file + STR narrative can show
    # *why* the score was high. Each component carries its weighted contribution
    # to the final score; the analyst can see at a glance which signal drove
    # the alert.
    for a in alerts:
        v = float(a.pop("velocity_score", 0))
        d = float(a.pop("deviation_score", 0))
        c = float(a.pop("channel_score", 0))
        a["feature_attribution"] = {
            "velocity": round(v * 0.4, 4),
            "amount_deviation": round(d * 0.3, 4),
            "channel_mixing": round(c * 0.3, 4),
        }
        # Identify the dominant signal for a one-line explanation.
        dominant = max(
            (("velocity", v * 0.4), ("amount_deviation", d * 0.3), ("channel_mixing", c * 0.3)),
            key=lambda kv: kv[1],
        )
        a["explanation"] = (
            f"Behavioral score driven primarily by '{dominant[0]}' "
            f"(contribution {dominant[1]:.2f} to risk_score {a['risk_score']})."
        )
    return alerts
