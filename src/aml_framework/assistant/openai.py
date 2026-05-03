"""OpenAI backend — opt-in cloud LLM.

Requires `OPENAI_API_KEY`. PII transit to OpenAI must be cleared with
the institution's data-protection process before this backend is
used in production. The spec's `program.ai_audit_log` flag controls
whether the full reply text or a SHA-256 hash is logged to
`ai_interactions.jsonl`.

All HTTP IO lives in `_call_openai` so tests patch that one symbol —
same testing posture as `narratives.openai._call_openai`.
"""

from __future__ import annotations

import json
import os
from typing import Any

from aml_framework.assistant.base import AssistantError
from aml_framework.assistant.models import AssistantContext, AssistantReply
from aml_framework.assistant.ollama import _build_prompt, _build_reply

DEFAULT_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def _call_openai(
    url: str,
    model: str,
    api_key: str,
    prompt: str,
    *,
    timeout: float = 60.0,
) -> dict[str, Any]:  # pragma: no cover
    """POST to OpenAI chat completions with json_object response_format."""
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    body = json.dumps(
        {
            "model": model,
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
    req = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - explicit OpenAI URL
            return json.loads(resp.read())
    except HTTPError as e:
        raise AssistantError(
            f"OpenAI returned HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
        ) from e
    except URLError as e:
        raise AssistantError(f"OpenAI request failed: {e}") from e


class OpenAIBackend:
    """Cloud LLM via OpenAI Chat Completions."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        url: str = DEFAULT_OPENAI_URL,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise AssistantError("OpenAIBackend requires OPENAI_API_KEY (env or constructor arg).")
        self.url = url
        self.model = model or os.environ.get("AML_OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        self.timeout = timeout

    @property
    def name(self) -> str:
        return f"openai:{self.model}"

    def reply(self, question: str, context: AssistantContext) -> AssistantReply:
        prompt = _build_prompt(question, context)
        response = _call_openai(self.url, self.model, self.api_key, prompt, timeout=self.timeout)
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise AssistantError(f"Unexpected OpenAI response shape: {e}") from e

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise AssistantError(
                f"OpenAI returned non-JSON despite response_format=json_object: {e}"
            ) from e

        return _build_reply(parsed, context, backend=self.name)
