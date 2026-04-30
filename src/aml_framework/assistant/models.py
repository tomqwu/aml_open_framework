"""Pydantic models — input context and structured assistant reply.

Both frozen so the same context can be passed to multiple backends in
parallel for A/B comparison or fallback. The `Citation` shape is
imported from `narratives.models` so audit pipelines that already
parse narrative citations work unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aml_framework.narratives.models import Citation

Confidence = Literal["high", "medium", "low"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AssistantContext(_Base):
    """Bundle of run + page state passed to the backend.

    Built once per panel render from `st.session_state`. Backends should
    never reach back into session state — everything they need is here.
    """

    page: str  # e.g. "Executive Dashboard"
    persona: str | None = None  # selected_audience: cco / vp / analyst / ...
    spec_name: str = ""
    spec_jurisdiction: str = ""
    spec_regulator: str = ""
    rule_count: int = 0
    metric_count: int = 0
    run_id: str = ""
    alert_count: int = 0
    case_count: int = 0
    decision_count: int = 0

    # Deep-link mirrors — populated when the operator drilled here from
    # another page (PR-A row-click pattern). Lets the assistant scope
    # its reply ("for case X, here's what I see").
    selected_customer_id: str | None = None
    selected_case_id: str | None = None
    selected_rule_id: str | None = None
    selected_metric_id: str | None = None


class AssistantReply(_Base):
    """Structured output from any Assistant backend.

    `text` is what the operator reads. The remaining fields make the
    reply auditable: every claim should reference an entity ID so an
    auditor can trace what the AI said back to the spec or run.
    """

    text: str
    citations: list[Citation] = Field(default_factory=list)
    referenced_metric_ids: list[str] = Field(default_factory=list)
    referenced_case_ids: list[str] = Field(default_factory=list)
    referenced_customer_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = "low"

    backend: str  # e.g. "template:v1" / "openai:gpt-4o-mini"
    prompted_with_persona: str | None = None
    prompted_with_page: str = ""
    answered_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


def reply_to_audit_dict(reply: AssistantReply, *, full_text: bool) -> dict[str, Any]:
    """Render an AssistantReply as a row for ai_interactions.jsonl.

    When `full_text` is False (default per the spec's `ai_audit_log`
    field), the reply text is replaced with a SHA-256 hash so PII is
    bounded. When True, the full text is logged for forensic recall —
    institutions opt into this only after clearing it against their
    privacy posture.
    """
    import hashlib

    base: dict[str, Any] = {
        "ts": reply.answered_at.isoformat(),
        "page": reply.prompted_with_page,
        "persona": reply.prompted_with_persona,
        "backend": reply.backend,
        "confidence": reply.confidence,
        "citations": [c.model_dump() for c in reply.citations],
        "referenced_metric_ids": list(reply.referenced_metric_ids),
        "referenced_case_ids": list(reply.referenced_case_ids),
        "referenced_customer_ids": list(reply.referenced_customer_ids),
    }
    if full_text:
        base["reply_text"] = reply.text
    else:
        base["reply_text_hash"] = hashlib.sha256(reply.text.encode("utf-8")).hexdigest()
    return base
