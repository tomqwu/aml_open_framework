"""Spec tests -- loader, validation, cross-references, multi-jurisdiction."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
import yaml

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.spec import load_spec
from aml_framework.spec.models import (
    AMLSpec,
    Column,
    DataContract,
    ListMatchLogic,
    Program,
    Queue,
    RegulationRef,
    Report,
    ReportSection,
    Rule,
    Workflow,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"
SPEC_CA = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
SPEC_EU = Path(__file__).resolve().parents[1] / "examples" / "eu_bank" / "aml.yaml"
SPEC_UK = Path(__file__).resolve().parents[1] / "examples" / "uk_bank" / "aml.yaml"
SPEC_VASP = Path(__file__).resolve().parents[1] / "examples" / "crypto_vasp" / "aml.yaml"


# ---------------------------------------------------------------------------
# From test_spec_loader.py
# ---------------------------------------------------------------------------


def test_example_spec_loads():
    spec = load_spec(EXAMPLE)
    assert spec.program.name == "community_bank_aml"
    assert any(r.id == "structuring_cash_deposits" for r in spec.rules)


def test_rule_references_unknown_contract_fails(tmp_path):
    raw = yaml.safe_load(EXAMPLE.read_text())
    raw["rules"][0]["logic"]["source"] = "nonexistent"
    bad = tmp_path / "aml.yaml"
    bad.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="unknown data_contract"):
        load_spec(bad)


def test_rule_escalates_to_unknown_queue_fails(tmp_path):
    raw = yaml.safe_load(EXAMPLE.read_text())
    raw["rules"][0]["escalate_to"] = "does_not_exist"
    bad = tmp_path / "aml.yaml"
    bad.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="unknown queue"):
        load_spec(bad)


def test_missing_required_field_fails_schema(tmp_path):
    raw = yaml.safe_load(EXAMPLE.read_text())
    del raw["program"]["regulator"]
    bad = tmp_path / "aml.yaml"
    bad.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="JSON Schema validation"):
        load_spec(bad)


class TestEvaluationMode:
    """`rule.evaluation_mode` records institution intent (batch / streaming /
    both) so an operator can route at deployment time. v1 engine only runs
    batch — the field is a contract for downstream tooling."""

    def test_default_is_batch(self):
        spec = load_spec(EXAMPLE)
        for rule in spec.rules:
            assert rule.evaluation_mode == "batch"

    def test_explicit_streaming_is_accepted(self, tmp_path):
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["rules"][0]["evaluation_mode"] = "streaming"
        good = tmp_path / "aml.yaml"
        good.write_text(yaml.safe_dump(raw))
        spec = load_spec(good)
        assert spec.rules[0].evaluation_mode == "streaming"

    def test_explicit_both_is_accepted(self, tmp_path):
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["rules"][0]["evaluation_mode"] = "both"
        good = tmp_path / "aml.yaml"
        good.write_text(yaml.safe_dump(raw))
        spec = load_spec(good)
        assert spec.rules[0].evaluation_mode == "both"

    def test_invalid_mode_rejected(self, tmp_path):
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["rules"][0]["evaluation_mode"] = "realtime"  # not in enum
        bad = tmp_path / "aml.yaml"
        bad.write_text(yaml.safe_dump(raw))
        with pytest.raises(ValueError):
            load_spec(bad)

    def test_engine_runs_batch_regardless_of_field(self, tmp_path):
        """v1 engine only executes batch. Setting evaluation_mode='streaming'
        on a rule must NOT change the run output — this protects existing
        users when the streaming evaluator lands later."""
        raw = yaml.safe_load(EXAMPLE.read_text())
        for rule in raw["rules"]:
            rule["evaluation_mode"] = "streaming"
        labelled = tmp_path / "aml.yaml"
        labelled.write_text(yaml.safe_dump(raw))

        spec_default = load_spec(EXAMPLE)
        spec_streaming = load_spec(labelled)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)

        r1 = run_spec(
            spec=spec_default,
            spec_path=EXAMPLE,
            data=data,
            as_of=as_of,
            artifacts_root=tmp_path / "a",
        )
        r2 = run_spec(
            spec=spec_streaming,
            spec_path=labelled,
            data=data,
            as_of=as_of,
            artifacts_root=tmp_path / "b",
        )
        # Same alert hashes — evaluation_mode is metadata, not behavior.
        for rid in r1.manifest["rule_outputs"]:
            assert r1.manifest["rule_outputs"][rid] == r2.manifest["rule_outputs"][rid]


# ---------------------------------------------------------------------------
# From test_canadian_example.py
# ---------------------------------------------------------------------------


def _run_ca(tmp_path):
    spec = load_spec(SPEC_CA)
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)
    result = run_spec(spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path)
    return spec, result


def test_ca_spec_validates():
    spec = load_spec(SPEC_CA)
    assert spec.program.jurisdiction == "CA"
    assert spec.program.regulator == "FINTRAC"
    assert len(spec.rules) == 10
    assert len(spec.workflow.queues) == 5


def test_pass_through_rule_fires(tmp_path):
    """Planted pass-through scenario (C0007) must trigger the rapid_pass_through rule."""
    _, result = _run_ca(tmp_path)
    alerts = result.alerts.get("rapid_pass_through", [])
    assert len(alerts) >= 1, "planted pass-through case must be detected"
    assert any(a.get("customer_id") == "C0007" for a in alerts)


def test_shell_company_rule_fires(tmp_path):
    """Planted shell company (C0008, no business_activity) must trigger."""
    _, result = _run_ca(tmp_path)
    alerts = result.alerts.get("shell_company_indicators", [])
    assert len(alerts) >= 1, "planted shell company must be detected"
    assert any(a.get("customer_id") == "C0008" for a in alerts)


def test_channel_coverage_metric(tmp_path):
    """Coverage metric must be computed. When all typology tags fire, it should be 1.0."""
    _, result = _run_ca(tmp_path)
    coverage = [m for m in result.metrics if m.id == "channel_coverage_gap"]
    assert len(coverage) == 1
    assert coverage[0].value == 1.0
    assert coverage[0].rag == "green"


def test_internal_alert_ignored_metric_exists(tmp_path):
    """The repeat-alert metric must be computed (even as 0.0 in reference engine)."""
    _, result = _run_ca(tmp_path)
    ignored = [m for m in result.metrics if m.id == "internal_alert_ignored"]
    assert len(ignored) == 1
    assert ignored[0].rag == "green"


def test_all_five_reports_generated(tmp_path):
    """All 5 audience reports must be rendered."""
    _, result = _run_ca(tmp_path)
    expected = {"cao_quarterly", "mlro_monthly", "fintrac_readiness", "ops_daily", "osfi_exam_prep"}
    assert set(result.reports.keys()) == expected


def test_run_is_reproducible(tmp_path):
    """Two identical runs must produce the same output AND decisions hashes."""
    spec = load_spec(SPEC_CA)
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)

    r1 = run_spec(
        spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path / "a"
    )
    r2 = run_spec(
        spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path / "b"
    )

    for rule_id, hash1 in r1.manifest["rule_outputs"].items():
        assert hash1 == r2.manifest["rule_outputs"][rule_id], f"output hash drift on rule {rule_id}"

    assert r1.manifest["decisions_hash"] == r2.manifest["decisions_hash"], (
        "decisions_hash must be deterministic across runs"
    )
    assert r1.manifest["spec_content_hash"] == r2.manifest["spec_content_hash"]
    assert r1.manifest["inputs"] == r2.manifest["inputs"], (
        "input manifest must be byte-identical across runs"
    )


# ---------------------------------------------------------------------------
# From test_new_features.py: TestDataQuality
# ---------------------------------------------------------------------------


class TestDataQuality:
    def test_quality_checks_in_spec(self):
        spec = load_spec(SPEC_CA)
        txn_contract = next(c for c in spec.data_contracts if c.id == "txn")
        assert len(txn_contract.quality_checks) > 0, "txn contract must have quality checks"

    def test_not_null_check_passes_on_synthetic_data(self, tmp_path):
        """Synthetic data should have no nulls in required fields."""
        spec = load_spec(SPEC_CA)
        data = generate_dataset(as_of=datetime(2026, 4, 23, 12, 0, 0), seed=42)
        txn_contract = next(c for c in spec.data_contracts if c.id == "txn")
        for qc in txn_contract.quality_checks:
            if "not_null" in qc:
                for field in qc["not_null"]:
                    for row in data["txn"]:
                        assert row.get(field) is not None, f"{field} has null in txn data"

    def test_unique_check_passes_on_synthetic_data(self, tmp_path):
        spec = load_spec(SPEC_CA)
        data = generate_dataset(as_of=datetime(2026, 4, 23, 12, 0, 0), seed=42)
        txn_contract = next(c for c in spec.data_contracts if c.id == "txn")
        for qc in txn_contract.quality_checks:
            if "unique" in qc:
                for field in qc["unique"]:
                    values = [row[field] for row in data["txn"]]
                    assert len(values) == len(set(values)), f"{field} has duplicates"


# ---------------------------------------------------------------------------
# From test_new_sprint.py: TestEUSpec, TestAMLD6FrameworkAlignment, TestUKSpec
# ---------------------------------------------------------------------------


class TestEUSpec:
    def test_eu_spec_validates(self):
        spec = load_spec(SPEC_EU)
        assert spec.program.jurisdiction == "EU"
        assert spec.program.regulator == "EBA"
        # Round-5 #2 added the FATF R.16 travel-rule python_ref rule.
        assert len(spec.rules) == 6
        assert any(r.id == "travel_rule_completeness" for r in spec.rules)

    def test_eu_spec_runs(self, tmp_path):
        spec = load_spec(SPEC_EU)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_EU, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        assert result.total_alerts >= 1
        assert result.manifest is not None

    def test_eu_sanctions_screening_fires(self, tmp_path):
        spec = load_spec(SPEC_EU)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_EU, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        sanctions = result.alerts.get("sanctions_screening", [])
        assert len(sanctions) >= 1

    def test_eu_has_pep_rule(self):
        spec = load_spec(SPEC_EU)
        pep_rules = [r for r in spec.rules if r.id == "pep_screening"]
        assert len(pep_rules) == 1
        assert pep_rules[0].severity == "critical"

    def test_eu_report_generated(self, tmp_path):
        spec = load_spec(SPEC_EU)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_EU, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        assert "mlro_quarterly" in result.reports


class TestAMLD6FrameworkAlignment:
    def test_amld6_data_exists(self):
        from aml_framework.dashboard.data_layer import AMLD6_REQUIREMENTS

        assert len(AMLD6_REQUIREMENTS) >= 7
        articles = [r["article"] for r in AMLD6_REQUIREMENTS]
        assert "Art. 50" in articles
        assert "Art. 20-23" in articles

    def test_eu_framework_tabs(self):
        from aml_framework.dashboard.data_layer import get_framework_tabs

        tabs = get_framework_tabs("EU")
        labels = [t["label"] for t in tabs]
        assert "AMLD6 Requirements" in labels
        assert "FATF Recommendations" in labels
        assert "Wolfsberg Principles" in labels
        assert "FinCEN BSA Pillars" not in labels
        assert "PCMLTFA Pillars" not in labels


class TestUKSpec:
    def test_uk_spec_validates(self):
        spec = load_spec(SPEC_UK)
        assert spec.program.jurisdiction == "UK"
        assert spec.program.regulator == "FCA"
        assert len(spec.rules) == 4

    def test_uk_spec_runs(self, tmp_path):
        spec = load_spec(SPEC_UK)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_UK, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        assert result.total_alerts >= 1

    def test_uk_ofsi_sanctions_fires(self, tmp_path):
        spec = load_spec(SPEC_UK)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_UK, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        sanctions = result.alerts.get("sanctions_ofsi", [])
        assert len(sanctions) >= 1


class TestCryptoVASPSpec:
    """Crypto VASP example spec uses network_pattern + list_match against
    sanctioned wallets. Demonstrates the framework's crypto coverage."""

    def test_vasp_spec_validates(self):
        spec = load_spec(SPEC_VASP)
        assert spec.program.jurisdiction == "VASP"
        assert spec.program.regulator == "FATF"
        rule_types = {r.logic.type for r in spec.rules}
        assert "network_pattern" in rule_types
        assert "list_match" in rule_types
        assert "aggregation_window" in rule_types

    def test_vasp_spec_has_sanctioned_wallet_rule(self):
        spec = load_spec(SPEC_VASP)
        rule_ids = {r.id for r in spec.rules}
        assert "sanctioned_wallet_screening" in rule_ids
        assert "nested_wallet_ring" in rule_ids
        assert "stablecoin_velocity_48h" in rule_ids

    def test_sanctioned_wallets_list_exists(self):
        from aml_framework.paths import REFERENCE_LISTS_DIR

        path = REFERENCE_LISTS_DIR / "sanctioned_wallets.csv"
        assert path.exists(), f"sanctioned_wallets.csv missing at {path}"
        # Has at least one address row.
        text = path.read_text()
        assert "OFAC" in text or "FINTRAC" in text


