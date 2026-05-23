"""PR-A2 follow-up: business_intent + out_of_scope wired into
STR narrative + control matrix + MRM dossier + audit-pack.

The fields were added to `Rule` in PR-A2 (PR #392) and populated on
example specs in PR-A2b (#411). This PR wires them through the
generator outputs so an examiner / 2LoD reviewer sees the rule
author's scope boundary directly in the artifacts they read.

Tests cover both the populated path (fields render) and the negative
path (rule with neither field set renders cleanly, no `None` literals
and no empty-section noise).
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from aml_framework.generators.audit_pack import build_audit_pack
from aml_framework.generators.docs import render_control_matrix
from aml_framework.generators.mrm import build_dossier, render_dossier_markdown
from aml_framework.generators.narrative import generate_str_narrative
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_CA = PROJECT_ROOT / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


# ---------------------------------------------------------------------------
# Builders — keep test specs self-contained so the negative path doesn't
# depend on whichever example currently has unpopulated fields.
# ---------------------------------------------------------------------------


def _rule(
    rule_id: str = "structuring_cash_deposits",
    *,
    business_intent: str | None = None,
    out_of_scope: list[str] | None = None,
) -> Rule:
    return Rule(
        id=rule_id,
        name=f"Rule {rule_id}",
        severity="high",
        regulation_refs=[RegulationRef(citation="X", description="X")],
        escalate_to="q1",
        logic=AggregationWindowLogic(
            type="aggregation_window",
            source="txn",
            group_by=["customer_id"],
            window="30d",
            having={"count": {"gte": 1}},
        ),
        business_intent=business_intent,
        out_of_scope=out_of_scope or [],
    )


def _spec(rules: list[Rule]) -> AMLSpec:
    return AMLSpec(
        version=1,
        program=Program(
            name="Test Bank",
            jurisdiction="CA",
            regulator="FINTRAC",
            owner="mlro",
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


_INTENT = "Detect cash structuring just below the LCTR threshold."
_EXCLUSIONS = [
    "single deposits >= $10,000 LCTR threshold (handled by large_cash_lctr)",
    "prepaid-load structuring (handled by prepaid_load_structuring)",
]


# ---------------------------------------------------------------------------
# STR narrative — positive + negative path
# ---------------------------------------------------------------------------


class TestSTRNarrativeProgramScope:
    def _case(self) -> dict:
        return {
            "case_id": "test",
            "rule_name": "structuring_cash_deposits",
            "severity": "high",
            "alert": {"sum_amount": 25000, "count": 3},
            "regulation_refs": [],
            "queue": "l1_aml_analyst",
        }

    def test_intent_and_exclusions_rendered_when_rule_supplied(self):
        rule = _rule(business_intent=_INTENT, out_of_scope=_EXCLUSIONS)
        narrative = generate_str_narrative(
            case=self._case(),
            customer={"full_name": "Test", "customer_id": "C0001"},
            transactions=[],
            jurisdiction="CA",
            rule=rule,
        )
        assert "Program scope" in narrative
        assert _INTENT in narrative
        for excl in _EXCLUSIONS:
            assert excl in narrative

    def test_section_collapses_when_rule_is_none(self):
        """Default call — no rule supplied — produces a narrative without
        a Program-scope section (preserves byte-stability for legacy callers)."""
        narrative = generate_str_narrative(
            case=self._case(),
            customer={"full_name": "Test", "customer_id": "C0001"},
            transactions=[],
            jurisdiction="CA",
        )
        assert "Program scope" not in narrative
        # No raw `None` literal leaks into the narrative when rule is absent.
        assert "None" not in narrative.split("---")[0]

    def test_section_collapses_when_rule_has_neither_field(self):
        rule = _rule()  # both fields unset / empty
        narrative = generate_str_narrative(
            case=self._case(),
            customer={"full_name": "Test", "customer_id": "C0001"},
            transactions=[],
            jurisdiction="CA",
            rule=rule,
        )
        assert "Program scope" not in narrative

    def test_intent_only_renders_without_out_of_scope_block(self):
        rule = _rule(business_intent=_INTENT)
        narrative = generate_str_narrative(
            case=self._case(),
            customer={"full_name": "Test", "customer_id": "C0001"},
            transactions=[],
            jurisdiction="CA",
            rule=rule,
        )
        assert "Program scope" in narrative
        assert _INTENT in narrative
        assert "Out-of-scope exclusions" not in narrative

    def test_out_of_scope_only_renders_without_intent_block(self):
        rule = _rule(out_of_scope=_EXCLUSIONS)
        narrative = generate_str_narrative(
            case=self._case(),
            customer={"full_name": "Test", "customer_id": "C0001"},
            transactions=[],
            jurisdiction="CA",
            rule=rule,
        )
        assert "Program scope" in narrative
        assert "Out-of-scope exclusions" in narrative
        # Intent line is conditionally suppressed.
        assert "Intent:" not in narrative


# ---------------------------------------------------------------------------
# Control matrix
# ---------------------------------------------------------------------------


class TestControlMatrixProgramIntent:
    def test_section_present_when_any_rule_populated(self):
        spec = _spec([_rule(business_intent=_INTENT, out_of_scope=_EXCLUSIONS)])
        md = render_control_matrix(spec)
        assert "## Program intent (per rule)" in md
        assert _INTENT in md
        for excl in _EXCLUSIONS:
            assert excl in md

    def test_section_absent_when_no_rule_populated(self):
        spec = _spec([_rule()])  # neither field set
        md = render_control_matrix(spec)
        assert "Program intent" not in md
        # Reviewer queues section still renders (not removed by the early-out).
        assert "## Reviewer queues" in md

    def test_section_only_lists_populated_rules(self):
        spec = _spec(
            [
                _rule(rule_id="populated", business_intent=_INTENT),
                _rule(rule_id="bare"),  # no intent — should be skipped
            ]
        )
        md = render_control_matrix(spec)
        assert "Program intent" in md
        assert "`populated`" in md
        # The bare rule appears in the top table but not in the intent section.
        intent_section, _, _ = md.partition("## Reviewer queues")
        intent_only = intent_section.split("## Program intent (per rule)")[1]
        assert "`bare`" not in intent_only

    def test_example_spec_round_trip(self):
        """End-to-end: the populated CA Schedule-I example renders an
        intent section that mentions the structuring rule's intent text."""
        spec = load_spec(SPEC_CA)
        md = render_control_matrix(spec)
        assert "## Program intent (per rule)" in md
        # Pin one populated rule from the example spec.
        assert "`structuring_cash_deposits`" in md


