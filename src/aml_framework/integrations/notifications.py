"""Slack and Teams notification integration.

Configure via environment:
  SLACK_WEBHOOK_URL — Slack incoming webhook
  TEAMS_WEBHOOK_URL — Teams incoming webhook

When not configured, methods are no-ops.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request

logger = logging.getLogger("aml.integrations.notifications")

_SLACK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
_TEAMS_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")

# Configurable severity routing — override via API or environment.
ROUTING_RULES: list[dict[str, str]] = [
    {"severity": "critical", "channel": "cco"},
    {"severity": "high", "channel": "investigators"},
    {"severity": "medium", "channel": "analysts"},
    {"severity": "low", "channel": "analysts"},
]


def get_channel_for_severity(severity: str) -> str:
    """Return the channel name for a given severity level."""
    for rule in ROUTING_RULES:
        if rule["severity"] == severity:
            return rule["channel"]
    return "general"


def is_configured() -> bool:
    return bool(_SLACK_URL or _TEAMS_URL)


def notify_alert(
    rule_id: str,
    severity: str,
    customer_id: str,
    amount: float,
    alert_count: int = 1,
) -> None:
    """Send alert notification to configured channels."""
    message = (
        f"*AML Alert* | {severity.upper()} severity\n"
        f"Rule: `{rule_id}` | Customer: `{customer_id}` | "
        f"Amount: ${amount:,.2f} | Count: {alert_count}"
    )
    if _SLACK_URL:
        _send_slack(message)
    if _TEAMS_URL:
        _send_teams(message)


def notify_run_complete(
    run_id: str,
    total_alerts: int,
    total_cases: int,
    spec_name: str,
) -> None:
    """Send run completion notification."""
    message = (
        f"*AML Run Complete* | `{run_id}`\n"
        f"Spec: {spec_name} | Alerts: {total_alerts} | Cases: {total_cases}"
    )
    if _SLACK_URL:
        _send_slack(message)
    if _TEAMS_URL:
        _send_teams(message)


def notify_sla_breach(case_id: str, queue: str, sla_hours: float, actual_hours: float) -> None:
    """Send SLA breach notification."""
    message = (
        f":warning: *SLA Breach* | Case `{case_id}`\n"
        f"Queue: {queue} | SLA: {sla_hours:.0f}h | Actual: {actual_hours:.1f}h"
    )
    if _SLACK_URL:
        _send_slack(message)
    if _TEAMS_URL:
        _send_teams(message)


def notify_regwatch_drift(report: dict) -> None:
    """Send regulator-drift notification.

    `report` is the dict form of a `DriftReport` (use `.to_dict()`):
      {drifted: [...], unreachable: [...], new: [...], removed: [...],
       unchanged_count: int}

    No-op when neither webhook is configured. Used by `aml regwatch
    --notify` so MLROs see drift findings on the same channel as
    other compliance signals.
    """
    drifted = report.get("drifted", [])
    unreachable = report.get("unreachable", [])
    new = report.get("new", [])
    removed = report.get("removed", [])
    if not (drifted or unreachable or new or removed):
        return  # no findings, nothing to notify

    lines = [":scroll: *Regulator Drift Detected*"]
    if drifted:
        lines.append(
            f"  • {len(drifted)} drifted: " + ", ".join(d["citation"] for d in drifted[:5])
        )
        if len(drifted) > 5:
            lines.append(f"    ... and {len(drifted) - 5} more")
    if unreachable:
        lines.append(f"  • {len(unreachable)} unreachable")
    if new:
        lines.append(f"  • {len(new)} new")
    if removed:
        lines.append(f"  • {len(removed)} removed")
    lines.append("  Run `aml regwatch <spec>` for the full report.")
    message = "\n".join(lines)

    if _SLACK_URL:
        _send_slack(message)
    if _TEAMS_URL:
        _send_teams(message)


def _send_slack(text: str) -> None:
    """POST to Slack incoming webhook."""
    try:
        payload = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(
            _SLACK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        logger.info("Slack notification sent")
    except Exception as e:
        logger.warning("Slack notification failed: %s", e)


def _send_teams(text: str) -> None:
    """POST to Teams incoming webhook (adaptive card)."""
    try:
        card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [{"type": "TextBlock", "text": text, "wrap": True}],
                    },
                }
            ],
        }
        payload = json.dumps(card).encode("utf-8")
        req = urllib.request.Request(
            _TEAMS_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        logger.info("Teams notification sent")
    except Exception as e:
        logger.warning("Teams notification failed: %s", e)
