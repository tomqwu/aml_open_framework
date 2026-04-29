"""Reference adapter for the FINOS Open Compliance API draft.

Process problem this addresses
------------------------------
When an STR-track investigation's subject is a counterparty held at
another bank, the cross-bank handoff today happens by email +
spreadsheet + 48-hour turnaround. Each pair of banks invents a custom
integration. The receiving FI re-collects evidence from the customer
even though the sending FI already has it.

This module is the thin code that maps our existing case shape into
the `HandoffRequest` envelope defined in
`src/aml_framework/api/openapi-compliance.yaml`. Institutions adopting
the framework's REST API can mount this adapter behind their existing
OIDC / mTLS perimeter and start exchanging handoffs with any peer
that implements the same draft, with no bespoke integration per peer.

Scope kept narrow:
- Outbound envelope construction (`build_handoff_request`)
- Outcome envelope construction (`build_outcome`)
- SHA-256 of an evidence bundle (`bundle_sha256`)

The actual HTTP server / client stays deliberately out of scope here.
Each institution's API team can wire it into their FastAPI / Spring
/ Express server in <1 day given the OpenAPI spec.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

Urgency = Literal["routine", "elevated", "immediate"]
Outcome = Literal[
    "str_filed",
    "no_action_documented",
    "escalated_to_law_enforcement",
    "withdrawn",
]

# SLAs the OpenAPI doc commits to per urgency tier — mirror them here so
# the adapter's `sla_deadline` calculation matches the contract.
_SLA_HOURS: dict[Urgency, int] = {
    "routine": 24,
    "elevated": 4,
    "immediate": 1,
}


@dataclass(frozen=True)
class InstitutionRef:
    """Sending or receiving FI identity."""

    name: str
    country: str
    lei: str | None = None
    bic: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "country": self.country}
        if self.lei:
            d["lei"] = self.lei
        if self.bic:
            d["bic"] = self.bic
        return d


def bundle_sha256(payload: bytes) -> str:
    """SHA-256 of a built evidence bundle ZIP."""
    return hashlib.sha256(payload).hexdigest()


def build_handoff_request(
    *,
    external_handoff_id: str,
    sending_fi: InstitutionRef,
    receiving_fi: InstitutionRef,
    case: dict[str, Any],
    evidence_zip: bytes,
    typology: str,
    urgency: Urgency = "routine",
    regulator_filed: bool = False,
    notes: str = "",
) -> dict[str, Any]:
    """Build a HandoffRequest envelope for one of our internal cases.

    `case` is the raw case dict the engine produces. We pull the
    counterparty subject from the alert payload — the receiving FI's
    customer is whoever the case's transaction was sent *to* (for
    outbound flows) or *from* (for inbound).
    """
    alert = case.get("alert") or {}
    subject_id = (
        alert.get("counterparty_account")
        or alert.get("counterparty_id")
        or case.get("counterparty_id", "")
    )
    subject_name = alert.get("counterparty_name") or case.get("counterparty_name", "")
    return {
        "external_handoff_id": external_handoff_id,
        "sending_fi": sending_fi.to_dict(),
        "receiving_fi": receiving_fi.to_dict(),
        "subject": {
            "identifier_type": "account_number" if subject_id else "opaque",
            "identifier_value": subject_id or "unknown",
            "display_name": subject_name,
        },
        "typology": typology,
        "urgency": urgency,
        "evidence_sha256": bundle_sha256(evidence_zip),
        "regulator_filed": regulator_filed,
        "notes": notes,
    }


def build_outcome(
    *,
    outcome: Outcome,
    decided_at: datetime,
    regulator_reference: str | None = None,
    narrative_summary: str = "",
) -> dict[str, Any]:
    """Build a HandoffOutcome envelope to send back to the originator."""
    body: dict[str, Any] = {
        "outcome": outcome,
        "decided_at": decided_at.isoformat(),
    }
    if regulator_reference:
        body["regulator_reference"] = regulator_reference
    if narrative_summary:
        body["narrative_summary"] = narrative_summary
    return body


def sla_deadline_for(urgency: Urgency, *, accepted_at: datetime) -> datetime:
    """Compute the receiver-side SLA deadline based on urgency."""
    return accepted_at + timedelta(hours=_SLA_HOURS[urgency])
