"""pacs.008 + pacs.009 XML parsers.

Both message types share a similar structure. We extract a common set
of fields into one normalized dict per `<CdtTrfTxInf>` block:

    txn_id              UETR if present, else EndToEndId, else MsgId+seq
    customer_id         Debtor name (best effort) — production setups
                        wire to a customer-id resolver
    amount              IntrBkSttlmAmt (Decimal-coerced)
    currency            IntrBkSttlmAmt @Ccy
    channel             "wire" (always — pacs.008 is wire credit transfer)
    direction           "out" (debtor side)
    booked_at           IntrBkSttlmDt → datetime
    counterparty_name   Creditor name
    counterparty_country Creditor country
    counterparty_account Creditor IBAN

Plus travel-rule + audit fields preserved as extra columns:

    uetr                ISO 20022 Unique End-to-end Transaction Reference
    msg_id              Group header MsgId
    purpose_code        Purp/Cd (e.g. GIFT, CHAR, INVS)
    debtor_iban         DbtrAcct IBAN
    debtor_bic          DbtrAgt BICFI
    creditor_bic        CdtrAgt BICFI
    instructing_agent   InstgAgt BICFI
    instructed_agent    InstdAgt BICFI
    charge_bearer       ChrgBr (DEBT/CRED/SHAR/SLEV)
    structured_remittance Strd remittance info as a dict (or None)
    debtor_country      Dbtr/PstlAdr/Ctry
    msg_kind            "pacs.008" or "pacs.009" — for downstream filters
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


def _strip_ns(tag: str) -> str:
    """`{urn:iso:std:iso:20022:...}MsgId` → `MsgId`."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find_local(elem: ET.Element, name: str) -> ET.Element | None:
    """Find first descendant by local tag name (namespace-agnostic)."""
    for child in elem.iter():
        if _strip_ns(child.tag) == name:
            return child
    return None


def _find_all_local(elem: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in elem.iter() if _strip_ns(child.tag) == name]


def _text(elem: ET.Element | None, default: str = "") -> str:
    if elem is None or elem.text is None:
        return default
    return elem.text.strip()