# ---------------------------------------------------------------------------
# MRM dossier
# ---------------------------------------------------------------------------


class TestMRMDossierProgramIntent:
    def test_dict_carries_both_fields(self):
        rule = _rule(business_intent=_INTENT, out_of_scope=_EXCLUSIONS)
        cs = build_dossier(rule).conceptual_soundness
        assert cs["business_intent"] == _INTENT
        assert cs["out_of_scope"] == _EXCLUSIONS

    def test_markdown_renders_both_blocks(self):
        rule = _rule(business_intent=_INTENT, out_of_scope=_EXCLUSIONS)
        md = render_dossier_markdown(build_dossier(rule))
        assert "**Business intent**" in md
        assert _INTENT in md
        assert "**Out-of-scope exclusions**" in md
        for excl in _EXCLUSIONS:
            assert excl in md

    def test_markdown_omits_blocks_when_unset(self):
        rule = _rule()  # neither populated
        md = render_dossier_markdown(build_dossier(rule))
        assert "**Business intent**" not in md
        assert "**Out-of-scope exclusions**" not in md

    def test_dict_carries_none_when_intent_unset(self):
        """Negative branch — `business_intent` defaults to None (not empty
        string) so 2LoD tooling can distinguish "undocumented" from
        "documented as empty"."""
        cs = build_dossier(_rule()).conceptual_soundness
        assert cs["business_intent"] is None
        assert cs["out_of_scope"] == []


# ---------------------------------------------------------------------------
# Audit pack — inventory + program_intent.md
# ---------------------------------------------------------------------------


