"""OpenTelemetry → Azure Monitor instrumentation (PR-AZ-7).

The landing zone provisions Application Insights in the platform RG;
this module wires the API + dashboard as telemetry consumers via
OpenTelemetry. When the connection string env var is unset (local dev,
non-Azure deployments), this module is a complete no-op.

Usage:
    from aml_framework.observability import init_observability
    init_observability()  # call once at app startup
"""

from __future__ import annotations

from .otel import init_observability

__all__ = ["init_observability"]
