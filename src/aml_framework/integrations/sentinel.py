"""Azure Sentinel SIEM connector — push decision events to a custom
Log Analytics table.

Existing `integrations/siem.py` is a passive CEF/JSON export — operators
hand the file to whichever SIEM they have. This module is the active
counterpart: pushes structured events to a Log Analytics workspace via
the Data Collector API so they appear immediately in Sentinel's
analytics, hunting queries, and SOAR playbooks.

Why this matters
----------------
Compliance teams want AML decisions to surface in the bank's existing
SIEM (Sentinel here) rather than in a separate dashboard. The Round 16
landing-zone deploy already provisions a platform Log Analytics
workspace; this connector points at the SAME workspace so Sentinel's
correlation rules see AML decisions alongside firewall / endpoint /
identity logs. Round 12 lineage + this surface = end-to-end audit
trail in the analyst's SIEM pane.

Auth: shared-key only (v1 API constraint)
-----------------------------------------
The v1 Data Collector API (`api-version=2016-04-01` at
`<workspace-id>.ods.opinsights.azure.com/api/logs`) accepts ONLY
HMAC-SHA256 shared-key auth — Bearer tokens are rejected with 401.
Migrating to the newer Logs Ingestion API (DCE/DCR, api-version
2023-01-01) would unlock Entra-ID auth but requires the operator
to preprovision a Data Collection Endpoint + Data Collection Rule
in terraform. Round 19 work.

For now: set `AZURE_SENTINEL_WORKSPACE_ID` + `AZURE_SENTINEL_SHARED_KEY`
(both available in the Sentinel workspace's "Agents Management"
blade). Sourceable from Key Vault on the deployed Container App via
the SecretsProvider — the shared key never needs to land in repo.

The active connector is opt-in: `AZURE_SENTINEL_WORKSPACE_ID` must be
set. When unset, `record_decision()` is a no-op so dev/local runs
don't pay for a network call they don't need.

All HTTP IO lives in `_post_to_sentinel()` so tests patch that one
symbol — same testing posture as `assistant.openai._call_openai`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any

# Default custom-log table name in Log Analytics. Operators can override
# by setting `AZURE_SENTINEL_LOG_TYPE` to route events into a different
# table — Sentinel auto-creates the `<name>_CL` table on first write.
DEFAULT_LOG_TYPE = "AmlOpenFramework"


class SentinelError(Exception):
    """Raised when a Sentinel push fails. Caller decides whether to
    log-and-continue (default) or surface to the operator. The
    audit-ledger hook treats these as warnings — never block a rule
    run on a downstream SIEM hiccup."""


def _shared_key_signature(workspace_id: str, shared_key: str, body: str, date_rfc1123: str) -> str:
    """Build the `Authorization` header for shared-key auth.

    Microsoft's Data Collector API specifies HMAC-SHA256 over a
    canonicalized string of method, content-length, content-type,
    x-ms-date, and resource path. Spec:
    https://learn.microsoft.com/azure/azure-monitor/logs/data-collector-api#authorization
    """
    content_length = len(body.encode("utf-8"))
    string_to_sign = (
        f"POST\n{content_length}\napplication/json\nx-ms-date:{date_rfc1123}\n/api/logs"
    )
    decoded_key = base64.b64decode(shared_key)
    signature = base64.b64encode(
        hmac.new(decoded_key, string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")
    return f"SharedKey {workspace_id}:{signature}"


def _post_to_sentinel(
    *,
    workspace_id: str,
    auth_header: str,
    log_type: str,
    body: str,
    date_rfc1123: str,
    timeout: float = 30.0,
) -> None:  # pragma: no cover
    """POST a JSON batch to the Log Analytics Data Collector API."""
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    url = f"https://{workspace_id}.ods.opinsights.azure.com/api/logs?api-version=2016-04-01"
    headers = {
        "Content-Type": "application/json",
        "Authorization": auth_header,
        "Log-Type": log_type,
        "x-ms-date": date_rfc1123,
        "time-generated-field": "timestamp",
    }
    req = Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - explicit Azure URL
            # Data Collector API returns 200 on success with empty body.
            if resp.status >= 300:
                raise SentinelError(f"Sentinel returned HTTP {resp.status}")
    except HTTPError as e:
        raise SentinelError(
            f"Sentinel returned HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
        ) from e
    except URLError as e:
        raise SentinelError(f"Sentinel request failed: {e}") from e


def _rfc1123_now() -> str:
    """RFC 1123 timestamp for the `x-ms-date` header. Sentinel
    rejects requests where this drifts >15 min from server time."""
    return datetime.now(tz=timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


def _enabled() -> bool:
    return bool(os.environ.get("AZURE_SENTINEL_WORKSPACE_ID"))


def record_decision(event: dict[str, Any], *, log_type: str | None = None) -> None:
    """Push a single decision event to Sentinel. No-op when the
    connector isn't configured.

    `event` is a JSON-serializable dict — typically built from an
    audit-ledger record. Adds a `timestamp` field if absent so
    `time-generated-field` resolves correctly on the Sentinel side.

    Errors are wrapped as `SentinelError` so the caller can choose
    log-and-continue (default for the audit hook) vs surface.
    """
    if not _enabled():
        return
    workspace_id = os.environ["AZURE_SENTINEL_WORKSPACE_ID"]
    shared_key = os.environ.get("AZURE_SENTINEL_SHARED_KEY", "")
    log_type_name = log_type or os.environ.get("AZURE_SENTINEL_LOG_TYPE", DEFAULT_LOG_TYPE)

    if not shared_key:
        raise SentinelError(
            "Sentinel push requires AZURE_SENTINEL_SHARED_KEY. The v1 Data "
            "Collector API doesn't accept Bearer tokens — Entra-ID auth needs "
            "a Logs Ingestion API endpoint (DCE/DCR), which Round 19 will "
            "wire up. For now, source the shared key from Key Vault."
        )

    payload = dict(event)
    payload.setdefault("timestamp", datetime.now(tz=timezone.utc).isoformat())
    body = json.dumps([payload], default=str)
    date_rfc1123 = _rfc1123_now()
    auth_header = _shared_key_signature(workspace_id, shared_key, body, date_rfc1123)

    _post_to_sentinel(
        workspace_id=workspace_id,
        auth_header=auth_header,
        log_type=log_type_name,
        body=body,
        date_rfc1123=date_rfc1123,
    )


# NOTE: this connector ships the surface (`record_decision`,
# `record_alert`) but no caller in this PR. The audit-ledger emit
# path will be wired in a follow-up so the integration can be
# reviewed in isolation. Any future integrator wiring this in
# should:
#   - Wrap calls in `try/except SentinelError` and log-and-continue.
#     The AML engine must never fail a rule run because a downstream
#     SIEM is offline.
#   - Batch — `record_decision` posts one event per call. Round 19
#     may add a batched flush path if call volume warrants.


def record_alert(
    *,
    rule_id: str,
    severity: str,
    customer_id: str,
    spec_name: str,
    sum_amount: float | None = None,
    matched_row_ids: list[int] | None = None,
    case_id: str | None = None,
) -> None:
    """Convenience wrapper that maps an alert to the standard event
    shape and pushes via `record_decision`. Use this from the
    audit-ledger emit path; raw `record_decision` for one-off custom
    events (e.g. spec validation failures)."""
    event = {
        "event_type": "alert",
        "rule_id": rule_id,
        "severity": severity,
        "customer_id": customer_id,
        "spec_name": spec_name,
    }
    if sum_amount is not None:
        event["sum_amount"] = sum_amount
    if matched_row_ids:
        event["matched_row_ids"] = matched_row_ids
    if case_id:
        event["case_id"] = case_id
    record_decision(event)
