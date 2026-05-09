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
    payee_first_use: bool = False,
    customer_session_id: str = "",
    confirmation_of_payee_status: str = "",
    invoice_id: str | None = None,
    invoice_amount: Decimal | None = None,
    declared_unit_price: Decimal | None = None,
    declared_quantity: int | None = None,
    hs_code: str | None = None,
    counterparty_id: str | None = None,
) -> dict[str, Any]:
    """Build a single transaction dict with deterministic shape.

    Wire / SEPA / e_transfer channels get auto-populated ISO 20022 fields
    (purpose_code, uetr, debtor_bic, creditor_bic, counterparty_country)
    so the dashboard exercises Round-5/6 rules on default invocations.
    Other channels get empty strings for those fields — preserves
    schema shape (the EU spec's `txn` contract declares `purpose_code`
    as nullable).

    `payee_first_use`, `customer_session_id`, `confirmation_of_payee_status`
    are UK-APP-fraud signals (uk_app_fraud spec). Defaults are
    rule-inert — `payee_first_use=False`, empty CoP status — so
    background noise txns don't accidentally trip the APP rules.

    `invoice_id`, `invoice_amount`, `declared_unit_price`,
    `declared_quantity`, `hs_code` are TBML signals (trade_based_ml
    spec). Defaults are None so background noise stays rule-inert
    (all TBML rules require these fields populated AND
    `purpose_code='TRAD'`).

    `counterparty_id` identifies the other side of the txn — a payee
    (when direction='out') or originator (when direction='in'). The
    us_rtp_fednow spec's `data_contract` declares this column nullable
    and three of its rules use it: `unusual_send_hour_for_customer_rtp`
    SELECTs it for evidence; `first_use_payee_large_amount_rtp` and
    `ramp_up_then_drain_rtp` GROUP BY (customer_id, counterparty_id)
    so multi-counterparty fan-out structure stays separable. Default
    is None — background noise generators populate a stable pool
    value so groupings remain meaningful without nudging unrelated
    rules.
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
        "payee_first_use": payee_first_use,
        "customer_session_id": customer_session_id,
        "confirmation_of_payee_status": confirmation_of_payee_status,
        "invoice_id": invoice_id,
        "invoice_amount": invoice_amount,
        "declared_unit_price": declared_unit_price,
        "declared_quantity": declared_quantity,
        "hs_code": hs_code,
        "counterparty_id": counterparty_id,
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
    vulnerable_customer_flag: bool = False,
    typical_payment_size_p95: Decimal | None = None,
    trade_lic_number: str | None = None,
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
        "vulnerable_customer_flag": vulnerable_customer_flag,
        "typical_payment_size_p95": typical_payment_size_p95,
        "trade_lic_number": trade_lic_number,
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
    # A small pool of recurring counterparties keeps `group_by [customer_id,
    # counterparty_id]` rules (us_rtp_fednow's first_use + ramp_up) on a
    # stable group structure across seeds — same counterparties get reused
    # so noise rows don't each look like a brand-new payee. Picked by
    # `tid % len(pool)` (not random.choice) to avoid consuming from the
    # global RNG state — that would shift every downstream channel/amount
    # draw and cascade-break tests that pin specific synthetic shapes.
    _NOISE_COUNTERPARTIES = [f"CP-NOISE-{i:03d}" for i in range(20)]
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
                counterparty_id=_NOISE_COUNTERPARTIES[tid % len(_NOISE_COUNTERPARTIES)],
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
    #
    # Cross-spec contamination guard: same pattern as the trade-based-ML
    # guard below. C0012's $7,500 RTP send (recent window) plus 4 weeks
    # of background noise pushes uk_bank's `unusual_volume_spike` over
    # its 5× ratio threshold — verified at seed=42. The same all-txn
    # group_by-customer aggregate exists in canadian_schedule_i_bank,
    # canadian_bank, and community_bank specs. Stripping noise for the
    # RTP/BOI plant ids isolates them so non-RTP specs see only the
    # planted shape, which is rule-inert for them.
    _rtp_boi_customer_ids = {"C0012", "C0013", "C0014", "C0015", "C0023"}
    txns = [t for t in txns if t["customer_id"] not in _rtp_boi_customer_ids]

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
        # Single $7,500 RTP send to a never-before-paid counterparty.
        # Anchored at hour=1 of the most recent local day before as_of
        # so the booked_at sits inside `first_use_payee_large_amount_
        # rtp`'s 1d sliding window `[as_of - 24h, as_of)` AND its hour
        # is unconditionally outside the 9-17 typical_send_window
        # (which `unusual_send_hour_for_customer_rtp` checks). A naive
        # `as_of - timedelta(hours=23)` only works when as_of itself
        # is in the early hours; for an as_of at, say, 15:00 UTC,
        # `-23h` lands at hour=16 — inside the typical window — and
        # the unusual-hour rule silently doesn't fire.
        c0012_send_at = as_of.replace(hour=1, minute=0, second=0, microsecond=0)
        if c0012_send_at >= as_of:
            c0012_send_at -= timedelta(days=1)
        txns.append(
            _make_txn(
                tid,
                "C0012",
                7500,
                c0012_send_at,
                channel="rtp",
                direction="out",
                counterparty_country="US",
                debtor_country="US",
                # Distinct, never-before-paid counterparty — that's the
                # "first-use payee" signal first_use_payee_large_amount_rtp
                # is meant to catch.
                counterparty_id="CP-NEW-2026-001",
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
        # 6 small inbound RTP credits inside one hour —
        # velocity_spike_on_receive_rtp uses a 1h sliding window
        # `[as_of - 1h, as_of)`, so the burst must end before as_of.
        # Earlier `-1d -14h` was 38h back, far outside that window;
        # this places the burst in the last 55 minutes (final credit
        # at as_of - 15min so all six are strictly < as_of).
        burst_start = as_of - timedelta(minutes=55)
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

    # --- C0023: RTP ramp-up then drain (small priming sends to one payee) ---
    # `ramp_up_then_drain_rtp` (us_rtp_fednow) filters direction=out, channel
    # in [rtp,fednow], amount < 500; groups by (customer_id, counterparty_id);
    # window 14d; having count >= 3 AND sum_amount >= 1000. Plant 4 small RTP
    # sends to one counterparty totaling $1,550 over 5 days inside the 14d
    # window.
    #
    # Intentional cross-rule firing: cyber_enabled_fraud's `ramp_up_then_drain`
    # rule (no channel filter) is a strict superset of the RTP variant, so
    # this same plant fires it too. That's correct typology coverage —
    # cyber_enabled_fraud previously had zero planted positives — not a leak.
    # If you ever need C0023 to fire ONLY the RTP variant, the architecture
    # can't help: any plant matching the subset rule matches the superset.
    if n_customers > 23:
        customers[23] = _customer_row(
            fake,
            "C0023",
            as_of - timedelta(days=120),  # mid-life account, plausible profile
            country="US",
            risk_rating="medium",
            full_name="Ramp Source LLC",
        )
        ramp_counterparty = "CP-RAMP-2026-001"
        for day_offset, amt in [(2, 300), (4, 400), (7, 450), (10, 400)]:
            txns.append(
                _make_txn(
                    tid,
                    "C0023",
                    amt,
                    as_of - timedelta(days=day_offset, hours=14),
                    channel="rtp",
                    direction="out",
                    counterparty_country="US",
                    debtor_country="US",
                    counterparty_id=ramp_counterparty,
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

    # ---------------------------------------------------------------------
    # UK APP-fraud planted positives (uk_app_fraud spec)
    # ---------------------------------------------------------------------
    # Each customer is shaped to trip exactly one of uk_app_fraud's four
    # rules. Without these markers `aml run examples/uk_app_fraud/...`
    # against synthetic data fires zero alerts — the same MRM-trustability
    # gap the Round-8/9 RTP positives (C0012/C0013) closed for us_rtp_fednow.
    #
    # Cross-spec contamination guard: each plant is GBP/faster_payments,
    # which is rule-inert for non-UK specs at face value. But the random
    # noise loop generates 4 weeks of background activity for these
    # customer ids, and the all-txn `unusual_volume_spike` aggregate in
    # uk_bank, canadian_schedule_i_bank, canadian_bank, and community_bank
    # (no channel/currency filter, fires when `recent_sum >= 5000 AND
    # recent > baseline_avg * 5`) flips on certain seeds — verified at
    # seed=7 where C0019 trips uk_bank's unusual_volume_spike. Clearing
    # the noise-loop's pre-existing rows for these ids isolates the
    # plants: with no baseline activity, the spike-ratio comparison
    # evaluates NULL and the rule can't fire on non-UK specs. Within-
    # spec uk_app_fraud rules don't depend on baseline (all four are
    # amount/flag/timing-based), so this doesn't weaken the within-spec
    # coverage.
    _uk_app_fraud_customer_ids = {"C0016", "C0017", "C0018", "C0019"}
    txns = [t for t in txns if t["customer_id"] not in _uk_app_fraud_customer_ids]

    # --- C0016: APP first-use payee, large amount (impersonation scam) ---
    if n_customers > 16:
        customers[16] = _customer_row(
            fake,
            "C0016",
            as_of - timedelta(days=400),
            country="GB",
            risk_rating="medium",
            full_name="Olivia Hughes",
        )
        # Single £1,500 outbound to a never-paid-before counterparty in
        # the last 24h — clears the rule's amount ≥ £1,000 threshold.
        txns.append(
            _make_txn(
                tid,
                "C0016",
                1500,
                as_of - timedelta(hours=6),
                channel="faster_payments",
                direction="out",
                currency="GBP",
                payee_first_use=True,
                customer_session_id="SESS-C0016-1",
            )
        )
        tid += 1

    # --- C0017: vulnerable customer, atypical large payment ---
    if n_customers > 17:
        customers[17] = _customer_row(
            fake,
            "C0017",
            as_of - timedelta(days=900),  # long-tenured account
            country="GB",
            risk_rating="low",
            full_name="Margaret Wallace",
            vulnerable_customer_flag=True,
            # p95 chosen so the noise-loop's max outbound amount (£4,800)
            # cannot satisfy `amount >= 5 * p95` — keeps the planted
            # positive the only true match. Reviewed in PR review.
            typical_payment_size_p95=Decimal("1000.00"),
        )
        # Single £6,000 outbound — 6× typical_payment_size_p95, well
        # above the rule's `amount >= 5 * p95 AND amount >= 500` floor
        # while staying within a realistic life-savings-handover scam scale.
        txns.append(
            _make_txn(
                tid,
                "C0017",
                6000,
                as_of - timedelta(hours=14),
                channel="faster_payments",
                direction="out",
                currency="GBP",
                customer_session_id="SESS-C0017-1",
            )
        )
        tid += 1

    # --- C0018: Confirmation-of-Payee mismatch with override ---
    if n_customers > 18:
        customers[18] = _customer_row(
            fake,
            "C0018",
            as_of - timedelta(days=200),
            country="GB",
            risk_rating="medium",
            full_name="Jacob Patterson",
        )
        # Two £150–£200 outbound payments in the last 7d, both with
        # `confirmation_of_payee_status=no_match` — the customer
        # overrode the CoP warning and proceeded anyway.
        for day_offset, amt in [(2, 150), (4, 200)]:
            txns.append(
                _make_txn(
                    tid,
                    "C0018",
                    amt,
                    as_of - timedelta(days=day_offset, hours=10),
                    channel="faster_payments",
                    direction="out",
                    currency="GBP",
                    confirmation_of_payee_status="no_match",
                    customer_session_id=f"SESS-C0018-{day_offset}",
                )
            )
            tid += 1

    # --- C0019: rapid pass-through (mule pattern within 1h) ---
    if n_customers > 19:
        customers[19] = _customer_row(
            fake,
            "C0019",
            as_of - timedelta(days=15),  # newish account, mule signal
            country="GB",
            risk_rating="medium",
            full_name="Mule Vector Ltd",
        )
        # Inbound £2,000 → outbound £1,700 (85% pass-through) within
        # 30 minutes. Both legs clear the £500 floor. Distinct
        # counterparties on each leg — the originator on the inbound
        # is a different party than the payee on the outbound (that's
        # what makes it a pass-through, not a self-transfer).
        pass_in = as_of - timedelta(days=1, hours=12)
        txns.append(
            _make_txn(
                tid,
                "C0019",
                2000,
                pass_in,
                channel="faster_payments",
                direction="in",
                currency="GBP",
                counterparty_id="CP-MULE-IN-2026-001",
            )
        )
        tid += 1
        txns.append(
            _make_txn(
                tid,
                "C0019",
                1700,
                pass_in + timedelta(minutes=30),
                channel="faster_payments",
                direction="out",
                currency="GBP",
                customer_session_id="SESS-C0019-1",
                counterparty_id="CP-MULE-OUT-2026-001",
            )
        )
        tid += 1

    # ---------------------------------------------------------------------
    # Trade-based ML planted positives (trade_based_ml spec)
    # ---------------------------------------------------------------------
    # Three planted customers cover three TBML rules: over-invoicing,
    # phantom shipping, and multiple invoicing. Rules 2 (under-invoicing)
    # and 5 (TRAD-to-high-risk-jurisdiction) are out of scope for this
    # PR — easy to extend later by planting C0023+ with the appropriate
    # shape. The hs_code_baseline reference table is required by rules
    # 1 and 2 (they JOIN on hs_code).
    #
    # Cross-spec contamination guard (caught in Codex review): each
    # planted trade wire is ≥$20k, which trips community_bank's
    # `dormant_account_activity` rule (`recent_large >= $10k joined
    # against any prior last_activity`). Clearing the random noise
    # loop's pre-existing rows for these customer ids isolates the
    # plants — the dormant rule's CTE join finds no `last_activity`
    # for them, so it doesn't fire on default community_bank runs.
    _trade_customer_ids = {"C0020", "C0021", "C0022"}
    txns = [t for t in txns if t["customer_id"] not in _trade_customer_ids]

    # --- C0020: over-invoicing (declared_unit_price ≥ 3× WCO median) ---
    if n_customers > 20:
        customers[20] = _customer_row(
            fake,
            "C0020",
            as_of - timedelta(days=400),
            country="US",
            risk_rating="medium",
            full_name="Apex Imports LLC",
            business_activity="import_export",
            trade_lic_number="US-IMP-2024-A0020",
        )
        # 2 trade payments with declared_unit_price = $2,000 (4× the
        # $500 baseline median for hs_code 8471.30 — consumer
        # electronics). Sum of `amount` >= $25k clears the rule's
        # `HAVING SUM >= 25000` threshold.
        for day_offset, qty in [(5, 10), (12, 10)]:
            txns.append(
                _make_txn(
                    tid,
                    "C0020",
                    20000,
                    as_of - timedelta(days=day_offset, hours=11),
                    channel="wire",
                    direction="out",
                    purpose_code="TRAD",
                    counterparty_country="DE",
                    invoice_id=f"INV-C0020-{day_offset:03d}",
                    invoice_amount=Decimal("20000.00"),
                    declared_unit_price=Decimal("2000.00"),  # 4× baseline median $500
                    declared_quantity=qty,
                    hs_code="8471.30",
                )
            )
            tid += 1

    # --- C0021: phantom shipping (TRAD payment with no invoice_id) ---
    if n_customers > 21:
        customers[21] = _customer_row(
            fake,
            "C0021",
            as_of - timedelta(days=300),
            country="US",
            risk_rating="medium",
            full_name="Vanguard Trading Corp",
            business_activity="wholesale",
            trade_lic_number="US-WHL-2024-V0021",
        )
        # 3 outbound TRAD payments without invoice_id, summing $60k
        # over 25 days — clears `count >= 3 AND sum_amount >= 50000`.
        for day_offset, amt in [(3, 22000), (10, 18000), (20, 20000)]:
            txns.append(
                _make_txn(
                    tid,
                    "C0021",
                    amt,
                    as_of - timedelta(days=day_offset, hours=14),
                    channel="wire",
                    direction="out",
                    purpose_code="TRAD",
                    counterparty_country="HK",
                    # invoice_id intentionally None — this is the rule signal.
                )
            )
            tid += 1

    # --- C0022: multiple invoicing (same invoice_id paid twice) ---
    if n_customers > 22:
        customers[22] = _customer_row(
            fake,
            "C0022",
            as_of - timedelta(days=250),
            country="US",
            risk_rating="medium",
            full_name="Continental Trade Group",
            business_activity="commodities",
            trade_lic_number="US-COM-2024-C0022",
        )
        # Same invoice_id paid twice within a week — Egmont T-07.
        dup_invoice = "INV-DUP-2026-04-001"
        for day_offset, amt in [(2, 30000), (8, 30000)]:
            txns.append(
                _make_txn(
                    tid,
                    "C0022",
                    amt,
                    as_of - timedelta(days=day_offset, hours=10),
                    channel="wire",
                    direction="out",
                    purpose_code="TRAD",
                    counterparty_country="SG",
                    invoice_id=dup_invoice,
                    invoice_amount=Decimal("30000.00"),
                )
            )
            tid += 1

    # ---------------------------------------------------------------------
    # HS-code baseline reference table (trade_based_ml spec)
    # ---------------------------------------------------------------------
    # Five representative HS codes with median + p5 + p95 unit prices
    # sourced from World Customs Organization summary data. Rules 1 and
    # 2 JOIN on hs_code, so without these baseline rows over/under-
    # invoicing alerts can't fire. Other specs ignore this contract.
    hs_code_baseline: list[dict[str, Any]] = [
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
            "hs_code": "8703.21",  # passenger motor vehicles ≤1.0L
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

    return {
        "customer": customers,
        "txn": txns,
        "txn_return": txn_returns,
        "hs_code_baseline": hs_code_baseline,
    }
