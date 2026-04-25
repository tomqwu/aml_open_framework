"""Tests for alert acknowledge/snooze, typology catalogue, comparative analytics, email digest."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


from aml_framework.engine import run_spec
from aml_framework.spec import load_spec

SPEC_CA = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


class TestTypologyCatalogue:
    def test_typology_data_exists(self):
        """Typology catalogue page should have rule templates."""
        # Import the TYPOLOGIES constant — page doesn't import streamlit at module level.

        # Can't import the page directly (it's a Streamlit script).
        # Instead, verify the file exists and has the expected structure.
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
        # Count rule definitions.
        rule_count = content.count('"name":')
        assert rule_count >= 20, f"Expected 20+ rule templates, found {rule_count}"


class TestComparativeAnalytics:
    def test_page_exists(self):
        page_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "aml_framework"
            / "dashboard"
            / "pages"
            / "19_Comparative_Analytics.py"
        )
        assert page_path.exists()


class TestEmailDigest:
    def test_email_digest_function_exists(self):
        from aml_framework.cli import email_digest  # noqa: F401

    def test_email_digest_generates_report(self, tmp_path):
        """The report generation part of email-digest should work."""
        from aml_framework.data.sources import resolve_source

        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = resolve_source("synthetic", spec, as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        # Should have at least one report with 'quarterly' or 'cao' in the ID.
        matching = [r for r in result.reports.items() if "cao" in r[0] or "svp" in r[0]]
        assert len(matching) >= 1
        _, markdown = matching[0]
        assert len(markdown) > 100
        assert "FINTRAC" in markdown or "schedule_i_bank" in markdown


class TestAlertAcknowledgeSnooze:
    def test_alert_queue_page_has_acknowledge_code(self):
        """Alert queue page should contain acknowledge/snooze logic."""
        page_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "aml_framework"
            / "dashboard"
            / "pages"
            / "3_Alert_Queue.py"
        )
        content = page_path.read_text()
        assert "acknowledged_alerts" in content
        assert "snoozed_alerts" in content
        assert "Acknowledge" in content
        assert "Snooze" in content
