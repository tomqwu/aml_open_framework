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
`aml://<deployment_id>/<spec>/<part>/<value>` so Purview can match
repeated pushes from the same deployment and update rather than
duplicate, and parallel deployments (UAT vs prod in the same tenant)
don't collide on identical `spec/rule_id/case_id` triples.
`deployment_id` is read from `AML_DEPLOYMENT_ID` env var (e.g. the
Container Apps revision or the per-app RG name); defaults to
`local` when unset so dev runs are obvious in the Purview catalog.

Opt-in via `PURVIEW_ENDPOINT` env var. Auth: DefaultAzureCredential
token at scope `https://purview.azure.net/.default` — the Container
App's UAMI needs the `Purview Data Curator` data-plane role on the
account.

API path: `/datamap/api/atlas/v2/entity/bulk` (Microsoft Purview Data
Map, api-version 2023-09-01). Bulk responses come back as
`EntityMutationResult` JSON — we parse `failedEntities` and raise
`PurviewError` when non-empty so partial-failure pushes are loud
rather than silent.
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


def _deployment_id() -> str:
    """Per-deployment namespace for `qualifiedName`. Read from
    `AML_DEPLOYMENT_ID` — typically the Container Apps revision name
    or the per-app RG name. Defaults to `local` so dev pushes are
    obvious in the Purview catalog rather than colliding with
    production data on identical spec/rule/case triples."""
    return os.environ.get("AML_DEPLOYMENT_ID", "local")


def _qualified(deployment_id: str, spec: str, *parts: str) -> str:
    """`aml://<deployment_id>/<spec>/<part>/<part>` — stable enough
    that re-pushing from the same deployment updates rather than
    duplicates the Purview entity, AND distinct deployments (UAT vs
    prod in the same tenant) never collide on identical
    spec/rule_id/case_id triples. Parts are URL-quoted so values
    containing `/` (e.g. file paths) don't fragment the namespace."""
    from urllib.parse import quote

    quoted = "/".join(quote(p, safe="") for p in parts)
    return f"{DEFAULT_QUALIFIED_NAME_PREFIX}{quote(deployment_id, safe='')}/{quote(spec, safe='')}/{quoted}"


def _build_entities(chain: dict[str, Any], spec_name: str) -> list[dict[str, Any]]:
    """Map a `walk_lineage` chain to Atlas entity dicts.

    Returns a list ready for `POST /datamap/api/atlas/v2/entity/bulk`.
    Skips pieces of the chain that are missing (old runs predating
    Round 12 won't have rule_version stamped; the helper degrades
    gracefully).

    Atlas built-in types used: `DataSet` (for sources + cases) and
    `Process` (for rules). Atlas's built-in `Process` schema doesn't
    declare AML-specific fields like `ruleVersion` / `specContentHash`,
    so those go under the Process entity's `customAttributes` dict
    (Purview surfaces them as string properties in the UI without
    requiring a `typedefs` registration up-front). Future migration
    path: register an `aml_rule_process` custom type extending
    `Process` via `/datamap/api/atlas/v2/types/typedefs` and move
    these fields to first-class attributes for query/filter support.
    """
    entities: list[dict[str, Any]] = []
    rule_id = chain.get("rule_id")
    case_id = chain.get("case_id")
    if not (rule_id and case_id):
        return entities

    deployment_id = _deployment_id()

    # 1. Source data sets — one per input_files entry.
    input_qns: list[str] = []
    for input_file in chain.get("input_files") or []:
        # input_file is a dict {path, sha256, ...} per audit.py.
        path = input_file.get("path") if isinstance(input_file, dict) else str(input_file)
        if not path:
            continue
        qn = _qualified(deployment_id, spec_name, "source", str(path))
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
    rule_qn = _qualified(deployment_id, spec_name, "rule", rule_id)
    case_qn = _qualified(deployment_id, spec_name, "case", case_id)
    custom_attributes: dict[str, str] = {}
    if chain.get("rule_version"):
        custom_attributes["ruleVersion"] = str(chain["rule_version"])
    if chain.get("spec_content_hash"):
        custom_attributes["specContentHash"] = str(chain["spec_content_hash"])
    rule_process: dict[str, Any] = {
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
    if custom_attributes:
        rule_process["customAttributes"] = custom_attributes
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


def _check_mutation_result(payload: dict[str, Any]) -> None:
    """Raise `PurviewError` when Atlas's `EntityMutationResult`
    includes any failed entities. Atlas's bulk endpoint returns
    HTTP 200 even on partial failure — the failures show up in the
    `failedEntities` field. Silent partial failures masked Round 17
    bugs longer than they should have; this parser fails loud.

    Pure function over the parsed JSON body so tests can exercise
    the failure path without spinning up a real HTTP server."""
    failed = payload.get("failedEntities") or {}
    if not failed:
        return
    # Atlas emits `failedEntities` as a map keyed by entity GUID,
    # value: {typeName, qualifiedName?, errorMessage}. Surface the
    # first 5 so the operator log line stays scannable.
    summaries: list[str] = []
    for guid, info in list(failed.items())[:5]:
        type_name = (info or {}).get("typeName", "?")
        qn = (info or {}).get("qualifiedName", guid)
        err = (info or {}).get("errorMessage", "(no error message)")
        summaries.append(f"{type_name} {qn}: {err}")
    raise PurviewError(
        f"Purview bulk push had {len(failed)} failed entities: " + "; ".join(summaries)
    )


def _post_to_purview(
    endpoint: str, token: str, body: str, timeout: float = 30.0
) -> None:  # pragma: no cover
    """POST entities to Purview's Atlas bulk endpoint and parse the
    response for partial-failure entries."""
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
            try:
                payload = json.loads(resp.read())
            except json.JSONDecodeError:
                # Some Atlas versions return empty body on success.
                return
            _check_mutation_result(payload)
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
