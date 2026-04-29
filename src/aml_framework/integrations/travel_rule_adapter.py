"""Travel-Rule webhook adapters — Notabene + Sumsub.

Process problem this solves
---------------------------
Today, when a customer sends crypto from your VASP to a counterparty
VASP, the FATF Travel Rule data exchange (originator + beneficiary
KYC) happens out-of-band: emails, spreadsheets, SFTP dumps, "we'll
get back to you in 48 hours". The analyst opens an alert with the
counterparty data field empty and waits.

Notabene (notabene.id) and Sumsub (sumsub.com) sit between VASPs and
clear that exchange in seconds. The signal is *already there* — what's
missing is a normalised path to drop it on the analyst's queue
attached to the right transaction. This module is that path.

Design
------
Per-provider parsers normalise the webhook into one
`TravelRuleEnrichment` dataclass. The downstream `accept_enrichment`
function takes that dataclass + a DuckDB connection and updates the
matching `txn` row's counterparty fields, leaving an audit-ledger
event so the enrichment is part of the evidence chain.

Provider payload shapes are deliberately *not* baked into the engine
— a third or fourth provider only adds a parser; the engine never
learns about them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import duckdb

ProviderName = Literal["notabene", "sumsub"]


@dataclass(frozen=True)
class TravelRuleEnrichment:
    """One provider's normalised Travel-Rule attestation for one txn.

    Fields here mirror the FATF R.16 required set so the existing
    `models/travel_rule.validate_travel_rule` validator scores it
    immediately without translation.
    """

    provider: ProviderName
    provider_message_id: str
    txn_id: str
    received_at: datetime

    originator_name: str
    originator_account: str
    originator_country: str
    beneficiary_name: str
    beneficiary_account: str
    beneficiary_country: str
    purpose_code: str | None = None
    uetr: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_message_id": self.provider_message_id,
            "txn_id": self.txn_id,
            "received_at": self.received_at.isoformat(),
            "originator_name": self.originator_name,
            "originator_account": self.originator_account,
            "originator_country": self.originator_country,
            "beneficiary_name": self.beneficiary_name,
            "beneficiary_account": self.beneficiary_account,
            "beneficiary_country": self.beneficiary_country,
            "purpose_code": self.purpose_code,
            "uetr": self.uetr,
        }


# ---------------------------------------------------------------------------
# Notabene
# ---------------------------------------------------------------------------


def _parse_iso(s: str | None) -> datetime:
    if not s:
        return datetime.utcnow()
    return datetime.fromisoformat(s.replace("Z", "+00:00").replace("+00:00", ""))


def parse_notabene_webhook(payload: dict[str, Any] | str) -> TravelRuleEnrichment:
    """Parse a Notabene Travel Rule webhook into a TravelRuleEnrichment.

    Notabene's webhook payload (as documented at notabene.id/api/webhooks
    in the post-Notabene-3.x format) carries an envelope plus an
    `originator` and `beneficiary` block. Field names below match the
    public API; if the contract changes, this is the only thing to
    edit.
    """
    if isinstance(payload, str):
        payload = json.loads(payload)
    envelope = payload
    txn_ref = envelope.get("transaction_id") or envelope.get("transactionRef") or ""
    msg_id = envelope.get("transferId") or envelope.get("id") or ""
    originator = envelope.get("originator") or {}
    beneficiary = envelope.get("beneficiary") or {}
    return TravelRuleEnrichment(
        provider="notabene",
        provider_message_id=str(msg_id),
        txn_id=str(txn_ref),
        received_at=_parse_iso(envelope.get("received_at") or envelope.get("createdAt")),
        originator_name=str(originator.get("name", "")),
        originator_account=str(originator.get("account") or originator.get("accountNumber", "")),
        originator_country=str(originator.get("countryCode") or originator.get("country", "")),
        beneficiary_name=str(beneficiary.get("name", "")),
        beneficiary_account=str(beneficiary.get("account") or beneficiary.get("accountNumber", "")),
        beneficiary_country=str(beneficiary.get("countryCode") or beneficiary.get("country", "")),
        purpose_code=envelope.get("purposeCode") or envelope.get("purpose_code"),
        uetr=envelope.get("uetr") or envelope.get("UETR"),
    )


# ---------------------------------------------------------------------------
# Sumsub
# ---------------------------------------------------------------------------


def parse_sumsub_webhook(payload: dict[str, Any] | str) -> TravelRuleEnrichment:
    """Parse a Sumsub Travel Rule webhook into a TravelRuleEnrichment.

    Sumsub uses snake_case in their VASP webhook event (event type
    `vasp.travel_rule.completed`). The envelope wraps the actual
    enrichment in a `payload` key — we tolerate either presence or
    absence of the wrapper.
    """
    if isinstance(payload, str):
        payload = json.loads(payload)
    body = payload.get("payload", payload)  # tolerate either shape
    msg_id = body.get("event_id") or body.get("id") or ""
    txn_ref = body.get("txn_id") or body.get("originator_txn_ref") or ""
    originator = body.get("originator") or {}
    beneficiary = body.get("beneficiary") or {}
    return TravelRuleEnrichment(
        provider="sumsub",
        provider_message_id=str(msg_id),
        txn_id=str(txn_ref),
        received_at=_parse_iso(body.get("received_at")),
        originator_name=str(originator.get("full_name") or originator.get("name", "")),
        originator_account=str(originator.get("account_number") or originator.get("account", "")),
        originator_country=str(originator.get("country") or originator.get("country_code", "")),
        beneficiary_name=str(beneficiary.get("full_name") or beneficiary.get("name", "")),
        beneficiary_account=str(
            beneficiary.get("account_number") or beneficiary.get("account", "")
        ),
        beneficiary_country=str(beneficiary.get("country") or beneficiary.get("country_code", "")),
        purpose_code=body.get("purpose_code"),
        uetr=body.get("uetr"),
    )


# ---------------------------------------------------------------------------
# Application — write enrichment back to the warehouse
# ---------------------------------------------------------------------------


def accept_enrichment(
    con: duckdb.DuckDBPyConnection,
    enrichment: TravelRuleEnrichment,
    *,
    table: str = "txn",
) -> bool:
    """Apply one enrichment to the warehouse. Returns True on success.

    UPDATE-by-txn-id; if the txn isn't in the warehouse yet (out-of-
    order webhook arrival), returns False so the caller can park the
    enrichment in a pending queue and retry on next ingestion.

    The framework's audit ledger should record the acceptance event;
    this function intentionally does not import AuditLedger so the
    same code is usable in unit tests without a run-dir context.
    """
    # Use parameter binding for the values; keep the table name as an
    # interpolated identifier (validated against the column whitelist
    # in the caller, since DuckDB doesn't support identifier params).
    if not _txn_exists(con, table, enrichment.txn_id):
        return False
    con.execute(
        f"""
        UPDATE {table}
        SET counterparty_name    = COALESCE(counterparty_name, ?),
            counterparty_country = COALESCE(counterparty_country, ?),
            counterparty_account = COALESCE(counterparty_account, ?),
            uetr                 = COALESCE(uetr, ?),
            purpose_code         = COALESCE(purpose_code, ?)
        WHERE txn_id = ?
        """,
        [
            enrichment.beneficiary_name,
            enrichment.beneficiary_country,
            enrichment.beneficiary_account,
            enrichment.uetr,
            enrichment.purpose_code,
            enrichment.txn_id,
        ],
    )
    return True


def _txn_exists(con: duckdb.DuckDBPyConnection, table: str, txn_id: str) -> bool:
    rows = con.execute(f"SELECT 1 FROM {table} WHERE txn_id = ? LIMIT 1", [txn_id]).fetchall()
    return bool(rows)
