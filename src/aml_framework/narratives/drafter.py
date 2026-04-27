"""Backend factory — `get_drafter("ollama")` returns a NarrativeDrafter."""

from __future__ import annotations

from aml_framework.narratives.base import NarrativeDrafter, NarrativeError


def get_drafter(name: str = "template", **kwargs) -> NarrativeDrafter:
    """Look up a backend by short name.

    Available: `template`, `ollama`, `openai`. Backend imports are lazy so
    failures in one optional dependency don't block the others.
    """
    n = name.lower()
    if n == "template":
        from aml_framework.narratives.template import TemplateBackend

        return TemplateBackend(**kwargs)
    if n == "ollama":
        from aml_framework.narratives.ollama import OllamaBackend

        return OllamaBackend(**kwargs)
    if n == "openai":
        from aml_framework.narratives.openai import OpenAIBackend

        return OpenAIBackend(**kwargs)
    raise NarrativeError(f"Unknown drafter backend: {name!r}")
