"""Tests for generators/effectiveness.py — the FinCEN NPRM evidence pack."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aml_framework.generators.effectiveness import (
    FINCEN_PRIORITIES,
    NPRM_VERSION,
    build_effectiveness_pack,
    build_effectiveness_pack_json,
    export_pack_from_run_dir,
    render_effectiveness_markdown,
)
from aml_framework.spec import load_spec

EXAMPLE_CA = (
    Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
)
EXAMPLE_US = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"


# ---------------------------------------------------------------------------
# Schema + top-level envelope
# ---------------------------------------------------------------------------


class TestEnvelope:
    def test_schema_and_docket_present(self):
        pack = build_effectiveness_pack(load_spec(EXAMPLE_US))
        assert pack["_schema"] == NPRM_VERSION
        assert "_docket" in pack
        assert "_engine_version" in pack

    def test_programme_metadata_populated(self):
        pack = build_effectiveness_pack(load_spec(EXAMPLE_US))
        prog = pack["programme"]
        assert prog["name"]
        assert prog["jurisdiction"]
        assert prog["regulator"]

    def test_audit_anchor_pulls_from_manifest(self):
        manifest = {
            "spec_content_hash": "abc",
            "decisions_hash": "def",
            "as_of": "2026-04-27T00:00:00",
            "run_dir": "/tmp/run-x",
        }
        pack = build_effectiveness_pack(load_spec(EXAMPLE_US), manifest=manifest)
        anchor = pack["audit_trail_anchor"]
        assert anchor["spec_content_hash"] == "abc"
        assert anchor["decisions_hash"] == "def"
        assert anchor["run_dir"] == "/tmp/run-x"

    def test_summary_counts_findings_by_status(self):
        pack = build_effectiveness_pack(load_spec(EXAMPLE_US))
        s = pack["summary"]
        assert s["pillars_evaluated"] == 4
        # Sum of categories must equal total findings across all pillars.
        total_findings = sum(len(p["findings"]) for p in pack["pillars"])
        assert (
            s["findings_satisfied"] + s["findings_warning"] + s["findings_gap"]
            <= total_findings  # informational findings aren't counted
        )

    def test_byte_deterministic(self):
        spec = load_spec(EXAMPLE_US)
        ts = datetime(2026, 4, 27, tzinfo=timezone.utc)
        a = build_effectiveness_pack_json(spec, generated_at=ts)
        b = build_effectiveness_pack_json(spec, generated_at=ts)
        assert a == b


# ---------------------------------------------------------------------------
# Pillar 1 — Risk-assessment alignment
# ---------------------------------------------------------------------------


class TestRiskAlignmentPillar:
    def test_counts_rules_with_regulation_refs(self):
        spec = load_spec(EXAMPLE_US)
        pack = build_effectiveness_pack(spec)
        pillar = next(p for p in pack["pillars"] if p["pillar"] == "risk_assessment_alignment")
        keys = {f["key"]: f for f in pillar["findings"]}
        assert keys["rules_total"]["value"] == len(spec.rules)
        # All US-spec rules carry ≥1 regulation_ref (load_spec enforces this).
        assert keys["rules_with_regulation_refs"]["value"] == len(spec.rules)
        assert keys["rules_with_regulation_refs"]["status"] == "satisfied"

    def test_severity_distribution_present(self):
        spec = load_spec(EXAMPLE_US)
        pack = build_effectiveness_pack(spec)
        pillar = next(p for p in pack["pillars"] if p["pillar"] == "risk_assessment_alignment")
        sev = next(f for f in pillar["findings"] if f["key"] == "severity_distribution")
        assert isinstance(sev["value"], dict)
        assert sum(sev["value"].values()) == len(spec.rules)


# ---------------------------------------------------------------------------
# Pillar 2 — Priority coverage (the new aml_priority field)
# ---------------------------------------------------------------------------


class TestPriorityCoveragePillar:
    def test_unmapped_rules_listed_as_gap(self):
        # Default example spec doesn't set aml_priority on any rule.
        spec = load_spec(EXAMPLE_US)
        pack = build_effectiveness_pack(spec)
        pillar = next(p for p in pack["pillars"] if p["pillar"] == "aml_cft_priority_coverage")
        unmapped = next(f for f in pillar["findings"] if f["key"] == "unmapped_rules")
        assert unmapped["status"] == "gap"
        assert sorted(unmapped["value"]) == sorted(r.id for r in spec.rules)

    def test_mapped_rule_appears_under_priority(self):
        # Build a spec with one rule that has aml_priority set.
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

        spec = AMLSpec(
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
            rules=[
                Rule(
                    id="rule_corruption",
                    name="Corruption rule",
                    severity="high",
                    aml_priority="corruption",
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
            ],
            workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
        )
        pack = build_effectiveness_pack(spec)
        pillar = next(p for p in pack["pillars"] if p["pillar"] == "aml_cft_priority_coverage")
        by_priority = next(f for f in pillar["findings"] if f["key"] == "rules_by_priority")
        assert "rule_corruption" in by_priority["value"]["corruption"]

    def test_coverage_pct_is_satisfied_when_majority_priorities_have_rules(self):
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

        # Cover 5 of 8 priorities → > 50% → satisfied.
        rules = []
        for i, p in enumerate(FINCEN_PRIORITIES[:5]):
            rules.append(
                Rule(
                    id=f"rule_{i}",
                    name=f"Rule {i}",
                    severity="medium",
                    aml_priority=p,
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
            )
        spec = AMLSpec(
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
        pack = build_effectiveness_pack(spec)
        pillar = next(p for p in pack["pillars"] if p["pillar"] == "aml_cft_priority_coverage")
        coverage = next(f for f in pillar["findings"] if f["key"] == "priority_coverage_pct")
        assert coverage["value"] == round(5 / 8, 4)
        assert coverage["status"] == "satisfied"


# ---------------------------------------------------------------------------
# Pillar 3 — Control output quality
# ---------------------------------------------------------------------------


class TestControlQualityPillar:
    def test_alert_counts_present(self):
        spec = load_spec(EXAMPLE_US)
        pack = build_effectiveness_pack(
            spec,
            alerts_by_rule={"r1": [{"x": 1}, {"x": 2}], "r2": [{"x": 3}]},
        )
        pillar = next(p for p in pack["pillars"] if p["pillar"] == "control_output_quality")
        keys = {f["key"]: f for f in pillar["findings"]}
        assert keys["total_alerts"]["value"] == 3
        assert keys["alerts_by_rule"]["value"] == {"r1": 2, "r2": 1}

    def test_fp_proxy_computed_from_decisions(self):
        spec = load_spec(EXAMPLE_US)
        decisions = [
            {"event": "closed", "disposition": "closed_no_action"},
            {"event": "closed", "disposition": "closed_no_action"},
            {"event": "closed", "disposition": "filed_str"},
        ]
        pack = build_effectiveness_pack(spec, decisions=decisions)
        pillar = next(p for p in pack["pillars"] if p["pillar"] == "control_output_quality")
        fp = next(f for f in pillar["findings"] if f["key"] == "false_positive_proxy")
        # 2 closed_no_action / 3 total = 0.6667
        assert fp["value"] == round(2 / 3, 4)

    def test_narrative_acceptance_rate(self):
        spec = load_spec(EXAMPLE_US)
        decisions = [
            {"event": "narrative_review", "disposition": "accept"},
            {"event": "narrative_review", "disposition": "amend"},
            {"event": "narrative_review", "disposition": "accept"},
        ]
        pack = build_effectiveness_pack(spec, decisions=decisions)
        pillar = next(p for p in pack["pillars"] if p["pillar"] == "control_output_quality")
        accept = next(
            f for f in pillar["findings"] if f["key"] == "narrative_review_acceptance_rate"
        )
        assert accept["value"] == round(2 / 3, 4)

    def test_tuning_runs_recorded_satisfied_when_present(self):
        spec = load_spec(EXAMPLE_US)
        decisions = [{"event": "tuning_run", "rule_id": "r1", "best_f1": {"f1": 0.9}}]
        pack = build_effectiveness_pack(spec, decisions=decisions)
        pillar = next(p for p in pack["pillars"] if p["pillar"] == "control_output_quality")
        tuning = next(f for f in pillar["findings"] if f["key"] == "tuning_runs_recorded")
        assert tuning["status"] == "satisfied"

    def test_tuning_warning_when_absent(self):
        spec = load_spec(EXAMPLE_US)
        pack = build_effectiveness_pack(spec, decisions=[])
        pillar = next(p for p in pack["pillars"] if p["pillar"] == "control_output_quality")
        tuning = next(f for f in pillar["findings"] if f["key"] == "tuning_runs_recorded")
        assert tuning["status"] == "warning"

    def test_red_metrics_count(self):
        spec = load_spec(EXAMPLE_US)
        metrics = [
            {"id": "m1", "rag": "red"},
            {"id": "m2", "rag": "amber"},
            {"id": "m3", "rag": "green"},
        ]
        pack = build_effectiveness_pack(spec, metrics=metrics)
        pillar = next(p for p in pack["pillars"] if p["pillar"] == "control_output_quality")
        red = next(f for f in pillar["findings"] if f["key"] == "metrics_red_count")
        assert red["value"] == 1
        assert red["status"] == "warning"


# ---------------------------------------------------------------------------
# Pillar 4 — Feedback loop evidence
# ---------------------------------------------------------------------------


class TestFeedbackLoopPillar:
    def test_event_counts(self):
        spec = load_spec(EXAMPLE_US)
        decisions = [
            {"event": "pkyc_review", "disposition": "approve_re_review"},
            {"event": "tuning_run", "rule_id": "r1"},
            {"event": "narrative_review", "disposition": "accept"},
            {"event": "narrative_review", "disposition": "amend"},
            {"event": "escalated_to_str", "case_id": "x"},
        ]
        pack = build_effectiveness_pack(spec, decisions=decisions)
        pillar = next(p for p in pack["pillars"] if p["pillar"] == "feedback_loop_evidence")
        keys = {f["key"]: f for f in pillar["findings"]}
        assert keys["pkyc_review_count"]["value"] == 1
        assert keys["tuning_run_count"]["value"] == 1
        assert keys["str_escalation_count"]["value"] == 1
        assert keys["narrative_review_action_mix"]["value"] == {
            "accept": 1,
            "amend": 1,
        }

    def test_pkyc_warning_when_zero(self):
        spec = load_spec(EXAMPLE_US)
        pack = build_effectiveness_pack(spec, decisions=[])
        pillar = next(p for p in pack["pillars"] if p["pillar"] == "feedback_loop_evidence")
        pkyc = next(f for f in pillar["findings"] if f["key"] == "pkyc_review_count")
        assert pkyc["status"] == "warning"


# ---------------------------------------------------------------------------
# Markdown render
# ---------------------------------------------------------------------------


class TestMarkdownRender:
    def test_includes_programme_name(self):
        spec = load_spec(EXAMPLE_US)
        pack = build_effectiveness_pack(spec)
        md = render_effectiveness_markdown(pack)
        assert spec.program.name in md

    def test_includes_pillar_sections(self):
        spec = load_spec(EXAMPLE_US)
        pack = build_effectiveness_pack(spec)
        md = render_effectiveness_markdown(pack)
        for pillar_key in (
            "Risk Assessment Alignment",
            "Aml Cft Priority Coverage",
            "Control Output Quality",
            "Feedback Loop Evidence",
        ):
            assert pillar_key in md

    def test_audit_anchor_included(self):
        spec = load_spec(EXAMPLE_US)
        pack = build_effectiveness_pack(
            spec,
            manifest={
                "spec_content_hash": "abc123",
                "decisions_hash": "def456",
                "as_of": "2026-04-27T12:00:00",
                "run_dir": "/tmp/run-x",
            },
        )
        md = render_effectiveness_markdown(pack)
        assert "abc123" in md
        assert "def456" in md


# ---------------------------------------------------------------------------
# Run-dir round-trip end-to-end
# ---------------------------------------------------------------------------


class TestRunDirRoundTrip:
    def test_export_from_finalised_run(self, tmp_path):
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

        pack_bytes = export_pack_from_run_dir(spec, run_dir)
        pack = json.loads(pack_bytes)
        assert pack["_schema"] == NPRM_VERSION
        assert (
            pack["audit_trail_anchor"]["spec_content_hash"] == result.manifest["spec_content_hash"]
        )
        # All 4 pillars present.
        assert {p["pillar"] for p in pack["pillars"]} == {
            "risk_assessment_alignment",
            "aml_cft_priority_coverage",
            "control_output_quality",
            "feedback_loop_evidence",
        }

    def test_missing_run_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            export_pack_from_run_dir(load_spec(EXAMPLE_US), tmp_path / "nope")


# ---------------------------------------------------------------------------
# aml_priority spec field
# ---------------------------------------------------------------------------


class TestAmlPriorityField:
    def test_default_is_none(self):
        spec = load_spec(EXAMPLE_US)
        for r in spec.rules:
            assert r.aml_priority is None

    def test_invalid_priority_rejected(self):
        from pydantic import ValidationError

        from aml_framework.spec.models import (
            AggregationWindowLogic,
            RegulationRef,
            Rule,
        )

        with pytest.raises(ValidationError):
            Rule(
                id="r",
                name="x",
                severity="high",
                aml_priority="not_a_priority",  # type: ignore[arg-type]
                regulation_refs=[RegulationRef(citation="X", description="X")],
                escalate_to="q",
                logic=AggregationWindowLogic(
                    type="aggregation_window",
                    source="txn",
                    group_by=["customer_id"],
                    window="30d",
                    having={"count": {"gte": 1}},
                ),
            )
