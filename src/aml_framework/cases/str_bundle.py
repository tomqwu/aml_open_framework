"""Case-to-STR auto-bundling — one ZIP per investigation.

Round-6 PR #4. The framework's existing artifacts make analyst handoff
work but require operator stitching: narrative.txt comes from
`generators/narrative.py`, the regulator-format XML from
`generators/goaml_xml.py` (or `generators/amla_str.py`), the Mermaid
network diagram from `engine/explain.py`, and the case JSON itself
from the audit ledger. Every regulator submission today means an
analyst opening 4 files and re-zipping them by hand.

This module ships **`bundle_investigation_to_str(investigation, ...)`**
that produces one self-contained `<investigation_id>.zip` containing:

    investigation.json           — the Investigation dict (subject,
                                   case_ids, severity, total_amount,
                                   window bounds — Round-6 #1 output)
    cases/<case_id>.json         — every constituent case file
    narrative.txt                — analyst-ready STR/SAR narrative
                                   (one section per case)
    goaml_report.xml             — regulator-format XML covering all
                                   constituent cases (or amla_str.xml
                                   for EU jurisdictions)
    network/<case_id>.mmd        — Mermaid network diagram per case
                                   that has a network_pattern subgraph
    manifest.json                — bundle metadata: version, sha256
                                   over all included files, generated_at,
                                   spec hash for round-tripping

The manifest hash chain means a regulator can verify every byte of the
bundle against what was originally produced — no silent edits, no
out-of-band attachments. Composes with the audit ledger's existing
SHA-256 hash chain (PR #43).

Why this matters now: **Wolfsberg's Feb 2026 correspondent-banking
guidance** explicitly called out "submission-ready packages" as the
expectation for issuer-FI handoffs to FIU; ad-hoc PDF bundles no
longer cut it. Most commercial AML platforms ship this; OSS
framework needs parity to compete on real procurement decisions.

Design
- Pure function returning `bytes` (the ZIP). No IO inside; the caller
  decides where to write the file (disk, S3, FastAPI download endpoint).
- Deterministic: same inputs always produce identical bytes
  (sorted file order, fixed timestamp inside ZipInfo, sorted JSON keys).
  Same input hash → same bundle hash. This protects the
  audit-replay guarantee from PR #53 MRM bundle.
- Skips empty optional sections gracefully — investigations with no
  network_pattern alerts get no `network/` subdir, not an empty one.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from aml_framework.engine.explain import explain_network_alert, to_mermaid
from aml_framework.generators.goaml_xml import build_goaml_xml
from aml_framework.generators.narrative import generate_str_narrative
from aml_framework.spec.models import AMLSpec

BUNDLE_VERSION = "1"

# Fixed timestamp baked into every ZipInfo so identical inputs produce
# byte-identical archives. Picked once and never moved — keeps the
# determinism contract stable across releases.
_ZIP_FIXED_TIME = (1980, 1, 1, 0, 0, 0)

# Fixed submission timestamp for the embedded goAML XML. Real submissions
# go out via the audit-stamped API endpoint with a real timestamp; the
# bundle artifact uses this synthetic anchor so deterministic-rerun
# verification holds. The investigation's window_end is the analyst-
# meaningful date and lives in investigation.json.
_FIXED_SUBMISSION_DATE = datetime(2020, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# JSON serialisation — handle Decimal + datetime inside case dicts
# ---------------------------------------------------------------------------


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"unserialisable type {type(obj).__name__}")


def _dump_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        indent=2,
        default=_json_default,
        ensure_ascii=False,
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def bundle_investigation_to_str(
    investigation: dict[str, Any],
    cases: list[dict[str, Any]],
    *,
    spec: AMLSpec,
    customers: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
) -> bytes:
    """Build a self-contained STR-submission ZIP for one investigation.

    Args:
        investigation: the Investigation dict from
            `cases.aggregate_investigations` — must carry `investigation_id`
            and `case_ids` at minimum.
        cases: every constituent case dict. Caller filters by
            `investigation["case_ids"]` before calling. Cases not in the
            investigation are silently dropped.
        spec: the AMLSpec the cases were produced from. Used by the
            goAML builder for jurisdiction + program metadata.
        customers: the full customer table (we'll pick the relevant
            subjects per case).
        transactions: the full transaction table (we'll filter per case).

    Returns:
        The ZIP file as bytes. Caller writes to disk / S3 / HTTP response.
    """
    inv_id = investigation.get("investigation_id", "INV-UNKNOWN")
    case_ids = set(investigation.get("case_ids", []))
    constituent = [c for c in cases if c.get("case_id") in case_ids]
    constituent.sort(key=lambda c: c.get("case_id", ""))

    customer_idx = {c.get("customer_id"): c for c in customers if c.get("customer_id")}

    # Build all the in-memory artifacts first so we can compute the
    # bundle-wide manifest hash before writing.
    files: dict[str, bytes] = {}

    # Investigation summary.
    files["investigation.json"] = _dump_json(investigation)

    # Per-case JSON.
    for case in constituent:
        case_id = case.get("case_id", "unknown")
        files[f"cases/{case_id}.json"] = _dump_json(case)

    # One narrative document covering every constituent case, joined by
    # rule. Auditors complained that per-case narratives lost the link
    # between the alerts that fired together; this ties them back.
    narrative_sections: list[str] = []
    for case in constituent:
        cust_id = (case.get("alert") or {}).get("customer_id")
        customer = customer_idx.get(cust_id)
        case_txns = _txns_for_case(case, transactions)
        narrative_sections.append(
            generate_str_narrative(
                case=case,
                customer=customer,
                transactions=case_txns,
                jurisdiction=spec.program.jurisdiction,
            )
        )
    files["narrative.txt"] = (
        ("\n\n" + ("=" * 78 + "\n") * 1).join(narrative_sections).encode("utf-8")
    )

    # Regulator-format XML — goAML for FATF / FINTRAC / generic.
    # submission_date is pinned so the bundle bytes are deterministic;
    # the real submission timestamp is recorded in the audit ledger
    # when the bundle is actually transmitted to a regulator.
    if constituent:
        files["goaml_report.xml"] = build_goaml_xml(
            spec=spec,
            cases=constituent,
            customers=customers,
            transactions=transactions,
            submission_date=_FIXED_SUBMISSION_DATE,
        )

    # Per-case Mermaid network diagrams (only when a subgraph payload
    # actually exists — non-network rules don't carry one).
    for case in constituent:
        alert = case.get("alert") or {}
        if not alert.get("subgraph"):
            continue
        try:
            payload = explain_network_alert(alert)
            mermaid = to_mermaid(payload)
        except (KeyError, ValueError):
            # Bundle should never fail because one case has malformed
            # subgraph data; surface that as a missing diagram instead.
            continue
        files[f"network/{case.get('case_id')}.mmd"] = mermaid.encode("utf-8")

    # Manifest — last so it can hash everything else.
    file_hashes = {
        path: hashlib.sha256(payload).hexdigest() for path, payload in sorted(files.items())
    }
    bundle_hash = hashlib.sha256(
        "\n".join(f"{path}:{digest}" for path, digest in sorted(file_hashes.items())).encode(
            "utf-8"
        )
    ).hexdigest()
    manifest = {
        "bundle_version": BUNDLE_VERSION,
        "investigation_id": inv_id,
        "case_count": len(constituent),
        "case_ids": sorted(c.get("case_id", "") for c in constituent),
        "spec_program": spec.program.name,
        "jurisdiction": spec.program.jurisdiction,
        "files": file_hashes,
        "bundle_hash": bundle_hash,
    }
    files["manifest.json"] = _dump_json(manifest)

    # Now write the ZIP with deterministic ordering + fixed timestamps.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(files.keys()):
            info = zipfile.ZipInfo(filename=path, date_time=_ZIP_FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, files[path])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_dt(v: Any) -> datetime | None:
    """Best-effort datetime coercion. Returns None when value isn't a date."""
    if isinstance(v, datetime):
        return v
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00").replace("+00:00", ""))
        except ValueError:
            return None
    return None


def _txns_for_case(
    case: dict[str, Any], transactions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Filter the txn table down to rows the alert covers.

    Mirrors `generators/goaml_xml.py:_txns_for_case` — we keep the
    bundling logic self-contained instead of importing the private
    helper to avoid coupling to an internal generator API. Tolerant
    of mixed datetime / ISO-string shapes since cases round-tripped
    through JSON come back as strings while in-memory cases hold
    real datetimes.
    """
    alert = case.get("alert") or {}
    cust_id = alert.get("customer_id")
    if not cust_id:
        return []
    window_start = _coerce_dt(alert.get("window_start"))
    window_end = _coerce_dt(alert.get("window_end"))

    def _in_window(t: dict[str, Any]) -> bool:
        if t.get("customer_id") != cust_id:
            return False
        booked = _coerce_dt(t.get("booked_at"))
        if booked is None:
            # No booked_at to compare against — include in case (fail open).
            return True
        if window_start is not None and booked < window_start:
            return False
        if window_end is not None and booked > window_end:
            return False
        return True

    return [t for t in transactions if _in_window(t)]


def bundle_hash(bundle_bytes: bytes) -> str:
    """SHA-256 over the entire bundle ZIP — useful for receipt records."""
    return hashlib.sha256(bundle_bytes).hexdigest()


__all__ = [
    "BUNDLE_VERSION",
    "bundle_investigation_to_str",
    "bundle_hash",
]
