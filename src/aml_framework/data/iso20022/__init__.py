"""ISO 20022 payment-message ingestion.

The framework can score transactions but historically couldn't natively
consume the messages banks actually move money with. SWIFT completed
its MX-only cutover on **2025-11-22** (CBPR+ coexistence period ended);
FedNow / RTP / SEPA Instant volumes crossed inflection in Q1 2026.
Without pacs.008 / pacs.009 / pain.001 ingestion the framework is
unusable on real correspondent traffic.

This module is the foundation for Round-5 features 2-5 (travel-rule
validator, purpose-code typology library, corporate pain.001, return-
reason mining) and downstream Round-7 TBML / Round-8 RTP-fraud work.

Adapters:
- `Pacs008Parser` — customer credit transfer (the bulk of cross-border
  wire traffic).
- `Pacs009Parser` — financial-institution credit transfer (cover
  payments, FI-to-FI settlements).
- `Pain001Parser` — corporate credit transfer initiation (Round-5 #4).
- `Pacs004Parser` — payment return (Round-5 #5). Rows go to a separate
  `txn_return` contract for return-rate mining (UK PSR APP-fraud
  reimbursement mandate; mule-network detection via repeated AC03/
  AC04/AM05/MD07 reasons against the same originator).

The credit-transfer parsers produce dicts conforming to the `txn`
data contract; pacs.004 produces dicts on `txn_return`. Both flows
preserve travel-rule + audit fields (UETR, BIC originator/beneficiary,
structured remittance, purpose code, return reason code).

Design
- Pure parsers — no IO. Tests pass payload bytes; live ingestion goes
  through `data/sources.py:resolve_source('iso20022')`.
- Namespace-tolerant: `_strip_ns()` lets specs use the official
  `urn:iso:std:iso:20022:tech:xsd:pacs.008.001.13` schema or any
  bank-internal variant without re-coding.
- Multi-transaction: a single pacs.008 file can carry many
  `<CdtTrfTxInf>` blocks; each becomes one txn row.
"""

from aml_framework.data.iso20022.parser import (
    Pacs004Parser,
    Pacs008Parser,
    Pacs009Parser,
    Pain001Parser,
    load_iso20022_dir,
    load_iso20022_returns_dir,
    parse_iso20022_xml,
)

__all__ = [
    "Pacs004Parser",
    "Pacs008Parser",
    "Pacs009Parser",
    "Pain001Parser",
    "parse_iso20022_xml",
    "load_iso20022_dir",
    "load_iso20022_returns_dir",
]
