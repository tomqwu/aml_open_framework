"""Tests for the spec-specific planted-positive generators (#522).

Three newer specs (us_rtp_fednow, uk_app_fraud, trade_based_ml) serve
their own isolated C9xxx planted-positive band instead of inheriting the
shared community-bank C0xxx dataset. These tests guard:

1. **Determinism** — same `as_of` -> identical output (no RNG, no
   `datetime.now()`).
2. **Dispatch wiring** — `generate_dataset_for_spec` routes each spec to
   its dedicated generator by `program.name`, and every UNregistered
   spec falls back to the shared community-bank `generate_dataset`
   byte-identically.
3. **Per-typology coverage** — each planted shape produces the expected
   rows AND each spec fires >= 1 alert per planted typology end-to-end
   through `run_spec`.

If a contributor edits a generator and breaks a planted marker, the
spec's demo + tuning + backtest scores silently regress — these tests
fail loudly first.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from aml_framework.cli import app
from aml_framework.data import (
    generate_dataset,
    generate_dataset_for_spec,
    generate_rtp_fednow_dataset,
    generate_trade_based_ml_dataset,
    generate_uk_app_fraud_dataset,
)
from aml_framework.engine.backtest import BacktestPeriod, _make_default_data_loader
from aml_framework.engine.runner import run_spec
from aml_framework.spec.loader import load_spec

_EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
AS_OF = datetime(2026, 6, 1, 12, 0, 0)


def _alerts_by_rule(spec_path: Path, data, tmp_path) -> dict[str, int]:
    spec = load_spec(spec_path)
    result = run_spec(
        spec=spec,
        spec_path=spec_path,
        data=data,
        as_of=AS_OF,
        artifacts_root=tmp_path,
    )
    # `result.alerts` is a dict[rule_id, list[alert]].
    return {rule_id: len(rows) for rule_id, rows in result.alerts.items()}


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_generators_are_deterministic() -> None:
    for gen in (
        generate_rtp_fednow_dataset,
        generate_uk_app_fraud_dataset,
        generate_trade_based_ml_dataset,
    ):
        assert gen(as_of=AS_OF, seed=42) == gen(as_of=AS_OF, seed=42)


def test_seed_does_not_change_output() -> None:
    # The generators carry no stochastic draw — `seed` is signature
    # parity only — so changing it must not change the output.
    for gen in (
        generate_rtp_fednow_dataset,
        generate_uk_app_fraud_dataset,
        generate_trade_based_ml_dataset,
    ):
        assert gen(as_of=AS_OF, seed=1) == gen(as_of=AS_OF, seed=999)


# ---------------------------------------------------------------------------
# Dispatch wiring
# ---------------------------------------------------------------------------


def test_dispatch_routes_registered_specs_to_dedicated_generator() -> None:
    cases = {
        "us_rtp_fednow": (generate_rtp_fednow_dataset, "C9001", "C9029"),
        "uk_app_fraud": (generate_uk_app_fraud_dataset, "C9101", "C9129"),
        "trade_based_ml": (generate_trade_based_ml_dataset, "C9201", "C9229"),
    }
    for name, (gen, lo, hi) in cases.items():
        spec = load_spec(_EXAMPLES / name / "aml.yaml")
        dispatched = generate_dataset_for_spec(spec=spec, as_of=AS_OF, seed=42)
        assert dispatched == gen(as_of=AS_OF, seed=42)
        ids = {c["customer_id"] for c in dispatched["customer"]}
        assert lo in ids and hi in ids
        # No community-bank C0xxx contamination.
        assert not any(cid.startswith("C00") for cid in ids)


def test_dispatch_falls_back_to_community_bank_for_unregistered_spec() -> None:
    spec = load_spec(_EXAMPLES / "community_bank" / "aml.yaml")
    dispatched = generate_dataset_for_spec(spec=spec, as_of=AS_OF, seed=42)
    # Byte-identical to the legacy shared generator path.
    assert dispatched == generate_dataset(as_of=AS_OF, seed=42)


# ---------------------------------------------------------------------------
# us_rtp_fednow — planted rows + end-to-end alerts
# ---------------------------------------------------------------------------


def test_rtp_planted_rows() -> None:
    data = generate_rtp_fednow_dataset(as_of=AS_OF)
    cust = {c["customer_id"]: c for c in data["customer"]}

    # C9001 — first-use large send, anchored < as_of inside 24h, hour 1.
    c9001 = [t for t in data["txn"] if t["customer_id"] == "C9001"]
    assert len(c9001) == 1
    send = c9001[0]
    assert send["direction"] == "out" and send["channel"] == "rtp"
    assert send["amount"] >= 1000
    assert send["booked_at"] < AS_OF and (AS_OF - send["booked_at"]) <= timedelta(hours=24)
    assert send["booked_at"].hour == 1  # outside 9-17 typical window
    assert cust["C9001"]["typical_send_window_start_hour"] == 9

    # C9002 — receive-velocity spike: 6 inbound RTP inside the final hour.
    c9002 = [t for t in data["txn"] if t["customer_id"] == "C9002"]
    assert len(c9002) == 6
    assert all(t["direction"] == "in" and t["channel"] == "rtp" for t in c9002)
    assert (AS_OF - min(t["booked_at"] for t in c9002)) <= timedelta(hours=1)

    # C9003 — ramp-up: 4 priming sends < $500 to one counterparty.
    c9003 = [t for t in data["txn"] if t["customer_id"] == "C9003"]
    assert len(c9003) == 4
    assert all(t["amount"] < 500 and t["direction"] == "out" for t in c9003)
    assert len({t["counterparty_id"] for t in c9003}) == 1

    # C9004-C9007 — 4 mules sharing one device_id (component_size >= 4).
    ring = {cust[c]["device_id"] for c in ("C9004", "C9005", "C9006", "C9007")}
    assert ring == {"DEV-RTP-MULE-001"}


def test_rtp_fires_every_typology(tmp_path) -> None:
    data = generate_rtp_fednow_dataset(as_of=AS_OF)
    counts = _alerts_by_rule(_EXAMPLES / "us_rtp_fednow" / "aml.yaml", data, tmp_path)
    for rule in (
        "first_use_payee_large_amount_rtp",
        "velocity_spike_on_receive_rtp",
        "ramp_up_then_drain_rtp",
        "mule_receiver_fan_out_rtp",
        "unusual_send_hour_for_customer_rtp",
    ):
        assert counts.get(rule, 0) >= 1, f"{rule} did not fire: {counts}"
    # The unusual-hour rule must fire exactly once (only the C9001 plant,
    # not background customers).
    assert counts["unusual_send_hour_for_customer_rtp"] == 1


# ---------------------------------------------------------------------------
# uk_app_fraud — planted rows + end-to-end alerts
# ---------------------------------------------------------------------------


def test_uk_app_fraud_planted_rows() -> None:
    data = generate_uk_app_fraud_dataset(as_of=AS_OF)
    cust = {c["customer_id"]: c for c in data["customer"]}

    # C9101 — first-use large payee.
    c9101 = [t for t in data["txn"] if t["customer_id"] == "C9101"]
    assert len(c9101) == 1
    assert c9101[0]["payee_first_use"] is True and c9101[0]["amount"] >= 1000

    # C9102 — vulnerable customer, atypical (>= 5x p95) payment.
    assert cust["C9102"]["vulnerable_customer_flag"] is True
    c9102 = [t for t in data["txn"] if t["customer_id"] == "C9102"]
    assert c9102[0]["amount"] >= 5 * cust["C9102"]["typical_payment_size_p95"]

    # C9103 — CoP mismatch override on 2 payments.
    c9103 = [t for t in data["txn"] if t["customer_id"] == "C9103"]
    assert len(c9103) == 2
    assert all(t["confirmation_of_payee_status"] == "no_match" for t in c9103)

    # C9104 — rapid pass-through mule, account opened < 30 days.
    assert (AS_OF - cust["C9104"]["onboarded_at"]) < timedelta(days=30)
    c9104 = [t for t in data["txn"] if t["customer_id"] == "C9104"]
    ins = [t for t in c9104 if t["direction"] == "in"]
    outs = [t for t in c9104 if t["direction"] == "out"]
    assert ins and outs
    assert (outs[0]["booked_at"] - ins[0]["booked_at"]) <= timedelta(hours=1)


def test_uk_app_fraud_fires_every_typology(tmp_path) -> None:
    data = generate_uk_app_fraud_dataset(as_of=AS_OF)
    counts = _alerts_by_rule(_EXAMPLES / "uk_app_fraud" / "aml.yaml", data, tmp_path)
    for rule in (
        "first_use_payee_large_amount",
        "cop_mismatch_override",
        "vulnerable_customer_atypical_payment",
        "rapid_pass_through_mule",
    ):
        assert counts.get(rule, 0) >= 1, f"{rule} did not fire: {counts}"


# ---------------------------------------------------------------------------
# trade_based_ml — planted rows + end-to-end alerts
# ---------------------------------------------------------------------------


def test_tbml_planted_rows() -> None:
    data = generate_trade_based_ml_dataset(as_of=AS_OF)
    assert len(data["hs_code_baseline"]) == 5

    # C9201 — over-invoicing (4x baseline), sum >= $25k.
    c9201 = [t for t in data["txn"] if t["customer_id"] == "C9201"]
    assert all(t["declared_unit_price"] >= 3 * 500 for t in c9201)
    assert sum(t["amount"] for t in c9201) >= 25000

    # C9202 — under-invoicing (<= 0.5x baseline).
    c9202 = [t for t in data["txn"] if t["customer_id"] == "C9202"]
    assert all(t["declared_unit_price"] <= 0.5 * 500 for t in c9202)

    # C9203 — phantom shipping: 3 TRAD with no invoice_id, sum >= $50k.
    c9203 = [t for t in data["txn"] if t["customer_id"] == "C9203"]
    assert len(c9203) == 3
    assert all(t["invoice_id"] is None and t["purpose_code"] == "TRAD" for t in c9203)
    assert sum(t["amount"] for t in c9203) >= 50000

    # C9204 — multiple invoicing: same invoice_id paid twice.
    c9204 = [t for t in data["txn"] if t["customer_id"] == "C9204"]
    assert len({t["invoice_id"] for t in c9204}) == 1 and len(c9204) == 2

    # C9205 — TRAD to FATF high-risk jurisdiction (RU), sum >= $50k.
    c9205 = [t for t in data["txn"] if t["customer_id"] == "C9205"]
    assert all(t["counterparty_country"] == "RU" for t in c9205)
    assert sum(t["amount"] for t in c9205) >= 50000


def test_tbml_fires_every_typology(tmp_path) -> None:
    data = generate_trade_based_ml_dataset(as_of=AS_OF)
    counts = _alerts_by_rule(_EXAMPLES / "trade_based_ml" / "aml.yaml", data, tmp_path)
    for rule in (
        "over_invoicing_unit_price",
        "under_invoicing_unit_price",
        "phantom_shipping",
        "multiple_invoicing",
        "trad_to_high_risk_jurisdiction",
    ):
        assert counts.get(rule, 0) >= 1, f"{rule} did not fire: {counts}"


# ---------------------------------------------------------------------------
# codex P2 (#522): ALL synthetic entry points route through the per-spec
# dispatcher. The replay path is the determinism-critical one — a run
# created via the spec-aware source must replay against the SAME data.
# ---------------------------------------------------------------------------


def test_rtp_replay_reproduces_same_rule_output_hashes(tmp_path) -> None:
    """The replay determinism invariant for a newer spec — exercised
    through the real `aml run` -> `aml replay` CLI path (#522 codex P2).

    `aml run` (synthetic) and `aml replay` both resolve data through
    `generate_dataset_for_spec`. This drives both commands via CliRunner
    and asserts replay reports the per-rule output hashes all MATCH.

    Fail-mode this guards: if `aml replay` regressed to the shared
    `generate_dataset`, it would replay us_rtp_fednow against the OLD
    community-bank data (no C9xxx plants), the RTP-rule hashes would
    diverge, and replay would print "Hash mismatch detected." — making
    this test fail. (Verified by temporarily reverting the routing.)
    """
    runner = CliRunner()
    spec_path = _EXAMPLES / "us_rtp_fednow" / "aml.yaml"
    artifacts = tmp_path / "art"

    run_res = runner.invoke(
        app,
        ["run", str(spec_path), "--seed", "42", "--artifacts", str(artifacts)],
    )
    assert run_res.exit_code == 0, run_res.output

    run_dirs = sorted(artifacts.glob("run-*"))
    assert len(run_dirs) == 1, f"expected one run dir, got {run_dirs}"
    run_dir = run_dirs[0]

    # The original run's manifest must carry the RTP-only rule hashes
    # that exist ONLY because the C9xxx plants fired — proof the run used
    # the per-spec band, not community-bank data.
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    rule_outputs = manifest.get("rule_outputs", {})
    assert "first_use_payee_large_amount_rtp" in rule_outputs
    assert "mule_receiver_fan_out_rtp" in rule_outputs

    replay_res = runner.invoke(
        app,
        ["replay", str(spec_path), str(run_dir), "--seed", "42", "--artifacts", str(artifacts)],
    )
    assert replay_res.exit_code == 0, replay_res.output
    assert "All hashes match." in replay_res.output
    assert "Hash mismatch detected." not in replay_res.output


def test_backtest_default_loader_uses_per_spec_band() -> None:
    """The backtest default loader is spec-aware (#522 codex P2).

    For us_rtp_fednow it must serve the dedicated C9xxx planted band, not
    the shared community-bank C0xxx dataset — otherwise backtested numbers
    would diverge from what the engine run path produces.
    """
    spec = load_spec(_EXAMPLES / "us_rtp_fednow" / "aml.yaml")
    loader = _make_default_data_loader(spec)
    period = BacktestPeriod(label="2026-Q2", as_of=AS_OF, seed=42)
    data = loader(period)
    ids = {c["customer_id"] for c in data["customer"]}
    assert "C9001" in ids and "C9029" in ids
    assert not any(cid.startswith("C00") for cid in ids)
    # Byte-identical to calling the dedicated generator directly.
    assert data == generate_dataset_for_spec(spec=spec, as_of=AS_OF, seed=42)


def test_backtest_default_loader_falls_back_for_community_bank() -> None:
    spec = load_spec(_EXAMPLES / "community_bank" / "aml.yaml")
    loader = _make_default_data_loader(spec)
    period = BacktestPeriod(label="2026-Q2", as_of=AS_OF, seed=42)
    assert loader(period) == generate_dataset(as_of=AS_OF, seed=42)
