"""Pre-examination audit pack tests — Round-7 PR #5.

Verifies the FINTRAC audit pack is well-formed, deterministic
(byte-identical for identical inputs), contains all required
sections, has a verifiable manifest hash, and rejects unsupported
jurisdictions.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from aml_framework.generators.audit_pack import (
    PACK_VERSION,
    SUPPORTED_JURISDICTIONS,
    build_audit_pack,
    build_audit_pack_from_run_dir,
)
from aml_framework.spec import load_spec

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_CA = PROJECT_ROOT / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _case(case_id: str, rule_id: str = "structuring_cash") -> dict[str, Any]:
    return {
        "case_id": case_id,
        "rule_id": rule_id,
        "rule_name": rule_id.replace("_", " ").title(),
        "severity": "high",
        "queue": "l1_aml_analyst",
        "alert": {"customer_id": "C0001", "sum_amount": 12000},
        "evidence_requested": [],
        "spec_program": "schedule_i_bank_aml",
        "input_hash": {},
        "status": "open",
    }


def _decision(case_id: str, event: str, **extras: Any) -> dict[str, Any]:
    d = {"case_id": case_id, "event": event}
    d.update(extras)
    return d


# ---------------------------------------------------------------------------
# Bundle structure
# ---------------------------------------------------------------------------


class TestBundleStructure:
    def test_pack_is_valid_zip(self):
        spec = load_spec(SPEC_CA)
        payload = build_audit_pack(spec, cases=[], decisions=[])
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            assert zf.testzip() is None

    def test_required_files_present(self):
        spec = load_spec(SPEC_CA)
        payload = build_audit_pack(spec, cases=[], decisions=[])
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
        for required in (
            "program.md",
            "inventory.json",
            "alerts_summary.json",
            "cases_summary.json",
            "audit_trail_verification.json",
            "sanctions_evidence.json",
            "manifest.json",
        ):
            assert required in names, f"missing {required!r}"

    def test_fintrac_specific_files_present(self):
        spec = load_spec(SPEC_CA)
        payload = build_audit_pack(spec, cases=[], decisions=[])
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
        # CA-FINTRAC pack adds two markdown section maps.
        assert "pcmltfa_section_map.md" in names
        assert "osfi_b8_pillars.md" in names

    def test_program_md_carries_program_metadata(self):
        spec = load_spec(SPEC_CA)
        payload = build_audit_pack(spec, cases=[], decisions=[])
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            program = zf.read("program.md").decode("utf-8")
        assert "schedule_i_bank_aml" in program
        assert "FINTRAC" in program

    def test_inventory_lists_every_rule(self):
        spec = load_spec(SPEC_CA)
        payload = build_audit_pack(spec, cases=[], decisions=[])
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            inventory = json.loads(zf.read("inventory.json"))
        assert len(inventory["rules"]) == len(spec.rules)
        # Every rule entry has the regulation_refs list populated.
        for rule_entry in inventory["rules"]:
            assert "regulation_refs" in rule_entry
            assert isinstance(rule_entry["regulation_refs"], list)


# ---------------------------------------------------------------------------
# Manifest contract
# ---------------------------------------------------------------------------


class TestManifest:
    def _manifest(self, payload: bytes) -> dict[str, Any]:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            return json.loads(zf.read("manifest.json"))

    def test_manifest_version(self):
        spec = load_spec(SPEC_CA)
        payload = build_audit_pack(spec, cases=[], decisions=[])
        assert self._manifest(payload)["pack_version"] == PACK_VERSION

    def test_manifest_jurisdiction(self):
        spec = load_spec(SPEC_CA)
        payload = build_audit_pack(spec, cases=[], decisions=[])
        assert self._manifest(payload)["jurisdiction"] == "CA-FINTRAC"

    def test_manifest_per_file_hashes_match_archive(self):
        spec = load_spec(SPEC_CA)
        payload = build_audit_pack(spec, cases=[], decisions=[])
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            for path, claimed in manifest["files"].items():
                actual = hashlib.sha256(zf.read(path)).hexdigest()
                assert actual == claimed, f"hash mismatch on {path}"

    def test_manifest_excludes_itself(self):
        spec = load_spec(SPEC_CA)
        payload = build_audit_pack(spec, cases=[], decisions=[])
        manifest = self._manifest(payload)
        assert "manifest.json" not in manifest["files"]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_input_same_bytes(self):
        spec = load_spec(SPEC_CA)
        a = build_audit_pack(spec, cases=[], decisions=[])
        b = build_audit_pack(spec, cases=[], decisions=[])
        assert a == b

    def test_case_order_does_not_change_bundle(self):
        spec = load_spec(SPEC_CA)
        cases = [_case(f"c{i}") for i in range(3)]
        a = build_audit_pack(spec, cases=cases, decisions=[])
        # Reverse order should not change bundle bytes (alerts_summary
        # aggregates by rule, so order doesn't matter).
        b = build_audit_pack(spec, cases=list(reversed(cases)), decisions=[])
        assert a == b


# ---------------------------------------------------------------------------
# Section content
# ---------------------------------------------------------------------------


class TestSectionContent:
    def test_alerts_summary_counts_by_rule(self):
        spec = load_spec(SPEC_CA)
        cases = [
            _case("c1", rule_id="structuring_cash"),
            _case("c2", rule_id="structuring_cash"),
            _case("c3", rule_id="rapid_movement"),
        ]
        payload = build_audit_pack(spec, cases=cases, decisions=[])
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            summary = json.loads(zf.read("alerts_summary.json"))
        assert summary["total_alerts"] == 3
        assert summary["by_rule"]["structuring_cash"]["total"] == 2
        assert summary["by_rule"]["rapid_movement"]["total"] == 1

    def test_cases_summary_str_filed_count(self):
        spec = load_spec(SPEC_CA)
        cases = [_case("c1"), _case("c2"), _case("c3")]
        decisions = [_decision("c1", "str_filed"), _decision("c2", "closed_no_action")]
        payload = build_audit_pack(spec, cases=cases, decisions=decisions)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            summary = json.loads(zf.read("cases_summary.json"))
        assert summary["total_cases"] == 3
        assert summary["str_filed"] == 1
        assert summary["closed_no_action"] == 1
        assert summary["pending"] == 1
        assert summary["filing_rate_pct"] == round(1 / 3 * 100, 2)

    def test_pcmltfa_map_groups_by_section(self):
        spec = load_spec(SPEC_CA)
        payload = build_audit_pack(spec, cases=[], decisions=[])
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            md = zf.read("pcmltfa_section_map.md").decode("utf-8")
        # CA spec uses PCMLTFA citations — expect at least one section heading.
        assert "PCMLTFA" in md or "PCMLTFR" in md

    def test_osfi_b8_pillars_listed(self):
        spec = load_spec(SPEC_CA)
        payload = build_audit_pack(spec, cases=[], decisions=[])
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            md = zf.read("osfi_b8_pillars.md").decode("utf-8")
        for pillar in (
            "Board oversight",
            "Risk-based approach",
            "Automated transaction monitoring",
            "Sanctions integration",
        ):
            assert pillar in md

    def test_sanctions_evidence_lists_screening_rules(self):
        spec = load_spec(SPEC_CA)
        payload = build_audit_pack(spec, cases=[], decisions=[])
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            sanctions = json.loads(zf.read("sanctions_evidence.json"))
        assert "screening_rules" in sanctions
        # CA spec includes SEMA sanctions screening; should have at least 1 rule.
        list_match_count = sum(1 for r in spec.rules if r.logic.type == "list_match")
        assert len(sanctions["screening_rules"]) == list_match_count

    def test_audit_trail_verification_emits_chain_intact_field(self):
        spec = load_spec(SPEC_CA)
        # Empty decisions = trivially intact.
        payload = build_audit_pack(spec, cases=[], decisions=[])
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            audit = json.loads(zf.read("audit_trail_verification.json"))
        assert "chain_intact" in audit
        assert "chain_length" in audit
        assert audit["chain_intact"] is True
        assert audit["chain_length"] == 0


# ---------------------------------------------------------------------------
# Jurisdiction guard
# ---------------------------------------------------------------------------


class TestJurisdictionGuard:
    def test_unsupported_jurisdiction_raises(self):
        spec = load_spec(SPEC_CA)
        with pytest.raises(ValueError, match="unsupported jurisdiction"):
            build_audit_pack(spec, cases=[], decisions=[], jurisdiction="XX-BOGUS")

    def test_supported_jurisdictions_only_fintrac_for_now(self):
        # Documents the v1 scope. Adding new jurisdictions = adding
        # new section assemblers + section list to build_audit_pack.
        assert SUPPORTED_JURISDICTIONS == {"CA-FINTRAC"}


# ---------------------------------------------------------------------------
# End-to-end via run dir loader
# ---------------------------------------------------------------------------


class TestEndToEndWithEngine:
    def test_run_dir_loader_against_real_engine_run(self, tmp_path):
        from aml_framework.data import generate_dataset
        from aml_framework.engine import run_spec

        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23)
        result = run_spec(
            spec=spec,
            spec_path=SPEC_CA,
            data=generate_dataset(as_of=as_of, seed=42),
            as_of=as_of,
            artifacts_root=tmp_path,
        )
        # Find the run dir that just got created.
        run_dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert run_dirs, "engine should write a run dir"
        run_dir = run_dirs[0]
        payload = build_audit_pack_from_run_dir(spec, run_dir)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            assert zf.testzip() is None
            summary = json.loads(zf.read("alerts_summary.json"))
        # The summary should match the engine's case count.
        assert summary["total_alerts"] == len(result.case_ids)
