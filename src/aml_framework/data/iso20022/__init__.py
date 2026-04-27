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

Two adapters in v1:
- `Pacs008Parser` — customer credit transfer (the bulk of cross-border
  wire traffic).
- `Pacs009Parser` — financial-institution credit transfer (cover
  payments, FI-to-FI settlements).

Both produce dicts conforming to the existing `txn` data contract so
the engine + every downstream rule type works with no further change.
Travel-rule fields (UETR, BIC originator/beneficiary, structured
remittance, purpose code) are preserved as additional columns ready
for the Round-5 #2 validator.

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
    Pacs008Parser,
    Pacs009Parser,
    load_iso20022_dir,
    parse_iso20022_xml,
)

__all__ = [
    "Pacs008Parser",
    "Pacs009Parser",
    "parse_iso20022_xml",
    "load_iso20022_dir",
]
