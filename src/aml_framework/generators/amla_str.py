"""AMLA harmonised STR profile — EU AMLA RTS draft (Feb 2026 consultation).

The EU's Anti-Money Laundering Authority (AMLA) is finalising a single
harmonised SAR/STR template across the bloc. The Regulatory Technical
Standards (RTS) on the SAR template have a delivery deadline of
**10 July 2026**; three drafts have been in public consultation since
February 2026. This module emits institution submissions aligned to
that consultation draft so EU obliged entities have a day-zero
adapter the moment the RTS is ratified.

⚠️  DRAFT WARNING
This generator targets the AMLA RTS *consultation draft* dated
2026-02. Field names, mandatory-vs-optional split, and typology
enums **will change** before 10 July 2026. Every output payload
includes an explicit `_draft_warning` field so downstream consumers
cannot mistake it for a final submission. When the final RTS lands,
the diff lives in this file and the JSON shape — no engine changes.

Mapping
    case ──────────────> one entry in `reports[]`
    rule_id + tags ────> AMLA typology code(s) (Annex II — placeholder
                         names, real codes finalised by RTS)
    regulation_refs ───> indicators[].source_regulation
    customer ──────────> subject.{personal,entity} block
    txns in window ────> transactions[]
    program.jurisdiction → submission_jurisdiction
    spec.program.name  → obliged_entity.programme_name

Conformance: every payload also includes a `conformance` block listing
which AMLA-required fields the spec successfully populated and which
are stubbed pending manual fill-in. Auditors get a one-shot view of
"what's automated vs what still needs an analyst".

Determinism: identical inputs → identical bytes (cases sort by
(rule_id, case_id); transactions by (booked_at, txn_id);
submission_date is an explicit param). Same contract as
goaml_xml.py — re-runs are reproducible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from aml_framework.spec.models import AMLSpec

DRAFT_VERSION = "AMLA-RTS-DRAFT-2026-02"
DRAFT_WARNING = (
    "AMLA RTS is in consultation (draft 2026-02). Field names, mandatory "
    "fields, and typology enums will change before the 2026-07-10 deadline. "
    "Do NOT submit this payload to a regulator until the final RTS is "
    "ratified and this generator is updated."
)


# ---------------------------------------------------------------------------
# AMLA typology codes (Annex II — placeholder until ratified)
# ---------------------------------------------------------------------------


# These codes mirror the *categories* called out in the consultation
# draft. The final RTS will publish authoritative codes; until then we
# use STR-NNN placeholders that map cleanly to FATF / FinCEN / FINTRAC
# typology vocabularies.
class AMLATypology:
    STRUCTURING = "STR-001"
    SHELL_COMPANY = "STR-002"
    SANCTIONS_EVASION = "STR-003"
    PEP_INVOLVEMENT = "STR-004"
    HIGH_RISK_JURISDICTION = "STR-005"
    UNUSUAL_TRANSACTION_PATTERN = "STR-006"
    TRADE_BASED = "STR-007"
    VIRTUAL_ASSET_LAYERING = "STR-008"
    UNKNOWN = "STR-999"


# Best-effort mapping from rule_id substrings + tags to AMLA typology
# codes. Order matters — first match wins. The fallback is UNKNOWN so
# AMLA fields stay populated even when a programme uses custom rule_ids.
_TYPOLOGY_HINTS: list[tuple[str, str]] = [
    ("structuring", AMLATypology.STRUCTURING),
    ("shell", AMLATypology.SHELL_COMPANY),
    ("sanction", AMLATypology.SANCTIONS_EVASION),
    ("ofac", AMLATypology.SANCTIONS_EVASION),
    ("pep", AMLATypology.PEP_INVOLVEMENT),
    ("adverse_media", AMLATypology.PEP_INVOLVEMENT),
    ("high_risk_jurisdiction", AMLATypology.HIGH_RISK_JURISDICTION),
    ("country_risk", AMLATypology.HIGH_RISK_JURISDICTION),
    ("trade", AMLATypology.TRADE_BASED),
    ("nested_wallet", AMLATypology.VIRTUAL_ASSET_LAYERING),
    ("stablecoin", AMLATypology.VIRTUAL_ASSET_LAYERING),
    ("crypto", AMLATypology.VIRTUAL_ASSET_LAYERING),
    ("velocity", AMLATypology.UNUSUAL_TRANSACTION_PATTERN),
    ("dormant", AMLATypology.UNUSUAL_TRANSACTION_PATTERN),
    ("burst", AMLATypology.UNUSUAL_TRANSACTION_PATTERN),
]


def map_to_typology(rule_id: str, tags: list[str] | None = None) -> str:
    """Return the AMLA typology code for a rule. Falls back to UNKNOWN."""
    haystack = (rule_id or "").lower() + " " + " ".join(tags or []).lower()
    for hint, code in _TYPOLOGY_HINTS:
        if hint in haystack:
            return code
    return AMLATypology.UNKNOWN


# ---------------------------------------------------------------------------
# Reporting entity / submission metadata
# ---------------------------------------------------------------------------


SectorCode = Literal[
    "CREDIT_INSTITUTION",
    "PAYMENT_INSTITUTION",
    "EMI",  # e-money institution
    "INVESTMENT_FIRM",
    "INSURANCE",
    "VASP",  # Virtual Asset Service Provider
    "DNFBP",  # Designated Non-Financial Business or Profession
    "OTHER",
]


@dataclass(frozen=True)
class ObligedEntity:
    """The AMLA "obliged entity" — sender of the report.

    `lei` is required by the RTS draft; placeholder zeros are accepted
    for testing but the final submission must carry a real ISO 17442
    Legal Entity Identifier.
    """

    lei: str = "00000000000000000000"  # ISO 17442; 20 chars
    name: str = "Reporting Institution"
    sector: SectorCode = "CREDIT_INSTITUTION"
    jurisdiction: str = "EU"  # ISO-2 country or "EU"
    programme_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "lei": self.lei,
            "name": self.name,
            "sector": self.sector,
            "jurisdiction": self.jurisdiction,
            "programme_name": self.programme_name,
        }


@dataclass(frozen=True)
class SubmittingPerson:
    """Compliance officer signing the submission."""

    full_name: str = "Compliance Officer"
    role: str = "MLRO"
    email: str | None = None
    phone: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "full_name": self.full_name,
            "role": self.role,
            "email": self.email,
            "phone": self.phone,
        }


# ---------------------------------------------------------------------------
# Internal helpers — same shape as goaml_xml.py
# ---------------------------------------------------------------------------


def _customer_index(customers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {c["customer_id"]: c for c in customers if "customer_id" in c}


def _txns_for_case(case: dict[str, Any], txns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    alert = case.get("alert") or {}
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


def _format_iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value).replace(" ", "T", 1)


def _subject_block(customer: dict[str, Any] | None) -> dict[str, Any]:
    """Customer → AMLA `subject` block (personal vs entity branches)."""
    if customer is None:
        return {
            "type": "unknown",
            "missing_kyc": True,
            "_warning": "no resolved customer record — analyst must populate",
        }
    # The draft splits on entity vs natural person; we infer from
    # presence of date_of_birth.
    is_person = bool(customer.get("date_of_birth")) or "full_name" in customer
    block: dict[str, Any] = {
        "type": "natural_person" if is_person else "legal_entity",
        "subject_id": customer.get("customer_id", ""),
        "name": customer.get("full_name") or customer.get("legal_name", ""),
        "country_of_residence": customer.get("country", ""),
        "occupation_or_business": customer.get("occupation"),
        "risk_rating_at_filing": customer.get("risk_rating", "unknown"),
    }
    if customer.get("date_of_birth"):
        block["date_of_birth"] = str(customer["date_of_birth"])[:10]
    if customer.get("tax_id") or customer.get("national_id"):
        block["national_id"] = customer.get("tax_id") or customer.get("national_id")
    if customer.get("lei"):
        block["lei"] = customer["lei"]
    if customer.get("beneficial_owners"):
        # AMLA RTS draft requires beneficial-ownership chain for legal entities
        block["beneficial_owner_chain"] = customer["beneficial_owners"]
    return block


def _transaction_block(txn: dict[str, Any]) -> dict[str, Any]:
    return {
        "transaction_id": str(txn.get("txn_id", "")),
        "date": _format_iso(txn.get("booked_at")),
        "amount": str(txn.get("amount", "0")),
        "currency": txn.get("currency", "EUR"),
        "channel": str(txn.get("channel") or "UNKNOWN").upper(),
        "country": txn.get("country", ""),
        "counterparty_name": txn.get("counterparty_name"),
        "counterparty_country": txn.get("counterparty_country"),
        "counterparty_account": txn.get("counterparty_account"),
    }


def _cross_border(case_txns: list[dict[str, Any]], jurisdiction: str) -> bool:
    """True if any txn in the case has a counterparty country ≠ programme jurisdiction."""
    j = (jurisdiction or "").upper()
    for t in case_txns:
        cp = (t.get("counterparty_country") or "").upper()
        if cp and cp != j:
            return True
    return False


def _indicators_block(case: dict[str, Any]) -> list[dict[str, str]]:
    """rule_id + each regulation_ref → indicators[] entries."""
    out = [{"rule_id": case.get("rule_id", "unknown"), "type": "rule"}]
    for ref in case.get("regulation_refs") or []:
        out.append(
            {
                "rule_id": case.get("rule_id", "unknown"),
                "type": "regulation",
                "citation": ref.get("citation", ""),
                "description": ref.get("description", ""),
                "source_regulation": ref.get("citation", ""),
            }
        )
    for tag in case.get("tags") or []:
        out.append({"type": "tag", "value": tag})
    return out


# ---------------------------------------------------------------------------
# Conformance report
# ---------------------------------------------------------------------------


# AMLA RTS draft mandatory fields. We track which we populated from
# spec data vs which need analyst follow-up.
_AMLA_MANDATORY_FIELDS = (
    "obliged_entity.lei",
    "obliged_entity.sector",
    "submission_jurisdiction",
    "report.amla_typology_codes",
    "report.subject.subject_id",
    "report.subject.name",
    "report.subject.country_of_residence",
    "report.transactions",
    "report.indicators",
    "report.narrative_summary",
    "report.cross_border_indicator",
)


def _conformance_block(
    obliged_entity: ObligedEntity,
    reports: list[dict[str, Any]],
) -> dict[str, Any]:
    """Per-payload conformance: which mandatory fields were populated."""
    populated: list[str] = []
    unmapped: list[str] = []

    if obliged_entity.lei and obliged_entity.lei != "00000000000000000000":
        populated.append("obliged_entity.lei")
    else:
        unmapped.append("obliged_entity.lei")

    if obliged_entity.sector:
        populated.append("obliged_entity.sector")

    if reports:
        populated.append("submission_jurisdiction")

    for report in reports:
        if report.get("amla_typology_codes"):
            populated.append("report.amla_typology_codes")
        if report.get("subject", {}).get("subject_id"):
            populated.append("report.subject.subject_id")
        if report.get("subject", {}).get("name"):
            populated.append("report.subject.name")
        if report.get("subject", {}).get("country_of_residence"):
            populated.append("report.subject.country_of_residence")
        if report.get("transactions"):
            populated.append("report.transactions")
        if report.get("indicators"):
            populated.append("report.indicators")
        if report.get("narrative_summary"):
            populated.append("report.narrative_summary")
        if "cross_border_indicator" in report:
            populated.append("report.cross_border_indicator")

    populated_set = set(populated)
    for field_name in _AMLA_MANDATORY_FIELDS:
        if field_name not in populated_set:
            unmapped.append(field_name)

    return {
        "mandatory_fields_total": len(_AMLA_MANDATORY_FIELDS),
        "mandatory_fields_populated": len(set(populated) & set(_AMLA_MANDATORY_FIELDS)),
        "populated": sorted(set(populated) & set(_AMLA_MANDATORY_FIELDS)),
        "unmapped_required": sorted(set(unmapped)),
    }


# ---------------------------------------------------------------------------
# Top-level builders
# ---------------------------------------------------------------------------


def build_amla_report(
    case: dict[str, Any],
    customer: dict[str, Any] | None,
    transactions: list[dict[str, Any]],
    *,
    jurisdiction: str,
) -> dict[str, Any]:
    """One AMLA `report[]` entry from one case."""
    typology = map_to_typology(case.get("rule_id", ""), case.get("tags", []))
    narrative_summary = (
        f"Rule {case.get('rule_id', '?')} ({case.get('rule_name', '?')}) triggered "
        f"on customer {(case.get('alert') or {}).get('customer_id', '?')}. "
        f"Severity: {case.get('severity', 'unknown')}. "
        f"Window: {(case.get('alert') or {}).get('window_start', '?')} → "
        f"{(case.get('alert') or {}).get('window_end', '?')}."
    )
    return {
        "report_id": case.get("case_id", ""),
        "case_severity": case.get("severity", "unknown"),
        "amla_typology_codes": [typology],
        "subject": _subject_block(customer),
        "transactions": [_transaction_block(t) for t in transactions],
        "indicators": _indicators_block(case),
        "cross_border_indicator": _cross_border(transactions, jurisdiction),
        "narrative_summary": narrative_summary,
        "internal_queue": case.get("queue", "unknown"),
        "input_hash": case.get("input_hash") or {},
    }


def build_amla_str_payload(
    spec: AMLSpec,
    cases: list[dict[str, Any]],
    customers: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    *,
    obliged_entity: ObligedEntity | None = None,
    submitting_person: SubmittingPerson | None = None,
    submission_date: datetime | None = None,
) -> dict[str, Any]:
    """Build the AMLA-aligned JSON payload for one submission batch.

    Cases are sorted by (rule_id, case_id) for deterministic output.
    """
    obliged_entity = obliged_entity or ObligedEntity(programme_name=spec.program.name)
    submitting_person = submitting_person or SubmittingPerson()
    submission_date = submission_date or datetime.now(tz=timezone.utc)

    customer_idx = _customer_index(customers)
    sorted_cases = sorted(cases, key=lambda c: (c.get("rule_id", ""), c.get("case_id", "")))

    reports: list[dict[str, Any]] = []
    for case in sorted_cases:
        cust_id = (case.get("alert") or {}).get("customer_id")
        customer = customer_idx.get(cust_id) if cust_id else None
        case_txns = _txns_for_case(case, transactions)
        reports.append(
            build_amla_report(case, customer, case_txns, jurisdiction=spec.program.jurisdiction)
        )

    payload: dict[str, Any] = {
        "_schema": DRAFT_VERSION,
        "_draft_warning": DRAFT_WARNING,
        "submission_id": f"{spec.program.name.lower().replace(' ', '_')}-"
        f"{submission_date.strftime('%Y%m%dT%H%M%SZ')}",
        "submission_date": submission_date.isoformat(),
        "submission_jurisdiction": spec.program.jurisdiction,
        "obliged_entity": obliged_entity.to_dict(),
        "submitting_person": submitting_person.to_dict(),
        "reports": reports,
    }
    payload["conformance"] = _conformance_block(obliged_entity, reports)
    return payload


def build_amla_str_json(
    spec: AMLSpec,
    cases: list[dict[str, Any]],
    customers: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    **kwargs: Any,
) -> bytes:
    """Convenience: build payload and serialise to JSON bytes."""
    payload = build_amla_str_payload(spec, cases, customers, transactions, **kwargs)
    return json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")


def export_amla_str_from_run_dir(
    run_dir: Path,
    spec: AMLSpec,
    customers: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    **kwargs: Any,
) -> bytes:
    """Read cases from a finalised run directory and build the AMLA payload."""
    cases_dir = run_dir / "cases"
    if not cases_dir.exists():
        raise FileNotFoundError(f"No cases/ directory in {run_dir}")
    cases = [json.loads(p.read_bytes()) for p in sorted(cases_dir.glob("*.json"))]
    return build_amla_str_json(spec, cases, customers, transactions, **kwargs)
