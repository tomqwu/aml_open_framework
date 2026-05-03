"""Ollama backend — local-first LLM drafting.

Default backend choice for institutions that need PII to stay on-prem.
Talks to a locally-running Ollama server (default
http://localhost:11434), uses `format=json` for structured output, and
validates the response against `DraftedNarrative`.

Design notes
- HTTP only via stdlib (urllib) — no `ollama-python` dependency. The
  framework's install footprint stays the same.
- All network IO lives in `_call_ollama`. Tests patch that single
  function instead of the entire module.
- Failures (server down, malformed JSON, schema mismatch) raise
  `NarrativeError` so the caller can decide whether to fall back to
  the template backend.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from aml_framework.narratives.base import NarrativeError
from aml_framework.narratives.models import CaseEvidence, DraftedNarrative

DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"


def _build_prompt(evidence: CaseEvidence) -> str:
    """The drafter prompt. Kept short so models with small context windows
    (Llama 3.1 8B) still produce structured output reliably.

    Crucially: the prompt instructs the model to **only cite from the
    regulation_refs we provide**. Hallucinated citations are the worst
    failure mode for a regulator-facing artifact.
    """
    reg_refs_block = "\n".join(
        f"  - rule {evidence.rule_id} → {r.get('citation')}: {r.get('description')}"
        for r in evidence.regulation_refs
    )
    return f"""You are an AML compliance analyst drafting a Suspicious Transaction Report
narrative. Output VALID JSON ONLY matching this schema:

{{
  "case_id": "{evidence.case_id}",
  "narrative_text": "<3-5 paragraphs covering who/what/when/where/why/how>",
  "key_findings": ["<short bullet>", "..."],
  "citations": [
    {{"rule_id": "{evidence.rule_id}", "citation": "<one of the provided citations>",
      "claim": "<short text the citation supports>"}}
  ],
  "recommended_action": "file_str" | "close_no_action" | "investigate_further",
  "confidence": 0.0
}}

You MUST cite only from this list. Do not invent citations:
{reg_refs_block or "  (none provided)"}

Case facts:
- Rule: {evidence.rule_id} ({evidence.rule_name})
- Severity: {evidence.severity}
- Customer: {(evidence.customer or {}).get("full_name", "UNKNOWN")} \
({(evidence.customer or {}).get("customer_id", "?")})
- Alert: {json.dumps(evidence.alert, default=str)}
- Transaction count in window: {len(evidence.transactions)}
- Reasoning hint: {evidence.explanation or "(none)"}
"""


def _call_ollama(
    url: str, model: str, prompt: str, *, timeout: float = 60.0
) -> dict[str, Any]:  # pragma: no cover
    """POST to Ollama's /api/generate with format=json, return parsed body.

    Isolated so tests patch this single function. Returns the raw Ollama
    response dict (which contains a `response` field that itself is the
    JSON string the model produced).
    """
    from urllib.error import URLError
    from urllib.request import Request, urlopen

    body = json.dumps({"model": model, "prompt": prompt, "format": "json", "stream": False}).encode(
        "utf-8"
    )
    req = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - explicit local URL
            return json.loads(resp.read())
    except URLError as e:
        raise NarrativeError(f"Ollama request failed: {e}") from e


class OllamaBackend:
    """LLM drafter backed by a local Ollama server."""

    def __init__(
        self,
        *,
        url: str = DEFAULT_OLLAMA_URL,
        model: str = DEFAULT_OLLAMA_MODEL,
        timeout: float = 60.0,
    ) -> None:
        self.url = url
        self.model = model
        self.timeout = timeout

    @property
    def name(self) -> str:
        return f"ollama:{self.model}"

    def draft(self, evidence: CaseEvidence) -> DraftedNarrative:
        prompt = _build_prompt(evidence)
        ollama_response = _call_ollama(self.url, self.model, prompt, timeout=self.timeout)
        body = ollama_response.get("response", "")
        if not body:
            raise NarrativeError("Ollama returned empty response body")

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as e:
            raise NarrativeError(f"Ollama returned non-JSON despite format=json: {e}") from e

        # Stamp authoritative fields the model isn't allowed to set.
        parsed["case_id"] = evidence.case_id
        parsed["drafted_by"] = self.name
        parsed["drafted_at"] = datetime.now(tz=timezone.utc).isoformat()
        # The model often forgets `citations` when there are no refs;
        # guarantee the field exists so validation passes.
        parsed.setdefault("citations", [])
        parsed.setdefault("key_findings", [])
        parsed.setdefault("recommended_action", "investigate_further")
        parsed.setdefault("confidence", 0.5)

        try:
            return DraftedNarrative.model_validate(parsed)
        except ValidationError as e:
            raise NarrativeError(f"Ollama output failed schema validation: {e}") from e
