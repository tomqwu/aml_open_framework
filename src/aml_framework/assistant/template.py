"""Deterministic baseline backend — canned scaffolding, no deps.

Returns a structured reply that:
  - Acknowledges the question + page context (so the operator sees the
    panel is reaching them)
  - Tells them how to enable a real LLM backend (`AML_AI_BACKEND` env)
  - Cites whichever entity ID the deep-link mirrors carried in
    (selected_customer_id / case_id / rule_id / metric_id) so the
    citation column on the panel is never empty when the operator
    drilled into the page

This is what runs in CI and what production should fall back to when
the configured backend errors out. Same posture as
`narratives.template.TemplateBackend`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from aml_framework.assistant.models import AssistantContext, AssistantReply


class TemplateBackend:
    """Canned scaffolding. Always works, never calls out."""

    name = "template:v1"

    def __init__(self, *, _now: datetime | None = None) -> None:
        # `_now` is for tests; production should leave it None.
        self._now = _now

    def reply(self, question: str, context: AssistantContext) -> AssistantReply:
        focus = self._focus_line(context)
        body = (
            f"You asked: *{question.strip()}*\n\n"
            f"This is the **template backend** — a deterministic placeholder "
            f"that ships with the framework so the panel works without an LLM. "
            f"To get real answers, set `AML_AI_BACKEND=ollama` for on-prem "
            f"inference or `AML_AI_BACKEND=openai` (with `OPENAI_API_KEY`) for "
            f"cloud.\n\n"
            f"Context the assistant would have:\n"
            f"- Page: **{context.page}**\n"
            f"- Persona: **{context.persona or 'unset'}**\n"
            f"- Run: {context.alert_count} alert(s) · {context.case_count} case(s) "
            f"· {context.metric_count} metric(s) defined\n"
            f"{focus}"
        )
        return AssistantReply(
            text=body,
            citations=[],
            referenced_metric_ids=[context.selected_metric_id]
            if context.selected_metric_id
            else [],
            referenced_case_ids=[context.selected_case_id] if context.selected_case_id else [],
            referenced_customer_ids=[context.selected_customer_id]
            if context.selected_customer_id
            else [],
            confidence="low",
            backend=self.name,
            prompted_with_persona=context.persona,
            prompted_with_page=context.page,
            answered_at=self._now or datetime.now(tz=timezone.utc),
        )

    @staticmethod
    def _focus_line(ctx: AssistantContext) -> str:
        """Render an extra line if the deep-link mirrors carried an entity."""
        if ctx.selected_case_id:
            return f"- Focused on case: `{ctx.selected_case_id}`\n"
        if ctx.selected_customer_id:
            return f"- Focused on customer: `{ctx.selected_customer_id}`\n"
        if ctx.selected_rule_id:
            return f"- Focused on rule: `{ctx.selected_rule_id}`\n"
        if ctx.selected_metric_id:
            return f"- Focused on metric: `{ctx.selected_metric_id}`\n"
        return ""
