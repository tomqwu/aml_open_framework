"""Synthetic dataset generator for demos and tests.

Injects known-positive scenarios so the demo produces alerts for multiple
typologies without depending on randomness. The remaining volume is noise that
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


def _customer_row(
    fake: Faker,
    customer_id: str,
    onboarded_at: datetime,
    *,
    country: str | None = None,
    risk_rating: str | None = None,
    full_name: str | None = None,
    business_activity: str | None = None,
    edd_last_review: datetime | None = None,
) -> dict[str, Any]:
    return {
        "customer_id": customer_id,
        "full_name": full_name or fake.name(),
        "country": country or random.choice(_COUNTRIES),
        "risk_rating": risk_rating
        or random.choices(["low", "medium", "high"], weights=[70, 25, 5])[0],
        "onboarded_at": onboarded_at,
        "business_activity": business_activity or "",
        "edd_last_review": edd_last_review,
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
        customers.append(_customer_row(fake, cid, as_of - timedelta(days=random.randint(30, 1500))))

    # Add edd_last_review dates to high-risk customers.
    for c in customers:
        if c["risk_rating"] == "high":
            # Some high-risk customers have current EDD, some are overdue.
            c["edd_last_review"] = as_of - timedelta(days=random.choice([90, 180, 400]))

    # Override planted-positive customers with deterministic profiles.
    customers[3] = _customer_row(
        fake,
        "C0003",
        as_of - timedelta(days=200),
        country="RU",
        risk_rating="high",
        full_name="Alexei Volkov",
        edd_last_review=as_of - timedelta(days=60),  # Current EDD review.
    )
    customers[4] = _customer_row(
        fake,
        "C0004",
        as_of - timedelta(days=500),
        country="US",
        risk_rating="medium",
        full_name="Maria Chen",
    )
    customers[5] = _customer_row(
        fake,
        "C0005",
        as_of - timedelta(days=300),
        country="US",
        risk_rating="low",
        full_name="David Park",
    )
    customers[6] = _customer_row(
        fake,
        "C0006",
        as_of - timedelta(days=800),
        country="US",
        risk_rating="low",
        full_name="Sarah Thompson",
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
        amount = Decimal(random.choice([50, 120, 300, 750, 1200, 2500, 4800])).quantize(
            Decimal("0.01")
        )
        txns.append(
            {
                "txn_id": f"T{tid:08d}",
                "customer_id": cid,
                "amount": amount,
                "currency": "USD",
                "channel": random.choice(_CHANNELS),
                "direction": random.choice(["in", "out"]),
                "booked_at": booked_at,
            }
        )
        tid += 1

    # --- Planted positive: structuring by customer C0001. ---
    structurer = customer_ids[1]
    for day_offset, amt in [
        (2, 9800),
        (5, 9500),
        (9, 9900),
        (14, 7500),
        (21, 9200),
    ]:
        txns.append(
            {
                "txn_id": f"T{tid:08d}",
                "customer_id": structurer,
                "amount": Decimal(amt).quantize(Decimal("0.01")),
                "currency": "USD",
                "channel": "cash",
                "direction": "in",
                "booked_at": as_of - timedelta(days=day_offset, hours=random.randint(9, 17)),
            }
        )
        tid += 1

    # --- Planted positive: rapid movement by customer C0002. ---
    mover = customer_ids[2]
    base = as_of - timedelta(days=3)
    for i, (channel, direction, amt) in enumerate(
        [
            ("cash", "in", 20000),
            ("cash", "in", 18000),
            ("wire", "out", 15000),
            ("wire", "out", 17500),
        ]
    ):
        txns.append(
            {
                "txn_id": f"T{tid:08d}",
                "customer_id": mover,
                "amount": Decimal(amt).quantize(Decimal("0.01")),
                "currency": "USD",
                "channel": channel,
                "direction": direction,
                "booked_at": base + timedelta(hours=i * 6),
            }
        )
        tid += 1

    # --- Planted positive: high-risk jurisdiction by customer C0003 (RU). ---
    for day_offset, amt in [(5, 3500), (12, 4500), (18, 2800)]:
        txns.append(
            {
                "txn_id": f"T{tid:08d}",
                "customer_id": "C0003",
                "amount": Decimal(amt).quantize(Decimal("0.01")),
                "currency": "USD",
                "channel": "wire",
                "direction": "in",
                "booked_at": as_of - timedelta(days=day_offset, hours=10),
            }
        )
        tid += 1

    # --- Planted positive: large cash (CTR) by customer C0004. ---
    # Single-day cash deposits totalling $12,500 — exceeds $10k CTR threshold.
    ctr_day = as_of - timedelta(hours=18)
    for hour_offset, amt in [(9, 6500), (14, 6000)]:
        txns.append(
            {
                "txn_id": f"T{tid:08d}",
                "customer_id": "C0004",
                "amount": Decimal(amt).quantize(Decimal("0.01")),
                "currency": "USD",
                "channel": "cash",
                "direction": "in",
                "booked_at": ctr_day + timedelta(hours=hour_offset),
            }
        )
        tid += 1

    # --- Planted positive: unusual volume spike by customer C0005. ---
    # Prior 30 days: small activity ($200/week). Last 7 days: sudden $15k surge.
    for week in range(4):
        txns.append(
            {
                "txn_id": f"T{tid:08d}",
                "customer_id": "C0005",
                "amount": Decimal("200.00"),
                "currency": "USD",
                "channel": "ach",
                "direction": "out",
                "booked_at": as_of - timedelta(days=35 - week * 7, hours=11),
            }
        )
        tid += 1
    # Spike in last 7 days.
    for day_offset, amt in [(1, 5000), (3, 4500), (5, 5500)]:
        txns.append(
            {
                "txn_id": f"T{tid:08d}",
                "customer_id": "C0005",
                "amount": Decimal(amt).quantize(Decimal("0.01")),
                "currency": "USD",
                "channel": "wire",
                "direction": "out",
                "booked_at": as_of - timedelta(days=day_offset, hours=15),
            }
        )
        tid += 1

    # --- Planted positive: dormant account reactivation by customer C0006. ---
    # No activity for 50 days, then $15k deposit.
    txns.append(
        {
            "txn_id": f"T{tid:08d}",
            "customer_id": "C0006",
            "amount": Decimal("500.00"),
            "currency": "USD",
            "channel": "ach",
            "direction": "out",
            "booked_at": as_of - timedelta(days=55, hours=10),
        }
    )
    tid += 1
    txns.append(
        {
            "txn_id": f"T{tid:08d}",
            "customer_id": "C0006",
            "amount": Decimal("15000.00"),
            "currency": "USD",
            "channel": "wire",
            "direction": "in",
            "booked_at": as_of - timedelta(days=2, hours=14),
        }
    )
    tid += 1

    # --- Planted positive: rapid pass-through by customer C0007. ---
    # Cash-in followed by e-transfer-out within 48h, total >= $30k.
    # Models the TD Bank pass-through typology ($470M+ undetected).
    if n_customers > 7:
        customers[7] = _customer_row(
            fake,
            "C0007",
            as_of - timedelta(days=120),
            country="CA",
            risk_rating="medium",
            full_name="James Rivera",
        )
        pt_base = as_of - timedelta(days=5)
        # Cash deposits
        for h, amt in [(9, 12000), (14, 10000)]:
            txns.append(
                {
                    "txn_id": f"T{tid:08d}",
                    "customer_id": "C0007",
                    "amount": Decimal(amt).quantize(Decimal("0.01")),
                    "currency": "CAD",
                    "channel": "cash",
                    "direction": "in",
                    "booked_at": pt_base + timedelta(hours=h),
                }
            )
            tid += 1
        # E-transfer out within 48h
        for h, amt in [(28, 8000), (36, 7000), (42, 6000)]:
            txns.append(
                {
                    "txn_id": f"T{tid:08d}",
                    "customer_id": "C0007",
                    "amount": Decimal(amt).quantize(Decimal("0.01")),
                    "currency": "CAD",
                    "channel": "e_transfer",
                    "direction": "out",
                    "booked_at": pt_base + timedelta(hours=h),
                }
            )
            tid += 1

    # --- Planted positive: shell company by customer C0008. ---
    # No declared business_activity, 10+ incoming wires from multiple sources.
    if n_customers > 8:
        customers[8] = _customer_row(
            fake,
            "C0008",
            as_of - timedelta(days=90),
            country="CA",
            risk_rating="low",
            full_name="Oceanic Holdings Ltd",
            business_activity="",
        )
        for day_offset in range(0, 30, 3):
            txns.append(
                {
                    "txn_id": f"T{tid:08d}",
                    "customer_id": "C0008",
                    "amount": Decimal(random.randint(5000, 15000)).quantize(Decimal("0.01")),
                    "currency": "CAD",
                    "channel": "wire",
                    "direction": "in",
                    "booked_at": as_of - timedelta(days=day_offset, hours=11),
                }
            )
            tid += 1

    return {"customer": customers, "txn": txns}
