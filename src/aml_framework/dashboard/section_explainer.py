"""Per-section GenAI explanations — inline, auto-loaded.

The sidebar `ai_panel()` in `components.py` answers freeform questions
about the *whole page*. This module gives every visual section
(KPI card, chart, table) its own AI explanation that fires
automatically on page render, scoped to *that specific section's data*.

Design:

- **Inline.** Renders directly into the page flow via `st.container()`
  + a `#####` markdown header. No expander, no click.
- **Auto-fire on first render.** Every `section_explainer()` call
  invokes the configured backend during page render. The
  `(section_id, data_hash, persona)` cache key short-circuits repeat
  visits in the same session — only the first paint per filter-state
  pays the LLM cost. Within an Ollama Cloud free-tier session, this
  is cheap; for paid backends, the operator can switch to
  `AML_AI_BACKEND=template` for zero-cost canned scaffolding.
- **Visible spinner.** Wrapped in `st.spinner(...)` so the operator
  sees the LLM call is in flight rather than a frozen page.
- **Audit-logged.** Every reply appended to the run's
  `ai_interactions.jsonl` with `event="ai_section_explanation"` so an
  auditor can trace exactly which sections were explained.
- **Failure-visible.** Outer try/except catches any error (backend
  down, no key, JSON parse failure) and renders a visible
  `st.error(...)` banner naming the backend, model, and underlying
  exception so the operator can diagnose. Previously this swallowed
  errors and rendered a canned TemplateBackend reply, which masked
  ollama / openai bugs behind text that looked correct.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from typing import Any, Literal

import streamlit as st

# Default model identifiers for the two complexity tiers. Operators
# override via `AML_OLLAMA_MODEL_FAST` / `AML_OLLAMA_MODEL_DEEP` env
# vars on the Container App; if those are unset, fall back to
# `AML_OLLAMA_MODEL` (the historical single-model env). The defaults
# below match the user's Ollama Cloud tier — DeepSeek V4 Flash for
# cheap/fast summaries and DeepSeek V4 Pro for deep reasoning.
_DEFAULT_MODEL_FAST = "deepseek-v4:flash"
_DEFAULT_MODEL_DEEP = "deepseek-v4:pro"


def _resolve_model(complexity: Literal["fast", "deep"]) -> str:
    """Pick the model name for this complexity tier.

    Resolution order:
      1. `AML_OLLAMA_MODEL_FAST` / `AML_OLLAMA_MODEL_DEEP` (per-tier).
      2. `AML_OLLAMA_MODEL` (global single-model fallback).
      3. Hardcoded defaults: deepseek-v4:flash / deepseek-v4:pro.
    """
    tier_var = "AML_OLLAMA_MODEL_DEEP" if complexity == "deep" else "AML_OLLAMA_MODEL_FAST"
    tier_default = _DEFAULT_MODEL_DEEP if complexity == "deep" else _DEFAULT_MODEL_FAST
    return os.environ.get(tier_var) or os.environ.get("AML_OLLAMA_MODEL") or tier_default


# Process-global cache — shared across all Streamlit sessions in this
# container instance. Same (section_id, data_hash, persona, backend)
# tuple → same cached reply, regardless of which session originated
# the first call. Survives page refreshes + multi-user concurrency on
# the same replica. Lost on container restart (deploy rollover), which
# is acceptable: the LLM regenerates on the new image's first hit per
# section. Tests can poke this dict directly via section_explainer._PROCESS_CACHE.
_PROCESS_CACHE: dict[tuple[str, str, str, str], Any] = {}

# Legacy session-state key — kept for backward-compatibility shim in
# tests that still write here. New code path reads/writes _PROCESS_CACHE.
_CACHE_KEY = "section_explanations"


def _data_hash(data_summary: Mapping[str, Any]) -> str:
    """Stable 16-hex hash of a section's data summary.

    Sorted keys + `default=str` so any JSON-incompatible value (e.g.
    numpy scalars from pandas) falls back to repr. Keeps the hash
    deterministic across reruns while tolerating mixed types page
    authors throw in by mistake.
    """
    blob = json.dumps(dict(data_summary), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _cache_key(
    page: str, section_id: str, persona: str | None, data_hash: str
) -> tuple[str, str, str, str]:
    """4-tuple cache key. Note: `model` is intentionally NOT included
    because two different models on the same data should be treated as
    distinct CONTENT (different prompts, different reasoning), and
    callers that flip complexity at runtime are expected to invalidate
    via `data_hash` instead. If we ever want a same-data different-
    model cache, extend this to a 5-tuple."""
    return (page, section_id, persona or "", data_hash)


def _cache_get(page: str, section_id: str, persona: str | None, data_hash: str) -> Any:
    """Look up a cached reply in the process-global cache.

    Falls back to `st.session_state[_CACHE_KEY]` for backward-compat
    with tests that pre-seed the session-scoped cache directly.
    """
    key = _cache_key(page, section_id, persona, data_hash)
    hit = _PROCESS_CACHE.get(key)
    if hit is not None:
        return hit
    # Legacy session-state fallback (test compatibility).
    session_cache = st.session_state.get(_CACHE_KEY)
    if isinstance(session_cache, dict):
        return session_cache.get(key)
    return None


def _cache_put(page: str, section_id: str, persona: str | None, data_hash: str, reply: Any) -> None:
    """Write the reply to the process-global cache so all sessions on
    this container instance share it. Also mirrors into session_state
    so the legacy fallback path stays consistent for the originating
    session.
    """
    key = _cache_key(page, section_id, persona, data_hash)
    _PROCESS_CACHE[key] = reply
    cache = st.session_state.get(_CACHE_KEY)
    if not isinstance(cache, dict):
        cache = {}
        st.session_state[_CACHE_KEY] = cache
    cache[(page, section_id, persona or "", data_hash)] = reply


def _build_context(
    *,
    page: str,
    section_id: str,
    section_title: str,
    section_data: Mapping[str, Any],
    persona: str | None,
) -> Any:
    """Build an `AssistantContext` for a section explanation. Mirrors
    the field set `_handle_ai_submission` builds for the sidebar panel
    so the backend sees identical run-level context plus the new
    section_* fields.
    """
    from aml_framework.assistant.models import AssistantContext

    spec = st.session_state.get("spec")
    result = st.session_state.get("result")
    df_alerts = st.session_state.get("df_alerts")
    df_cases = st.session_state.get("df_cases")
    df_decisions = st.session_state.get("df_decisions")

    return AssistantContext(
        page=page,
        persona=persona or st.session_state.get("selected_audience"),
        spec_name=getattr(getattr(spec, "program", None), "name", "") or "",
        spec_jurisdiction=getattr(getattr(spec, "program", None), "jurisdiction", "") or "",
        spec_regulator=getattr(getattr(spec, "program", None), "regulator", "") or "",
        rule_count=len(getattr(spec, "rules", [])) if spec else 0,
        metric_count=len(getattr(spec, "metrics", [])) if spec else 0,
        run_id=str(getattr(result, "run_id", "")) if result else "",
        alert_count=len(df_alerts) if df_alerts is not None else 0,
        case_count=len(df_cases) if df_cases is not None else 0,
        decision_count=len(df_decisions) if df_decisions is not None else 0,
        selected_customer_id=st.session_state.get("selected_customer_id"),
        selected_case_id=st.session_state.get("selected_case_id"),
        selected_rule_id=st.session_state.get("selected_rule_id"),
        selected_metric_id=st.session_state.get("selected_metric_id"),
        section_id=section_id,
        section_title=section_title,
        section_data=dict(section_data),
    )


def _log_to_audit(reply: Any, *, section_id: str, section_title: str) -> None:
    """Append the section-explanation reply to `ai_interactions.jsonl`
    under `event="ai_section_explanation"`. Best-effort: any failure
    (no run_dir, write error) is swallowed so the page never breaks.
    """
    try:
        from pathlib import Path

        from aml_framework.assistant.models import reply_to_audit_dict
        from aml_framework.engine.audit import AuditLedger

        run_dir = st.session_state.get("run_dir")
        if run_dir is None:
            return
        spec = st.session_state.get("spec")
        audit_mode = getattr(getattr(spec, "program", None), "ai_audit_log", "hash_only")
        row = reply_to_audit_dict(reply, full_text=(audit_mode == "full_text"))
        row["section_id"] = section_id
        row["section_title"] = section_title
        AuditLedger.append_to_run_dir(
            Path(run_dir),
            {"event": "ai_section_explanation", **row},
            jsonl_name="ai_interactions.jsonl",
        )
    except Exception:  # noqa: BLE001
        return


def _render_reply(reply: Any) -> None:
    """Render an AssistantReply inside the popover. Compact form —
    DRAFT banner + body + confidence pill. No citation chips
    (the section context already scopes the claim)."""
    confidence_color = {"high": "#16a34a", "medium": "#d97706", "low": "#94a3b8"}.get(
        getattr(reply, "confidence", "low"), "#94a3b8"
    )
    st.markdown(
        '<div style="font-family:JetBrains Mono,monospace; font-size:10px; '
        "letter-spacing:0.08em; text-transform:uppercase; color:#dc2626; "
        'margin-top:4px; margin-bottom:6px;">DRAFT · analyst review required</div>',
        unsafe_allow_html=True,
    )
    st.markdown(getattr(reply, "text", "(no reply text)"))
    st.markdown(
        f'<span style="font-family:JetBrains Mono,monospace; font-size:10px; '
        f"padding:2px 6px; border-radius:3px; background:{confidence_color}22; "
        f'color:{confidence_color}; font-weight:600;">'
        f"confidence · {getattr(reply, 'confidence', 'low')}</span>",
        unsafe_allow_html=True,
    )


def section_explainer(
    *,
    page: str,
    section_id: str,
    section_title: str,
    data_summary: Mapping[str, Any],
    persona: str | None = None,
    complexity: Literal["fast", "deep"] = "fast",
) -> None:
    """Render an inline AI explanation for a dashboard section.

    Drop this immediately after a section's content (chart, table,
    KPI card). On first render, the LLM call fires automatically and
    the reply lands inline below the section. The
    `(section_id, data_hash, persona)` cache short-circuits repeat
    renders in the same session — only the first paint per
    filter-state pays the LLM cost.

    Args:
        page: Page title — matches the value passed to `page_header()`.
        section_id: Stable slug identifying this section across reruns
            (e.g. ``"exec.kpis.headline"``). Used as the cache key
            and audit-log identifier — keep it stable across UI
            tweaks so cached replies and audit trails persist.
        section_title: Human-readable label rendered in the popover
            header and sent to the backend as section_title.
        data_summary: JSON-serializable dict describing the section's
            data. This is the *entire* view the LLM has of the
            section — curate it (no raw DataFrames, no PII unless
            opt-in). Numbers, counts, top-N breakdowns, RAG bands.
        persona: Override `selected_audience` if the section is
            persona-pinned. Usually None; defaults to the operator's
            current sidebar selection.

    The function never raises — every failure (no key, backend down,
    JSON parse error, missing session state) is surfaced as a single
    `st.error(...)` banner naming the backend and underlying exception.
    """
    # Resolve backend + model up-front so the outer except handler can
    # name them in the error banner even if a failure happens before
    # the main code path reaches its own resolution step (e.g. a
    # `_data_hash` failure on exotic data types).
    backend_name = os.environ.get("AML_AI_BACKEND", "template")
    model = _resolve_model(complexity)

    try:
        data_hash = _data_hash(data_summary)
        effective_persona = persona or st.session_state.get("selected_audience")
        cached_reply = _cache_get(page, section_id, effective_persona, data_hash)

        # Inline render — no expander, no click, no env flag. The
        # explanation is part of the page flow: after the section's
        # content, the explainer renders its own header + spinner +
        # reply. On first render the LLM call fires synchronously
        # inside `st.spinner(...)` so the user sees a legible "in
        # flight" state; the reply lands in place when the call
        # returns. Subsequent reruns hit the (section_id, data_hash,
        # persona) `_PROCESS_CACHE` and render in <1 ms.
        #
        # The synchronous path replaces an earlier async-dispatch
        # attempt (PR #304) where the LLM call ran on a background
        # ThreadPoolExecutor. That model made the page interactive
        # in ~5 ms but the reply never surfaced without an
        # interaction-driven rerun — operators saw spinners that
        # never resolved. A polling fragment fixed visibility but
        # killed Playwright e2e via networkidle starvation. The
        # synchronous baseline is the trade-off: ~2-3 sec block per
        # unique section on first paint, but the AI output is
        # actually visible.
        with st.container():
            st.markdown(f"##### ℹ {section_title} — AI Explanation")
            if effective_persona:
                st.caption(f"Tailored for persona: `{effective_persona}`")

            if cached_reply is not None:
                _render_reply(cached_reply)
                return

            context = _build_context(
                page=page,
                section_id=section_id,
                section_title=section_title,
                section_data=data_summary,
                persona=effective_persona,
            )
            question = (
                f"Explain the '{section_title}' section to the operator. "
                "Highlight what is normal, what is unusual, and what an "
                "analyst should do next."
            )

            with st.spinner(f"Generating explanation via `{backend_name}` — typically 2-3 sec…"):
                reply = _call_backend(
                    question=question,
                    context=context,
                    backend_name=backend_name,
                    model=model,
                )

            _cache_put(page, section_id, effective_persona, data_hash, reply)
            _log_to_audit(reply, section_id=section_id, section_title=section_title)
            _render_reply(reply)
    except Exception as exc:  # noqa: BLE001
        # Don't break the page (the host section already rendered) but
        # surface the actual error so the operator can diagnose the LLM
        # backend instead of silently seeing canned TemplateBackend
        # text while believing they're on ollama/openai.
        try:
            st.error(f"AI Explanation failed via `{backend_name}` (model `{model}`): {exc!s}")
        except Exception:  # noqa: BLE001
            return


def _call_backend(*, question: str, context: Any, backend_name: str, model: str | None) -> Any:
    """Blocking LLM call. Raises on backend failure so the caller can
    surface the real error — historically this swallowed every
    exception and returned a TemplateBackend reply, which masked auth /
    model-name / network bugs on ollama and openai backends behind
    canned scaffolding text. Template responses now only appear when
    the operator explicitly selects `AML_AI_BACKEND=template`.

    The `model` kwarg is only threaded to the **ollama** backend —
    `_resolve_model` reads `AML_OLLAMA_MODEL_FAST/DEEP/MODEL` which name
    ollama model strings. Passing that to OpenAI / Azure OpenAI would
    either send `deepseek-v4:pro` to the OpenAI API (400) or pass an
    unsupported kwarg to AzureOpenAIBackend. OpenAI reads its own
    `AML_OPENAI_MODEL` env in its backend constructor, and the Azure
    backend reads its deployment name from `AML_AZURE_OPENAI_DEPLOYMENT`.
    """
    from aml_framework.assistant.factory import get_assistant

    kwargs: dict[str, Any] = {}
    if model and backend_name == "ollama":
        kwargs["model"] = model
    return get_assistant(backend_name, **kwargs).reply(question, context)
