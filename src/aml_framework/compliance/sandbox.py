"""Cross-border typology-sharing sandbox — FATF R.18.

Process problem this solves
---------------------------
FATF Recommendation 18 says financial institutions should share AML
typology patterns across jurisdictions. AMLA's central register makes
this an EU-wide expectation by H2 2026. **In practice no FI does this
because their lawyers say no** — raw counterparty data crosses the
GDPR / PIPEDA / cross-border-transfer rules of three jurisdictions
before it reaches the partner FI.

The legal blocker isn't the *pattern*. It's the **identifiers**. A
"this customer was the centre of a 4-node fan-out cluster" insight
has zero PII once you obfuscate the customer ids — it's a
*structural* observation. Two FIs can compare those obfuscated shapes
and discover overlap (the same mule cluster touched both of them)
without ever exchanging an account number.

What this module ships
----------------------
- `obfuscate_pattern_match` — turn an engine `network_pattern` match
  into a privacy-preserving `ObfuscatedPattern`: per-FI HMAC-SHA-256
  of each customer id (so identifiers can never be reversed without
  the salt) plus the structural fingerprint (component size, max
  hop, edge count).
- `verify_pattern_overlap` — given two obfuscated patterns from
  different FIs, identify whether they share *structural* shape and
  whether any obfuscated identifiers overlap (re-using a shared salt
  arrangement, see the docstring for the salt-rotation note).

The sandbox itself is one file because the privacy story is the
value; over-engineering the transport would distract from it.

Salt arrangement
----------------
Two FIs that want to share patterns agree on a per-pair, per-period
salt out-of-band (e.g. monthly rotation via a shared key vault).
With a shared salt, identical raw customer ids produce identical
HMACs across the two FIs — that's how overlap detection works. Salts
are rotated to bound the linkability window. Without the shared
salt, the sandbox is a structural fingerprint exchange only.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable


@dataclass(frozen=True)
class ObfuscatedPattern:
    """One FI's privacy-preserving description of a network match.

    No raw identifiers; the only customer-derived data is the HMAC of
    each id under the per-pair salt. Add new fields here only if they
    can be derived without leaking PII (counts and structural metrics
    are fine; names, addresses, account numbers are never).
    """

    fi_id: str  # the publishing FI's LEI / BIC
    rule_family: str  # taxonomy slug e.g. "rtp_mule_cluster"
    detected_at: datetime
    pattern_kind: str  # e.g. "component_size", "fan_out", "ramp_up_then_drain"
    structural_fingerprint: dict[str, int]  # node_count, edge_count, max_hop, etc.
    obfuscated_subject_ids: list[str] = field(default_factory=list)
    obfuscated_neighbour_ids: list[str] = field(default_factory=list)
    salt_period: str = ""  # e.g. "2026-04" — receiving FI checks they have the same period

    def to_dict(self) -> dict[str, Any]:
        return {
            "fi_id": self.fi_id,
            "rule_family": self.rule_family,
            "detected_at": self.detected_at.isoformat(),
            "pattern_kind": self.pattern_kind,
            "structural_fingerprint": self.structural_fingerprint,
            "obfuscated_subject_ids": list(self.obfuscated_subject_ids),
            "obfuscated_neighbour_ids": list(self.obfuscated_neighbour_ids),
            "salt_period": self.salt_period,
        }


@dataclass(frozen=True)
class OverlapReport:
    """Result of comparing two ObfuscatedPatterns from different FIs."""

    structural_match: bool
    structural_distance: int  # 0 = identical fingerprint
    overlapping_obfuscated_ids: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def has_identifier_overlap(self) -> bool:
        return bool(self.overlapping_obfuscated_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "structural_match": self.structural_match,
            "structural_distance": self.structural_distance,
            "overlapping_obfuscated_ids": list(self.overlapping_obfuscated_ids),
            "has_identifier_overlap": self.has_identifier_overlap,
            "note": self.note,
        }


# ---------------------------------------------------------------------------
# Obfuscation
# ---------------------------------------------------------------------------


def obfuscate_id(raw_id: str, *, salt: bytes) -> str:
    """HMAC-SHA-256(salt, id) hex-encoded.

    HMAC (not bare hash) so an attacker without the salt can't pre-
    compute a rainbow table over the customer-id space. Keep the
    encoded form short (16 hex chars = 64 bits) — birthday-paradox
    collisions across an FI's customer base are negligible at <10⁹
    customers and we leak less if the obfuscated set is exposed.
    """
    digest = hmac.new(salt, raw_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:16]


def obfuscate_pattern_match(
    *,
    fi_id: str,
    rule_family: str,
    detected_at: datetime,
    pattern_kind: str,
    subject_ids: Iterable[str],
    neighbour_ids: Iterable[str] = (),
    structural_fingerprint: dict[str, int] | None = None,
    salt: bytes,
    salt_period: str = "",
) -> ObfuscatedPattern:
    """Construct an `ObfuscatedPattern` ready to publish to a peer FI."""
    if not salt:
        raise ValueError("salt is required — refuse to publish without obfuscation")
    subjects = sorted({obfuscate_id(s, salt=salt) for s in subject_ids if s})
    neighbours = sorted({obfuscate_id(n, salt=salt) for n in neighbour_ids if n})
    fp = dict(structural_fingerprint or {})
    fp.setdefault("subject_count", len(subjects))
    fp.setdefault("neighbour_count", len(neighbours))
    return ObfuscatedPattern(
        fi_id=fi_id,
        rule_family=rule_family,
        detected_at=detected_at,
        pattern_kind=pattern_kind,
        structural_fingerprint=fp,
        obfuscated_subject_ids=subjects,
        obfuscated_neighbour_ids=neighbours,
        salt_period=salt_period,
    )


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def _l1_distance(a: dict[str, int], b: dict[str, int]) -> int:
    keys = set(a) | set(b)
    return sum(abs(a.get(k, 0) - b.get(k, 0)) for k in keys)


def verify_pattern_overlap(
    local: ObfuscatedPattern,
    peer: ObfuscatedPattern,
    *,
    structural_tolerance: int = 1,
) -> OverlapReport:
    """Compare two patterns. Returns structural-match + identifier overlap.

    Identifier overlap is **only meaningful when both FIs used the
    same salt** (per-pair, per-period agreement). The function does
    not enforce that — it can't, since the salt is never sent over
    the wire — but it includes the `salt_period` mismatch as a note
    so the caller knows the overlap signal is degenerate.
    """
    if local.pattern_kind != peer.pattern_kind:
        return OverlapReport(
            structural_match=False,
            structural_distance=-1,
            note=f"pattern_kind mismatch: {local.pattern_kind} vs {peer.pattern_kind}",
        )

    distance = _l1_distance(local.structural_fingerprint, peer.structural_fingerprint)
    structural_match = distance <= structural_tolerance

    overlapping: list[str] = []
    note = ""
    if local.salt_period and peer.salt_period and local.salt_period == peer.salt_period:
        local_set = set(local.obfuscated_subject_ids) | set(local.obfuscated_neighbour_ids)
        peer_set = set(peer.obfuscated_subject_ids) | set(peer.obfuscated_neighbour_ids)
        overlapping = sorted(local_set & peer_set)
    else:
        note = (
            "salt_period mismatch or absent — identifier overlap not meaningful "
            "without a shared per-pair salt agreement"
        )

    return OverlapReport(
        structural_match=structural_match,
        structural_distance=distance,
        overlapping_obfuscated_ids=overlapping,
        note=note,
    )
