"""goAML 5.0.2 XML exporter — UNODC STR/SAR submission format.

Maps finalised cases (audit-ledger output) to UNODC's goAML 5.0.2 schema.
goAML is the de-facto FIU reporting standard accepted by 60+ FIUs (FINTRAC,
AUSTRAC, FIU-NL, FCRO, etc.). The EU AMLA ITS (draft due July 2026) builds on
this same spec with additional fields, so today's exporter is the foundation,
not a throwaway — AMLA-specific extensions land as deltas on top.

Mapping
    case ──────────────> <report>      (one STR/SAR per typology event)
    rule_id ───────────> <report_indicators>/<indicator>
    regulation_refs ───> <reason>
    customer ──────────> <t_person>
    txns in window ────> <transaction>

Determinism
    Output is byte-identical for a given (cases, customers, txns,
    submission_date). Cases are sorted by (rule_id, case_id); transactions by
    booked_at then txn_id. The exporter's submission_date is an explicit
    parameter so callers running the same data twice produce the same bytes.

Limitations
    - We emit one <report> per case for granularity. Real banks usually batch
      by customer/typology — that's a downstream concern outside this layer.
    - We don't fabricate counterparty PII. <t_to> is populated only from the
      transaction row; missing fields stay empty (goAML accepts empty leaf
      text on optional fields).
    - The XML uses the goAML 5.0.2 element shape but is not XSD-validated
      here — XSD shipping is a UNODC artefact, not redistributable. CI checks
      structural shape; jurisdictional XSD validation is a deployment step.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.etree.ElementTree import Element, SubElement

from aml_framework.spec.models import AMLSpec

GOAML_VERSION = "5.0.2"
DEFAULT_REPORT_CODE = "STR"  # Suspicious Transaction Report. SAR is a US synonym.


@dataclass(frozen=True)
class ReportingPerson:
    """The compliance officer signing the STR/SAR."""

    first_name: str = "Compliance"
    last_name: str = "Officer"
    title: str = "MLRO"
    email: str | None = None
    phone: str | None = None


@dataclass(frozen=True)
class ReportingEntity:
    """The regulated institution submitting the report."""

    rentity_id: str = "0"  # FIU-assigned; placeholder zero until provisioned
    rentity_branch: str = "HEAD_OFFICE"
    name: str = "Reporting Institution"
    address: str | None = None


_JURISDICTION_CURRENCY = {
    "CA": "CAD",
    "US": "USD",
    "EU": "EUR",
    "UK": "GBP",
    "GB": "GBP",
    "DE": "EUR",
    "FR": "EUR",
    "AU": "AUD",
}


def _currency_for_jurisdiction(jurisdiction: str) -> str:
    return _JURISDICTION_CURRENCY.get(jurisdiction.upper(), "USD")


def _text(parent: Element, tag: str, value: Any) -> Element:
    """Append <tag>value</tag>. None/empty values become an empty element so
    the resulting XML stays schema-shaped even when source fields are missing."""
    el = SubElement(parent, tag)
    el.text = "" if value is None else str(value)
    return el


def _format_iso(value: Any) -> str:
    """Coerce a date/datetime/string to ISO 8601. Tolerates the engine's
    'YYYY-MM-DD HH:MM:SS' string form by swapping the space separator."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    s = str(value)
    return s.replace(" ", "T", 1)