class TestAuditPackProgramIntent:
    def _build(self, spec: AMLSpec) -> bytes:
        return build_audit_pack(spec, cases=[], decisions=[])

    def test_program_intent_md_present_in_bundle(self):
        spec = _spec([_rule(business_intent=_INTENT, out_of_scope=_EXCLUSIONS)])
        payload = self._build(spec)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
        assert "program_intent.md" in names

    def test_program_intent_md_renders_populated_rule(self):
        spec = _spec([_rule(business_intent=_INTENT, out_of_scope=_EXCLUSIONS)])
        payload = self._build(spec)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            md = zf.read("program_intent.md").decode("utf-8")
        assert _INTENT in md
        for excl in _EXCLUSIONS:
            assert excl in md

    def test_program_intent_md_flags_undocumented_rule(self):
        spec = _spec([_rule(rule_id="bare")])  # nothing populated
        payload = self._build(spec)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            md = zf.read("program_intent.md").decode("utf-8")
        assert "`bare`" in md
        # Documentation-gap marker fires on the negative path.
        assert "No `business_intent` or `out_of_scope` declared" in md

    def test_inventory_carries_business_intent_and_out_of_scope(self):
        spec = _spec([_rule(business_intent=_INTENT, out_of_scope=_EXCLUSIONS)])
        payload = self._build(spec)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            inv = json.loads(zf.read("inventory.json"))
        rule_entry = inv["rules"][0]
        assert rule_entry["business_intent"] == _INTENT
        assert rule_entry["out_of_scope"] == _EXCLUSIONS

    def test_inventory_intent_none_when_unset(self):
        spec = _spec([_rule()])
        payload = self._build(spec)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            inv = json.loads(zf.read("inventory.json"))
        rule_entry = inv["rules"][0]
        assert rule_entry["business_intent"] is None
        assert rule_entry["out_of_scope"] == []

    def test_manifest_includes_program_intent_md_hash(self):
        """`program_intent.md` is a first-class artifact — its bytes
        contribute to the bundle's manifest hash. Pins the file order:
        adding the artifact must also update the manifest section."""
        spec = _spec([_rule(business_intent=_INTENT)])
        payload = self._build(spec)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert "program_intent.md" in manifest["files"]

    def test_example_spec_audit_pack_program_intent_md(self):
        """End-to-end: the populated CA Schedule-I example produces a
        program_intent.md that mentions the populated structuring rule."""
        spec = load_spec(SPEC_CA)
        payload = build_audit_pack(spec, cases=[], decisions=[])
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            md = zf.read("program_intent.md").decode("utf-8")
        assert "structuring_cash_deposits" in md


# ---------------------------------------------------------------------------
# str_bundle wires the rule through to the narrative — pinned via the
# bundle's narrative.txt artifact so a regression in the lookup is
# caught without exercising the dashboard.
# ---------------------------------------------------------------------------


class TestStrBundlePassesRuleToNarrative:
    def test_bundle_narrative_includes_program_scope(self, tmp_path):
        from aml_framework.cases.str_bundle import bundle_investigation_to_str

        spec = _spec([_rule(business_intent=_INTENT, out_of_scope=_EXCLUSIONS)])
        case = {
            "case_id": "C0001-r-1",
            "rule_id": "structuring_cash_deposits",
            "rule_name": "Rule structuring_cash_deposits",
            "severity": "high",
            "queue": "q1",
            "alert": {
                "customer_id": "C0001",
                "sum_amount": 25000,
                "count": 3,
                "window_start": "2026-04-01",
                "window_end": "2026-04-30",
            },
            "regulation_refs": [],
            "evidence_requested": [],
            "spec_program": spec.program.name,
            "input_hash": {},
            "status": "open",
        }
        investigation = {
            "investigation_id": "INV-001",
            "case_ids": ["C0001-r-1"],
        }
        payload = bundle_investigation_to_str(
            investigation=investigation,
            cases=[case],
            spec=spec,
            customers=[{"customer_id": "C0001", "full_name": "Acme"}],
            transactions=[],
        )
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            narrative = zf.read("narrative.txt").decode("utf-8")
        assert _INTENT in narrative
        for excl in _EXCLUSIONS:
            assert excl in narrative
