"""Round-7 PR #3 spec validation tests.

Two new example specs land in this PR:
  - examples/trade_based_ml/aml.yaml (FATF/Egmont TBML typologies)
  - examples/uk_app_fraud/aml.yaml (PSR mandatory reimbursement)

These tests verify both pass schema + Pydantic validation, carry the
expected rule shapes, and integrate with the framework's existing
multi-jurisdiction tooling.
"""

from __future__ import annotations

from pathlib import Path

from aml_framework.spec import load_spec

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_TBML = PROJECT_ROOT / "examples" / "trade_based_ml" / "aml.yaml"
SPEC_APP = PROJECT_ROOT / "examples" / "uk_app_fraud" / "aml.yaml"


# ---------------------------------------------------------------------------
# TBML spec
# ---------------------------------------------------------------------------


class TestTBMLSpec:
    def test_loads_without_error(self):
        spec = load_spec(SPEC_TBML)
        assert spec.program.name == "tbml_correspondent_bank"
        assert spec.program.jurisdiction == "US"
        assert spec.program.regulator == "FinCEN"

    def test_has_five_tbml_rules(self):
        spec = load_spec(SPEC_TBML)
        assert len(spec.rules) == 5
        rule_ids = {r.id for r in spec.rules}
        assert rule_ids == {
            "over_invoicing_unit_price",
            "under_invoicing_unit_price",
            "phantom_shipping",
            "multiple_invoicing",
            "trad_to_high_risk_jurisdiction",
        }

    def test_every_rule_has_tbml_tag(self):
        spec = load_spec(SPEC_TBML)
        for rule in spec.rules:
            assert "tbml" in rule.tags, f"rule {rule.id} missing tbml tag"

    def test_every_rule_cites_fatf_or_egmont(self):
        spec = load_spec(SPEC_TBML)
        for rule in spec.rules:
            citations = [r.citation for r in rule.regulation_refs]
            assert any("FATF" in c or "Egmont" in c for c in citations), (
                f"rule {rule.id} should cite at least one FATF or Egmont source"
            )

    def test_hs_code_baseline_contract_declared(self):
        spec = load_spec(SPEC_TBML)
        contract_ids = {c.id for c in spec.data_contracts}
        assert "hs_code_baseline" in contract_ids, "TBML rules need hs_code_baseline reference data"

    def test_workflow_has_str_filing_queue(self):
        spec = load_spec(SPEC_TBML)
        queue_ids = {q.id for q in spec.workflow.queues}
        assert "str_filing" in queue_ids


# ---------------------------------------------------------------------------
# UK APP-fraud spec
# ---------------------------------------------------------------------------


class TestAPPFraudSpec:
    def test_loads_without_error(self):
        spec = load_spec(SPEC_APP)
        assert spec.program.name == "uk_challenger_app_fraud"
        assert spec.program.jurisdiction == "UK"
        assert spec.program.regulator == "FCA"

    def test_has_four_app_rules(self):
        spec = load_spec(SPEC_APP)
        assert len(spec.rules) == 4
        rule_ids = {r.id for r in spec.rules}
        assert rule_ids == {
            "first_use_payee_large_amount",
            "cop_mismatch_override",
            "vulnerable_customer_atypical_payment",
            "rapid_pass_through_mule",
        }

    def test_every_rule_has_app_fraud_tag(self):
        spec = load_spec(SPEC_APP)
        for rule in spec.rules:
            assert "app_fraud" in rule.tags, f"rule {rule.id} missing app_fraud tag"

    def test_every_rule_cites_psr_or_fca(self):
        spec = load_spec(SPEC_APP)
        for rule in spec.rules:
            citations = [r.citation for r in rule.regulation_refs]
            assert any("PSR" in c or "FCA" in c or "POCA" in c for c in citations), (
                f"rule {rule.id} should cite PSR / FCA / POCA"
            )

    def test_payment_held_queue_for_intervention(self):
        spec = load_spec(SPEC_APP)
        queue_ids = {q.id for q in spec.workflow.queues}
        # APP fraud requires fast intervention; this queue lets payments
        # be held pending L2 review.
        assert "payment_held" in queue_ids
        assert "customer_intervention" in queue_ids
        assert "reimbursement_decision" in queue_ids

    def test_l1_queue_sla_is_one_hour(self):
        spec = load_spec(SPEC_APP)
        l1 = next(q for q in spec.workflow.queues if q.id == "l1_app_analyst")
        # APP fraud requires fast intervention before settlement.
        assert l1.sla == "1h"

    def test_psr_reimbursement_form_declared(self):
        spec = load_spec(SPEC_APP)
        forms = spec.reporting.forms if spec.reporting else {}
        assert "PSR_REIMBURSEMENT" in forms
        assert "NCA_SAR" in forms

    def test_critical_severity_for_vulnerable_customer_rule(self):
        spec = load_spec(SPEC_APP)
        rule = next(r for r in spec.rules if r.id == "vulnerable_customer_atypical_payment")
        # PSR CRS Annex 4 makes this the highest-impact pattern.
        assert rule.severity == "critical"

    def test_cop_mismatch_severity_critical(self):
        spec = load_spec(SPEC_APP)
        rule = next(r for r in spec.rules if r.id == "cop_mismatch_override")
        assert rule.severity == "critical"


# ---------------------------------------------------------------------------
# Cross-cutting: both new specs validate via the same loader
# ---------------------------------------------------------------------------


class TestNewSpecsIntegrateWithFramework:
    def test_both_specs_in_examples_dir(self):
        # Documentation-discoverability test — `docs/jurisdictions.md`
        # walks examples/. Both specs need to be present where the doc
        # generator looks.
        assert SPEC_TBML.exists()
        assert SPEC_APP.exists()

    def test_neither_spec_uses_python_ref_with_unbuilt_callable(self):
        # The python_ref security gate restricts callables to
        # aml_framework.models.* — unbuilt callables would break
        # `aml run`. Both specs avoid python_ref to keep their first-
        # run experience clean.
        for spec_path in (SPEC_TBML, SPEC_APP):
            spec = load_spec(spec_path)
            for rule in spec.rules:
                assert rule.logic.type != "python_ref", (
                    f"{spec_path.name} rule {rule.id} uses python_ref — "
                    "ship the callable in aml_framework.models.* first"
                )
