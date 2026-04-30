"""Backend factory — `get_assistant("template")` returns an Assistant."""

from __future__ import annotations

import os

from aml_framework.assistant.base import Assistant, AssistantError


def get_assistant(name: str | None = None, **kwargs) -> Assistant:
    """Look up a backend by short name.

    When ``name`` is ``None`` (or "auto"), reads ``AML_AI_BACKEND`` from
    the environment, defaulting to ``"template"`` if unset. Backend
    imports are lazy so a missing optional dep (e.g. no ``openai``
    package installed) does not block other backends from working.
    """
    n = (name or os.environ.get("AML_AI_BACKEND", "template")).lower()

    if n == "template":
        from aml_framework.assistant.template import TemplateBackend

        return TemplateBackend(**kwargs)
    if n == "ollama":
        from aml_framework.assistant.ollama import OllamaBackend

        return OllamaBackend(**kwargs)
    if n == "openai":
        from aml_framework.assistant.openai import OpenAIBackend

        return OpenAIBackend(**kwargs)
    raise AssistantError(f"Unknown assistant backend: {name!r}")
