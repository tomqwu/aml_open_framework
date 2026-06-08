"""Spec-specific synthetic dataset for the ``trade_based_ml`` example.

Planted-positive demo data for the TBML correspondent-bank spec
(``program.name = tbml_correspondent_bank``). Modelled on
``data/synthetic.py`` — deterministic, seed-pinned, stdlib only (no
faker / pandas / numpy), no ``datetime.now()``.

Customer IDs live in a dedicated **C9201-C9229** band so the TBML demo
is cleanly isolated from the shared community-bank C0xxx band.

Planted typologies (each trips exactly the named rule in
``examples/trade_based_ml/aml.yaml``). All five TBML rules are covered
here — including under-invoicing and trad-to-high-risk-jurisdiction,
which the shared community-bank dataset left at zero:

* **over_invoicing_unit_price** — C9201 (importer): 2 TRAD wires with
  declared_unit_price = $2,000 (4x the $500 baseline for HS 8471.30),
  sum $40k (>= $25k).
* **under_invoicing_unit_price** — C9202 (supplier, same entity graph
  as C9201 via a shared invoice corridor): 2 TRAD wires with
  declared_unit_price = $200 (0.4x the $500 baseline), sum $50k.
* **phantom_shipping** — C9203: 3 outbound TRAD wires with no
  ``invoice_id`` over 25 days summing $60k (count >= 3, sum >= $50k).
* **multiple_invoicing** — C9204: same ``invoice_id`` paid twice in a
  week (count >= 2).
* **trad_to_high_risk_jurisdiction** — C9205: 2 TRAD wires of $30k each
  to RU (FATF call-for-action), sum $60k (per-leg >= $25k, sum >= $50k).

The over/under pair (C9201 buyer ↔ C9202 supplier) models a single
mis-invoicing corridor — over-declared on the import leg and
under-declared on the export leg of the same notional shipment.

The remaining slots (C9206-C9229) are benign background trade wires so
the dashboard's volume views aren't empty.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

# Five representative HS codes with median + p5 + p95 unit prices
# (World Customs Organization summary data). Rules 1 + 2 JOIN on
# hs_code, so this baseline must ship with the dataset. Same rows as
# data/synthetic.py's community-bank build for cross-spec consistency.
_HS_CODE_BASELINE: list[dict[str, Any]] = [
    {
        "hs_code": "8471.30",  # consumer electronics (laptops, tablets)
        "median_unit_price": Decimal("500.00"),
        "p5_unit_price": Decimal("300.00"),
        "p95_unit_price": Decimal("800.00"),
    },
    {
        "hs_code": "7113.19",  # precious-metal jewellery
        "median_unit_price": Decimal("2000.00"),
        "p5_unit_price": Decimal("1500.00"),
        "p95_unit_price": Decimal("3000.00"),
    },
    {
        "hs_code": "6203.42",  # men's cotton trousers
        "median_unit_price": Decimal("50.00"),
        "p5_unit_price": Decimal("30.00"),
        "p95_unit_price": Decimal("80.00"),
    },
    {
        "hs_code": "8703.21",  # passenger motor vehicles <=1.0L
        "median_unit_price": Decimal("15000.00"),
        "p5_unit_price": Decimal("10000.00"),
        "p95_unit_price": Decimal("25000.00"),
    },
    {
        "hs_code": "2710.19",  # petroleum oils, refined
        "median_unit_price": Decimal("5.00"),
        "p5_unit_price": Decimal("3.00"),
        "p95_unit_price": Decimal("8.00"),
    },
]


def _txn(
    tid: int,
    customer_id: str,
    amount: Any,
    booked_at: datetime,
    *,
    channel: str = "wire",
    direction: str = "out",
    currency: str = "USD",
    purpose_code: str = "",
    counterparty_country: str = "",
    invoice_id: str | None = None,
    invoice_amount: Decimal | None = None,
    declared_unit_price: Decimal | None = None,
    declared_quantity: int | None = None,
    hs_code: str | None = None,
) -> dict[str, Any]:
    """Build one ``txn`` row matching the trade_based_ml data contract."""
    return {
        "txn_id": f"T9{tid:07d}",
        "customer_id": customer_id,
        "amount": Decimal(amount).quantize(Decimal("0.01")),
        "currency": currency,
        "channel": channel,
        "direction": direction,
        "booked_at": booked_at,
        "purpose_code": purpose_code,
        "counterparty_country": counterparty_country,
        "invoice_id": invoice_id,
        "invoice_amount": invoice_amount,
        "declared_unit_price": declared_unit_price,
        "declared_quantity": declared_quantity,
        "hs_code": hs_code,
    }


def _customer(
    customer_id: str,
    full_name: str,
    onboarded_at: datetime,
    *,
    country: str = "US",
    risk_rating: str = "medium",
    business_activity: str = "",
    trade_lic_number: str | None = None,
) -> dict[str, Any]:
    """Build one ``customer`` row matching the trade_based_ml data contract."""
    return {
        "customer_id": customer_id,
        "full_name": full_name,
        "country": country,
        "risk_rating": risk_rating,
        "onboarded_at": onboarded_at,
        "business_activity": business_activity,
        "trade_lic_number": trade_lic_number,
    }


def generate_trade_based_ml_dataset(
    as_of: datetime,
    seed: int = 42,
) -> dict[str, list[dict[str, Any]]]:
    """Produce ``{customer, txn, hs_code_baseline}`` rows for the
    trade_based_ml spec.

    Deterministic: every amount + time offset is hardcoded (no
    ``random``). ``seed`` is accepted for signature parity with
    ``generate_dataset``; it does not change the output.
    """
    _ = seed  # signature parity — no stochastic draw to seed
    customers: list[dict[str, Any]] = []
    txns: list[dict[str, Any]] = []
    tid = 0

    # --- C9201: over-invoicing importer (declared price 4x baseline) ---
    customers.append(
        _customer(
            "C9201",
            "Apex Imports LLC",
            as_of - timedelta(days=400),
            business_activity="import_export",
            trade_lic_number="US-IMP-2024-C9201",
        )
    )
    for day_offset in (5, 12):
        txns.append(
            _txn(
                tid,
                "C9201",
                20000,
                as_of - timedelta(days=day_offset, hours=11),
                direction="out",
                purpose_code="TRAD",
                counterparty_country="DE",
                # Shared invoice corridor with the C9202 export leg.
                invoice_id=f"INV-CORRIDOR-{day_offset:03d}-IMP",
                invoice_amount=Decimal("20000.00"),
                declared_unit_price=Decimal("2000.00"),  # 4x $500 baseline
                declared_quantity=10,
                hs_code="8471.30",
            )
        )
        tid += 1

    # --- C9202: under-invoicing supplier (declared price 0.4x baseline) ---
    # Same notional shipment corridor as C9201 — over-declared on the
    # import leg, under-declared on the export leg.
    customers.append(
        _customer(
            "C9202",
            "Apex Exports Pte",
            as_of - timedelta(days=380),
            country="SG",
            business_activity="import_export",
            trade_lic_number="SG-EXP-2024-C9202",
        )
    )
    for day_offset in (6, 13):
        txns.append(
            _txn(
                tid,
                "C9202",
                25000,
                as_of - timedelta(days=day_offset, hours=12),
                direction="out",
                purpose_code="TRAD",
                counterparty_country="US",
                invoice_id=f"INV-CORRIDOR-{day_offset - 1:03d}-EXP",
                invoice_amount=Decimal("25000.00"),
                declared_unit_price=Decimal("200.00"),  # 0.4x $500 baseline
                declared_quantity=125,
                hs_code="8471.30",
            )
        )
        tid += 1

    # --- C9203: phantom shipping (TRAD payments with no invoice_id) ---
    customers.append(
        _customer(
            "C9203",
            "Vanguard Trading Corp",
            as_of - timedelta(days=300),
            business_activity="wholesale",
            trade_lic_number="US-WHL-2024-C9203",
        )
    )
    for day_offset, amt in [(3, 22000), (10, 18000), (20, 20000)]:
        txns.append(
            _txn(
                tid,
                "C9203",
                amt,
                as_of - timedelta(days=day_offset, hours=14),
                direction="out",
                purpose_code="TRAD",
                counterparty_country="HK",
                # invoice_id intentionally None — this is the rule signal.
            )
        )
        tid += 1

    # --- C9204: multiple invoicing (same invoice paid twice) ---
    customers.append(
        _customer(
            "C9204",
            "Continental Trade Group",
            as_of - timedelta(days=250),
            business_activity="commodities",
            trade_lic_number="US-COM-2024-C9204",
        )
    )
    dup_invoice = "INV-DUP-2026-C9204-001"
    for day_offset in (2, 8):
        txns.append(
            _txn(
                tid,
                "C9204",
                30000,
                as_of - timedelta(days=day_offset, hours=10),
                direction="out",
                purpose_code="TRAD",
                counterparty_country="SG",
                invoice_id=dup_invoice,
                invoice_amount=Decimal("30000.00"),
            )
        )
        tid += 1

    # --- C9205: TRAD payment to FATF high-risk jurisdiction (RU) ---
    customers.append(
        _customer(
            "C9205",
            "Meridian Resources Ltd",
            as_of - timedelta(days=350),
            risk_rating="high",
            business_activity="commodities",
            trade_lic_number="US-COM-2024-C9205",
        )
    )
    for day_offset in (4, 11):
        txns.append(
            _txn(
                tid,
                "C9205",
                30000,  # per-leg >= $25k; sum $60k >= $50k
                as_of - timedelta(days=day_offset, hours=9),
                direction="out",
                purpose_code="TRAD",
                counterparty_country="RU",
            )
        )
        tid += 1

    # --- C9206-C9229: benign background trade wires ---
    # Lone TRAD wires at the baseline median price (rule-inert: a single
    # wire never clears the count/sum HAVING floors, and the unit price
    # sits at 1.0x baseline). RNG-free; indexed by tid.
    _BG = [
        ("6203.42", Decimal("50.00"), 12, 600),
        ("8703.21", Decimal("15000.00"), 1, 15000),
        ("2710.19", Decimal("5.00"), 4000, 20000),
    ]
    bg_ids = [f"C{9200 + i:04d}" for i in range(6, 30)]
    for n, cid in enumerate(bg_ids):
        customers.append(
            _customer(
                cid,
                f"Trade Customer {n + 6}",
                as_of - timedelta(days=300 + n * 4),
                risk_rating="low",
                business_activity="import_export",
                trade_lic_number=f"US-TRD-2024-{9200 + 6 + n:04d}",
            )
        )
        hs, unit, qty, amt = _BG[n % len(_BG)]
        txns.append(
            _txn(
                tid,
                cid,
                amt,
                as_of - timedelta(days=(tid % 40) + 1, hours=10),
                direction="out",
                purpose_code="TRAD",
                counterparty_country="DE",
                invoice_id=f"INV-BG-{tid:04d}",
                invoice_amount=Decimal(amt).quantize(Decimal("0.01")),
                declared_unit_price=unit,  # 1.0x baseline — rule-inert
                declared_quantity=qty,
                hs_code=hs,
            )
        )
        tid += 1

    return {
        "customer": customers,
        "txn": txns,
        "hs_code_baseline": list(_HS_CODE_BASELINE),
    }