def _customer_index(customers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {c["customer_id"]: c for c in customers if "customer_id" in c}


def _txns_for_case(case: dict[str, Any], txns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter transactions matching the case customer and within the window."""
    alert = case.get("alert", {}) or {}
    cust_id = alert.get("customer_id")
    if cust_id is None:
        return []
    start = str(alert.get("window_start") or "")
    end = str(alert.get("window_end") or "")
    matched: list[dict[str, Any]] = []
    for t in txns:
        if t.get("customer_id") != cust_id:
            continue
        ts = str(t.get("booked_at") or "")
        if start and ts < start:
            continue
        if end and ts > end:
            continue
        matched.append(t)
    matched.sort(key=lambda t: (str(t.get("booked_at", "")), str(t.get("txn_id", ""))))
    return matched


def _person_element(parent: Element, customer: dict[str, Any] | None) -> None:
    """Emit a goAML <t_person> from a customer record. When the customer
    can't be resolved, emit a stub so the document still parses; analysts
    can fill in the missing PII before submission."""
    person = SubElement(parent, "t_person")
    if customer is None:
        _text(person, "first_name", "UNKNOWN")
        _text(person, "last_name", "UNKNOWN")
        return

    full = str(customer.get("full_name") or "").strip()
    parts = full.split(" ", 1) if full else ["UNKNOWN", "UNKNOWN"]
    _text(person, "first_name", parts[0] or "UNKNOWN")
    _text(person, "last_name", parts[1] if len(parts) > 1 else "UNKNOWN")

    if customer.get("country"):
        _text(person, "nationality1", customer["country"])
    if customer.get("occupation"):
        _text(person, "occupation", customer["occupation"])
    if customer.get("date_of_birth"):
        _text(person, "birthdate", _format_iso(customer["date_of_birth"])[:10])

    tax_id = customer.get("tax_id") or customer.get("national_id")
    if tax_id:
        ident = SubElement(person, "identification")
        _text(ident, "type", "TAX_ID")
        _text(ident, "number", tax_id)


def _transaction_element(
    parent: Element,
    txn: dict[str, Any],
    customer: dict[str, Any] | None,
) -> None:
    transaction = SubElement(parent, "transaction")
    _text(transaction, "transactionnumber", txn.get("txn_id", ""))
    _text(transaction, "internal_ref_number", txn.get("txn_id", ""))
    _text(transaction, "transaction_location", txn.get("country", ""))
    _text(transaction, "date_transaction", _format_iso(txn.get("booked_at")))
    channel = str(txn.get("channel") or "UNKNOWN").upper()
    _text(transaction, "transmode_code", channel)
    _text(transaction, "amount_local", str(txn.get("amount", "0")))

    # The bank's customer is the originator in a typical STR — t_from_my_client
    # is the goAML element reserved for "this transaction's source is one of
    # the reporting institution's accounts/clients".
    t_from = SubElement(transaction, "t_from_my_client")
    _text(t_from, "from_funds_code", _funds_code_for_channel(channel))
    _text(t_from, "from_country", customer.get("country", "") if customer else "")
    _person_element(t_from, customer)

    t_to = SubElement(transaction, "t_to")
    _text(t_to, "to_funds_code", _funds_code_for_channel(channel))
    _text(t_to, "to_country", txn.get("counterparty_country", ""))
    if txn.get("counterparty_name"):
        cp_person = SubElement(t_to, "t_person")
        cp_full = str(txn["counterparty_name"]).split(" ", 1)
        _text(cp_person, "first_name", cp_full[0] or "UNKNOWN")
        _text(cp_person, "last_name", cp_full[1] if len(cp_full) > 1 else "UNKNOWN")


def _funds_code_for_channel(channel: str) -> str:
    """Map our channel taxonomy to goAML funds codes.

    goAML uses a controlled vocabulary: K=Cash, A=Account/Wire, X=Other.
    Anything we don't recognise falls back to X so the document still parses.
    """
    mapping = {
        "CASH": "K",
        "ATM": "K",
        "WIRE": "A",
        "ACH": "A",
        "EFT": "A",
        "CRYPTO": "X",
        "CHEQUE": "A",
    }
    return mapping.get(channel.upper(), "X")


def _reason_text(case: dict[str, Any]) -> str:
    """Build the <reason> element from rule_name + regulation_refs."""
    parts = [f"Rule {case.get('rule_id', '?')} ({case.get('rule_name', '?')}) triggered."]
    for ref in case.get("regulation_refs", []) or []:
        citation = ref.get("citation", "")
        description = ref.get("description", "")
        parts.append(f"  - {citation}: {description}")
    return "\n".join(parts)


def build_report_element(
    case: dict[str, Any],
    customer: dict[str, Any] | None,
    transactions: list[dict[str, Any]],
    *,
    entity: ReportingEntity,
    person: ReportingPerson,
    submission_date: datetime,
    currency: str,
    report_code: str = DEFAULT_REPORT_CODE,
) -> Element:
    """Build a single goAML <report> element from a case."""
    report = Element("report")

    _text(report, "rentity_id", entity.rentity_id)
    _text(report, "rentity_branch", entity.rentity_branch)
    _text(report, "submission_code", "E")  # E = Electronic
    _text(report, "report_code", report_code)
    _text(report, "submission_date", submission_date.isoformat())
    _text(report, "currency_code_local", currency)

    rp = SubElement(report, "reporting_person")
    _text(rp, "first_name", person.first_name)
    _text(rp, "last_name", person.last_name)
    _text(rp, "title", person.title)
    if person.email:
        _text(rp, "email", person.email)
    if person.phone:
        _text(rp, "phone", person.phone)

    _text(report, "reason", _reason_text(case))

    for txn in transactions:
        _transaction_element(report, txn, customer)

    indicators = SubElement(report, "report_indicators")
    _text(indicators, "indicator", case.get("rule_id", "unknown"))
    for tag in case.get("tags", []) or []:
        _text(indicators, "indicator", tag)

    additional_lines = [
        f"case_id: {case.get('case_id', '')}",
        f"severity: {case.get('severity', 'unknown')}",
        f"queue: {case.get('queue', 'unknown')}",
        f"spec_program: {case.get('spec_program', '')}",
    ]
    for ctr_id, info in (case.get("input_hash") or {}).items():
        if isinstance(info, dict):
            additional_lines.append(f"input_hash[{ctr_id}]: {info.get('content_hash', '')}")
    _text(report, "additional_info", "\n".join(additional_lines))

    return report


def build_goaml_xml(
    spec: AMLSpec,
    cases: list[dict[str, Any]],
    customers: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    *,
    entity: ReportingEntity | None = None,
    person: ReportingPerson | None = None,
    submission_date: datetime | None = None,
    report_code: str = DEFAULT_REPORT_CODE,
) -> bytes:
    """Build a goAML 5.0.2 XML document containing one <report> per case.

    The root element is <reports> for batch submission. Single-report
    submissions can extract the inner <report> element directly.
    """
    entity = entity or ReportingEntity(name=spec.program.name)
    person = person or ReportingPerson()
    submission_date = submission_date or datetime.now(tz=timezone.utc)
    currency = _currency_for_jurisdiction(spec.program.jurisdiction)

    customer_idx = _customer_index(customers)

    root = Element("reports")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("schema_version", GOAML_VERSION)

    # Deterministic ordering: rule first (so all SARs of a typology cluster),
    # then case id (lexicographic — already includes timestamp).
    sorted_cases = sorted(cases, key=lambda c: (c.get("rule_id", ""), c.get("case_id", "")))
    for case in sorted_cases:
        cust_id = (case.get("alert") or {}).get("customer_id")
        customer = customer_idx.get(cust_id) if cust_id else None
        case_txns = _txns_for_case(case, transactions)
        report = build_report_element(
            case,
            customer,
            case_txns,
            entity=entity,
            person=person,
            submission_date=submission_date,
            currency=currency,
            report_code=report_code,
        )
        root.append(report)

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True, short_empty_elements=False)


def export_goaml_from_run_dir(
    run_dir: Path,
    spec: AMLSpec,
    customers: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    *,
    entity: ReportingEntity | None = None,
    person: ReportingPerson | None = None,
    submission_date: datetime | None = None,
    report_code: str = DEFAULT_REPORT_CODE,
) -> bytes:
    """Read cases from a finalised run directory and build goAML XML."""
    cases_dir = run_dir / "cases"
    if not cases_dir.exists():
        raise FileNotFoundError(f"No cases/ directory in {run_dir}")
    cases = [json.loads(p.read_bytes()) for p in sorted(cases_dir.glob("*.json"))]
    return build_goaml_xml(
        spec,
        cases,
        customers,
        transactions,
        entity=entity,
        person=person,
        submission_date=submission_date,
        report_code=report_code,
    )
