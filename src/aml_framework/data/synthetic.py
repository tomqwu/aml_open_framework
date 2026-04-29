"""Synthetic dataset generator for demos and tests.

Injects known-positive scenarios so the demo produces alerts for multiple
typologies without depending on randomness. The remaining volume is noise that
should NOT trigger the reference rules.

ISO 20022 enrichment (Round 5/6 surface)
- Wire / SEPA / e_transfer txns get optional `purpose_code`, `uetr`,
  `debtor_bic`, `creditor_bic`, `counterparty_country` fields populated
  so the dashboard exercises Round-5 rules (FATF R.16 travel-rule
  validator, INVS purpose-code velocity, etc.) on default `aml run`
  invocations. Cash / ACH / card stay unchanged.
- A separate `txn_return` list is also emitted, carrying pacs.004
  return events that compose with the Round-5 #5 return-reason mining
  library. Operators using only the base `txn` contract ignore it.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from faker import Faker

_CHANNELS = ["cash", "wire", "ach", "card"]
_COUNTRIES = ["US", "CA", "GB", "DE", "MX"]

# Channels that carry ISO 20022 metadata in real banking flows.
_ISO20022_CHANNELS = frozenset({"wire", "sepa", "e_transfer"})

# ExternalPurpose1Code distribution for noise wires — biased toward
# benign codes so planted INVS positives are clearly anomalous.
_PURPOSE_CODE_NOISE = ["GDDS", "SUPP", "SALA", "GDDS", "GDDS", "SUPP", "INTC", "TAXS"]

# BIC codes for synthetic counterparties — real-format strings (8 or 11
# chars) keyed to bank/country so the Travel Rule validator sees them
# as well-formed.
_BICS = {
    "US": ["CHASUS33XXX", "BOFAUS3NXXX", "CITIUS33XXX"],
    "CA": ["ROYCCAT2XXX", "BOFMCAM2XXX", "TDOMCATTXXX"],
    "GB": ["HBUKGB4BXXX", "BARCGB22XXX", "NWBKGB2LXXX"],
    "DE": ["DEUTDEFFXXX", "COBADEFFXXX"],
    "FR": ["BNPAFRPPXXX", "CRLYFRPPXXX"],
    "CH": ["UBSWCHZH80A", "CRESCHZZ80A"],
    "RU": ["SABRRUMMXXX"],
    "MX": ["BNMXMXMMXXX"],
}


def _bic_for(country: str) -> str:
    pool = _BICS.get(country, ["UNKNOWNXXX"])
    return random.choice(pool)


def _iso20022_enrichment(
    *,
    channel: str,
    direction: str,
    debtor_country: str,
    counterparty_country: str | None = None,
    purpose_code: str | None = None,
) -> dict[str, Any]:
    """Generate ISO 20022 fields appropriate for a given channel.

    Wire / SEPA / e_transfer get a UETR + originator/beneficiary BICs +
    purpose code. Other channels get empty strings (the EU spec's
    `purpose_code` column is nullable; rules degrade gracefully).
    """
    if channel not in _ISO20022_CHANNELS:
        return {
            "purpose_code": "",
            "uetr": "",
            "debtor_bic": "",
            "creditor_bic": "",
            "counterparty_country": counterparty_country or "",
        }
    cp_country = counterparty_country or random.choice(["US", "CA", "GB", "DE", "FR"])
    debtor_bic, creditor_bic = (
        (_bic_for(debtor_country), _bic_for(cp_country))
        if direction == "out"
        else (_bic_for(cp_country), _bic_for(debtor_country))
    )
    return {
        "purpose_code": purpose_code or random.choice(_PURPOSE_CODE_NOISE),
        # Deterministic UETR (uuid5 from a stable namespace + counter is
        # reproducible across runs since random.seed governs the caller).
        "uetr": str(uuid.UUID(int=random.getrandbits(128), version=4)),
        "debtor_bic": debtor_bic,
        "creditor_bic": creditor_bic,
        "counterparty_country": cp_country,
    }


def _make_txn(
    tid: int,
    customer_id: str,
    amount,
    booked_at: datetime,
    *,
    channel: str = "cash",
    direction: str = "in",
    currency: str = "USD",
    purpose_code: str | None = None,
    counterparty_country: str | None = None,
    debtor_country: str = "US",
) -> dict[str, Any]:
    """Build a single transaction dict with deterministic shape.

    Wire / SEPA / e_transfer channels get auto-populated ISO 20022 fields
    (purpose_code, uetr, debtor_bic, creditor_bic, counterparty_country)
    so the dashboard exercises Round-5/6 rules on default invocations.
    Other channels get empty strings for those fields — preserves
    schema shape (the EU spec's `txn` contract declares `purpose_code`
    as nullable).
    """
    iso = _iso20022_enrichment(
        channel=channel,
        direction=direction,
        debtor_country=debtor_country,
        counterparty_country=counterparty_country,
        purpose_code=purpose_code,
    )
    return {
        "txn_id": f"T{tid:08d}",
        "customer_id": customer_id,
        "amount": Decimal(amount).quantize(Decimal("0.01")),
        "currency": currency,
        "channel": channel,
        "direction": direction,
        "booked_at": booked_at,
        **iso,
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

    # --- Planted positive: INVS-velocity (pig-butchering) by C0010. ---
    # 3 outbound wires with purpose_code=INVS to a CH offshore vehicle
    # within 14 days, sum > $5k — triggers eu_bank's
    # `invs_velocity_investment_scam` rule. Compose with FATF's Feb 2026
    # Cyber-Enabled Fraud paper which calls out INVS misuse as the
    # canonical pig-butchering payout marker.
    if n_customers > 10:
        customers[10] = _customer_row(
            fake,
            "C0010",
            as_of - timedelta(days=180),
            country="DE",
            risk_rating="medium",
            full_name="Klara Becker",
        )
        for day_offset, amt in [(2, 2500), (5, 3000), (10, 2800)]:
            txns.append(
                _make_txn(
                    tid,
                    "C0010",
                    amt,
                    as_of - timedelta(days=day_offset, hours=14),
                    channel="wire",
                    direction="out",
                    currency="EUR",
                    purpose_code="INVS",
                    counterparty_country="CH",
                    debtor_country="DE",
                )
            )
            tid += 1

    # --- pacs.004 return events (Round-5 #5) ---
    # Mule-probing pattern: 3 returns from one originator (C0011) within
    # one week with high-risk reason codes (AC03/AC04/MD07). Triggers
    # the `high_risk_return_burst_mule_probing` snippet from
    # spec/library/iso20022_return_reasons.yaml when an operator drops
    # that snippet into their spec + populates the txn_return contract.
    txn_returns: list[dict[str, Any]] = []
    if n_customers > 11:
        customers[11] = _customer_row(
            fake,
            "C0011",
            as_of - timedelta(days=400),
            country="GB",
            risk_rating="medium",
            full_name="ROAMR LTD",
        )
        return_id = 0
        for day_offset, code, amt, info in [
            (2, "AC03", 12000, "Invalid creditor account number"),
            (4, "AC04", 9500, "Closed creditor account"),
            (5, "MD07", 7800, "End-customer deceased"),
        ]:
            return_id += 1
            txn_returns.append(
                {
                    "return_id": f"RTR-{return_id:03d}",
                    "original_uetr": str(uuid.UUID(int=random.getrandbits(128), version=4)),
                    "original_end_to_end_id": f"ROAMR-2026-04-{20 + day_offset}-A",
                    "original_tx_id": f"ORIG-{return_id}",
                    "amount": Decimal(amt).quantize(Decimal("0.01")),
                    "currency": "EUR",
                    "returned_at": as_of - timedelta(days=day_offset, hours=10),
                    "reason_code": code,
                    "reason_info": info,
                    "originator_name": "ROAMR LTD",
                    "originator_country": "GB",
                    "beneficiary_name": f"SHELL VEHICLE {return_id}",
                    "beneficiary_country": "CH",
                    "msg_id": "RTR-2026-04-20-001",
                    "msg_kind": "pacs.004",
                }
            )

    # ---------------------------------------------------------------------
    # Round-8/9 planted positives — RTP/FedNow + BOI workflow
    # ---------------------------------------------------------------------
    # These exist so the new specs (us_rtp_fednow, BOI page) ship with
    # ground-truth signal in the synthetic dataset. Without these, tuning
    # and backtest scores against the new rules read as 0/0 — the very
    # MRM-trustability problem PR-G is meant to fix.
    #
    # All planted RTP customers carry a `typical_send_window_*_hour`
    # so the unusual-time-for-customer rule has a baseline to compare
    # against. Their flagged transactions are deliberately outside
    # that window.

    # --- C0012: RTP first-use-payee large amount (push-fraud drain) ---
    if n_customers > 12:
        customers[12] = _customer_row(
            fake,
            "C0012",
            as_of - timedelta(days=600),
            country="US",
            risk_rating="medium",
            full_name="Daniel Park",
        )
        customers[12]["typical_send_window_start_hour"] = 9
        customers[12]["typical_send_window_end_hour"] = 17
        # Single $7,500 RTP send to a never-before-paid counterparty,
        # at 23:00 (outside typical window) — fires both
        # first_use_payee_large_amount_rtp and unusual_send_hour.
        txns.append(
            _make_txn(
                tid,
                "C0012",
                7500,
                as_of - timedelta(days=1, hours=1),  # 23:00 the day before
                channel="rtp",
                direction="out",
                counterparty_country="US",
                debtor_country="US",
            )
        )
        tid += 1

    # --- C0013: RTP velocity spike on receive (mule pattern) ---
    if n_customers > 13:
        customers[13] = _customer_row(
            fake,
            "C0013",
            as_of - timedelta(days=20),  # newish account, classic mule signal
            country="US",
            risk_rating="medium",
            full_name="Mule Ventures LLC",
            business_activity="financial_services",  # also makes BOI relevant
        )
        # 6 small inbound RTP credits inside one hour — velocity_spike_on_receive_rtp
        burst_start = as_of - timedelta(days=1, hours=14)
        for i, amt in enumerate([400, 350, 480, 410, 390, 460]):
            txns.append(
                _make_txn(
                    tid,
                    "C0013",
                    amt,
                    burst_start + timedelta(minutes=i * 8),
                    channel="rtp",
                    direction="in",
                )
            )
            tid += 1

    # --- C0014: BOI missing — entity customer with no review on file ---
    if n_customers > 14:
        customers[14] = _customer_row(
            fake,
            "C0014",
            as_of - timedelta(days=200),
            country="US",
            risk_rating="medium",
            full_name="Cresent Holdings Inc",
            business_activity="real_estate_holding",
            edd_last_review=None,  # explicitly missing — drives BOI status=missing
        )

    # --- C0015: BOI stale — entity reviewed long ago ---
    if n_customers > 15:
        customers[15] = _customer_row(
            fake,
            "C0015",
            as_of - timedelta(days=900),
            country="US",
            risk_rating="medium",
            full_name="Northway Imports Inc",
            business_activity="import_export",
            edd_last_review=as_of - timedelta(days=500),  # past 365-day default
        )

    return {"customer": customers, "txn": txns, "txn_return": txn_returns}
