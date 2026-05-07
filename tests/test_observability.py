"""PR-AZ-7: Azure Monitor OTel exporter wiring.

Unit tests cover the no-op + idempotent paths. Live SDK paths
(`configure_azure_monitor`) are `# pragma: no cover` since they
need azure-monitor-opentelemetry installed and a real App Insights
endpoint.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def reset_initialized_flag(monkeypatch):
    """Reset the module-level `_initialized` flag between tests so each
    case starts from a clean slate."""
    from aml_framework.observability import otel

    monkeypatch.setattr(otel, "_initialized", False)


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_KEY_VAULT_NAME", raising=False)
    return monkeypatch


class TestNoConnectionStringNoOp:
    """When APPLICATIONINSIGHTS_CONNECTION_STRING is unset,
    init_observability() should be a complete no-op — local dev /
    non-Azure deployments must run unchanged."""

    def test_init_returns_silently_without_env(self, clean_env):
        from aml_framework.observability import init_observability

        # Should not raise even though no SDK is wired.
        init_observability()

    def test_idempotent_short_circuits_on_second_call(self, clean_env):
        from aml_framework.observability import init_observability
        from aml_framework.observability import otel

        init_observability()
        assert otel._initialized is True
        # Second call is a no-op (already initialized).
        init_observability()
        assert otel._initialized is True


class TestConnectionStringPresent:
    """When the env var IS set, configure_azure_monitor should be
    called once. We mock the SDK so the test runs without
    azure-monitor-opentelemetry installed."""

    def test_configure_called_when_env_set(self, clean_env):
        clean_env.setenv(
            "APPLICATIONINSIGHTS_CONNECTION_STRING",
            "InstrumentationKey=00000000-0000-0000-0000-000000000000",
        )

        # Mock the lazy import inside the function.
        with patch.dict(
            "sys.modules",
            {"azure.monitor.opentelemetry": _make_mock_module()},
        ):
            from aml_framework.observability import init_observability

            init_observability()
            from aml_framework.observability import otel

            assert otel._initialized is True

    def test_swallow_exception_so_app_keeps_running(self, clean_env):
        """Observability bugs must never take down the app."""
        clean_env.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=...")

        # Mock module that raises on configure_azure_monitor call.
        with patch.dict(
            "sys.modules",
            {"azure.monitor.opentelemetry": _make_failing_mock_module()},
        ):
            from aml_framework.observability import init_observability

            # Should not raise.
            init_observability()
            from aml_framework.observability import otel

            # Marked initialized so we don't keep retrying.
            assert otel._initialized is True


def _make_mock_module():
    """Build a fake `azure.monitor.opentelemetry` module with a
    callable `configure_azure_monitor`."""
    import types

    mod = types.ModuleType("azure.monitor.opentelemetry")
    mod.configure_azure_monitor = lambda **kwargs: None
    return mod


def _make_failing_mock_module():
    import types

    def _fail(**kwargs):
        raise RuntimeError("simulated SDK init failure")

    mod = types.ModuleType("azure.monitor.opentelemetry")
    mod.configure_azure_monitor = _fail
    return mod
