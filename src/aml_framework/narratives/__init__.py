"""Narrative drafter — pluggable backends for STR/SAR text generation.

Three backends ship in v1:
  - TemplateBackend  : deterministic, dependency-free; wraps the existing
                       `generators/narrative.py` text. Used by default
                       and in tests.
  - OllamaBackend    : local-first; calls a running Ollama server (no
                       cloud calls). PII never leaves the host.
  - OpenAIBackend    : opt-in; requires OPENAI_API_KEY. Useful for higher-
                       quality drafts where the institution has cleared
                       PII transit with the vendor.

All backends produce a `DraftedNarrative` Pydantic model with structured
fields (text, key findings, **rule_id-tagged citations**, recommended
action, confidence). Structure is what makes the output auditable:
analysts can verify each citation links back to a regulation reference
the rule already declared, not text the model invented.
"""

from aml_framework.narratives.base import NarrativeDrafter, NarrativeError
from aml_framework.narratives.drafter import get_drafter
from aml_framework.narratives.models import (
    CaseEvidence,
    Citation,
    DraftedNarrative,
    case_to_evidence,
    load_case_evidence_from_run_dir,
)
from aml_framework.narratives.template import TemplateBackend

__all__ = [
    "NarrativeDrafter",
    "NarrativeError",
    "CaseEvidence",
    "Citation",
    "DraftedNarrative",
    "case_to_evidence",
    "load_case_evidence_from_run_dir",
    "get_drafter",
    "TemplateBackend",
]
