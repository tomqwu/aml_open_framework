"""Azure OpenAI backend — for enterprise tenants with Azure commitments.

Same wire shape as `openai.py` (Chat Completions, `response_format:
json_object`), but routes to an Azure OpenAI deployment endpoint and
authenticates via either an API key or an Entra-ID token.

Auth precedence:
1. `AZURE_OPENAI_API_KEY` — explicit key, sourced from Key Vault when
   the deployment runs on the landing zone (the SecretsProvider
   already resolves KV references when `AZURE_KEY_VAULT_NAME` is set).
2. `DefaultAzureCredential` token at scope
   `https://cognitiveservices.azure.com/.default` — the Entra-ID
   path used by the rest of the Azure plumbing (api/db.py for
   Postgres, integrations for Cosmos / KV). Preferred for production
   because no key rotation is needed.

Required env vars / constructor args:
- `AZURE_OPENAI_ENDPOINT` — the deployment endpoint
  (e.g. `https://my-openai.openai.azure.com/`).
- `AZURE_OPENAI_DEPLOYMENT` — the deployment name (NOT the model id;
  Azure routes by deployment).

Optional:
- `AZURE_OPENAI_API_VERSION` — defaults to `2024-10-01-preview`
  which is the GA-stable Chat Completions API version at time of
  writing. Operators on a different version can override.

PII handling: same data-protection process applies as the cloud
OpenAI backend. The `program.ai_audit_log` flag still governs whether
full replies or only SHA-256 hashes land in `ai_interactions.jsonl`.

All HTTP IO lives in `_call_azure_openai` so tests patch that one
symbol — same pattern as `assistant.openai._call_openai`.
"""

from __future__ import annotations

import json
import os
from typing import Any

from aml_framework.assistant.base import AssistantError
from aml_framework.assistant.models import AssistantContext, AssistantReply
from aml_framework.assistant.ollama import _build_prompt, _build_reply

DEFAULT_AZURE_OPENAI_API_VERSION = "2024-10-01-preview"
AAD_OPENAI_SCOPE = "https://cognitiveservices.azure.com/.default"


def _azure_openai_url(endpoint: str, deployment: str, api_version: str) -> str:
    """Compose the Chat Completions URL for a deployment.

    Azure routes by `deployment` (the operator-set name), not by
    `model` (which lives inside the deployment definition). The same
    underlying GPT-4o is served at different URLs in different
    deployments / regions.
    """
    base = endpoint.rstrip("/")
    return f"{base}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"


def _call_azure_openai(
    url: str,
    api_key: str | None,
    bearer_token: str | None,
    prompt: str,
    *,
    timeout: float = 60.0,
) -> dict[str, Any]:  # pragma: no cover
    """POST to Azure OpenAI Chat Completions.

    Exactly one of `api_key` / `bearer_token` must be supplied —
    Azure uses different header names (`api-key` vs
    `Authorization: Bearer`). Mixing both confuses the gateway.
    """
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    if (api_key is None) == (bearer_token is None):
        raise AssistantError("AzureOpenAIBackend requires exactly one of api_key or bearer_token")
    body = json.dumps(
        {
            "messages": [
                {
                    "role": "system",
                    "content": "You are an AML compliance co-pilot. Output JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
    ).encode("utf-8")
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key is not None:
        headers["api-key"] = api_key
    else:
        headers["Authorization"] = f"Bearer {bearer_token}"
    req = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - explicit Azure URL
            return json.loads(resp.read())
    except HTTPError as e:
        raise AssistantError(
            f"Azure OpenAI returned HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
        ) from e
    except URLError as e:
        raise AssistantError(f"Azure OpenAI request failed: {e}") from e


class AzureOpenAIBackend:
    """Azure OpenAI Chat Completions backend.

    Same JSON-only response contract as the cloud OpenAI backend so
    `_build_reply` can parse the output without per-backend branches.
    """

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        deployment: str | None = None,
        api_version: str | None = None,
        api_key: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        # Route through SecretsProvider so values can live in Key Vault
        # on Container Apps / AKS deployments.
        from aml_framework.secrets import SECRETS

        self.endpoint = endpoint or SECRETS.get("AZURE_OPENAI_ENDPOINT", "") or ""
        self.deployment = deployment or SECRETS.get("AZURE_OPENAI_DEPLOYMENT", "") or ""
        self.api_version = (
            api_version
            or os.environ.get("AZURE_OPENAI_API_VERSION")
            or DEFAULT_AZURE_OPENAI_API_VERSION
        )
        if not self.endpoint or not self.deployment:
            raise AssistantError(
                "AzureOpenAIBackend requires AZURE_OPENAI_ENDPOINT and "
                "AZURE_OPENAI_DEPLOYMENT (env, Key Vault, or constructor args)."
            )
        # API key OR Entra-ID token — prefer key when present (explicit,
        # no extra dependency), fall back to DefaultAzureCredential.
        # The token is fetched lazily on `reply()` because the access
        # token has a 1-hour lifetime; we mint a fresh one per request
        # rather than caching a stale value.
        self.api_key = api_key or SECRETS.get("AZURE_OPENAI_API_KEY", "") or ""
        self.timeout = timeout

    @property
    def name(self) -> str:
        return f"azure_openai:{self.deployment}"

    def _bearer_token(self) -> str:  # pragma: no cover -- runtime-only
        from azure.identity import DefaultAzureCredential

        return DefaultAzureCredential().get_token(AAD_OPENAI_SCOPE).token

    def reply(self, question: str, context: AssistantContext) -> AssistantReply:
        prompt = _build_prompt(question, context)
        url = _azure_openai_url(self.endpoint, self.deployment, self.api_version)
        if self.api_key:
            response = _call_azure_openai(
                url, api_key=self.api_key, bearer_token=None, prompt=prompt, timeout=self.timeout
            )
        else:
            response = _call_azure_openai(
                url,
                api_key=None,
                bearer_token=self._bearer_token(),
                prompt=prompt,
                timeout=self.timeout,
            )
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise AssistantError(f"Unexpected Azure OpenAI response shape: {e}") from e
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise AssistantError(
                f"Azure OpenAI returned non-JSON despite response_format=json_object: {e}"
            ) from e
        return _build_reply(parsed, context, backend=self.name)
