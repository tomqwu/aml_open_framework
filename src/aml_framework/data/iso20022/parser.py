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
# Auto-detect helper
# ---------------------------------------------------------------------------


def parse_iso20022_xml(payload: bytes | str) -> list[dict[str, Any]]:
    """Auto-detect message kind from the root element and dispatch.

    Falls back to pacs.008 layout for unknown variants — both message
    types share the `<CdtTrfTxInf>` block shape, so the parser still
    extracts usable rows even if `msg_kind` is mislabelled.
    """
    text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload
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