def _decimal(value: str | None) -> Decimal:
    if not value:
        return Decimal("0")
    try:
        return Decimal(value).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _parse_iso_date(value: str) -> datetime | None:
    """Parse an ISO 8601 date or datetime; return None if unparseable."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        # Some files emit just YYYY-MM-DD
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# Per-transaction block extraction (shared between pacs.008 and pacs.009)
# ---------------------------------------------------------------------------


def _extract_party(parent: ET.Element, tag: str) -> dict[str, str]:
    """Extract `<Dbtr>` or `<Cdtr>` block: name + country + (IBAN, BIC)."""
    party_elem = _find_local(parent, tag)
    if party_elem is None:
        return {"name": "", "country": ""}
    name = _text(_find_local(party_elem, "Nm"))
    country = ""
    pstl = _find_local(party_elem, "PstlAdr")
    if pstl is not None:
        country = _text(_find_local(pstl, "Ctry"))
    return {"name": name, "country": country}


def _extract_account_iban(parent: ET.Element, tag: str) -> str:
    """`<DbtrAcct>/<Id>/<IBAN>` or `<CdtrAcct>/<Id>/<IBAN>`."""
    acct = _find_local(parent, tag)
    if acct is None:
        return ""
    return _text(_find_local(acct, "IBAN"))


def _extract_agent_bic(parent: ET.Element, tag: str) -> str:
    """`<DbtrAgt>/<FinInstnId>/<BICFI>` (or BIC for older messages).

    Note: do NOT use `or` to fall back from BICFI → BIC. ET.Element
    evaluates falsy when it has no children (BICFI is a leaf), so
    `_find_local(...) or _find_local(...)` would silently swap to the
    fallback even when BICFI was found.
    """
    agent = _find_local(parent, tag)
    if agent is None:
        return ""
    fin = _find_local(agent, "FinInstnId")
    if fin is None:
        return ""
    bic = _find_local(fin, "BICFI")
    if bic is None:
        bic = _find_local(fin, "BIC")
    return _text(bic)


def _extract_purpose_code(parent: ET.Element) -> str:
    purp = _find_local(parent, "Purp")
    if purp is None:
        return ""
    return _text(_find_local(purp, "Cd"))


def _extract_structured_remittance(parent: ET.Element) -> dict[str, Any] | None:
    """Pull `<RmtInf>/<Strd>` into a dict. Returns None when missing."""
    rmt = _find_local(parent, "RmtInf")
    if rmt is None:
        return None
    strd = _find_local(rmt, "Strd")
    if strd is None:
        return None
    out: dict[str, Any] = {}
    for child in strd.iter():
        tag = _strip_ns(child.tag)
        if tag == "Strd":
            continue
        text = _text(child)
        if text:
            out[tag] = text
    return out or None


def _amount_currency(parent: ET.Element) -> tuple[Decimal, str]:
    """`<IntrBkSttlmAmt Ccy="EUR">100000</IntrBkSttlmAmt>`."""
    amt = _find_local(parent, "IntrBkSttlmAmt")
    if amt is None:
        return Decimal("0"), ""
    return _decimal(amt.text), amt.attrib.get("Ccy", "")


def _normalise_block(
    block: ET.Element,
    *,
    msg_id: str,
    seq: int,
    msg_kind: str,
) -> dict[str, Any]:
    """Map one `<CdtTrfTxInf>` to a txn dict."""
    pmt_id = _find_local(block, "PmtId")
    uetr = _text(_find_local(pmt_id, "UETR")) if pmt_id is not None else ""
    end_to_end = _text(_find_local(pmt_id, "EndToEndId")) if pmt_id is not None else ""
    txn_id = uetr or end_to_end or f"{msg_id}-{seq}"

    amount, currency = _amount_currency(block)
    settlement_dt = _parse_iso_date(_text(_find_local(block, "IntrBkSttlmDt")))

    debtor = _extract_party(block, "Dbtr")
    creditor = _extract_party(block, "Cdtr")

    return {
        "txn_id": txn_id,
        "customer_id": debtor["name"] or f"UNKNOWN-{msg_id}-{seq}",
        "amount": amount,
        "currency": currency,
        "channel": "wire",
        "direction": "out",
        "booked_at": settlement_dt,
        "counterparty_name": creditor["name"],
        "counterparty_country": creditor["country"],
        "counterparty_account": _extract_account_iban(block, "CdtrAcct"),
        # Travel-rule + audit fields (extra columns, ignored by base contract):
        "uetr": uetr,
        "msg_id": msg_id,
        "msg_kind": msg_kind,
        "purpose_code": _extract_purpose_code(block),
        "debtor_iban": _extract_account_iban(block, "DbtrAcct"),
        "debtor_bic": _extract_agent_bic(block, "DbtrAgt"),
        "creditor_bic": _extract_agent_bic(block, "CdtrAgt"),
        "instructing_agent": _extract_agent_bic(block, "InstgAgt"),
        "instructed_agent": _extract_agent_bic(block, "InstdAgt"),
        "charge_bearer": _text(_find_local(block, "ChrgBr")),
        "debtor_country": debtor["country"],
        "structured_remittance": _extract_structured_remittance(block),
    }


# ---------------------------------------------------------------------------
# Public parsers
# ---------------------------------------------------------------------------


class _BaseParser:
    """Shared XML walking; subclasses set msg_kind."""

    msg_kind: str = ""

    def parse(self, payload: bytes | str) -> list[dict[str, Any]]:
        text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []

        # Group header / MsgId — used as fallback for txn_id.
        grp_hdr = _find_local(root, "GrpHdr")
        msg_id = _text(_find_local(grp_hdr, "MsgId")) if grp_hdr is not None else ""

        out: list[dict[str, Any]] = []
        for seq, block in enumerate(_find_all_local(root, "CdtTrfTxInf"), start=1):
            out.append(_normalise_block(block, msg_id=msg_id, seq=seq, msg_kind=self.msg_kind))
        return out

    def load(self, path: str | Path) -> list[dict[str, Any]]:
        return self.parse(Path(path).read_bytes())


class Pacs008Parser(_BaseParser):
    """pacs.008 — customer credit transfer (FIToFICstmrCdtTrf)."""

    msg_kind = "pacs.008"


class Pacs009Parser(_BaseParser):
    """pacs.009 — FI credit transfer (FICdtTrf)."""

    msg_kind = "pacs.009"


# ---------------------------------------------------------------------------
# pain.001 — Customer Credit Transfer Initiation (corporate batches)
# ---------------------------------------------------------------------------
#
# Round-5 PR #4. pacs.008/009 (PRs #56 above) are FI-to-FI inter-bank
# messages. pain.001 is the **corporate-banking** equivalent: a single
# corporate customer submits one batch with debtor info at the top and
# many beneficiary credit transfers underneath. Wolfsberg Group's Feb
# 2026 correspondent-banking guidance flagged this layer as the
# surveillance gap — bulk corporate files often slip past per-txn
# monitoring because the debtor + KYC context is shared at the file
# level, not repeated per row.
#
# pain.001 structure:
#   <Document>/<CstmrCdtTrfInitn>
#     <GrpHdr>                      (MsgId, CtrlSum, NbOfTxs, ...)
#     <PmtInf>                       (one per execution date / debtor)
#       <PmtInfId>                   (payment-information id)
#       <ReqdExctnDt>                (requested execution date)
#       <Dbtr>/<Nm>                  (debtor — shared across all CdtTrfTxInf)
#       <DbtrAcct>/<Id>/<IBAN>
#       <DbtrAgt>/<FinInstnId>/<BICFI>
#       <CdtTrfTxInf>                (one per beneficiary transfer)
#         <PmtId>/<EndToEndId>
#         <Amt>/<InstdAmt Ccy="EUR">
#         <CdtrAgt>/<FinInstnId>/<BICFI>
#         <Cdtr>/<Nm>
#         <CdtrAcct>/<Id>/<IBAN>
#         <RmtInf>/<Strd>


def _extract_pain001_amount(parent: ET.Element) -> tuple[Decimal, str]:
    """pain.001 uses `<Amt>/<InstdAmt Ccy=...>` instead of pacs.008's
    `<IntrBkSttlmAmt>`. Returns (amount, currency)."""
    amt_block = _find_local(parent, "Amt")
    if amt_block is None:
        return Decimal("0"), ""
    instd = _find_local(amt_block, "InstdAmt")
    if instd is None:
        return Decimal("0"), ""
    return _decimal(instd.text), instd.attrib.get("Ccy", "")


def _normalise_pain001_tx(
    tx: ET.Element,
    *,
    pmt_inf: ET.Element,
    msg_id: str,
    pmt_inf_id: str,
    seq: int,
    debtor: dict[str, str],
    debtor_iban: str,
    debtor_bic: str,
    execution_date: datetime | None,
) -> dict[str, Any]:
    """Map one `<CdtTrfTxInf>` inside a `<PmtInf>` to a txn dict.

    The debtor block is taken from the parent `<PmtInf>` (shared
    across all transfers in this corporate batch) — that's the key
    structural difference vs pacs.008/009 where each transfer carries
    its own debtor.
    """
    pmt_id = _find_local(tx, "PmtId")
    end_to_end = _text(_find_local(pmt_id, "EndToEndId")) if pmt_id is not None else ""
    instr_id = _text(_find_local(pmt_id, "InstrId")) if pmt_id is not None else ""
    txn_id = end_to_end or instr_id or f"{msg_id}-{pmt_inf_id}-{seq}"

    amount, currency = _extract_pain001_amount(tx)
    creditor = _extract_party(tx, "Cdtr")

    return {
        "txn_id": txn_id,
        "customer_id": debtor["name"] or f"UNKNOWN-{msg_id}-{seq}",
        "amount": amount,
        "currency": currency,
        "channel": "wire",
        "direction": "out",
        "booked_at": execution_date,
        "counterparty_name": creditor["name"],
        "counterparty_country": creditor["country"],
        "counterparty_account": _extract_account_iban(tx, "CdtrAcct"),
        # pain.001 doesn't carry UETR — it's a customer-initiated message;
        # UETR is assigned by the FI when it forwards as pacs.008.
        "uetr": "",
        "msg_id": msg_id,
        "msg_kind": "pain.001",
        "purpose_code": _extract_purpose_code(tx),
        "debtor_iban": debtor_iban,
        "debtor_bic": debtor_bic,
        "creditor_bic": _extract_agent_bic(tx, "CdtrAgt"),
        "instructing_agent": "",
        "instructed_agent": "",
        "charge_bearer": _text(_find_local(tx, "ChrgBr")) or _text(_find_local(pmt_inf, "ChrgBr")),
        "debtor_country": debtor["country"],
        "structured_remittance": _extract_structured_remittance(tx),
        # pain.001-specific extras for downstream corporate-banking analytics:
        "payment_information_id": pmt_inf_id,
        "requested_execution_date": execution_date,
    }


class Pain001Parser:
    """pain.001 — Customer Credit Transfer Initiation (corporate batches).

    Output rows conform to the same `txn` data contract as pacs.008/009,
    so the downstream engine + travel-rule validator + purpose-code
    library all work unchanged.
    """

    msg_kind = "pain.001"

    def parse(self, payload: bytes | str) -> list[dict[str, Any]]:
        text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []

        grp_hdr = _find_local(root, "GrpHdr")
        msg_id = _text(_find_local(grp_hdr, "MsgId")) if grp_hdr is not None else ""

        out: list[dict[str, Any]] = []
        for pmt_inf in _find_all_local(root, "PmtInf"):
            pmt_inf_id = _text(_find_local(pmt_inf, "PmtInfId"))
            execution_date = _parse_iso_date(_text(_find_local(pmt_inf, "ReqdExctnDt")))
            debtor = _extract_party(pmt_inf, "Dbtr")
            debtor_iban = _extract_account_iban(pmt_inf, "DbtrAcct")
            debtor_bic = _extract_agent_bic(pmt_inf, "DbtrAgt")
            for seq, tx in enumerate(_find_all_local(pmt_inf, "CdtTrfTxInf"), start=1):
                out.append(
                    _normalise_pain001_tx(
                        tx,
                        pmt_inf=pmt_inf,
                        msg_id=msg_id,
                        pmt_inf_id=pmt_inf_id,
                        seq=seq,
                        debtor=debtor,
                        debtor_iban=debtor_iban,
                        debtor_bic=debtor_bic,
                        execution_date=execution_date,
                    )
                )
        return out

    def load(self, path: str | Path) -> list[dict[str, Any]]:
        return self.parse(Path(path).read_bytes())


# ---------------------------------------------------------------------------
# Auto-detect helper
# ---------------------------------------------------------------------------


def parse_iso20022_xml(payload: bytes | str) -> list[dict[str, Any]]:
    """Auto-detect message kind from the root element and dispatch.

    Dispatch order: pain.001 → pacs.009 → pacs.008 fallback.
    """
    text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload
    if "pain.001" in text or "CstmrCdtTrfInitn" in text:
        return Pain001Parser().parse(text)
    if "pacs.009" in text or "FICdtTrf" in text:
        return Pacs009Parser().parse(text)
    return Pacs008Parser().parse(text)


def load_iso20022_dir(directory: str | Path) -> list[dict[str, Any]]:
    """Load every `*.xml` file under `directory` and concatenate the rows.

    The `data/sources.py:resolve_source` integration calls this; tests
    can call it directly against a tmp_path.
    """
    out: list[dict[str, Any]] = []
    for xml_file in sorted(Path(directory).glob("**/*.xml")):
        out.extend(parse_iso20022_xml(xml_file.read_bytes()))
    return out
