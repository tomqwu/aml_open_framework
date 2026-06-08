"""Spec-specific synthetic dataset for the ``uk_app_fraud`` example.

Planted-positive demo data for the UK challenger-bank APP-fraud spec
(``program.name = uk_challenger_app_fraud``). Modelled on
``data/synthetic.py`` — deterministic, seed-pinned, stdlib only (no
faker / pandas / numpy), no ``datetime.now()``.

Customer IDs live in a dedicated **C9101-C9129** band so the APP-fraud
demo is cleanly isolated from the shared community-bank C0xxx band.

Planted typologies (each trips exactly the named rule in
``examples/uk_app_fraud/aml.yaml``):

* **first_use_payee_large_amount** — C9101 makes one £1,500 outbound
  ``payee_first_use=true`` payment in the last 24h (>= £1,000).
* **vulnerable_customer_atypical_payment** — C9102 (vulnerable,
  ``typical_payment_size_p95`` = £1,000) makes a £6,000 outbound
  (>= 5x p95 AND >= £500).
* **cop_mismatch_override** — C9103 makes two outbound payments with
  ``confirmation_of_payee_status='no_match'`` in the last 7d (>= £100).
* **rapid_pass_through_mule** — C9104 (PSP-switching mule: account
  opened < 30 days) receives £2,000 inbound then forwards £1,700
  outbound 30 min later (both >= £500, within 1h).

The remaining slots (C9105-C9129) are benign background faster-payments
activity so the dashboard's volume views aren't empty.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any


def _txn(
    tid: int,
    customer_id: str,
    amount: Any,
    booked_at: datetime,
    *,
    channel: str = "faster_payments",
    direction: str = "out",
    currency: str = "GBP",
    purpose_code: str = "",
    counterparty_account: str = "",
    counterparty_name: str = "",
    counterparty_sort_code: str = "",
    payee_first_use: bool = False,
    customer_session_id: str = "",
    confirmation_of_payee_status: str = "",
) -> dict[str, Any]:
    """Build one ``txn`` row matching the uk_app_fraud data contract."""
    return {
        "txn_id": f"T9{tid:07d}",
        "customer_id": customer_id,
        "amount": Decimal(amount).quantize(Decimal("0.01")),
        "currency": currency,
        "channel": channel,
        "direction": direction,
        "booked_at": booked_at,
        "purpose_code": purpose_code,
        "counterparty_account": counterparty_account,
        "counterparty_name": counterparty_name,
        "counterparty_sort_code": counterparty_sort_code,
        "payee_first_use": payee_first_use,
        "customer_session_id": customer_session_id,
        "confirmation_of_payee_status": confirmation_of_payee_status,
    }


def _customer(
    customer_id: str,
    full_name: str,
    onboarded_at: datetime,
    *,
    country: str = "GB",
    risk_rating: str = "medium",
    vulnerable_customer_flag: bool = False,
    typical_payment_size_p95: Decimal | None = None,
) -> dict[str, Any]:
    """Build one ``customer`` row matching the uk_app_fraud data contract."""
    return {
        "customer_id": customer_id,
        "full_name": full_name,
        "country": country,
        "risk_rating": risk_rating,
        "onboarded_at": onboarded_at,
        "vulnerable_customer_flag": vulnerable_customer_flag,
        "typical_payment_size_p95": typical_payment_size_p95,
    }


def generate_uk_app_fraud_dataset(
    as_of: datetime,
    seed: int = 42,
) -> dict[str, list[dict[str, Any]]]:
    """Produce ``{customer, txn}`` rows for the uk_app_fraud spec.

    Deterministic: every amount + time offset is hardcoded (no
    ``random``). ``seed`` is accepted for signature parity with
    ``generate_dataset``; it does not change the output.
    """
    _ = seed  # signature parity — no stochastic draw to seed
    customers: list[dict[str, Any]] = []
    txns: list[dict[str, Any]] = []
    tid = 0

    # --- C9101: first-use payee, large amount (impersonation scam) ---
    customers.append(
        _customer(
            "C9101",
            "Olivia Hughes",
            as_of - timedelta(days=400),
        )
    )
    txns.append(
        _txn(
            tid,
            "C9101",
            1500,
            as_of - timedelta(hours=6),
            direction="out",
            payee_first_use=True,
            customer_session_id="SESS-C9101-1",
            counterparty_name="HMRC Refund Dept",
        )
    )
    tid += 1

    # --- C9102: vulnerable customer, atypical large payment ---
    customers.append(
        _customer(
            "C9102",
            "Margaret Wallace",
            as_of - timedelta(days=900),  # long-tenured
            risk_rating="low",
            vulnerable_customer_flag=True,
            # p95 chosen so background noise (<= £4,800 here) cannot
            # satisfy amount >= 5 * p95 — keeps this the only true match.
            typical_payment_size_p95=Decimal("1000.00"),
        )
    )
    txns.append(
        _txn(
            tid,
            "C9102",
            6000,  # 6x p95
            as_of - timedelta(hours=14),
            direction="out",
            customer_session_id="SESS-C9102-1",
            counterparty_name="Safe Account Holdings",
        )
    )
    tid += 1

    # --- C9103: Confirmation-of-Payee mismatch with override ---
    customers.append(
        _customer(
            "C9103",
            "Jacob Patterson",
            as_of - timedelta(days=200),
        )
    )
    for day_offset, amt in [(2, 150), (4, 200)]:
        txns.append(
            _txn(
                tid,
                "C9103",
                amt,
                as_of - timedelta(days=day_offset, hours=10),
                direction="out",
                confirmation_of_payee_status="no_match",
                customer_session_id=f"SESS-C9103-{day_offset}",
                counterparty_name="Unverified Payee",
            )
        )
        tid += 1

    # --- C9104: rapid pass-through mule (PSP-switching, opened < 30d) ---
    customers.append(
        _customer(
            "C9104",
            "Mule Vector Ltd",
            as_of - timedelta(days=12),  # PSP-switching signal — opened < 30 days
        )
    )
    pass_in = as_of - timedelta(days=1, hours=12)
    txns.append(
        _txn(
            tid,
            "C9104",
            2000,
            pass_in,
            direction="in",
            counterparty_name="Victim Source",
        )
    )
    tid += 1
    txns.append(
        _txn(
            tid,
            "C9104",
            1700,  # 85% pass-through, 30 min later
            pass_in + timedelta(minutes=30),
            direction="out",
            customer_session_id="SESS-C9104-1",
            counterparty_name="Onward Mule",
        )
    )
    tid += 1

    # --- C9105-C9129: benign background faster-payments volume ---
    # Lone txns spread over customers/time (RNG-free; indexed by tid).
    # Amounts capped well under any rule threshold and never carry the
    # APP signal flags, so they stay rule-inert.
    _BG_AMOUNTS = [80, 175, 320, 610, 940, 1450]
    bg_ids = [f"C{9100 + i:04d}" for i in range(5, 30)]
    for n, cid in enumerate(bg_ids):
        customers.append(
            _customer(
                cid,
                f"Retail Customer {n + 5}",
                as_of - timedelta(days=250 + n * 4),
                risk_rating="low",
            )
        )
        for k in range(2):
            txns.append(
                _txn(
                    tid,
                    cid,
                    _BG_AMOUNTS[tid % len(_BG_AMOUNTS)],
                    as_of - timedelta(days=(tid % 40) + 1, hours=11),
                    direction="in" if k == 0 else "out",
                    confirmation_of_payee_status="match",
                    counterparty_name=f"Known Payee {tid % 12}",
                )
            )
            tid += 1

    return {"customer": customers, "txn": txns}
