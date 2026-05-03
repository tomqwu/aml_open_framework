"""OpenAI backend — opt-in LLM drafting.

Requires `OPENAI_API_KEY` in the environment; refuses to instantiate
without it. PII transit to OpenAI must be cleared with the institution's
data-protection process before this backend is used in production.

Like the Ollama backend, all HTTP IO lives in a single `_call_openai`
function so tests patch that one symbol.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from aml_framework.narratives.base import NarrativeError
from aml_framework.narratives.models import CaseEvidence, DraftedNarrative
from aml_framework.narratives.ollama import _build_prompt

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
                    "content": "You are an AML compliance analyst. Output JSON only.",
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
        raise NarrativeError(
            f"OpenAI returned HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
        ) from e
    except URLError as e:
        raise NarrativeError(f"OpenAI request failed: {e}") from e


class OpenAIBackend:
    """LLM drafter backed by the OpenAI Chat Completions API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        url: str = DEFAULT_OPENAI_URL,
        model: str = DEFAULT_OPENAI_MODEL,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise NarrativeError("OpenAIBackend requires OPENAI_API_KEY (env or constructor arg).")
        self.url = url
        self.model = model
        self.timeout = timeout

    @property
    def name(self) -> str:
        return f"openai:{self.model}"

    def draft(self, evidence: CaseEvidence) -> DraftedNarrative:
        prompt = _build_prompt(evidence)
        response = _call_openai(self.url, self.model, self.api_key, prompt, timeout=self.timeout)
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise NarrativeError(f"Unexpected OpenAI response shape: {e}") from e

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise NarrativeError(
                f"OpenAI returned non-JSON despite response_format=json_object: {e}"
            ) from e

        parsed["case_id"] = evidence.case_id
        parsed["drafted_by"] = self.name
        parsed["drafted_at"] = datetime.now(tz=timezone.utc).isoformat()
        parsed.setdefault("citations", [])
        parsed.setdefault("key_findings", [])
        parsed.setdefault("recommended_action", "investigate_further")
        parsed.setdefault("confidence", 0.5)

        try:
            return DraftedNarrative.model_validate(parsed)
        except ValidationError as e:
            raise NarrativeError(f"OpenAI output failed schema validation: {e}") from e
