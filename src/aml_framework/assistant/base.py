"""Assistant protocol + shared error type.

Mirrors `narratives.base` deliberately. Same backend pattern, different
output shape: `narratives` produces a structured STR/SAR draft from
case evidence; `assistant` produces a free-form reply with structured
citations from a free-form question + page context.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aml_framework.assistant.models import AssistantContext, AssistantReply


class AssistantError(RuntimeError):
    """Raised when a backend fails to produce a usable reply.

    Backends should raise this rather than returning a placeholder so
    the panel can fall back to the template backend (which always works)
    or surface the failure to the operator with the backend's name.
    """


@runtime_checkable
class Assistant(Protocol):
    """Stable interface every backend implements."""

    name: str  # used as the `backend` field on the reply

    def reply(self, question: str, context: AssistantContext) -> AssistantReply:
        """Produce a structured reply from a question + page context."""
        ...  # pragma: no cover
