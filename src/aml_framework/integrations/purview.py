"""Microsoft Purview lineage push — emit AML decision chains as Atlas
entity graphs.

Round 12 shipped end-to-end lineage (walk_lineage) — case → rule_id →
rule_version → spec_content_hash → input_file_hashes. That lineage
lives in the run artifacts and renders in the dashboard's Lineage
Explorer page. This module pushes the same chains to **Microsoft
Purview** via the Atlas REST API so AML lineage appears in the bank's
existing data-governance pane alongside warehouse + ETL lineage.

Why this matters (regulatory)
-----------------------------
BCBS 239 (data aggregation + risk reporting) and FinCEN's effectiveness
NPRM both demand end-to-end lineage in the governance system, not in
a separate AML tool. A 3LoD auditor asks "show me where this alert
came from" — if the answer requires switching to a separate dashboard,
audit confidence drops. Surfacing AML rules + decisions in Purview
closes that loop.

Differentiator
--------------
Most transaction-monitoring vendors don't push to Purview. The
framework's `walk_lineage` data is already audit-grade; this connector
makes it visible at the same surface a Data Governance officer
already uses.

Entity model
------------
For each case lineage chain:

  Process(rule:<rule_id>)
      ↓ inputs:  DataSet(source-table)
      ↓ outputs: DataSet(alert:<alert-id>)
                 ↓ produces
                 DataSet(case:<case-id>)
                 ↓ files (optional)
                 DataSet(STR:<str-bundle-id>)

Each entity carries a `qualifiedName` of the form
`aml://<spec>/<rule_id>` so Purview can match repeated pushes and
update rather than duplicate.

Opt-in via `PURVIEW_ENDPOINT` env var. Auth: DefaultAzureCredential
token at scope `https://purview.azure.net/.default` — the Container
App's UAMI needs the `Purview Data Curator` data-plane role on the
account.
"""

from __future__ import annotations

import json
import os
from typing import Any

AAD_PURVIEW_SCOPE = "https://purview.azure.net/.default"
DEFAULT_QUALIFIED_NAME_PREFIX = "aml://"


class PurviewError(Exception):
    """Raised when Purview push fails. Caller decides whether to
    log-and-continue (default for the lineage hook) or surface."""


def _enabled() -> bool:
    return bool(os.environ.get("PURVIEW_ENDPOINT"))


def _qualified(spec: str, *parts: str) -> str:
    """`aml://<spec>/<part>/<part>` — stable enough that re-pushing
    the same case updates rather than duplicates the Purview entity."""
    return f"{DEFAULT_QUALIFIED_NAME_PREFIX}{spec}/" + "/".join(parts)


def _build_entities(chain: dict[str, Any], spec_name: str) -> list[dict[str, Any]]:
    """Map a `walk_lineage` chain to Atlas entity dicts.

    Returns a list ready for `POST /api/atlas/v2/entity/bulk`. Skips
    pieces of the chain that are missing (old runs predating Round 12
    won't have rule_version stamped; the helper degrades gracefully).
    """
    entities: list[dict[str, Any]] = []
    rule_id = chain.get("rule_id")
    case_id = chain.get("case_id")
    if not (rule_id and case_id):
        return entities

    # 1. Source data sets — one per input_files entry.
    input_qns: list[str] = []
    for input_file in chain.get("input_files") or []:
        # input_file is a dict {path, sha256, ...} per audit.py.
        path = input_file.get("path") if isinstance(input_file, dict) else str(input_file)
        if not path:
            continue
        qn = _qualified(spec_name, "source", str(path))
        input_qns.append(qn)
        entities.append(
            {
                "typeName": "DataSet",
                "attributes": {
                    "qualifiedName": qn,
                    "name": f"source:{path}",
                    "description": "AML input source — hash-verified at run time.",
                },
            }
        )

    # 2. Rule as a Process. Atlas Process entities link inputs → outputs.
    rule_qn = _qualified(spec_name, "rule", rule_id)
    case_qn = _qualified(spec_name, "case", case_id)
    rule_process = {
        "typeName": "Process",
        "attributes": {
            "qualifiedName": rule_qn,
            "name": f"rule:{rule_id}",
            "description": (chain.get("rule_sql") or "")[:500],
            "inputs": [
                {"typeName": "DataSet", "uniqueAttributes": {"qualifiedName": q}} for q in input_qns
            ],
            "outputs": [{"typeName": "DataSet", "uniqueAttributes": {"qualifiedName": case_qn}}],
        },
    }
    # Stamp rule_version + spec_content_hash so the auditor sees
    # which spec snapshot drove this case.
    if chain.get("rule_version"):
        rule_process["attributes"]["ruleVersion"] = chain["rule_version"]
    if chain.get("spec_content_hash"):
        rule_process["attributes"]["specContentHash"] = chain["spec_content_hash"]
    entities.append(rule_process)

    # 3. Case as the Process output.
    entities.append(
        {
            "typeName": "DataSet",
            "attributes": {
                "qualifiedName": case_qn,
                "name": f"case:{case_id}",
                "description": "AML case opened by the rule above.",
                "queue": chain.get("queue"),
            },
        }
    )

    return entities


def _post_to_purview(
    endpoint: str, token: str, body: str, timeout: float = 30.0
) -> None:  # pragma: no cover
    """POST entities to Purview's Atlas bulk endpoint."""
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    url = f"{endpoint.rstrip('/')}/datamap/api/atlas/v2/entity/bulk"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    req = Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - explicit Purview URL
            if resp.status >= 300:
                raise PurviewError(f"Purview returned HTTP {resp.status}")
    except HTTPError as e:
        raise PurviewError(
            f"Purview returned HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
        ) from e
    except URLError as e:
        raise PurviewError(f"Purview request failed: {e}") from e


def _bearer_token() -> str:
    """Mint a fresh Entra-ID token. Wraps SDK exceptions in
    `PurviewError` so an operator debugging a lineage hook sees an
    actionable message."""
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as e:
        raise PurviewError(
            "Purview push requires `azure-identity` — install via `[azure]` extras."
        ) from e
    try:
        return DefaultAzureCredential().get_token(AAD_PURVIEW_SCOPE).token
    except Exception as e:  # noqa: BLE001
        raise PurviewError(
            "Purview push couldn't mint an Entra-ID token. Attach a managed "
            "identity with `Purview Data Curator` data-plane role. "
            f"Root cause: {e}"
        ) from e


def push_lineage(chain: dict[str, Any], *, spec_name: str) -> None:
    """Push one case's lineage chain to Purview.

    `chain` is the dict returned by `walk_lineage(run_dir, case_id)`.
    No-op when `PURVIEW_ENDPOINT` is unset. Raises `PurviewError` on
    transport / auth failure so the caller can log-and-continue.

    NOTE: like the Sentinel connector, the audit-ledger emit hook
    is NOT wired in this PR. Future integrators MUST wrap calls in
    `try/except PurviewError` and log-and-continue. The AML engine
    must never fail a rule run because Purview is offline.
    """
    if not _enabled():
        return
    endpoint = os.environ["PURVIEW_ENDPOINT"]
    entities = _build_entities(chain, spec_name)
    if not entities:
        return  # nothing to push — chain was sparse (old run, etc.)
    body = json.dumps({"entities": entities}, default=str)
    token = _bearer_token()
    _post_to_purview(endpoint, token, body)
