"""Ollama backend — local-first, PII-safe.

Calls a running Ollama server on `http://localhost:11434` (override
via `AML_OLLAMA_URL`). All HTTP IO lives in `_call_ollama` so tests
patch that one symbol — same testing posture as
`narratives.ollama._call_ollama`.

Output contract: backend asks the model for a JSON blob with
`text`, `confidence`, and `citations`/`referenced_*_ids`. We parse
defensively and fall back to a low-confidence reply if the model
returns malformed JSON.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from aml_framework.assistant.base import AssistantError
from aml_framework.assistant.models import AssistantContext, AssistantReply
from aml_framework.narratives.models import Citation

DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_OLLAMA_MODEL = "llama3.1"


def _build_prompt(question: str, context: AssistantContext) -> str:
    """Render question + context as a JSON-output prompt."""
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
    timeout: float = 60.0,
) -> dict[str, Any]:
    """POST to Ollama generate endpoint with JSON format."""
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
    ).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
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
    """Local LLM via Ollama. PII never leaves the host."""

    def __init__(
        self,
        *,
        url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.url = url or os.environ.get("AML_OLLAMA_URL", DEFAULT_OLLAMA_URL)
        self.model = model or os.environ.get("AML_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
        self.timeout = timeout

    @property
    def name(self) -> str:
        return f"ollama:{self.model}"

    def reply(self, question: str, context: AssistantContext) -> AssistantReply:
        prompt = _build_prompt(question, context)
        response = _call_ollama(self.url, self.model, prompt, timeout=self.timeout)
        try:
            content = response["response"]
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
