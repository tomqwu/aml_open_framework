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
