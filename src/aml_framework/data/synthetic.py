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


def _make_txn(
    tid: int,
    customer_id: str,
    amount,
    booked_at: datetime,
    *,
    channel: str = "cash",
    direction: str = "in",
    currency: str = "USD",
) -> dict[str, Any]:
    """Build a single transaction dict with deterministic shape.

    `amount` may be int / float / Decimal — quantized to 2 d.p. either way.
    Output is byte-identical to the previous inline dict literals; the
    determinism test (`test_run_is_reproducible`) verifies this.
    """
    return {
        "txn_id": f"T{tid:08d}",
        "customer_id": customer_id,
        "amount": Decimal(amount).quantize(Decimal("0.01")),
        "currency": currency,
        "channel": channel,
        "direction": direction,
        "booked_at": booked_at,
    }


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
    pep_status: str | None = None,
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
        "pep_status": pep_status or "",
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
    # PEP customer for EU spec testing.
    if n_customers > 9:
        customers[9] = _customer_row(
            fake,
            "C0009",
            as_of - timedelta(days=400),
            country="DE",
            risk_rating="high",
            full_name="Hans Mueller",
            pep_status="domestic_pep",
            edd_last_review=as_of - timedelta(days=30),
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
        amount = random.choice([50, 120, 300, 750, 1200, 2500, 4800])
        txns.append(
            _make_txn(
                tid,
                cid,
                amount,
                booked_at,
                channel=random.choice(_CHANNELS),
                direction=random.choice(["in", "out"]),
            )
        )
        tid += 1

    # --- Planted positive: structuring by customer C0001. ---
    structurer = customer_ids[1]
    for day_offset, amt in [(2, 9800), (5, 9500), (9, 9900), (14, 7500), (21, 9200)]:
        txns.append(
            _make_txn(
                tid,
                structurer,
                amt,
                as_of - timedelta(days=day_offset, hours=random.randint(9, 17)),
                channel="cash",
                direction="in",
            )
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
            _make_txn(
                tid, mover, amt, base + timedelta(hours=i * 6), channel=channel, direction=direction
            )
        )
        tid += 1

    # --- Planted positive: high-risk jurisdiction by customer C0003 (RU). ---
    for day_offset, amt in [(5, 3500), (12, 4500), (18, 2800)]:
        txns.append(
            _make_txn(
                tid,
                "C0003",
                amt,
                as_of - timedelta(days=day_offset, hours=10),
                channel="wire",
                direction="in",
            )
        )
        tid += 1

    # --- Planted positive: large cash (CTR) by customer C0004. ---
    # Single-day cash deposits totalling $12,500 — exceeds $10k CTR threshold.
    ctr_day = as_of - timedelta(hours=18)
    for hour_offset, amt in [(9, 6500), (14, 6000)]:
        txns.append(
            _make_txn(
                tid,
                "C0004",
                amt,
                ctr_day + timedelta(hours=hour_offset),
                channel="cash",
                direction="in",
            )
        )
        tid += 1

    # --- Planted positive: unusual volume spike by customer C0005. ---
    # Prior 30 days: small activity ($200/week). Last 7 days: sudden $15k surge.
    for week in range(4):
        txns.append(
            _make_txn(
                tid,
                "C0005",
                "200.00",
                as_of - timedelta(days=35 - week * 7, hours=11),
                channel="ach",
                direction="out",
            )
        )
        tid += 1
    # Spike in last 7 days.
    for day_offset, amt in [(1, 5000), (3, 4500), (5, 5500)]:
        txns.append(
            _make_txn(
                tid,
                "C0005",
                amt,
                as_of - timedelta(days=day_offset, hours=15),
                channel="wire",
                direction="out",
            )
        )
        tid += 1

    # --- Planted positive: dormant account reactivation by customer C0006. ---
    # No activity for 50 days, then $15k deposit.
    txns.append(
        _make_txn(
            tid,
            "C0006",
            "500.00",
            as_of - timedelta(days=55, hours=10),
            channel="ach",
            direction="out",
        )
    )
    tid += 1
    txns.append(
        _make_txn(
            tid,
            "C0006",
            "15000.00",
            as_of - timedelta(days=2, hours=14),
            channel="wire",
            direction="in",
        )
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
                _make_txn(
                    tid,
                    "C0007",
                    amt,
                    pt_base + timedelta(hours=h),
                    channel="cash",
                    direction="in",
                    currency="CAD",
                )
            )
            tid += 1
        # E-transfer out within 48h
        for h, amt in [(28, 8000), (36, 7000), (42, 6000)]:
            txns.append(
                _make_txn(
                    tid,
                    "C0007",
                    amt,
                    pt_base + timedelta(hours=h),
                    channel="e_transfer",
                    direction="out",
                    currency="CAD",
                )
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
                _make_txn(
                    tid,
                    "C0008",
                    random.randint(5000, 15000),
                    as_of - timedelta(days=day_offset, hours=11),
                    channel="wire",
                    direction="in",
                    currency="CAD",
                )
            )
            tid += 1

    return {"customer": customers, "txn": txns}
