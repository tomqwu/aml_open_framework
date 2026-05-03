"""NarrativeDrafter protocol + shared error type."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aml_framework.narratives.models import CaseEvidence, DraftedNarrative


class NarrativeError(RuntimeError):
    """Raised when a backend fails to produce a usable structured draft.

    Backends should raise this rather than returning a placeholder so
    callers can decide whether to fall back to the template backend or
    surface the failure to the analyst.
    """


@runtime_checkable
class NarrativeDrafter(Protocol):
    """Stable interface every backend implements."""

    name: str  # used as the `drafted_by` field on the output

    def draft(self, evidence: CaseEvidence) -> DraftedNarrative:
        """Produce a structured narrative from case evidence."""
        ...  # pragma: no cover
