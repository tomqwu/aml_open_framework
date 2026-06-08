"""Spec-specific synthetic dataset for the ``us_rtp_fednow`` example.

Planted-positive demo data for the US instant-payments push-fraud spec
(``program.name = us_rtp_fednow_push_fraud``). Modelled on
``data/synthetic.py`` — deterministic, seed-pinned, stdlib only (no
faker / pandas / numpy), no ``datetime.now()``.

Customer IDs live in a dedicated **C9001-C9029** band so the RTP demo
is cleanly isolated from the shared community-bank C0xxx band: a
prospective RTP user sees ONLY RTP/FedNow typologies, not 60
community-bank customers.

Planted typologies (each trips exactly the named rule in
``examples/us_rtp_fednow/aml.yaml``):

* **first_use_payee_large_amount_rtp** — C9001 sends one $7,500 RTP to
  a never-before-paid counterparty in the last 24h (>= $1,000 floor).
* **velocity_spike_on_receive_rtp** — C9002 (newish mule account)
  receives 6 small RTP credits inside the final hour (count >= 5).
* **ramp_up_then_drain_rtp** — C9003 makes 4 priming RTP sends < $500
  to one counterparty over 10 days summing $1,550 (count >= 3,
  sum >= $1,000).
* **mule_receiver_fan_out_rtp** — C9004-C9007 (network_pattern):
  four mule accounts opened from the same ``device_id`` (component
  size >= 4) — a shared-device mule herd.
* **unusual_send_hour_for_customer_rtp** — C9001's $7,500 send is
  anchored at 01:00 local, outside its 09:00-17:00
  ``typical_send_window`` (custom_sql, amount >= $500).

The remaining slots (C9008-C9029) are benign background RTP/FedNow
activity so the dashboard's volume views aren't empty.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

_RTP_CHANNELS = ["rtp", "fednow"]


def _txn(
    tid: int,
    customer_id: str,
    amount: Any,
    booked_at: datetime,
    *,
    channel: str = "rtp",
    direction: str = "out",
    currency: str = "USD",
    counterparty_id: str | None = None,
    counterparty_name: str = "",
    counterparty_bic: str = "",
    cop_match_status: str = "match",
) -> dict[str, Any]:
    """Build one ``txn`` row matching the us_rtp_fednow data contract."""
    return {
        "txn_id": f"T9{tid:07d}",
        "customer_id": customer_id,
        "amount": Decimal(amount).quantize(Decimal("0.01")),
        "currency": currency,
        "channel": channel,
        "direction": direction,
        "booked_at": booked_at,
        "counterparty_id": counterparty_id,
        "counterparty_name": counterparty_name,
        "counterparty_bic": counterparty_bic,
        "cop_match_status": cop_match_status,
    }


def _customer(
    customer_id: str,
    full_name: str,
    onboarded_at: datetime,
    *,
    country: str = "US",
    risk_rating: str = "medium",
    typical_send_window_start_hour: int | None = None,
    typical_send_window_end_hour: int | None = None,
    device_id: str | None = None,
) -> dict[str, Any]:
    """Build one ``customer`` row matching the us_rtp_fednow data contract."""
    return {
        "customer_id": customer_id,
        "full_name": full_name,
        "country": country,
        "risk_rating": risk_rating,
        "onboarded_at": onboarded_at,
        "typical_send_window_start_hour": typical_send_window_start_hour,
        "typical_send_window_end_hour": typical_send_window_end_hour,
        "device_id": device_id,
    }


def generate_rtp_fednow_dataset(
    as_of: datetime,
    seed: int = 42,
) -> dict[str, list[dict[str, Any]]]:
    """Produce ``{customer, txn}`` rows for the us_rtp_fednow spec.

    Deterministic: every amount + time offset is hardcoded (no
    ``random``), so the output depends only on ``as_of``. ``seed`` is
    accepted for signature parity with ``generate_dataset`` and to keep
    the dispatch registry uniform; it does not change the output because
    there is no stochastic draw to seed.
    """
    _ = seed  # signature parity — no stochastic draw to seed
    customers: list[dict[str, Any]] = []
    txns: list[dict[str, Any]] = []
    tid = 0

    # --- C9001: first-use payee large send + unusual-hour anomaly ---
    customers.append(
        _customer(
            "C9001",
            "Daniel Reyes",
            as_of - timedelta(days=600),
            typical_send_window_start_hour=9,
            typical_send_window_end_hour=17,
        )
    )
    # Anchor at 01:00 of the most recent local day before as_of so the
    # send sits inside first_use_payee_large_amount_rtp's 1d window
    # [as_of - 24h, as_of) AND its hour is unconditionally outside the
    # 9-17 typical_send_window the unusual-hour rule checks.
    c9001_send_at = as_of.replace(hour=1, minute=0, second=0, microsecond=0)
    if c9001_send_at >= as_of:
        c9001_send_at -= timedelta(days=1)
    txns.append(
        _txn(
            tid,
            "C9001",
            7500,
            c9001_send_at,
            channel="rtp",
            direction="out",
            counterparty_id="CP-RTP-NEW-001",
            counterparty_name="Romance Contact LLC",
        )
    )
    tid += 1

    # --- C9002: velocity spike on receive (mule pattern) ---
    customers.append(
        _customer(
            "C9002",
            "Mule Ventures LLC",
            as_of - timedelta(days=18),  # newish account — classic mule signal
        )
    )
    # 6 small inbound RTP credits inside the final hour. The rule's 1h
    # sliding window is [as_of - 1h, as_of), so the last credit must be
    # strictly < as_of; place the burst in the last 55 minutes.
    burst_start = as_of - timedelta(minutes=55)
    for i, amt in enumerate([400, 350, 480, 410, 390, 460]):
        txns.append(
            _txn(
                tid,
                "C9002",
                amt,
                burst_start + timedelta(minutes=i * 8),
                channel="rtp",
                direction="in",
                counterparty_id=f"CP-RTP-IN-{i:03d}",
            )
        )
        tid += 1

    # --- C9003: ramp-up then drain (priming sends < $500 to one payee) ---
    customers.append(
        _customer(
            "C9003",
            "Ramp Source LLC",
            as_of - timedelta(days=120),
        )
    )
    for day_offset, amt in [(2, 300), (4, 400), (7, 450), (10, 400)]:
        txns.append(
            _txn(
                tid,
                "C9003",
                amt,
                as_of - timedelta(days=day_offset, hours=14),
                channel="rtp",
                direction="out",
                counterparty_id="CP-RTP-RAMP-001",
            )
        )
        tid += 1

    # --- C9004-C9007: mule-receiver fan-out (network_pattern) ---
    # Four mules opened from the same device_id — component_size >= 4.
    mule_device = "DEV-RTP-MULE-001"
    for mule_idx, mule_id in enumerate(("C9004", "C9005", "C9006", "C9007")):
        customers.append(
            _customer(
                mule_id,
                f"Mule Ring Member {mule_idx + 1}",
                as_of - timedelta(days=10 + mule_idx),  # all newish
                device_id=mule_device,
            )
        )
        # One small RTP credit per mule so the case panel has evidence
        # rows — not enough to trip velocity_spike (count < 5 each).
        txns.append(
            _txn(
                tid,
                mule_id,
                Decimal("250.00") + Decimal(mule_idx * 50),
                as_of - timedelta(hours=3 + mule_idx),
                channel="rtp",
                direction="in",
                counterparty_id=f"CP-RTP-RING-{mule_idx + 1:02d}",
            )
        )
        tid += 1

    # --- C9008-C9029: benign background RTP/FedNow volume (RNG-free) ---
    # Lone txns spread over customers/time so the rail columns aren't
    # sparse. Indexed by `tid` (no random.*) so the output is purely a
    # function of `as_of`. Amounts/shapes never aggregate into any
    # rule's count/sum thresholds (rule-inert).
    _BG_AMOUNTS = [120, 260, 540, 880, 1300, 2100]
    bg_ids = [f"C{9000 + i:04d}" for i in range(8, 30)]
    for n, cid in enumerate(bg_ids):
        customers.append(
            _customer(
                cid,
                f"Retail Customer {n + 8}",
                as_of - timedelta(days=200 + n * 5),
                risk_rating="low",
                typical_send_window_start_hour=8,
                typical_send_window_end_hour=20,
            )
        )
        # 2 benign in/out txns. Anchor the timestamp at 12:00 of a past
        # day (construct the date, then force hour=12) so it sits inside
        # every background customer's 08:00-20:00 typical_send_window and
        # the unusual-hour rule stays quiet for background customers,
        # regardless of `as_of`'s own hour.
        bg_day = (as_of - timedelta(days=(tid % 40) + 1)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        for k in range(2):
            txns.append(
                _txn(
                    tid,
                    cid,
                    _BG_AMOUNTS[tid % len(_BG_AMOUNTS)],
                    bg_day,
                    channel=_RTP_CHANNELS[tid % 2],
                    direction="in" if k == 0 else "out",
                    counterparty_id=f"CP-RTP-BG-{(tid % 12):03d}",
                )
            )
            tid += 1

    return {"customer": customers, "txn": txns}
