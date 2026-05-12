"""Sentinel SIEM connector tests.

Strategy: patch `_post_to_sentinel` (the single HTTP IO point) and
assert the shape of what would have been sent. No live Azure
needed.
"""

from __future__ import annotations

import base64
from unittest import mock

import pytest

from aml_framework.integrations import sentinel


class TestRecordDecisionDisabledByDefault:
    def test_no_workspace_id_is_noop(self, monkeypatch):
        """When `AZURE_SENTINEL_WORKSPACE_ID` is unset, the connector
        must silently no-op — dev / local / CI runs shouldn't make a
        network call they don't need."""
        monkeypatch.delenv("AZURE_SENTINEL_WORKSPACE_ID", raising=False)
        with mock.patch.object(sentinel, "_post_to_sentinel") as posted:
            sentinel.record_decision({"event_type": "test"})
        posted.assert_not_called()


class TestRecordDecisionSharedKeyPath:
    def test_shared_key_signature_header_format(self):
        """Spot-check that `_shared_key_signature` builds a
        well-formed `Authorization: SharedKey <workspace>:<base64>`."""
        sig = sentinel._shared_key_signature(
            workspace_id="abc-123",
            shared_key=base64.b64encode(b"shared-secret").decode(),
            body='[{"event_type":"test"}]',
            date_rfc1123="Wed, 11 May 2026 12:00:00 GMT",
        )
        assert sig.startswith("SharedKey abc-123:")
        # The signature suffix must be valid base64.
        suffix = sig.split(":", 1)[1]
        base64.b64decode(suffix)  # raises on bad b64

    def test_record_decision_uses_shared_key_when_set(self, monkeypatch):
        monkeypatch.setenv("AZURE_SENTINEL_WORKSPACE_ID", "wks-test")
        monkeypatch.setenv(
            "AZURE_SENTINEL_SHARED_KEY",
            base64.b64encode(b"shared-secret").decode(),
        )

        captured: dict = {}

        def fake_post(*, workspace_id, auth_header, log_type, body, date_rfc1123, timeout=30.0):
            captured["workspace_id"] = workspace_id
            captured["auth_header"] = auth_header
            captured["log_type"] = log_type
            captured["body"] = body

        with mock.patch.object(sentinel, "_post_to_sentinel", side_effect=fake_post):
            sentinel.record_decision({"event_type": "alert", "rule_id": "r1"})

        assert captured["workspace_id"] == "wks-test"
        assert captured["auth_header"].startswith("SharedKey wks-test:"), captured["auth_header"]
        assert captured["log_type"] == "AmlOpenFramework"  # default
        # Body is a JSON array with one row carrying our event + timestamp.
        import json as _j

        rows = _j.loads(captured["body"])
        assert len(rows) == 1
        assert rows[0]["event_type"] == "alert"
        assert rows[0]["rule_id"] == "r1"
        assert "timestamp" in rows[0]

    def test_custom_log_type_via_env(self, monkeypatch):
        """`AZURE_SENTINEL_LOG_TYPE` overrides the default table name."""
        monkeypatch.setenv("AZURE_SENTINEL_WORKSPACE_ID", "wks-test")
        monkeypatch.setenv(
            "AZURE_SENTINEL_SHARED_KEY",
            base64.b64encode(b"shared-secret").decode(),
        )
        monkeypatch.setenv("AZURE_SENTINEL_LOG_TYPE", "BankCustomTable")

        captured: dict = {}

        def fake_post(*, log_type, **kw):
            captured["log_type"] = log_type

        with mock.patch.object(sentinel, "_post_to_sentinel", side_effect=fake_post):
            sentinel.record_decision({"event_type": "alert"})
        assert captured["log_type"] == "BankCustomTable"


class TestRecordDecisionRequiresSharedKey:
    """The v1 Data Collector API only accepts HMAC shared-key auth.
    Bearer tokens are valid only on the newer Logs Ingestion API
    (DCE/DCR), which would need an operator to preprovision a
    Data Collection Endpoint + Rule in terraform — deferred to
    Round 19. For now, omitting the shared key when the connector
    is enabled must raise a clear `SentinelError` rather than
    silently 401 against Azure."""

    def test_missing_shared_key_raises_actionable_error(self, monkeypatch):
        monkeypatch.setenv("AZURE_SENTINEL_WORKSPACE_ID", "wks-test")
        monkeypatch.delenv("AZURE_SENTINEL_SHARED_KEY", raising=False)
        with pytest.raises(sentinel.SentinelError, match="AZURE_SENTINEL_SHARED_KEY"):
            sentinel.record_decision({"event_type": "alert"})


class TestRecordAlertWrapper:
    def test_record_alert_maps_to_event_shape(self, monkeypatch):
        monkeypatch.setenv("AZURE_SENTINEL_WORKSPACE_ID", "wks-test")
        monkeypatch.setenv(
            "AZURE_SENTINEL_SHARED_KEY",
            base64.b64encode(b"shared-secret").decode(),
        )

        captured: dict = {}

        def fake_post(*, body, **kw):
            import json as _j

            captured["row"] = _j.loads(body)[0]

        with mock.patch.object(sentinel, "_post_to_sentinel", side_effect=fake_post):
            sentinel.record_alert(
                rule_id="structuring_cash",
                severity="high",
                customer_id="C0123",
                spec_name="canadian_schedule_i_bank",
                sum_amount=22500.0,
                matched_row_ids=[1, 2, 3],
                case_id="case-123",
            )

        row = captured["row"]
        assert row["event_type"] == "alert"
        assert row["rule_id"] == "structuring_cash"
        assert row["severity"] == "high"
        assert row["customer_id"] == "C0123"
        assert row["spec_name"] == "canadian_schedule_i_bank"
        assert row["sum_amount"] == 22500.0
        assert row["matched_row_ids"] == [1, 2, 3]
        assert row["case_id"] == "case-123"

    def test_record_alert_omits_optional_fields_when_absent(self, monkeypatch):
        monkeypatch.setenv("AZURE_SENTINEL_WORKSPACE_ID", "wks-test")
        monkeypatch.setenv(
            "AZURE_SENTINEL_SHARED_KEY",
            base64.b64encode(b"shared-secret").decode(),
        )

        captured: dict = {}

        def fake_post(*, body, **kw):
            import json as _j

            captured["row"] = _j.loads(body)[0]

        with mock.patch.object(sentinel, "_post_to_sentinel", side_effect=fake_post):
            sentinel.record_alert(
                rule_id="r1", severity="low", customer_id="C001", spec_name="demo"
            )
        row = captured["row"]
        assert "sum_amount" not in row
        assert "matched_row_ids" not in row
        assert "case_id" not in row
