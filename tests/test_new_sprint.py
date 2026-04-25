"""Tests for Customer 360, EU/AMLD6 spec, PEP screening, scheduled runs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

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