# ---------------------------------------------------------------------------
# Cyber-enabled fraud / pig-butchering example (Round-4)
# ---------------------------------------------------------------------------


SPEC_CEF = Path(__file__).resolve().parents[1] / "examples" / "cyber_enabled_fraud" / "aml.yaml"


class TestCyberEnabledFraudSpec:
    """The cyber_enabled_fraud spec ships pig-butchering / APP-fraud
    detection composing network_pattern, aggregation_window, and
    list_match primitives. Round-4 PR shipped against FATF Feb 2026
    plenary signal."""

    def test_spec_validates(self):
        spec = load_spec(SPEC_CEF)
        assert spec.program.jurisdiction == "US"
        assert spec.program.regulator == "FinCEN"
        # Three distinct rules, three distinct logic types in v1.
        assert len(spec.rules) == 3

    def test_spec_uses_three_logic_types(self):
        spec = load_spec(SPEC_CEF)
        rule_types = {r.logic.type for r in spec.rules}
        assert "network_pattern" in rule_types
        assert "aggregation_window" in rule_types
        assert "list_match" in rule_types

    def test_pig_butchering_rules_present(self):
        spec = load_spec(SPEC_CEF)
        rule_ids = {r.id for r in spec.rules}
        assert "pig_butchering_payout_fan" in rule_ids
        assert "ramp_up_then_drain" in rule_ids
        assert "pig_butchering_nexus_screening" in rule_ids

    def test_payout_fan_is_critical_severity(self):
        spec = load_spec(SPEC_CEF)
        rule = next(r for r in spec.rules if r.id == "pig_butchering_payout_fan")
        assert rule.severity == "critical"
        # network_pattern with component_size threshold.
        assert rule.logic.type == "network_pattern"
        assert rule.logic.pattern == "component_size"
        assert rule.logic.having["component_size"]["gte"] == 3

    def test_ramp_up_then_drain_has_tuning_grid(self):
        # PR #50 enabled tuning_grid on rules; this rule declares one so
        # MLROs can sweep before promotion.
        spec = load_spec(SPEC_CEF)
        rule = next(r for r in spec.rules if r.id == "ramp_up_then_drain")
        assert rule.tuning_grid is not None
        # The grid sweeps the count + sum_amount thresholds.
        assert "logic.having.count" in rule.tuning_grid
        assert "logic.having.sum_amount" in rule.tuning_grid

    def test_nexus_screening_references_bundled_list(self):
        spec = load_spec(SPEC_CEF)
        rule = next(r for r in spec.rules if r.id == "pig_butchering_nexus_screening")
        assert rule.logic.list == "pig_butchering_nexus"
        # And the list ships in the reference data.
        from aml_framework.paths import REFERENCE_LISTS_DIR

        path = REFERENCE_LISTS_DIR / "pig_butchering_nexus.csv"
        assert path.exists(), f"pig_butchering_nexus.csv missing at {path}"
        text = path.read_text()
        assert "HUIONE" in text  # Section 311 designation cited in spec

    def test_regulation_refs_cite_fatf_and_fincen(self):
        spec = load_spec(SPEC_CEF)
        all_citations = " ".join(ref.citation for r in spec.rules for ref in r.regulation_refs)
        assert "FATF" in all_citations
        assert "FinCEN" in all_citations
        assert "FIN-2023-Alert005" in all_citations  # SAR Advisory Key Term

    def test_workflow_includes_str_filing_queue(self):
        spec = load_spec(SPEC_CEF)
        queue_ids = {q.id for q in spec.workflow.queues}
        assert "str_filing" in queue_ids
        # And SAR form is wired up.
        if spec.reporting and spec.reporting.forms:
            assert "fincen_sar" in spec.reporting.forms

    def test_spec_runs_end_to_end(self, tmp_path):
        # Even though synthetic data doesn't plant pig-butchering positives,
        # the spec must run cleanly to demo on the example dataset.
        from datetime import datetime

        from aml_framework.data import generate_dataset
        from aml_framework.engine import run_spec

        spec = load_spec(SPEC_CEF)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec,
            spec_path=SPEC_CEF,
            data=data,
            as_of=as_of,
            artifacts_root=tmp_path,
        )
        # Manifest shape we can rely on later.
        assert "spec_content_hash" in result.manifest
        # All three rules executed (zero alerts is fine on synthetic data).
        assert set(result.alerts.keys()) >= {
            "pig_butchering_payout_fan",
            "ramp_up_then_drain",
            "pig_butchering_nexus_screening",
        }


