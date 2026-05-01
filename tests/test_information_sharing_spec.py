"""Information-sharing spec syntax + CLI surface (PR-DATA-10a).

Backs the "Data is the AML problem" whitepaper's DATA-10 claim that
the framework ships a cross-border information-sharing **reference
surface** so a Manifest can declare partners, scope, and audit trail.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

from aml_framework.cli import app
from aml_framework.spec.models import (
    AggregationWindowLogic,
    AMLSpec,
    Column,
    DataContract,
    InformationSharing,
    InformationSharingPartner,
    Program,
    Queue,
    RegulationRef,
    Rule,
    Workflow,
)


def _minimal_spec(info_sharing: InformationSharing | None = None) -> AMLSpec:
    return AMLSpec(
        version=1,
        program=Program(
            name="T",
            jurisdiction="US",
            regulator="FinCEN",
            owner="MLRO",
            effective_date=date(2026, 1, 1),
        ),
        data_contracts=[
            DataContract(
                id="customer",
                source="s_customer",
                columns=[
                    Column(name="customer_id", type="string", nullable=False, pii=True),
                ],
            )
        ],
        rules=[
            Rule(
                id="r",
                name="R",
                severity="low",
                regulation_refs=[RegulationRef(citation="x", description="x")],
                logic=AggregationWindowLogic(
                    type="aggregation_window",
                    source="customer",
                    group_by=["customer_id"],
                    window="7d",
                    having={"count": {"gte": 1}},
                ),
                escalate_to="q1",
                evidence=[],
            )
        ],
        workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
        information_sharing=info_sharing,
    )


# ---------------------------------------------------------------------------
# Spec model
# ---------------------------------------------------------------------------


class TestInformationSharingSpec:
    def test_default_is_none(self):
        spec = _minimal_spec()
        assert spec.information_sharing is None

    def test_disabled_block_constructs(self):
        spec = _minimal_spec(InformationSharing(enabled=False))
        assert spec.information_sharing is not None
        assert not spec.information_sharing.enabled
        assert spec.information_sharing.partners == []

    def test_partner_with_full_metadata(self):
        info = InformationSharing(
            enabled=True,
            partners=[
                InformationSharingPartner(
                    fi_id="BANK-A-LEI-123",
                    label="Bank A · cross-border partner",
                    jurisdictions=["US", "CA"],
                    typology_scope=["rtp_mule_cluster", "fan_out_layering"],
                    salt_rotation="monthly",
                )
            ],
            notes="FATF R.18 / FinCEN 314(b) pilot",
        )
        spec = _minimal_spec(info)
        partner = spec.information_sharing.partners[0]
        assert partner.fi_id == "BANK-A-LEI-123"
        assert partner.salt_rotation == "monthly"
        assert "rtp_mule_cluster" in partner.typology_scope

    def test_invalid_salt_rotation_rejected(self):
        import pytest

        with pytest.raises(Exception):  # pydantic ValidationError
            InformationSharingPartner(fi_id="x", salt_rotation="never")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CLI: aml share-pattern
# ---------------------------------------------------------------------------


class TestSharePatternCli:
    def test_refuses_when_not_enabled(self, tmp_path: Path):
        # community_bank doesn't declare information_sharing — share-pattern
        # must refuse with a non-zero exit.
        spec_path = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "share-pattern",
                str(spec_path),
                "--partner",
                "BANK-A",
                "--salt",
                "secret",
                "--out",
                str(tmp_path / "out.json"),
            ],
        )
        assert result.exit_code == 1
        assert "no enabled `information_sharing` block" in result.stdout

    def test_refuses_unknown_partner(self, tmp_path: Path):
        # Build a spec with information_sharing enabled but a different
        # partner; the CLI must refuse non-declared partner IDs.
        spec_yaml = """
version: 1
program:
  name: T
  jurisdiction: US
  regulator: FinCEN
  owner: MLRO
  effective_date: 2026-01-01
data_contracts:
  - id: customer
    source: s
    columns:
      - { name: customer_id, type: string, nullable: false, pii: true }
rules:
  - id: r
    name: R
    severity: low
    regulation_refs:
      - { citation: x, description: x }
    logic:
      type: aggregation_window
      source: customer
      group_by: [customer_id]
      window: 7d
      having: { count: { gte: 1 } }
    escalate_to: q1
    evidence: []
