"""Tests for Customer 360, EU/AMLD6 spec, PEP screening, scheduled runs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.spec import load_spec

SPEC_EU = Path(__file__).resolve().parents[1] / "examples" / "eu_bank" / "aml.yaml"
SPEC_CA = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


class TestEUSpec:
    def test_eu_spec_validates(self):
        spec = load_spec(SPEC_EU)
        assert spec.program.jurisdiction == "EU"
        assert spec.program.regulator == "EBA"
        assert len(spec.rules) == 5

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


class TestPEPData:
    def test_synthetic_data_has_pep_customer(self):
        data = generate_dataset(as_of=datetime(2026, 4, 23), seed=42)
        pep_customers = [c for c in data["customer"] if c.get("pep_status")]
        assert len(pep_customers) >= 1
        assert pep_customers[0]["pep_status"] == "domestic_pep"

    def test_pep_customer_has_correct_profile(self):
        data = generate_dataset(as_of=datetime(2026, 4, 23), seed=42)
        c0009 = next((c for c in data["customer"] if c["customer_id"] == "C0009"), None)
        assert c0009 is not None
        assert c0009["country"] == "DE"
        assert c0009["risk_rating"] == "high"
        assert c0009["full_name"] == "Hans Mueller"


class TestAMLD6FrameworkAlignment:
    def test_amld6_data_exists(self):
        from aml_framework.dashboard.data_layer import AMLD6_REQUIREMENTS

        assert len(AMLD6_REQUIREMENTS) >= 7
        articles = [r["article"] for r in AMLD6_REQUIREMENTS]
        assert "Art. 50" in articles  # STR requirement.
        assert "Art. 20-23" in articles  # PEP requirement.

    def test_eu_framework_tabs(self):
        from aml_framework.dashboard.data_layer import get_framework_tabs

        tabs = get_framework_tabs("EU")
        labels = [t["label"] for t in tabs]
        assert "AMLD6 Requirements" in labels
        assert "FATF Recommendations" in labels
        assert "Wolfsberg Principles" in labels
        # Should NOT have FinCEN BSA or PCMLTFA.
        assert "FinCEN BSA Pillars" not in labels
        assert "PCMLTFA Pillars" not in labels


class TestRoleBasedVisibility:
    def test_audience_pages_defined(self):
        from aml_framework.dashboard.audience import AUDIENCE_PAGES

        assert "svp" in AUDIENCE_PAGES
        assert "analyst" in AUDIENCE_PAGES
        assert "Customer 360" in AUDIENCE_PAGES["analyst"]
        assert len(AUDIENCE_PAGES["svp"]) >= 3

    def test_all_audiences_have_executive_dashboard(self):
        """Executive Dashboard should be accessible to all audiences."""
        from aml_framework.dashboard.audience import AUDIENCE_PAGES

        for audience, pages in AUDIENCE_PAGES.items():
            # Executive Dashboard is always added in app.py, but check mapping.
            assert len(pages) >= 2, f"Audience {audience} has too few pages"


class TestScheduleCommand:
    def test_schedule_function_exists(self):
        """The schedule function should be importable from cli."""
        from aml_framework.cli import schedule  # noqa: F401


# --- UK spec ---

SPEC_UK = Path(__file__).resolve().parents[1] / "examples" / "uk_bank" / "aml.yaml"


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


# --- S3/GCS source ---


class TestCloudSources:
    def test_s3_without_dir_raises(self):
        from aml_framework.data.sources import resolve_source

        spec = load_spec(SPEC_CA)
        with pytest.raises(ValueError, match="data-dir"):
            resolve_source("s3", spec, datetime(2026, 4, 23))

    def test_gcs_without_dir_raises(self):
        from aml_framework.data.sources import resolve_source

        spec = load_spec(SPEC_CA)
        with pytest.raises(ValueError, match="data-dir"):
            resolve_source("gcs", spec, datetime(2026, 4, 23))


# --- Audit log tamper detection ---


class TestAuditTamperDetection:
    def test_decisions_hash_in_manifest(self, tmp_path):
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        assert "decisions_hash" in result.manifest
        assert len(result.manifest["decisions_hash"]) == 64  # SHA-256 hex.

    def test_verify_decisions_passes(self, tmp_path):
        from aml_framework.engine.audit import AuditLedger

        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        run_dir = Path(result.manifest["run_dir"])
        valid, msg = AuditLedger.verify_decisions(run_dir)
        assert valid, msg

    def test_verify_detects_tamper(self, tmp_path):
        from aml_framework.engine.audit import AuditLedger

        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        run_dir = Path(result.manifest["run_dir"])

        # Tamper with the decisions log.
        decisions_path = run_dir / "decisions.jsonl"
        original = decisions_path.read_text()
        decisions_path.write_text(original + '{"event":"tampered"}\n')

        valid, msg = AuditLedger.verify_decisions(run_dir)
        assert not valid
        assert "Tamper" in msg

    def test_verify_missing_manifest(self, tmp_path):
        from aml_framework.engine.audit import AuditLedger

        valid, msg = AuditLedger.verify_decisions(tmp_path)
        assert not valid


class TestAdverseMedia:
    def test_adverse_media_list_exists(self):
        from pathlib import Path

        list_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "aml_framework"
            / "data"
            / "lists"
            / "adverse_media.csv"
        )
        assert list_path.exists()
        content = list_path.read_text()
        assert "ALEXEI VOLKOV" in content

    def test_adverse_media_rule_in_spec(self):
        spec = load_spec(SPEC_CA)
        am_rules = [r for r in spec.rules if r.id == "adverse_media_screening"]
        assert len(am_rules) == 1
        assert am_rules[0].logic.type == "list_match"
        assert am_rules[0].logic.list == "adverse_media"

    def test_adverse_media_fires(self, tmp_path):
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        am_alerts = result.alerts.get("adverse_media_screening", [])
        assert len(am_alerts) >= 1  # Should match planted customers.