# ---------------------------------------------------------------------------
# From test_sprint_final.py: TestTypologyCatalogue, TestSpecEditor
# ---------------------------------------------------------------------------


class TestTypologyCatalogue:
    def test_typology_data_exists(self):
        """Typology catalogue page should have rule templates."""
        page_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "aml_framework"
            / "dashboard"
            / "pages"
            / "18_Typology_Catalogue.py"
        )
        assert page_path.exists()
        content = page_path.read_text()
        assert "TYPOLOGIES" in content
        assert "Structuring" in content
        assert "Layering" in content
        assert "Trade-Based ML" in content
        assert "Crypto" in content

    def test_catalogue_has_minimum_rules(self):
        page_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "aml_framework"
            / "dashboard"
            / "pages"
            / "18_Typology_Catalogue.py"
        )
        content = page_path.read_text()
        rule_count = content.count('"name":')
        assert rule_count >= 20, f"Expected 20+ rule templates, found {rule_count}"


class TestSpecEditor:
    def test_page_exists(self):
        page_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "aml_framework"
            / "dashboard"
            / "pages"
            / "20_Spec_Editor.py"
        )
        assert page_path.exists()
        content = page_path.read_text()
        assert "Validate" in content
        assert "yaml" in content.lower()


# ---------------------------------------------------------------------------
# From test_coverage_final_push.py: test_spec_cross_ref_bad_metric_in_report
# ---------------------------------------------------------------------------


def test_spec_cross_ref_bad_metric_in_report():
    """Report referencing nonexistent metric should fail validation."""
    with pytest.raises(Exception):
        AMLSpec(
            version=1,
            program=Program(
                name="test",
                jurisdiction="CA",
                regulator="FINTRAC",
                owner="cco",
                effective_date="2026-01-01",
            ),
            data_contracts=[
                DataContract(
                    id="txn",
                    source="raw.txn",
                    columns=[Column(name="txn_id", type="string")],
                ),
            ],
            rules=[
                Rule(
                    id="r1",
                    name="Test",
                    severity="high",
                    regulation_refs=[RegulationRef(citation="t", description="t")],
                    logic=ListMatchLogic(
                        type="list_match",
                        source="txn",
                        field="txn_id",
                        list="test",
                        match="exact",
                    ),
                    escalate_to="q1",
                ),
            ],
            workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
            metrics=[],
            reports=[
                Report(
                    id="bad_report",
                    audience="svp",
                    cadence="quarterly",
                    sections=[ReportSection(title="Test", metrics=["nonexistent_metric"])],
                ),
            ],
        )
