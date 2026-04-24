"""SIEM/SOAR export — Common Event Format (CEF) for Splunk, Sentinel, QRadar.

Converts AML alerts to CEF syslog format that any SIEM can ingest.
Also supports JSON lines export for modern SIEM platforms.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# CEF severity mapping (0-10 scale).
_SEVERITY_MAP = {"low": 3, "medium": 5, "high": 8, "critical": 10}


def alert_to_cef(
    alert: dict[str, Any],
    rule_id: str,
    severity: str,
    spec_name: str = "AML Open Framework",
) -> str:
    """Convert a single alert to CEF format.

    CEF: Version|Vendor|Product|Version|SignatureID|Name|Severity|Extensions
    """
    cef_severity = _SEVERITY_MAP.get(severity, 5)
    customer = alert.get("customer_id", "unknown")
    amount = float(alert.get("sum_amount", 0))
    ts = datetime.now(tz=timezone.utc).strftime("%b %d %Y %H:%M:%S")

    extensions = (
        f"src={customer} "
        f"msg=AML alert from rule {rule_id} "
        f"cn1={amount:.2f} cn1Label=Amount "
        f"cs1={severity} cs1Label=Severity "
        f"cs2={rule_id} cs2Label=RuleID "
        f"rt={ts}"
    )
    return (
        f"CEF:0|AMLFramework|{spec_name}|1.0|{rule_id}|"
        f"AML Alert: {rule_id}|{cef_severity}|{extensions}"
    )


def export_cef(
    alerts: dict[str, list[dict[str, Any]]],
    severity_map: dict[str, str],
    spec_name: str = "AML Open Framework",
) -> str:
    """Export all alerts as CEF-formatted lines."""
    lines: list[str] = []
    for rule_id, rule_alerts in alerts.items():
        severity = severity_map.get(rule_id, "medium")
        for alert in rule_alerts:
            lines.append(alert_to_cef(alert, rule_id, severity, spec_name))
    return "\n".join(lines)


def export_jsonl(
    alerts: dict[str, list[dict[str, Any]]],
    severity_map: dict[str, str],
) -> str:
    """Export all alerts as JSON lines (for modern SIEM ingest)."""
    import json

    lines: list[str] = []
    ts = datetime.now(tz=timezone.utc).isoformat()
    for rule_id, rule_alerts in alerts.items():
        severity = severity_map.get(rule_id, "medium")
        for alert in rule_alerts:
            event = {
                "timestamp": ts,
                "source": "aml_framework",
                "event_type": "aml_alert",
                "rule_id": rule_id,
                "severity": severity,
                "customer_id": alert.get("customer_id", "unknown"),
                "amount": float(alert.get("sum_amount", 0)),
                "details": {k: str(v) for k, v in alert.items()},
            }
            lines.append(json.dumps(event, sort_keys=True))
    return "\n".join(lines)
