"""Tests for `compliance/sandbox.py` — cross-border typology sharing.

The legal-defensibility invariants this guards:
- raw customer ids never appear in the published artifact
- different salts produce different obfuscated ids (per-pair isolation)
- structural overlap can be computed without identifier overlap
- identifier overlap requires both FIs to declare the same salt period
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest

from aml_framework.compliance.sandbox import (
    ObfuscatedPattern,
    OverlapReport,
    obfuscate_id,
    obfuscate_pattern_match,
    verify_pattern_overlap,
)


# ---------------------------------------------------------------------------
# Obfuscation primitives
# ---------------------------------------------------------------------------


def test_obfuscate_id_is_deterministic_per_salt() -> None:
    salt = b"shared-pair-key-v1"
    a = obfuscate_id("C0001", salt=salt)
    b = obfuscate_id("C0001", salt=salt)
    assert a == b
    assert len(a) == 16  # 64-bit truncation as documented


def test_obfuscate_id_changes_when_salt_changes() -> None:
    a = obfuscate_id("C0001", salt=b"salt-1")
    b = obfuscate_id("C0001", salt=b"salt-2")
    assert a != b


def test_obfuscate_id_does_not_leak_raw_id() -> None:
    """An obfuscated id must not contain the raw id in any form."""
    raw = "C-very-distinctive-12345"
    out = obfuscate_id(raw, salt=os.urandom(16))
    assert raw not in out
    assert "12345" not in out  # substring leak check


# ---------------------------------------------------------------------------
# Pattern construction
# ---------------------------------------------------------------------------


def test_obfuscate_pattern_match_emits_obfuscated_subjects_only() -> None:
    salt = b"pair-2026-04"
    pattern = obfuscate_pattern_match(
        fi_id="LEI-A",
        rule_family="rtp_mule_cluster",
        detected_at=datetime(2026, 4, 28),
        pattern_kind="component_size",
        subject_ids=["C0013", "C0023"],
        neighbour_ids=["X0001", "X0002", "X0003"],
        salt=salt,
        salt_period="2026-04",
    )
    assert isinstance(pattern, ObfuscatedPattern)
    # Raw ids must never appear.
    serialized = str(pattern.to_dict())
    assert "C0013" not in serialized
    assert "X0001" not in serialized
    # Counts are the only structural info auto-derived.
    assert pattern.structural_fingerprint["subject_count"] == 2
    assert pattern.structural_fingerprint["neighbour_count"] == 3


def test_obfuscate_refuses_empty_salt() -> None:
    with pytest.raises(ValueError, match="salt is required"):
        obfuscate_pattern_match(
            fi_id="LEI-A",
            rule_family="rtp_mule_cluster",
            detected_at=datetime(2026, 4, 28),
            pattern_kind="component_size",
            subject_ids=["C0013"],
            salt=b"",
        )


def test_obfuscate_pattern_dedups_subject_ids() -> None:
    salt = b"pair-2026-04"
    pattern = obfuscate_pattern_match(
        fi_id="LEI-A",
        rule_family="rtp_mule_cluster",
        detected_at=datetime(2026, 4, 28),
        pattern_kind="component_size",
        subject_ids=["C0013", "C0013", "C0013"],
        salt=salt,
    )
    assert len(pattern.obfuscated_subject_ids) == 1


# ---------------------------------------------------------------------------
# Overlap detection
# ---------------------------------------------------------------------------


def _pattern(
    *, salt: bytes, salt_period: str, subjects: list[str], fi_id: str
) -> ObfuscatedPattern:
    return obfuscate_pattern_match(
        fi_id=fi_id,
        rule_family="rtp_mule_cluster",
        detected_at=datetime(2026, 4, 28),
        pattern_kind="component_size",
        subject_ids=subjects,
        structural_fingerprint={"node_count": len(subjects), "max_hop": 2},
        salt=salt,
        salt_period=salt_period,
    )


def test_overlap_detects_shared_obfuscated_ids_with_shared_salt() -> None:
    """Two FIs using the same agreed salt see overlap on the same raw id."""
    salt = b"AB-pair-2026-04"
    a = _pattern(
        salt=salt,
        salt_period="2026-04",
        subjects=["MULE-001", "MULE-002"],
        fi_id="LEI-A",
    )
    b = _pattern(
        salt=salt,
        salt_period="2026-04",
        subjects=["MULE-001", "MULE-099"],
        fi_id="LEI-B",
    )
    overlap = verify_pattern_overlap(a, b)
    assert isinstance(overlap, OverlapReport)
    assert overlap.has_identifier_overlap
    # MULE-001 obfuscates to the same hash under the same salt; MULE-002
    # and MULE-099 don't overlap.
    assert len(overlap.overlapping_obfuscated_ids) == 1


def test_overlap_does_not_detect_when_salts_differ() -> None:
    """Different salts → no identifier overlap even on identical raw ids.
    This is the privacy guarantee that lets two FIs without a shared
    salt agreement still exchange structural patterns safely."""
    a = _pattern(salt=b"A-only", salt_period="2026-04", subjects=["MULE-001"], fi_id="LEI-A")
    b = _pattern(salt=b"B-only", salt_period="2026-04", subjects=["MULE-001"], fi_id="LEI-B")
    overlap = verify_pattern_overlap(a, b)
    # Note: salt_period matches but obfuscated values differ — no overlap.
    assert overlap.overlapping_obfuscated_ids == []


def test_overlap_warns_when_salt_periods_mismatch() -> None:
    a = _pattern(salt=b"AB", salt_period="2026-03", subjects=["MULE-001"], fi_id="LEI-A")
    b = _pattern(salt=b"AB", salt_period="2026-04", subjects=["MULE-001"], fi_id="LEI-B")
    overlap = verify_pattern_overlap(a, b)
    assert "salt_period mismatch" in overlap.note
    assert overlap.overlapping_obfuscated_ids == []


def test_structural_match_independent_of_salt() -> None:
    """Two FIs with no shared salt can still detect they're seeing the
    same structural shape (same component size, same hop depth, etc).
    This is the legal-safe minimum the sandbox must support."""
    a = _pattern(salt=b"A-only", salt_period="", subjects=["X1", "X2", "X3", "X4"], fi_id="LEI-A")
    b = _pattern(salt=b"B-only", salt_period="", subjects=["Y1", "Y2", "Y3", "Y4"], fi_id="LEI-B")
    overlap = verify_pattern_overlap(a, b)
    assert overlap.structural_match is True
    assert overlap.structural_distance == 0


def test_pattern_kind_mismatch_is_not_a_match() -> None:
    a = _pattern(salt=b"AB", salt_period="2026-04", subjects=["X1"], fi_id="LEI-A")
    b = obfuscate_pattern_match(
        fi_id="LEI-B",
        rule_family="rtp_mule_cluster",
        detected_at=datetime(2026, 4, 28),
        pattern_kind="ramp_up_then_drain",  # different kind
        subject_ids=["Y1"],
        salt=b"AB",
        salt_period="2026-04",
    )
    overlap = verify_pattern_overlap(a, b)
    assert overlap.structural_match is False
    assert "pattern_kind mismatch" in overlap.note


def test_structural_distance_grows_with_difference() -> None:
    salt = b"AB"
    a = obfuscate_pattern_match(
        fi_id="LEI-A",
        rule_family="x",
        detected_at=datetime(2026, 4, 28),
        pattern_kind="component_size",
        subject_ids=["S1", "S2", "S3"],
        structural_fingerprint={"node_count": 3, "max_hop": 2},
        salt=salt,
    )
    b = obfuscate_pattern_match(
        fi_id="LEI-B",
        rule_family="x",
        detected_at=datetime(2026, 4, 28),
        pattern_kind="component_size",
        subject_ids=["S4", "S5", "S6", "S7", "S8"],
        structural_fingerprint={"node_count": 5, "max_hop": 3},
        salt=salt,
    )
    overlap = verify_pattern_overlap(a, b, structural_tolerance=1)
    assert overlap.structural_match is False  # distance > tolerance
    assert overlap.structural_distance > 1
