"""OpenTelemetry → Azure Monitor exporter (PR-AZ-7).

Wires FastAPI request traces + Streamlit page renders into the
landing zone's Application Insights instance.

Activation: set `APPLICATIONINSIGHTS_CONNECTION_STRING` (resolved via
SecretsProvider so it can live in Key Vault). When unset, this module
is a no-op — the framework runs unchanged on local dev / non-Azure
deployments.

Idempotent: `init_observability()` short-circuits after the first
successful call, so calling it from both the API and the dashboard
entry points (which can run in the same process under streamlit run)
is safe.
"""

from __future__ import annotations

import logging

from aml_framework.secrets import SECRETS

logger = logging.getLogger("aml.observability")

_initialized = False


def init_observability() -> None:
    """Configure Azure Monitor exporter if connection string is set.

    Safe to call multiple times; idempotent. Failures (missing SDK,
    network, malformed connection string) are logged at WARNING and
    swallowed — observability bugs must never take down the app.
    """
    global _initialized
    if _initialized:
        return

    conn = SECRETS.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn:
        logger.debug(
            "APPLICATIONINSIGHTS_CONNECTION_STRING not set; OpenTelemetry → Azure Monitor disabled."
        )
        _initialized = True  # short-circuit subsequent calls
        return

    try:  # pragma: no cover — needs azure-monitor-opentelemetry installed
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(
            connection_string=conn,
            # The OTel Python SDK auto-detects FastAPI / WSGI / requests
            # / urllib instrumentations when their libraries are
            # imported. No per-instrumentation config needed.
            disable_offline_storage=False,  # default; OK for Container Apps
        )
        logger.info("Azure Monitor exporter configured")
        _initialized = True
    except Exception as exc:
        logger.warning(
            "Failed to configure Azure Monitor exporter (%s); continuing without OTel.",
            exc,
        )
        _initialized = True  # don't keep retrying
