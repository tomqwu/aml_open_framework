"""PR-D1 (#374) — optional `layer` on DataContract.

Names the medallion-architecture stage (bronze / silver / gold) the
contract represents. Engine ignores at runtime; downstream surfaces
(Data Integration page, regulator pack, NFR dashboard) consume. This
PR is additive-only — schema/model/diff wire-in; downstream rendering
ships in follow-ups.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aml_framework.spec.loader import load_spec

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


class TestDataContractLayer:
    def test_default_is_none(self):
        """Existing specs without `layer` keep loading — additive
        contract holds. Default None means "no medallion stage
        authored" (different from any of the three enum values)."""
        spec = load_spec(EXAMPLE)
        for contract in spec.data_contracts:
            assert contract.layer is None

    @pytest.mark.parametrize("layer", ["bronze", "silver", "gold"])
    def test_all_enum_values_accepted(self, tmp_path, layer):
        """All three enum values round-trip — guards against a typo
        in the schema enum / model Literal causing one tier to be
        silently rejected."""
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["data_contracts"][0]["layer"] = layer
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        spec = load_spec(f)
        assert spec.data_contracts[0].layer == layer

    def test_invalid_layer_rejected(self, tmp_path):
        """Schema enum constrains to bronze/silver/gold — anything else
        is a hard reject at load time so a typo can't ship as a
        valid-looking but unhandled value."""
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["data_contracts"][0]["layer"] = "platinum"  # not in the enum
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        with pytest.raises(ValueError):
            load_spec(f)


class TestSpecDiffSurfacesLayerChanges:
    """Schema description promised `layer` would be visible to
    medallion-architecture surfaces. The pre-D1 spec_diff path
    didn't track contracts at all, so `compute_spec_diff` must now
    surface layer transitions so an `aml diff` reviewer sees the
    re-tiering event, not just a silent edit."""

    def test_layer_change_surfaces_in_contract_diff(self, tmp_path):
        from aml_framework.diff import compute_spec_diff

        raw = yaml.safe_load(EXAMPLE.read_text())
        raw_a = {
            **raw,
            "data_contracts": [dict(raw["data_contracts"][0]), *raw["data_contracts"][1:]],
        }
        raw_a["data_contracts"][0] = {**raw_a["data_contracts"][0], "layer": "bronze"}
        raw_b = {
            **raw,
            "data_contracts": [dict(raw["data_contracts"][0]), *raw["data_contracts"][1:]],
        }
        raw_b["data_contracts"][0] = {**raw_b["data_contracts"][0], "layer": "silver"}
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        a.write_text(yaml.safe_dump(raw_a))
        b.write_text(yaml.safe_dump(raw_b))
        result = compute_spec_diff(a, b)
        contract_id = raw_a["data_contracts"][0]["id"]
        modified = next((c for c in result.data_contracts_modified if c.id == contract_id), None)
        assert modified is not None, "expected the modified contract in data_contracts_modified"
        assert "layer: bronze -> silver" in modified.changes, (
            f"layer edit must surface as a value transition; got {modified.changes}"
        )

    def test_layer_authoring_surfaces_in_contract_diff(self, tmp_path):
        """Going from unset (None) to authored is itself a medallion
        provenance change — must surface in the diff so a reviewer
        sees the first-time layering event."""
        from aml_framework.diff import compute_spec_diff

        raw = yaml.safe_load(EXAMPLE.read_text())
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        a.write_text(yaml.safe_dump(raw))
        raw_b = {
            **raw,
            "data_contracts": [dict(raw["data_contracts"][0]), *raw["data_contracts"][1:]],
        }
        raw_b["data_contracts"][0] = {**raw_b["data_contracts"][0], "layer": "gold"}
        b.write_text(yaml.safe_dump(raw_b))
        result = compute_spec_diff(a, b)
        contract_id = raw["data_contracts"][0]["id"]
        modified = next((c for c in result.data_contracts_modified if c.id == contract_id), None)
        assert modified is not None
        assert "layer: None -> gold" in modified.changes

    def test_no_spurious_row_when_layer_unchanged(self, tmp_path):
        """When neither side authors `layer`, the contract must NOT
        appear in `data_contracts_modified` — otherwise the diff path
        would flag every contract as "modified" the day this schema
        lands, which is exactly the additive-discipline failure mode."""
        from aml_framework.diff import compute_spec_diff

        raw = yaml.safe_load(EXAMPLE.read_text())
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        a.write_text(yaml.safe_dump(raw))
        b.write_text(yaml.safe_dump(raw))
        result = compute_spec_diff(a, b)
        assert result.data_contracts_modified == [], (
            f"unchanged contracts must not appear; got {result.data_contracts_modified}"
        )
