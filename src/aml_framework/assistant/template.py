"""Deterministic baseline backend — canned scaffolding, no deps.

Returns a structured reply that:
  - LEADS with a concise, plain-English, exec-readable summary of the
    section using the context it has (page, persona, alert/case/metric
    counts, focused entity) — so a non-technical reader sees a finished
    product, not developer setup jargon.
  - Echoes the question back (so the operator sees the panel is
    reaching them).
  - Closes with one short, muted operator line noting this is a
    baseline summary that an LLM backend would enrich — WITHOUT naming
    env vars in the exec-facing body.
  - Cites whichever entity ID the deep-link mirrors carried in
    (selected_customer_id / case_id / rule_id / metric_id) so the
    citation column on the panel is never empty when the operator
    drilled into the page

This is what runs in CI and when the operator explicitly selects
`AML_AI_BACKEND=template`. It is NOT a silent fallback for failing
ollama / openai backends — those now surface their real errors via
the dashboard's `st.error(...)` banners so misconfiguration is
visible rather than masked by canned scaffolding. Same posture as
`narratives.template.TemplateBackend`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from aml_framework.assistant.models import AssistantContext, AssistantReply


class TemplateBackend:
    """Canned scaffolding. Always works, never calls out."""

    name = "template:v1"

    def __init__(self, *, _now: datetime | None = None, model: str | None = None) -> None:
        # `_now` is for tests; production should leave it None.
        # `model` is accepted but ignored — callers (factory, section
        # explainer) pass it generically so every backend has a uniform
        # constructor signature. The template reply is hard-coded so
        # there is no per-model behavior to vary.
        self._now = _now
        self._model = model

    def reply(self, question: str, context: AssistantContext) -> AssistantReply:
        focus = self._focus_line(context)
        body = (
            f"**{context.page}** — this run surfaced "
            f"**{context.alert_count} alert(s)** across "
            f"**{context.case_count} case(s)**, evaluated against "
            f"**{context.metric_count} defined metric(s)**"
            f"{self._persona_clause(context)}. "
            f"{self._headline(context)}\n\n"
            f"{focus}"
            f"You asked: *{question.strip()}*\n\n"
            f"_Baseline summary — connect an LLM backend for richer analysis._"
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
    def _persona_clause(ctx: AssistantContext) -> str:
        """Tailor the lead to the reader's persona when one is set."""
        return f", framed for the **{ctx.persona}** view" if ctx.persona else ""

    @staticmethod
    def _headline(ctx: AssistantContext) -> str:
        """One plain-English next-step sentence sized to the run's volume.

        Deterministic, no env-var jargon — this is the exec-facing line.
        """
        if ctx.alert_count == 0:
            return "Nothing is flagged on this view right now."
        if ctx.case_count == 0:
            return "Flagged activity is still at the alert stage — none escalated to a case yet."
        return "Review the open cases first, then work down the remaining alerts."

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
