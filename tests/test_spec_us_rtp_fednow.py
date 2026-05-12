"""Smoke tests for the US RTP/FedNow push-fraud example spec.

Process problem this PR solves: pre-investigated cases at payment-time
on instant rails so the fraud CSR doesn't have to assemble evidence
when the customer phones in. These tests guard the spec's structural
correctness; behavioural-detection tests live in the engine layer.
"""

from __future__ import annotations

from pathlib import Path

from aml_framework.spec import load_spec

SPEC = Path(__file__).resolve().parent.parent / "examples" / "us_rtp_fednow" / "aml.yaml"


def test_spec_loads_and_validates() -> None:
    spec = load_spec(SPEC)
    assert spec.program.jurisdiction == "US"
    assert spec.program.regulator == "FinCEN"
    assert len(spec.rules) == 5


def test_every_rule_carries_fraud_priority() -> None:
    """Required so PR-C's fraud-AML linkage panel classifies these
    cases as fraud-domain. If a future contributor forgets the
    aml_priority on a new rule, this test will catch it."""
    spec = load_spec(SPEC)
    for rule in spec.rules:
        assert rule.aml_priority == "fraud", (
            f"rule {rule.id!r} must declare aml_priority: fraud "
            f"so case linkage classifies it correctly"
        )


def test_spec_uses_only_supported_rule_logic_types() -> None:
    spec = load_spec(SPEC)
    supported = {"aggregation_window", "custom_sql", "network_pattern", "list_match", "python_ref"}
    for rule in spec.rules:
        assert rule.logic.type in supported


def test_workflow_has_fraud_l2_queue_for_escalation() -> None:
    """All five rules escalate to fraud_l2; that queue must exist."""
    spec = load_spec(SPEC)
    queue_ids = {q.id for q in spec.workflow.queues}
    assert "fraud_l2" in queue_ids
    for rule in spec.rules:
        assert rule.escalate_to in queue_ids


def test_txn_contract_includes_rtp_and_fednow_channels() -> None:
    spec = load_spec(SPEC)
    txn = next(c for c in spec.data_contracts if c.id == "txn")
    channel = next(col for col in txn.columns if col.name == "channel")
    assert channel.enum is not None
    assert "rtp" in channel.enum
    assert "fednow" in channel.enum


def test_txn_contract_carries_cop_field_for_uk_style_reimbursement_signal() -> None:
    """Confirmation-of-Payee (CoP) status is one of the few signals
    available before a real-time payment lands. The contract must
    surface it so future detector rules can use it."""
    spec = load_spec(SPEC)
    txn = next(c for c in spec.data_contracts if c.id == "txn")
    field_names = {col.name for col in txn.columns}
    assert "cop_match_status" in field_names


def test_unusual_send_hour_rule_selects_counterparty_id_in_sql() -> None:
    """Fast contract check: the rule's `custom_sql` selects the
    `counterparty_id` evidence column. Pairs with the heavier
    end-to-end `..._alert_carries_counterparty_id_for_evidence` test
    below — this one catches an obvious SQL-string break in O(1),
    the heavy one verifies the alert payload actually carries a
    non-empty value end-to-end."""
    spec = load_spec(SPEC)
    rule = next(r for r in spec.rules if r.id == "unusual_send_hour_for_customer_rtp")
    assert "t.counterparty_id" in rule.logic.sql, (
        "rule SQL must select `t.counterparty_id` for evidence display"
    )


def test_unusual_send_hour_alert_carries_counterparty_id_for_evidence() -> None:
    """End-to-end: the unusual_send_hour rule's SELECT includes
    `t.counterparty_id` so analysts see which payee triggered the
    alert. Pre-Round-17 the synthetic generator didn't populate the
    column, so the SELECT silently broke (psycopg2 BinderException
    on the deployed Postgres). With counterparty_id now populated
    (#279), this test pins that the alert payload carries the column.
    Regression-safe: a future change that drops counterparty_id from
    the rule's SELECT or stops emitting it on the synthetic generator
    fails here.
    """
    from datetime import datetime

    from aml_framework.data import generate_dataset
    from aml_framework.engine import run_spec

    spec = load_spec(SPEC)
    as_of = datetime(2026, 4, 28)
    data = generate_dataset(as_of=as_of, seed=42)
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        result = run_spec(
            spec=spec,
            spec_path=SPEC,
            data=data,
            as_of=as_of,
            artifacts_root=Path(tmp),
        )
    alerts = result.alerts.get("unusual_send_hour_for_customer_rtp", [])
    assert alerts, "expected at least one unusual_send_hour alert"
    for alert in alerts:
        assert "counterparty_id" in alert, (
            f"alert payload missing `counterparty_id`; keys={sorted(alert.keys())}"
        )
        assert alert["counterparty_id"], (
            f"counterparty_id must be non-empty for evidence display; got {alert['counterparty_id']!r}"
        )
