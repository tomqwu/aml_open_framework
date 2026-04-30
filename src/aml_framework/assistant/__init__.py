"""Assistant — page-aware GenAI co-pilot, sibling to the narratives module.

Three backends ship in MVP:
  - TemplateBackend  : canned scaffolding, no deps. Default; works
                       offline, never fails. Tells the operator how to
                       enable a real LLM. Used in CI.
  - OllamaBackend    : local-first; calls a running Ollama server. PII
                       stays on the host.
  - OpenAIBackend    : opt-in cloud; requires OPENAI_API_KEY. The spec's
                       `program.ai_audit_log` flag controls whether full
                       reply text or a SHA-256 hash is logged.

All backends produce an `AssistantReply` Pydantic model with cited
rule_id / metric_id / case_id references — the `Citation` shape is
the same one `narratives.models.Citation` defines so audit pipelines
that already understand narrative citations can reuse the parser.
"""

from aml_framework.assistant.base import Assistant, AssistantError
from aml_framework.assistant.factory import get_assistant
from aml_framework.assistant.models import (
    AssistantContext,
    AssistantReply,
    Confidence,
)
from aml_framework.assistant.template import TemplateBackend

__all__ = [
    "Assistant",
    "AssistantContext",
    "AssistantError",
    "AssistantReply",
    "Confidence",
    "TemplateBackend",
    "get_assistant",
]
