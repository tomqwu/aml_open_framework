"""Zip-slip hardening for evidence packs (PR-H4).

`case_id` is `<rule>__<customer>__<ts>` and `customer_id` is data-derived,
so a malformed source could carry a path separator or `..` into a ZIP entry
name (zip-slip on extraction). These tests pin that ZIP entry *paths* are
separator-safe and that the archive-boundary guard rejects traversal.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aml_framework.generators.audit_pack import (
    _assert_safe_zip_path,
    _case_pack_files,
    _safe_zip_segment,
)
from aml_framework.spec import load_spec

SPEC = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


# --- _safe_zip_segment ----------------------------------------------------


@pytest.mark.parametrize("raw", ["a/b/c", "a\\b", "../../etc/passwd", "..", "/abs/path"])
def test_safe_zip_segment_removes_traversal(raw):
    out = _safe_zip_segment(raw)
    assert "/" not in out
    assert "\\" not in out
    assert ".." not in out


def test_safe_zip_segment_preserves_normal_case_id():
    assert _safe_zip_segment("rapid_movement__abc123__2026-04-23T12:00:00") == (
        "rapid_movement__abc123__2026-04-23T12:00:00"
    )


def test_safe_zip_segment_empty_falls_back():
    assert _safe_zip_segment("") == "case"


# --- _assert_safe_zip_path ------------------------------------------------


@pytest.mark.parametrize("path", ["cases/x.json", "program.md", "rules/r1.sql", "a/b/c.json"])
def test_assert_safe_zip_path_accepts_normal(path):
    _assert_safe_zip_path(path)  # must not raise


@pytest.mark.parametrize("path", ["/etc/passwd", "a\\b.json", "cases/../x.json", "../x.json"])
def test_assert_safe_zip_path_rejects_traversal(path):
    with pytest.raises(ValueError, match="unsafe zip entry path"):
        _assert_safe_zip_path(path)


# --- integration: malicious case_id can't escape --------------------------


def test_case_pack_paths_sanitised_for_malicious_case_id():
    spec = load_spec(SPEC)
    case = {
        "case_id": "r1__C1__../../../etc/passwd",
        "rule_id": "r1",
        "alert": {},
        "input_hash": {},
    }
    files = _case_pack_files(spec, case, Path("/nonexistent-run-dir"), [], {})

    assert files, "expected per-case files"
    for path in files:
        # Every entry path is contained and passes the archive-boundary guard.
        _assert_safe_zip_path(path)
        assert ".." not in path
        assert not path.startswith("/")
    # The standard subdirs are still present (just with a safe leaf).
    assert any(p.startswith("cases/") for p in files)
    assert any(p.startswith("lineage/") for p in files)
