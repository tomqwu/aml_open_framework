"""PR-D2 — `Program.nfrs` (NonFunctionalRequirements) optional block.

Closes part of #375. Engine ignores at runtime; downstream surfaces
(regulator pack, dashboard NFR card) will consume in follow-up PRs.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aml_framework.spec.loader import load_spec

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


class TestProgramNFRs:
    def test_default_is_none(self):
        """Existing specs without `nfrs` keep loading — additive contract.
        `None` (not an empty NFR object) means "not declared", which is
        semantically different from a fully-zeroed NFR (which the
        validator would reject anyway via `gt=0` constraints)."""
        spec = load_spec(EXAMPLE)
        assert spec.program.nfrs is None

    def test_full_block_round_trips(self, tmp_path):
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["program"]["nfrs"] = {
            "rto_minutes": 240,
            "rpo_minutes": 15,
            "sla_p95_ms": 750,
            "throughput_per_min": 12000,
            "retention_days": 2555,
            "notes": "Aligned to OSFI E-21 tier-2 (RTO 4h, RPO 15min).",
        }
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        spec = load_spec(f)
        assert spec.program.nfrs is not None
        nfrs = spec.program.nfrs
        assert nfrs.rto_minutes == 240
        assert nfrs.rpo_minutes == 15
        assert nfrs.sla_p95_ms == 750
        assert nfrs.throughput_per_min == 12000
        assert nfrs.retention_days == 2555
        assert "OSFI E-21" in nfrs.notes

    def test_partial_block_round_trips(self, tmp_path):
        """NFRs are pick-and-choose — declaring `rto_minutes` alone
        shouldn't require everything else."""
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["program"]["nfrs"] = {"rto_minutes": 60}
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        spec = load_spec(f)
        assert spec.program.nfrs is not None
        assert spec.program.nfrs.rto_minutes == 60
        assert spec.program.nfrs.rpo_minutes is None
        assert spec.program.nfrs.notes == ""

    def test_zero_rto_rejected(self, tmp_path):
        """`rto_minutes: 0` is meaningless (means "no recovery needed",
        which an examiner reads as missing the field). Validator forbids."""
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["program"]["nfrs"] = {"rto_minutes": 0}
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        with pytest.raises(ValueError):
            load_spec(f)

    def test_rpo_zero_is_allowed(self, tmp_path):
        """RPO=0 IS meaningful — "zero data loss tolerated" (synchronous
        replication). Unlike RTO, this should pass."""
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["program"]["nfrs"] = {"rpo_minutes": 0}
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        spec = load_spec(f)
        assert spec.program.nfrs is not None
        assert spec.program.nfrs.rpo_minutes == 0


class TestSpecDiffSurfacesNFRChanges:
    """Codex pass on PR-D2: `compute_spec_diff` must surface nfrs
    changes per-attribute. Otherwise an NFR-only update slips through
    audit review with no program_changes recorded."""

    def test_nfrs_only_change_surfaces_as_program_change(self, tmp_path):
        from aml_framework.diff import compute_spec_diff

        raw = yaml.safe_load(EXAMPLE.read_text())
        raw_a = {**raw, "program": {**raw["program"], "nfrs": {"rto_minutes": 60}}}
        raw_b = {**raw, "program": {**raw["program"], "nfrs": {"rto_minutes": 30}}}
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        a.write_text(yaml.safe_dump(raw_a))
        b.write_text(yaml.safe_dump(raw_b))
        result = compute_spec_diff(a, b)
        # The diff must call out the RTO change, not silently swallow it.
        nfrs_changes = [c for c in result.program_changes if c.field.startswith("nfrs.")]
        assert any(
            c.field == "nfrs.rto_minutes" and c.before == "60" and c.after == "30"
            for c in nfrs_changes
        ), f"expected nfrs.rto_minutes 60→30 in program_changes; got {nfrs_changes}"

    def test_nfrs_added_from_none_surfaces_in_diff(self, tmp_path):
        from aml_framework.diff import compute_spec_diff

        raw = yaml.safe_load(EXAMPLE.read_text())
        # spec A: no nfrs block. spec B: declares rto_minutes.
        raw_b = {**raw, "program": {**raw["program"], "nfrs": {"rto_minutes": 60}}}
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        a.write_text(yaml.safe_dump(raw))
        b.write_text(yaml.safe_dump(raw_b))
        result = compute_spec_diff(a, b)
        nfrs_changes = [c for c in result.program_changes if c.field.startswith("nfrs.")]
        assert any(
            c.field == "nfrs.rto_minutes" and c.before == "" and c.after == "60"
            for c in nfrs_changes
        ), f"adding an nfrs block must surface as a program_change; got {nfrs_changes}"
        # Codex pass 2: must NOT emit a bogus `nfrs.notes` row with
        # identical empty before/after — notes defaults to "" on a
        # fresh NFR block and that's not a change worth reporting.
        assert not any(c.field == "nfrs.notes" and c.before == c.after for c in nfrs_changes), (
            f"identical empty before/after on nfrs.notes is noise; got {nfrs_changes}"
        )