workflow:
  queues:
    - { id: q1, sla: 24h }
information_sharing:
  enabled: true
  partners:
    - { fi_id: BANK-A-LEI-123, label: Bank A, salt_rotation: monthly }
"""
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text(spec_yaml.strip())
        runner = CliRunner()
        # Refused: BANK-Z-BOGUS isn't in partners
        result = runner.invoke(
            app,
            [
                "share-pattern",
                str(spec_path),
                "--partner",
                "BANK-Z-BOGUS",
                "--salt",
                "secret",
                "--out",
                str(tmp_path / "out.json"),
            ],
        )
        assert result.exit_code == 1
        # rich console may line-wrap; collapse whitespace before matching.
        flattened = " ".join(result.stdout.split())
        assert "not in the spec's information_sharing.partners" in flattened

    def test_writes_partner_scoped_json(self, tmp_path: Path):
        spec_yaml = """
version: 1
program:
  name: T
  jurisdiction: US
  regulator: FinCEN
  owner: MLRO
  effective_date: 2026-01-01
data_contracts:
  - id: customer
    source: s
    columns:
      - { name: customer_id, type: string, nullable: false, pii: true }
rules:
  - id: r
    name: R
    severity: low
    regulation_refs:
      - { citation: x, description: x }
    logic:
      type: aggregation_window
      source: customer
      group_by: [customer_id]
      window: 7d
      having: { count: { gte: 1 } }
    escalate_to: q1
    evidence: []
workflow:
  queues:
    - { id: q1, sla: 24h }
information_sharing:
  enabled: true
  partners:
    - { fi_id: BANK-A-LEI-123, label: Bank A, salt_rotation: monthly }
"""
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text(spec_yaml.strip())
        out_path = tmp_path / "share.json"
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "share-pattern",
                str(spec_path),
                "--partner",
                "BANK-A-LEI-123",
                "--salt",
                "shared-secret-2026-04",
                "--salt-period",
                "2026-04",
                "--out",
                str(out_path),
            ],
        )
        assert result.exit_code == 0, result.stdout
        assert out_path.exists()
        body = json.loads(out_path.read_text(encoding="utf-8"))
        assert body["fi_id"]
        assert body["salt_period"] == "2026-04"
        assert "structural_fingerprint" in body


# ---------------------------------------------------------------------------
# CLI: aml verify-pattern
# ---------------------------------------------------------------------------


class TestVerifyPatternCli:
    def test_compares_two_obfuscated_patterns(self, tmp_path: Path):
        # Build two trivially-comparable obfuscated-pattern files.
        from aml_framework.compliance.sandbox import obfuscate_pattern_match

        salt = b"shared-secret"
        # Same subject + neighbour counts so the structural fingerprint
        # matches; one shared customer id under the shared salt to trigger
        # identifier overlap.
        local = obfuscate_pattern_match(
            fi_id="OUR-FI",
            rule_family="rtp_mule_cluster",
            detected_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            pattern_kind="component_size",
            structural_fingerprint={"node_count": 4, "edge_count": 6, "max_hop": 2},
            subject_ids=["C1", "C2"],
            neighbour_ids=["C3", "C4"],
            salt=salt,
            salt_period="2026-04",
        )
        partner = obfuscate_pattern_match(
            fi_id="THEIR-FI",
            rule_family="rtp_mule_cluster",
            detected_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            pattern_kind="component_size",
            structural_fingerprint={"node_count": 4, "edge_count": 6, "max_hop": 2},
            subject_ids=["C1", "X9"],  # one identifier overlaps (C1)
            neighbour_ids=["X10", "X11"],
            salt=salt,
            salt_period="2026-04",
        )
        local_path = tmp_path / "local.json"
        partner_path = tmp_path / "partner.json"
        local_path.write_text(json.dumps(local.to_dict()))
        partner_path.write_text(json.dumps(partner.to_dict()))

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["verify-pattern", str(local_path), str(partner_path)],
        )
        assert result.exit_code == 0, result.stdout
        assert "structural_match: True" in result.stdout
        assert "has_identifier_overlap: True" in result.stdout
