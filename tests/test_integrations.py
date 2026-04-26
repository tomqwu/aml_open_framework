"""Integration tests -- Jira, Slack, Teams, SIEM, notifications."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from aml_framework.integrations.jira import (
    SEVERITY_TO_PRIORITY,
    _build_description,
    create_issue,
    is_configured as jira_configured,
    update_status,
)
from aml_framework.integrations.notifications import (
    get_channel_for_severity,
    is_configured as notif_configured,
    notify_alert,
    notify_run_complete,
    notify_sla_breach,
)
from aml_framework.integrations.siem import alert_to_cef, export_cef, export_jsonl


# ---------------------------------------------------------------------------
# Original TestJiraIntegration
# ---------------------------------------------------------------------------


class TestJiraIntegration:
    def test_not_configured_by_default(self):
        assert not jira_configured()

    def test_create_issue_returns_none_when_unconfigured(self):
        result = create_issue({"case_id": "test", "severity": "high", "rule_id": "test_rule"})
        assert result is None


# ---------------------------------------------------------------------------
# Original TestNotifications
# ---------------------------------------------------------------------------


class TestNotifications:
    def test_not_configured_by_default(self):
        assert not notif_configured()


# ---------------------------------------------------------------------------
# Original TestSIEMExport
# ---------------------------------------------------------------------------


class TestSIEMExport:
    def test_cef_format(self):
        alert = {"customer_id": "C0001", "sum_amount": 45000, "count": 5}
        cef = alert_to_cef(alert, "structuring_cash_deposits", "high")
        assert cef.startswith("CEF:0|")
        assert "structuring_cash_deposits" in cef
        assert "C0001" in cef
        assert "8" in cef

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


# ---------------------------------------------------------------------------
# From test_coverage_99.py: TestJiraAPICalls
# ---------------------------------------------------------------------------


class TestJiraAPICalls:
    @patch("urllib.request.urlopen")
    def test_create_issue_success(self, mock_urlopen):
        from aml_framework.integrations import jira

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"key": "AML-123"}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        with (
            patch.object(jira, "_JIRA_URL", "https://jira.test"),
            patch.object(jira, "_JIRA_TOKEN", "test-token"),
        ):
            result = jira.create_issue({"case_id": "c1", "severity": "high", "rule_id": "r1"})
            assert result == "AML-123"

    @patch("urllib.request.urlopen", side_effect=Exception("network error"))
    def test_create_issue_failure(self, mock_urlopen):
        from aml_framework.integrations import jira

        with (
            patch.object(jira, "_JIRA_URL", "https://jira.test"),
            patch.object(jira, "_JIRA_TOKEN", "test-token"),
        ):
            result = jira.create_issue({"case_id": "c1", "severity": "high"})
            assert result is None

    @patch("urllib.request.urlopen")
    def test_update_status(self, mock_urlopen):
        from aml_framework.integrations import jira

        with (
            patch.object(jira, "_JIRA_URL", "https://jira.test"),
            patch.object(jira, "_JIRA_TOKEN", "test-token"),
        ):
            result = jira.update_status("AML-123", "Done")
            assert result is True

    @patch("urllib.request.urlopen", side_effect=Exception("fail"))
    def test_update_status_failure(self, mock_urlopen):
        from aml_framework.integrations import jira

        with (
            patch.object(jira, "_JIRA_URL", "https://jira.test"),
            patch.object(jira, "_JIRA_TOKEN", "test-token"),
        ):
            assert jira.update_status("AML-123", "Done") is False


# ---------------------------------------------------------------------------
# From test_coverage_99.py: TestNotificationSending
# ---------------------------------------------------------------------------


class TestNotificationSending:
    @patch("urllib.request.urlopen")
    def test_slack_send(self, mock_urlopen):
        from aml_framework.integrations import notifications

        with patch.object(notifications, "_SLACK_URL", "https://hooks.slack.com/test"):
            notify_alert("rule_a", "high", "C001", 5000.0)
            mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_teams_send(self, mock_urlopen):
        from aml_framework.integrations import notifications

        with patch.object(notifications, "_TEAMS_URL", "https://outlook.webhook.test"):
            notify_run_complete("r1", 10, 5, "test_spec")
            mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_sla_breach_notification(self, mock_urlopen):
        from aml_framework.integrations import notifications

        with patch.object(notifications, "_SLACK_URL", "https://hooks.slack.com/test"):
            notify_sla_breach("case_1", "l1_analyst", 24.0, 30.0)
            mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen", side_effect=Exception("fail"))
    def test_slack_failure_doesnt_raise(self, mock_urlopen):
        from aml_framework.integrations import notifications

        with patch.object(notifications, "_SLACK_URL", "https://hooks.slack.com/test"):
            notify_alert("rule_a", "high", "C001", 5000.0)

    @patch("urllib.request.urlopen", side_effect=Exception("fail"))
    def test_teams_failure_doesnt_raise(self, mock_urlopen):
        from aml_framework.integrations import notifications

        with patch.object(notifications, "_TEAMS_URL", "https://outlook.webhook.test"):
            notify_run_complete("r1", 10, 5, "test_spec")


# ---------------------------------------------------------------------------
# From test_coverage_99.py: TestNotificationsExtended
# ---------------------------------------------------------------------------


class TestNotificationsExtended:
    def test_notify_all_severity_channels(self):
        for sev in ("critical", "high", "medium", "low"):
            ch = get_channel_for_severity(sev)
            assert ch != ""


# ---------------------------------------------------------------------------
# From test_coverage_gaps.py: TestNotificationRouting
# ---------------------------------------------------------------------------


class TestNotificationRouting:
    def test_get_channel_for_severity(self):
        assert get_channel_for_severity("critical") == "cco"
        assert get_channel_for_severity("high") == "investigators"
        assert get_channel_for_severity("medium") == "analysts"
        assert get_channel_for_severity("unknown") == "general"


# ---------------------------------------------------------------------------
# From test_coverage_gaps.py: TestJiraMapping
# ---------------------------------------------------------------------------


class TestJiraMapping:
    def test_severity_priority_mapping(self):
        assert SEVERITY_TO_PRIORITY["critical"] == "Highest"
        assert SEVERITY_TO_PRIORITY["low"] == "Low"

    def test_build_description(self):
        desc = _build_description(
            {
                "case_id": "test_case",
                "rule_name": "test_rule",
                "severity": "high",
                "alert": {"customer_id": "C001", "sum_amount": 5000},
                "queue": "l1",
                "regulation_refs": [{"citation": "PCMLTFA s.7"}],
                "evidence_requested": ["transactions"],
            }
        )
        assert "C001" in desc
        assert "PCMLTFA" in desc


# ---------------------------------------------------------------------------
# From test_coverage_99.py: TestAuthExtended (update_status unconfigured)
# ---------------------------------------------------------------------------


class TestJiraUnconfigured:
    def test_update_status_unconfigured_returns_false(self):
        assert update_status("", "Done") is False


# ---------------------------------------------------------------------------
# From test_final_coverage.py: TestBothNotifiers
# ---------------------------------------------------------------------------


class TestBothNotifiers:
    @patch("urllib.request.urlopen")
    def test_both_slack_and_teams(self, mock_urlopen):
        from aml_framework.integrations import notifications

        with (
            patch.object(notifications, "_SLACK_URL", "https://slack.test"),
            patch.object(notifications, "_TEAMS_URL", "https://teams.test"),
        ):
            notify_alert("rule_a", "high", "C001", 5000.0)
            assert mock_urlopen.call_count == 2

    @patch("urllib.request.urlopen")
    def test_run_complete_both(self, mock_urlopen):
        from aml_framework.integrations import notifications

        with (
            patch.object(notifications, "_SLACK_URL", "https://slack.test"),
            patch.object(notifications, "_TEAMS_URL", "https://teams.test"),
        ):
            notify_run_complete("r1", 10, 5, "test")
            assert mock_urlopen.call_count == 2

    @patch("urllib.request.urlopen")
    def test_sla_breach_both(self, mock_urlopen):
        from aml_framework.integrations import notifications

        with (
            patch.object(notifications, "_SLACK_URL", "https://slack.test"),
            patch.object(notifications, "_TEAMS_URL", "https://teams.test"),
        ):
            notify_sla_breach("c1", "l1", 24.0, 30.0)
            assert mock_urlopen.call_count == 2
