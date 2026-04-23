"""Synthetic dataset generator for demos and tests.

Injects a known-positive structuring scenario so the demo produces at least
one alert without depending on randomness. The remaining volume is noise that
should NOT trigger the reference rules.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from faker import Faker

_CHANNELS = ["cash", "wire", "ach", "card"]
_COUNTRIES = ["US", "CA", "GB", "DE", "MX"]


def _customer_row(fake: Faker, customer_id: str, onboarded_at: datetime) -> dict[str, Any]:
    return {
        "customer_id": customer_id,
        "full_name": fake.name(),
        "country": random.choice(_COUNTRIES),
        "risk_rating": random.choices(["low", "medium", "high"], weights=[70, 25, 5])[0],
        "onboarded_at": onboarded_at,
    }


def generate_dataset(
    as_of: datetime,
    seed: int = 42,
    n_customers: int = 25,
    n_noise_txns: int = 400,
) -> dict[str, list[dict[str, Any]]]:
    """Produce ({customer rows, txn rows}) for the example spec's contracts."""
    random.seed(seed)
    fake = Faker()
    Faker.seed(seed)

    customers: list[dict[str, Any]] = []
    customer_ids: list[str] = []
    for i in range(n_customers):
        cid = f"C{i:04d}"
        customer_ids.append(cid)
        customers.append(
            _customer_row(fake, cid, as_of - timedelta(days=random.randint(30, 1500)))
        )

    txns: list[dict[str, Any]] = []
    tid = 0

    # --- Noise: random legitimate-looking activity over the last 60 days. ---
    for _ in range(n_noise_txns):
        cid = random.choice(customer_ids)
        booked_at = as_of - timedelta(
            days=random.randint(0, 59),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        amount = Decimal(random.choice([50, 120, 300, 750, 1200, 2500, 4800])).quantize(Decimal("0.01"))
        txns.append({
            "txn_id": f"T{tid:08d}",
            "customer_id": cid,
            "amount": amount,
            "currency": "USD",
            "channel": random.choice(_CHANNELS),
            "direction": random.choice(["in", "out"]),
            "booked_at": booked_at,
        })
        tid += 1

    # --- Planted positive: structuring by customer C0001. ---
    structurer = customer_ids[1]
    for day_offset, amt in [
        (2,  9800),
        (5,  9500),
        (9,  9900),
        (14, 7500),
        (21, 9200),
    ]:
        txns.append({
            "txn_id": f"T{tid:08d}",
            "customer_id": structurer,
            "amount": Decimal(amt).quantize(Decimal("0.01")),
            "currency": "USD",
            "channel": "cash",
            "direction": "in",
            "booked_at": as_of - timedelta(days=day_offset, hours=random.randint(9, 17)),
        })
        tid += 1

    # --- Planted positive: rapid movement by customer C0002. ---
    mover = customer_ids[2]
    base = as_of - timedelta(days=3)
    for i, (channel, direction, amt) in enumerate([
        ("cash", "in", 20000),
        ("cash", "in", 18000),
        ("wire", "out", 15000),
        ("wire", "out", 17500),
    ]):
        txns.append({
            "txn_id": f"T{tid:08d}",
            "customer_id": mover,
            "amount": Decimal(amt).quantize(Decimal("0.01")),
            "currency": "USD",
            "channel": channel,
            "direction": direction,
            "booked_at": base + timedelta(hours=i * 6),
        })
        tid += 1

    return {"customer": customers, "txn": txns}
