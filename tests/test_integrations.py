"""Tests for integrations (Jira, Slack, SIEM) — mocked, no real services needed."""

from __future__ import annotations

from aml_framework.integrations.jira import is_configured as jira_configured
from aml_framework.integrations.notifications import is_configured as notif_configured
from aml_framework.integrations.siem import alert_to_cef, export_cef, export_jsonl


class TestJiraIntegration:
    def test_not_configured_by_default(self):
        assert not jira_configured()

    def test_create_issue_returns_none_when_unconfigured(self):
        from aml_framework.integrations.jira import create_issue

        result = create_issue({"case_id": "test", "severity": "high", "rule_id": "test_rule"})
        assert result is None


class TestNotifications:
    def test_not_configured_by_default(self):
        assert not notif_configured()


class TestSIEMExport:
    def test_cef_format(self):
        alert = {"customer_id": "C0001", "sum_amount": 45000, "count": 5}
        cef = alert_to_cef(alert, "structuring_cash_deposits", "high")
        assert cef.startswith("CEF:0|")
        assert "structuring_cash_deposits" in cef
        assert "C0001" in cef
        assert "8" in cef  # High severity = 8

    def test_cef_severity_mapping(self):
        for sev, expected in [("low", "3"), ("medium", "5"), ("high", "8"), ("critical", "10")]:
            cef = alert_to_cef({"customer_id": "X"}, "rule", sev)
            assert f"|{expected}|" in cef

    def test_export_cef_multiple_rules(self):
        alerts = {
            "rule_a": [{"customer_id": "C001", "sum_amount": 1000}],
            "rule_b": [{"customer_id": "C002", "sum_amount": 2000}],
        }
        cef = export_cef(alerts, {"rule_a": "high", "rule_b": "low"})
        lines = cef.strip().split("\n")
        assert len(lines) == 2

    def test_export_jsonl_format(self):
        import json

        alerts = {"rule_a": [{"customer_id": "C001", "sum_amount": 1000}]}
        jsonl = export_jsonl(alerts, {"rule_a": "high"})
        parsed = json.loads(jsonl.strip())
        assert parsed["event_type"] == "aml_alert"
        assert parsed["rule_id"] == "rule_a"
        assert parsed["severity"] == "high"
