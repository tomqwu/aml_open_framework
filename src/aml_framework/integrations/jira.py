"""Jira integration — sync AML cases to Jira issues.

Configure via environment: JIRA_URL, JIRA_TOKEN, JIRA_PROJECT.
When not configured, all methods are no-ops so the framework runs
without Jira.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any

logger = logging.getLogger("aml.integrations.jira")

_JIRA_URL = os.environ.get("JIRA_URL", "")
_JIRA_TOKEN = os.environ.get("JIRA_TOKEN", "")
_JIRA_PROJECT = os.environ.get("JIRA_PROJECT", "AML")

SEVERITY_TO_PRIORITY = {
    "critical": "Highest",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}


def is_configured() -> bool:
    return bool(_JIRA_URL and _JIRA_TOKEN)


def create_issue(case: dict[str, Any], narrative: str = "") -> str | None:
    """Create a Jira issue from an AML case. Returns issue key or None."""
    if not is_configured():
        logger.debug("Jira not configured — skipping issue creation")
        return None

    severity = case.get("severity", "medium")
    payload = {
        "fields": {
            "project": {"key": _JIRA_PROJECT},
            "summary": f"[AML] {case.get('rule_name', case.get('rule_id', 'Alert'))}",
            "description": narrative or _build_description(case),
            "issuetype": {"name": "Task"},
            "priority": {"name": SEVERITY_TO_PRIORITY.get(severity, "Medium")},
            "labels": ["aml", "compliance", case.get("severity", "medium")],
        }
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{_JIRA_URL}/rest/api/2/issue",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_JIRA_TOKEN}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            issue_key = result.get("key", "")
            logger.info("Created Jira issue %s for case %s", issue_key, case.get("case_id"))
            return issue_key
    except Exception as e:
        logger.warning("Failed to create Jira issue: %s", e)
        return None


def update_status(issue_key: str, status: str) -> bool:
    """Update the status of an existing Jira issue. Returns success."""
    if not is_configured() or not issue_key:
        return False

    try:
        payload = json.dumps({"fields": {"status": {"name": status}}}).encode("utf-8")
        req = urllib.request.Request(
            f"{_JIRA_URL}/rest/api/2/issue/{issue_key}",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_JIRA_TOKEN}",
            },
            method="PUT",
        )
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        logger.warning("Failed to update Jira issue %s: %s", issue_key, e)
        return False


def _build_description(case: dict[str, Any]) -> str:
    alert = case.get("alert", {})
    refs = case.get("regulation_refs", [])
    return (
        f"*Case ID*: {case.get('case_id', 'N/A')}\n"
        f"*Rule*: {case.get('rule_name', case.get('rule_id', ''))}\n"
        f"*Severity*: {case.get('severity', '')}\n"
        f"*Customer*: {alert.get('customer_id', 'N/A')}\n"
        f"*Amount*: ${float(alert.get('sum_amount', 0)):,.2f}\n"
        f"*Queue*: {case.get('queue', '')}\n"
        f"*Regulations*: {', '.join(r.get('citation', '') for r in refs)}\n"
        f"*Evidence requested*: {', '.join(case.get('evidence_requested', []))}\n"
    )
