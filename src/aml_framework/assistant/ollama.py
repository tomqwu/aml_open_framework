"""Ollama backend — local daemon or Ollama Cloud, PII stays out of prompts.

Talks to either:
- A local Ollama daemon (``http://localhost:11434/api/chat`` — the
  default; no auth header).
- Ollama Cloud at ``https://ollama.com/api/chat`` (per
  https://docs.ollama.com/cloud) when ``AML_OLLAMA_URL`` is overridden
  and an ``OLLAMA_API_KEY`` is supplied — sent as ``Authorization:
  Bearer …``.

Both endpoints speak Ollama's native chat protocol
(``messages`` array, response under ``message.content``), so a single
code path handles both. All HTTP IO lives in ``_call_ollama`` so tests
patch that one symbol — same testing posture as
``narratives.ollama._call_ollama``.

Output contract: backend asks the model for a JSON blob with
``text``, ``confidence``, and ``citations``/``referenced_*_ids``. We
parse defensively and fall back to a low-confidence reply if the
model returns malformed JSON.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from aml_framework.assistant.base import AssistantError
from aml_framework.assistant.models import AssistantContext, AssistantReply
from aml_framework.narratives.models import Citation
from aml_framework.secrets import SECRETS

DEFAULT_OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_OLLAMA_MODEL = "llama3.1"

# Hosts that count as "local Ollama daemon" — no auth required. Any
# other host is treated as remote/cloud and must carry a Bearer token.
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1", ""})


def _is_local_host(url: str) -> bool:
    """True when the URL points at a localhost-style Ollama daemon."""
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return False
    return host.lower() in _LOCAL_HOSTS


def _build_prompt(question: str, context: AssistantContext) -> str:
    """Render question + context as a JSON-output prompt."""
    # Per-section block — only emitted when the caller is the
    # `section_explainer` popover (section_id is set). Embeds the
    # section's curated data summary inline as JSON so the model
    # has the actual numbers, not just a vague "explain the KPIs".
    section_block = ""
    if context.section_id:
        section_data_json = json.dumps(context.section_data, sort_keys=True, default=str)
        # Bound the inline blob — section_data is supposed to be small
        # but a careless page author could pass a large dict. Truncate
        # at ~2000 chars so we don't blow the context window.
        if len(section_data_json) > 2000:
            section_data_json = section_data_json[:2000] + "...(truncated)"
        section_block = (
            f"\nSection: {context.section_title or context.section_id}\n"
            f"Section data: {section_data_json}\n"
            "Answer specifically about this section's data. Do not reach "
            "for context outside it unless directly relevant.\n"
        )

    return (
        "You are an AML compliance co-pilot embedded in a dashboard.\n"
        "Answer the operator's question using ONLY the run + spec context "
        "below. Cite specific rule_id / metric_id / case_id where they "
        "exist. If you are unsure, say so and rate confidence as 'low'.\n\n"
        f"Page: {context.page}\n"
        f"Persona: {context.persona or 'unset'}\n"
        f"Spec: {context.spec_name or 'unknown'} "
        f"({context.spec_jurisdiction} · {context.spec_regulator})\n"
        f"Rules: {context.rule_count} · Metrics: {context.metric_count}\n"
        f"Run: {context.alert_count} alert(s) · {context.case_count} case(s) "
        f"· {context.decision_count} decision(s)\n"
        + (f"Focused case: {context.selected_case_id}\n" if context.selected_case_id else "")
        + (
            f"Focused customer: {context.selected_customer_id}\n"
            if context.selected_customer_id
            else ""
        )
        + (f"Focused rule: {context.selected_rule_id}\n" if context.selected_rule_id else "")
        + (f"Focused metric: {context.selected_metric_id}\n" if context.selected_metric_id else "")
        + section_block
        + f"\nQuestion: {question.strip()}\n\n"
        + 'Output JSON ONLY: {"text": "...", "confidence": "high|medium|low", '
        + '"referenced_metric_ids": [], "referenced_case_ids": [], '
        + '"referenced_customer_ids": [], '
        + '"citations": [{"rule_id": "...", "citation": "...", "claim": "..."}]}'
    )


def _call_ollama(
    url: str,
    model: str,
    prompt: str,
    *,
    api_key: str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:  # pragma: no cover
    """POST to the Ollama chat endpoint with JSON-format output.

    When ``api_key`` is provided we add ``Authorization: Bearer …`` —
    that's what Ollama Cloud accepts per docs.ollama.com/cloud. Local
    daemons ignore the header, so it's harmless to send it.
    """
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - explicit local URL
            return json.loads(resp.read())
    except HTTPError as e:
        raise AssistantError(
            f"Ollama returned HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
        ) from e
    except URLError as e:
        raise AssistantError(f"Ollama request failed: {e}") from e


class OllamaBackend:
    """LLM via local Ollama daemon or Ollama Cloud. PII stays out of prompts."""

    def __init__(
        self,
        *,
        url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.url = url or os.environ.get("AML_OLLAMA_URL", DEFAULT_OLLAMA_URL)
        self.model = model or os.environ.get("AML_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
        # Resolve the API key from env or Key Vault (`OLLAMA-API-KEY`)
        # via the SecretsProvider — same plumbing as OPENAI_API_KEY.
        self.api_key = api_key if api_key is not None else (SECRETS.get("OLLAMA_API_KEY") or "")
        self.timeout = timeout
        # Fail fast when a remote URL is configured without a key —
        # otherwise the operator gets a 401 from the server with no
        # hint about which env var to set.
        if not _is_local_host(self.url) and not self.api_key:
            raise AssistantError(
                f"OllamaBackend URL {self.url!r} is not localhost but no "
                "OLLAMA_API_KEY is set. Either set OLLAMA_API_KEY (Ollama "
                "Cloud) or point AML_OLLAMA_URL at a local Ollama daemon."
            )

    @property
    def name(self) -> str:
        return f"ollama:{self.model}"

    def reply(self, question: str, context: AssistantContext) -> AssistantReply:
        prompt = _build_prompt(question, context)
        response = _call_ollama(
            self.url,
            self.model,
            prompt,
            api_key=self.api_key or None,
            timeout=self.timeout,
        )
        try:
            content = response["message"]["content"]
        except (KeyError, TypeError) as e:
            raise AssistantError(f"Unexpected Ollama response shape: {e}") from e

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise AssistantError(f"Ollama returned non-JSON despite format=json: {e}") from e

        return _build_reply(parsed, context, backend=self.name)


def _build_reply(
    parsed: dict[str, Any],
    context: AssistantContext,
    *,
    backend: str,
) -> AssistantReply:
    """Parse a backend's JSON dict into a validated AssistantReply.

    Shared by Ollama + OpenAI; tolerant to missing optional fields so a
    minimally-cooperative model still produces a usable reply.
    """
    citations_raw = parsed.get("citations") or []
    citations: list[Citation] = []
    for c in citations_raw:
        if not isinstance(c, dict):
            continue
        try:
            citations.append(
                Citation(**{k: c.get(k, "") for k in ("rule_id", "citation", "claim")})
            )
        except ValidationError:
            continue

    confidence = str(parsed.get("confidence", "low")).lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"

    return AssistantReply(
        text=str(parsed.get("text", "(no reply text returned)")),
        citations=citations,
        referenced_metric_ids=[str(x) for x in parsed.get("referenced_metric_ids", [])],
        referenced_case_ids=[str(x) for x in parsed.get("referenced_case_ids", [])],
        referenced_customer_ids=[str(x) for x in parsed.get("referenced_customer_ids", [])],
        confidence=confidence,  # type: ignore[arg-type]
        backend=backend,
        prompted_with_persona=context.persona,
        prompted_with_page=context.page,
        answered_at=datetime.now(tz=timezone.utc),
    )
