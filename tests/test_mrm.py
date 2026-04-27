"""Tests for generators/mrm.py — SR 26-2 / OCC Bulletin 2026-13 dossiers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aml_framework.generators.mrm import (
    DEFAULT_CADENCE_MONTHS,
    GUIDANCE_VERSION,
    build_dossier,
    build_dossier_json,
    build_inventory,
    export_bundle_from_run_dir,
    render_dossier_markdown,
)
from aml_framework.spec import load_spec
from aml_framework.spec.models import (
    AggregationWindowLogic,
    AMLSpec,
    Column,
    DataContract,
    Program,
    Queue,
    RegulationRef,
    Rule,
    Workflow,
)

EXAMPLE_CA = (
    Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
)
EXAMPLE_US = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"


def _rule(rule_id="r1", model_tier=None, cadence=None):
    return Rule(
        id=rule_id,
        name=f"Rule {rule_id}",
        severity="high",
        model_tier=model_tier,
        validation_cadence_months=cadence,
        regulation_refs=[RegulationRef(citation="X", description="X")],
        escalate_to="q1",
        logic=AggregationWindowLogic(
            type="aggregation_window",
            source="txn",
            group_by=["customer_id"],
            window="30d",
            having={"count": {"gte": 1}},
        ),
    )


def _spec(rules):
    return AMLSpec(
        version=1,
        program=Program(
            name="Test",
            jurisdiction="US",
            regulator="FinCEN",
            owner="x",
            effective_date="2026-01-01",
        ),
        data_contracts=[
            DataContract(
                id="txn",
                source="synthetic://txn",
                columns=[Column(name="customer_id", type="string")],
            )
        ],
        rules=rules,
        workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
    )


# ---------------------------------------------------------------------------
# Spec field validation
# ---------------------------------------------------------------------------


class TestSpecFields:
    def test_default_tier_is_none(self):
        rule = _rule()
        assert rule.model_tier is None
        assert rule.validation_cadence_months is None

    def test_invalid_tier_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _rule(model_tier="extreme")  # type: ignore[arg-type]

    def test_cadence_bounds_enforced(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _rule(cadence=0)
        with pytest.raises(ValidationError):
            _rule(cadence=99)


# ---------------------------------------------------------------------------
# Tier + cadence resolution
# ---------------------------------------------------------------------------


class TestTierCadenceResolution:
    def test_explicit_tier_propagates(self):
        d = build_dossier(_rule(model_tier="high"))
        assert d.tier == "high"
        assert d.inventory["tier_classification_status"] == "explicit"

    def test_missing_tier_defaults_to_low_with_status(self):
        d = build_dossier(_rule())
        assert d.tier == "low"
        assert d.inventory["tier_classification_status"] == "defaulted_to_low"

    def test_default_cadence_picked_by_tier(self):
        assert build_dossier(_rule(model_tier="high")).cadence_months == 12
        assert build_dossier(_rule(model_tier="medium")).cadence_months == 18
        assert build_dossier(_rule(model_tier="low")).cadence_months == 24

    def test_explicit_cadence_overrides_default(self):
        d = build_dossier(_rule(model_tier="high", cadence=6))
        assert d.cadence_months == 6


# ---------------------------------------------------------------------------
# Dossier sections
# ---------------------------------------------------------------------------


class TestDossierSections:
    def test_inventory_carries_core_metadata(self):
        d = build_dossier(_rule(rule_id="my_rule", model_tier="medium"))
        inv = d.inventory
        assert inv["id"] == "my_rule"
        assert inv["tier"] == "medium"
        assert inv["severity"] == "high"

    def test_conceptual_soundness_includes_logic(self):
        d = build_dossier(_rule())
        cs = d.conceptual_soundness
        assert cs["logic"]["type"] == "aggregation_window"
        assert cs["logic"]["window"] == "30d"
        assert "narrative" in cs

    def test_conceptual_soundness_includes_regulation_refs(self):
        d = build_dossier(_rule())
        refs = d.conceptual_soundness["regulation_refs"]
        assert refs[0]["citation"] == "X"

    def test_implementation_records_engine_version_and_path(self):
        d = build_dossier(_rule())
        impl = d.implementation
        assert "engine_version" in impl
        assert "compile_rule_sql" in impl["code_path"] or "_execute" in impl["code_path"]

    def test_validation_evidence_pulls_tuning_runs(self):
        decisions = [
            {
                "event": "tuning_run",
                "rule_id": "r1",
                "ts": "2026-04-27T12:00:00",
                "grid_size": 12,
                "baseline_alerts": 5,
                "scenarios_with_more_alerts": 3,
                "scenarios_with_fewer_alerts": 4,
                "best_f1": {"f1": 0.8},
            },
            {  # noise
                "event": "tuning_run",
                "rule_id": "other_rule",
                "ts": "2026-04-27T12:00:00",
            },
        ]
        d = build_dossier(_rule(rule_id="r1"), decisions=decisions)
        assert len(d.validation_evidence) == 1
        ev = d.validation_evidence[0]
        assert ev.source == "tuning_run"
        assert ev.summary["grid_size"] == 12

    def test_no_validation_evidence_when_no_tuning_runs(self):
        d = build_dossier(_rule())
        assert d.validation_evidence == []

    def test_ongoing_monitoring_uses_tier_default_cadence(self):
        as_of = datetime(2026, 4, 27, tzinfo=timezone.utc)
        d = build_dossier(_rule(model_tier="high"), as_of=as_of)
        # next due = today + 12*30 days = roughly 2027-04 (12*30 = 360 days)
        next_due = d.ongoing_monitoring["next_validation_due"]
        assert next_due.startswith("2027-")

    def test_audit_anchor_pulls_from_manifest(self):
        manifest = {
            "spec_content_hash": "abc",
            "decisions_hash": "def",
            "as_of": "2026-04-27",
            "run_dir": "/tmp/r",
        }
        d = build_dossier(_rule(), manifest=manifest)
        assert d.audit_trail_anchor["spec_content_hash"] == "abc"


# ---------------------------------------------------------------------------
# Inventory aggregator
# ---------------------------------------------------------------------------


class TestInventory:
    def test_inventory_groups_by_tier(self):
        spec = _spec(
            [
                _rule("high1", model_tier="high"),
                _rule("med1", model_tier="medium"),
                _rule("low1", model_tier="low"),
                _rule("unset1"),  # → defaulted_to_low
            ]
        )
        inv = build_inventory(spec)
        assert inv["summary"]["by_tier"] == {"high": 1, "medium": 1, "low": 2}
        assert inv["summary"]["by_classification_status"]["explicit"] == 3
        assert inv["summary"]["by_classification_status"]["defaulted_to_low"] == 1

    def test_inventory_sorted_high_first(self):
        spec = _spec(
            [
                _rule("low1", model_tier="low"),
                _rule("high1", model_tier="high"),
                _rule("med1", model_tier="medium"),
            ]
        )
        inv = build_inventory(spec)
        ids = [r["rule_id"] for r in inv["rules"]]
        assert ids == ["high1", "med1", "low1"]

    def test_inventory_includes_guidance_metadata(self):
        spec = _spec([_rule(model_tier="high")])
        inv = build_inventory(spec)
        assert inv["_guidance"] == GUIDANCE_VERSION
        assert "_generated_at" in inv


# ---------------------------------------------------------------------------
# JSON / Markdown rendering
# ---------------------------------------------------------------------------


class TestRendering:
    def test_dossier_to_dict_round_trip(self):
        d = build_dossier(_rule(model_tier="medium"))
        round_trip = json.loads(build_dossier_json(_rule(model_tier="medium")))
        assert round_trip["rule_id"] == d.rule_id
        assert round_trip["tier"] == "medium"

    def test_markdown_includes_guidance_header(self):
        md = render_dossier_markdown(build_dossier(_rule(model_tier="high")))
        assert GUIDANCE_VERSION in md
        assert "## 1. Inventory" in md
        assert "## 2. Conceptual soundness" in md
        assert "## 4. Validation evidence" in md
        assert "## 6. Audit-trail anchor" in md

    def test_markdown_warns_when_tier_defaulted(self):
        md = render_dossier_markdown(build_dossier(_rule()))  # no tier
        assert "defaulted to `low`" in md

    def test_markdown_no_validation_evidence_message(self):
        md = render_dossier_markdown(build_dossier(_rule()))
        assert "No tuning_run evidence" in md

    def test_markdown_includes_validation_summary_when_present(self):
        decisions = [
            {
                "event": "tuning_run",
                "rule_id": "r1",
                "ts": "2026-04-27T12:00:00",
                "grid_size": 12,
                "best_f1": {"f1": 0.8, "params": {"x": 1}},
            }
        ]
        md = render_dossier_markdown(build_dossier(_rule(rule_id="r1"), decisions=decisions))
        assert "tuning_run" in md
        assert "0.8" in md


# ---------------------------------------------------------------------------
# Run-dir round-trip end-to-end
# ---------------------------------------------------------------------------


class TestRunDirRoundTrip:
    def test_export_writes_per_rule_files(self, tmp_path):
        from aml_framework.data import generate_dataset
        from aml_framework.engine import run_spec

        spec = load_spec(EXAMPLE_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec,
            spec_path=EXAMPLE_CA,
            data=data,
            as_of=as_of,
            artifacts_root=tmp_path,
        )
        run_dir = Path(result.manifest["run_dir"])
        out_dir = tmp_path / "mrm-out"

        bundle = export_bundle_from_run_dir(spec, run_dir, out_dir)
        # Per-rule files exist for each spec rule.
        for r in spec.rules:
            assert (out_dir / f"{r.id}.json").exists()
            assert (out_dir / f"{r.id}.md").exists()
        assert (out_dir / "inventory.json").exists()
        assert bundle["summary"]["total_rules"] == len(spec.rules)

    def test_export_filters_to_named_rules(self, tmp_path):
        from aml_framework.data import generate_dataset
        from aml_framework.engine import run_spec

        spec = load_spec(EXAMPLE_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=EXAMPLE_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        run_dir = Path(result.manifest["run_dir"])
        out_dir = tmp_path / "mrm-out"

        bundle = export_bundle_from_run_dir(
            spec, run_dir, out_dir, rule_ids=["structuring_cash_deposits"]
        )
        assert len(bundle["rules_written"]) == 1
        assert (out_dir / "structuring_cash_deposits.json").exists()
        # Other rules should not have files written.
        other_rules = [r.id for r in spec.rules if r.id != "structuring_cash_deposits"]
        for rid in other_rules:
            assert not (out_dir / f"{rid}.json").exists()

    def test_missing_run_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            export_bundle_from_run_dir(load_spec(EXAMPLE_US), tmp_path / "nope", tmp_path / "out")


# ---------------------------------------------------------------------------
# DEFAULT_CADENCE_MONTHS sanity
# ---------------------------------------------------------------------------


class TestCadenceTable:
    def test_cadence_table_covers_all_tiers(self):
        for tier in ("high", "medium", "low"):
            assert tier in DEFAULT_CADENCE_MONTHS

    def test_cadence_monotonic_high_lt_medium_lt_low(self):
        assert (
            DEFAULT_CADENCE_MONTHS["high"]
            < DEFAULT_CADENCE_MONTHS["medium"]
            < DEFAULT_CADENCE_MONTHS["low"]
        )
