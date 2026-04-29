"""Tests for `integrations/travel_rule_adapter.py`.

Process invariant guarded: VASP counterparty data arrives in the
analyst queue automatically, with provider-shape variation absorbed
at the adapter boundary so the engine sees one normalised record.
"""

from __future__ import annotations

import json

import duckdb
import pytest

from aml_framework.integrations.travel_rule_adapter import (
    TravelRuleEnrichment,
    accept_enrichment,
    parse_notabene_webhook,
    parse_sumsub_webhook,
)


# ---------------------------------------------------------------------------
# Fixture payloads — minimal but realistic shapes for each provider
# ---------------------------------------------------------------------------


NOTABENE_PAYLOAD = {
    "id": "nbn-msg-001",
    "transferId": "nbn-msg-001",
    "transaction_id": "TXN-100",
    "createdAt": "2026-04-28T12:00:00Z",
    "originator": {
        "name": "Alice Sender",
        "accountNumber": "ACCT-A",
        "countryCode": "US",
    },
    "beneficiary": {
        "name": "Bob Receiver",
        "accountNumber": "ACCT-B",
        "countryCode": "DE",
    },
    "purposeCode": "INVS",
    "uetr": "00000000-0000-0000-0000-000000000001",
}

SUMSUB_PAYLOAD = {
    "type": "vasp.travel_rule.completed",
    "payload": {
        "event_id": "ssm-msg-001",
        "txn_id": "TXN-200",
        "received_at": "2026-04-28T12:05:00",
        "originator": {"full_name": "Carol Sender", "account_number": "ACCT-C", "country": "GB"},
        "beneficiary": {
            "full_name": "Dan Receiver",
            "account_number": "ACCT-D",
            "country": "JP",
        },
        "purpose_code": "GDDS",
        "uetr": "00000000-0000-0000-0000-000000000002",
    },
}


# ---------------------------------------------------------------------------
# Notabene parser
# ---------------------------------------------------------------------------


def test_parse_notabene_webhook_yields_normalised_record() -> None:
    e = parse_notabene_webhook(NOTABENE_PAYLOAD)
    assert isinstance(e, TravelRuleEnrichment)
    assert e.provider == "notabene"
    assert e.provider_message_id == "nbn-msg-001"
    assert e.txn_id == "TXN-100"
    assert e.beneficiary_name == "Bob Receiver"
    assert e.beneficiary_country == "DE"
    assert e.purpose_code == "INVS"


def test_parse_notabene_webhook_accepts_string_payload() -> None:
    e = parse_notabene_webhook(json.dumps(NOTABENE_PAYLOAD))
    assert e.txn_id == "TXN-100"


# ---------------------------------------------------------------------------
# Sumsub parser
# ---------------------------------------------------------------------------


def test_parse_sumsub_webhook_yields_normalised_record() -> None:
    e = parse_sumsub_webhook(SUMSUB_PAYLOAD)
    assert e.provider == "sumsub"
    assert e.provider_message_id == "ssm-msg-001"
    assert e.txn_id == "TXN-200"
    assert e.beneficiary_name == "Dan Receiver"
    assert e.beneficiary_country == "JP"
    assert e.purpose_code == "GDDS"


def test_parse_sumsub_tolerates_missing_envelope() -> None:
    """Some Sumsub setups POST the inner payload directly. Must work."""
    e = parse_sumsub_webhook(SUMSUB_PAYLOAD["payload"])
    assert e.txn_id == "TXN-200"
    assert e.beneficiary_name == "Dan Receiver"


# ---------------------------------------------------------------------------
# Apply enrichment to warehouse
# ---------------------------------------------------------------------------


@pytest.fixture
def warehouse_with_txn() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE txn (
            txn_id VARCHAR PRIMARY KEY,
            counterparty_name VARCHAR,
            counterparty_country VARCHAR,
            counterparty_account VARCHAR,
            uetr VARCHAR,
            purpose_code VARCHAR
        )
        """
    )
    con.execute("INSERT INTO txn (txn_id) VALUES ('TXN-100')")
    return con


def test_accept_enrichment_updates_existing_txn(warehouse_with_txn) -> None:
    e = parse_notabene_webhook(NOTABENE_PAYLOAD)
    ok = accept_enrichment(warehouse_with_txn, e)
    assert ok is True
    row = warehouse_with_txn.execute(
        "SELECT counterparty_name, counterparty_country, purpose_code, uetr FROM txn WHERE txn_id = 'TXN-100'"
    ).fetchone()
    assert row == ("Bob Receiver", "DE", "INVS", "00000000-0000-0000-0000-000000000001")


def test_accept_enrichment_returns_false_when_txn_missing(warehouse_with_txn) -> None:
    e = parse_notabene_webhook(NOTABENE_PAYLOAD)
    e_missing = TravelRuleEnrichment(
        provider="notabene",
        provider_message_id="x",
        txn_id="DOES-NOT-EXIST",
        received_at=e.received_at,
        originator_name="",
        originator_account="",
        originator_country="",
        beneficiary_name="",
        beneficiary_account="",
        beneficiary_country="",
    )
    assert accept_enrichment(warehouse_with_txn, e_missing) is False


def test_accept_enrichment_does_not_overwrite_existing_values(warehouse_with_txn) -> None:
    """COALESCE preserves analyst-validated data — adapter is additive."""
    warehouse_with_txn.execute(
        "UPDATE txn SET counterparty_name='Already Validated' WHERE txn_id='TXN-100'"
    )
    e = parse_notabene_webhook(NOTABENE_PAYLOAD)
    accept_enrichment(warehouse_with_txn, e)
    row = warehouse_with_txn.execute(
        "SELECT counterparty_name FROM txn WHERE txn_id = 'TXN-100'"
    ).fetchone()
    assert row[0] == "Already Validated"
