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


def _send_slack(text: str) -> None:
    """POST to Slack incoming webhook."""
    try:
        payload = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(
            _SLACK_URL, data=payload,
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
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [{"type": "TextBlock", "text": text, "wrap": True}],
                },
            }],
        }
        payload = json.dumps(card).encode("utf-8")
        req = urllib.request.Request(
            _TEAMS_URL, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        logger.info("Teams notification sent")
    except Exception as e:
        logger.warning("Teams notification failed: %s", e)
