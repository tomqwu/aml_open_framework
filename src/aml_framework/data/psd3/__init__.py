"""PSD3 / Verification-of-Payee (VoP) ingestion adapter.

Round-7 PR #4. The EU's PSD3 + PSR (Payment Services Regulation) reached
provisional Council/Parliament agreement end-Q2 2026 ([Norton Rose
Fulbright PSD3 brief](
https://www.nortonrosefulbright.com/en/knowledge/publications/cedd39c6/psd3-and-psr-from-provisional-agreement-to-2026-readiness)).
The Verification-of-Payee (VoP) / payee-name-match liability applies
24 months after Official Journal entry into force — likely Q3 2028.
The 2-year window is the right time for a reference implementation
to exist before banks have to procure one.

Status: **DRAFT** — pinned to the Council/Parliament provisional
text. Format may shift in the corrigenda before Official Journal.
Operators using this adapter against pre-OJ payment streams should
expect schema changes in the next release.

What's here
- `parse_vop_response(payload)` — VoP API response → normalised dict
- `vop_match_outcome(...)` — classify a VoP response as one of
  match / close_match / no_match / not_checked / outside_scope
- `load_vop_dir(directory)` — bulk loader for JSON-Lines VoP logs

Why a separate adapter (not just CSV ingestion)
The VoP scheme operates as a real-time inter-bank API (similar to
the UK's CoP). Banks log every VoP query + response for liability
audit. Those logs need a structured parse to feed the framework's
`txn` data contract's `confirmation_of_payee_status` column (already
present in the UK APP-fraud spec from Round-7 #3).
"""

from aml_framework.data.psd3.parser import (
    VOP_OUTCOMES,
    VOP_SCHEMA_VERSION,
    VopResponse,
    load_vop_dir,
    parse_vop_response,
    vop_match_outcome,
)

__all__ = [
    "VOP_OUTCOMES",
    "VOP_SCHEMA_VERSION",
    "VopResponse",
    "load_vop_dir",
    "parse_vop_response",
    "vop_match_outcome",
]
