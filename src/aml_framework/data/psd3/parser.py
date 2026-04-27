"""VoP (Verification of Payee) response parser.

The PSD3/PSR Verification-of-Payee API response — agreed provisional
text, EU Official Journal expected end-Q2 2026 — uses a JSON envelope
that maps to four normalised outcomes:

  - `match`         — payee name matches the account holder exactly
  - `close_match`   — payee name matches with minor variation
                      (typo, abbreviation, case)
  - `no_match`      — payee name does not match
  - `not_checked`   — payee bank doesn't support VoP yet (transition
                      period under PSD3/PSR Article 50a)
  - `outside_scope` — payment outside the VoP-mandatory scope (e.g.
                      payment to own account at same bank)

Banks log every VoP request + response into a structured event store
for liability audit. This module parses those logs into the shape the
framework's `txn` data contract expects (the
`confirmation_of_payee_status` column added in the Round-7 #3 UK APP
spec — same column name works for both UK CoP and EU VoP).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# DRAFT — pinned to PSD3/PSR provisional Council/Parliament text.
# Bump this string when the Official Journal version differs.
VOP_SCHEMA_VERSION = "psd3-vop-2026-q2-draft"

VOP_OUTCOMES = frozenset({"match", "close_match", "no_match", "not_checked", "outside_scope"})

# Match-score thresholds. PSD3 RTS hasn't pinned exact cutoffs in the
# provisional text; these mirror the UK CoP scheme's effective
# thresholds (>= 0.85 = match, 0.70-0.84 = close_match) which is the
# closest precedent.
_MATCH_THRESHOLD = 0.85
_CLOSE_MATCH_THRESHOLD = 0.70


@dataclass(frozen=True)
class VopResponse:
    """One Verification-of-Payee response, parsed + normalised."""

    request_id: str
    payment_id: str  # the txn the VoP was performed against
    payer_iban: str
    payee_iban: str
    payee_name_supplied: str
    payee_name_actual: str  # what the receiving bank holds
    match_score: float  # 0.0-1.0; how closely the names matched
    outcome: str  # one of VOP_OUTCOMES
    payee_account_status: str  # active / closed / blocked / unknown
    response_time_ms: int  # SLA evidence
    received_at: datetime | None
    schema_version: str = VOP_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if isinstance(d.get("received_at"), datetime):
            d["received_at"] = d["received_at"].isoformat()
        return d


# ---------------------------------------------------------------------------
# Outcome classification
# ---------------------------------------------------------------------------


def vop_match_outcome(
    *,
    score: float | None,
    payee_supports_vop: bool = True,
    in_scope: bool = True,
) -> str:
    """Classify a VoP response into one of the five outcomes.

    Args:
        score: name-match score 0.0-1.0. None when the receiving bank
            didn't return one.
        payee_supports_vop: False when the payee bank is in the
            transition window and hasn't enabled VoP yet.
        in_scope: False for own-account / inter-bank / sanctioned
            channels that PSD3 carved out from VoP coverage.
    """
    if not in_scope:
        return "outside_scope"
    if not payee_supports_vop:
        return "not_checked"
    if score is None:
        return "not_checked"
    if score >= _MATCH_THRESHOLD:
        return "match"
    if score >= _CLOSE_MATCH_THRESHOLD:
        return "close_match"
    return "no_match"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_vop_response(payload: bytes | str | dict[str, Any]) -> VopResponse | None:
    """Parse a single VoP response into a normalised VopResponse.

    Returns None when the payload is malformed (we never raise — VoP
    logs come from production message buses where one bad message
    shouldn't block ingestion).
    """
    if isinstance(payload, (bytes, str)):
        try:
            data = json.loads(payload if isinstance(payload, str) else payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
    elif isinstance(payload, dict):
        data = payload
    else:
        return None

    if not isinstance(data, dict):
        return None

    # The provisional PSD3/PSR text uses these field names; we tolerate
    # both camelCase + snake_case variants since proto specs flip-flop.
    def _g(*keys: str, default: Any = "") -> Any:
        for k in keys:
            if k in data and data[k] is not None:
                return data[k]
        return default

    # Outcome resolution: prefer explicit field, otherwise compute from
    # score + flags using the same rules as `vop_match_outcome()`.
    outcome = _g("outcome", "matchOutcome", "match_outcome")
    score_raw = _g("matchScore", "match_score", default=None)
    score = None
    if score_raw is not None:
        try:
            score = float(score_raw)
        except (TypeError, ValueError):
            score = None

    if not outcome or outcome not in VOP_OUTCOMES:
        outcome = vop_match_outcome(
            score=score,
            payee_supports_vop=bool(_g("payeeSupportsVop", "payee_supports_vop", default=True)),
            in_scope=bool(_g("inScope", "in_scope", default=True)),
        )

    received_at_raw = _g("receivedAt", "received_at", default=None)
    received_at: datetime | None = None
    if isinstance(received_at_raw, str) and received_at_raw:
        try:
            received_at = datetime.fromisoformat(
                received_at_raw.replace("Z", "+00:00").replace("+00:00", "")
            )
        except ValueError:
            received_at = None

    try:
        response_time_ms = int(_g("responseTimeMs", "response_time_ms", default=0))
    except (TypeError, ValueError):
        response_time_ms = 0

    return VopResponse(
        request_id=str(_g("requestId", "request_id")),
        payment_id=str(_g("paymentId", "payment_id")),
        payer_iban=str(_g("payerIban", "payer_iban")),
        payee_iban=str(_g("payeeIban", "payee_iban")),
        payee_name_supplied=str(_g("payeeNameSupplied", "payee_name_supplied")),
        payee_name_actual=str(_g("payeeNameActual", "payee_name_actual")),
        match_score=score if score is not None else 0.0,
        outcome=outcome,
        payee_account_status=str(
            _g("payeeAccountStatus", "payee_account_status", default="unknown")
        ),
        response_time_ms=response_time_ms,
        received_at=received_at,
    )


# ---------------------------------------------------------------------------
# Bulk loader
# ---------------------------------------------------------------------------


def load_vop_dir(directory: str | Path) -> list[VopResponse]:
    """Load every `*.jsonl` file under `directory` as VoP responses.

    Skips malformed lines silently; returns the parsed responses sorted
    by `request_id` for deterministic output.
    """
    out: list[VopResponse] = []
    for vop_file in sorted(Path(directory).glob("**/*.jsonl")):
        for line in vop_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            response = parse_vop_response(line)
            if response is not None:
                out.append(response)
    return sorted(out, key=lambda r: r.request_id)
