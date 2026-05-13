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
- **Failure-safe.** Outer try/except catches any error (backend down,
  no key, JSON parse failure) and renders a single
  `st.caption("Explanation unavailable")` instead of breaking the page.
"""

from __future__ import annotations

import concurrent.futures
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


# Background worker pool for LLM calls. Lazy-initialised on first use
# (some tests don't want the pool spinning up at import time). Bounded
# at 4 workers — at most 4 concurrent backend calls per replica; later
# fires queue. The pool is shared across all Streamlit sessions in this
# container.
_EXECUTOR: concurrent.futures.ThreadPoolExecutor | None = None

# In-flight futures keyed by (page, section_id, persona, data_hash).
# When a section_explainer call first encounters a cache miss, it
# submits the LLM call to _EXECUTOR and stores the future here. The
# next page rerun (any user interaction) calls section_explainer
# again, which checks `.done()` and either keeps showing the spinner
# or promotes the result into _PROCESS_CACHE and renders the reply.
_FUTURES: dict[tuple[str, str, str, str], concurrent.futures.Future] = {}

# Per-future metadata that the audit-hook needs but isn't carried in
# the future's return value (section_title is a human label, not
# something the LLM produced). Populated at dispatch, drained when the
# future resolves into the cache.
_FUTURE_META: dict[tuple[str, str, str, str], dict[str, str]] = {}


def _get_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="aml-explain"
        )
    return _EXECUTOR


def _do_llm_call(question: str, context: Any, backend_name: str, model: str | None = None) -> Any:
    """Worker-thread entry point — blocking LLM call. Falls back to the
    template backend on any failure so the polling path always sees a
    valid AssistantReply rather than an exception. `model` overrides
    the backend's default model (so per-tier routing works without
    touching the env)."""
    try:
        from aml_framework.assistant.factory import get_assistant

        kwargs: dict[str, Any] = {}
        if model:
            kwargs["model"] = model
        return get_assistant(backend_name, **kwargs).reply(question, context)
    except Exception:  # noqa: BLE001
        from aml_framework.assistant.template import TemplateBackend

        return TemplateBackend().reply(question, context)


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
    JSON parse error, missing session state) collapses to a single
    `st.caption("Explanation unavailable")` line.
    """
    try:
        import os

        data_hash = _data_hash(data_summary)
        effective_persona = persona or st.session_state.get("selected_audience")
        cached_reply = _cache_get(page, section_id, effective_persona, data_hash)

        # Inline render — no expander, no click, no env flag. The
        # explanation is part of the page flow: after the section's
        # content, the explainer renders its own header + spinner +
        # reply. On first render the LLM call fires automatically;
        # subsequent reruns hit the (section_id, data_hash, persona)
        # cache and render in <1 ms. For cost-conscious deployments,
        # the operator sets `AML_AI_BACKEND=template` (the framework
        # default) — TemplateBackend returns canned scaffolding with
        # zero network calls.
        with st.container():
            st.markdown(f"##### ℹ {section_title} — AI Explanation")
            if effective_persona:
                st.caption(f"Tailored for persona: `{effective_persona}`")

            if cached_reply is not None:
                _render_reply(cached_reply)
                return

            # ----------------------------------------------------------
            # Cache miss — dispatch the LLM call to the background pool
            # so the script returns immediately. The page becomes
            # interactive within ~5 ms; the AI block fills in via a
            # polling fragment as the future resolves (~2-3 sec).
            # ----------------------------------------------------------
            key = _cache_key(page, section_id, effective_persona, data_hash)
            backend_name = os.environ.get("AML_AI_BACKEND", "template")

            future = _FUTURES.get(key)
            if future is None:
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
                # Pick model per complexity tier (DeepSeek V4 Flash for
                # simple summaries, Pro for narrative/reasoning).
                model = _resolve_model(complexity)
                future = _get_executor().submit(
                    _do_llm_call, question, context, backend_name, model
                )
                _FUTURES[key] = future
                # Carry section_title + chosen model so the cache-promotion
                # path can tag the audit log entry with the human label
                # and the resolved tier.
                _FUTURE_META[key] = {
                    "section_title": section_title,
                    "complexity": complexity,
                    "model": model,
                }

            placeholder = st.empty()
            _poll_and_render(
                placeholder=placeholder,
                key=key,
                page=page,
                section_id=section_id,
                section_title=section_title,
                persona=effective_persona,
                data_hash=data_hash,
                backend_name=backend_name,
            )
    except Exception:  # noqa: BLE001
        # Don't break the page. The host section has already rendered
        # — just skip the explainer chrome.
        try:
            st.caption("Explanation unavailable")
        except Exception:  # noqa: BLE001
            return


def _poll_and_render(
    *,
    placeholder: Any,
    key: tuple[str, str, str, str],
    page: str,
    section_id: str,
    section_title: str,
    persona: str | None,
    data_hash: str,
    backend_name: str,
) -> None:
    """Resolve the future + render. Synchronous promotion when the
    future has already resolved; otherwise register a polling
    fragment that re-runs every 1 sec until it does.

    Synchronous fast-path matters for: (a) cache hits across sessions —
    the same data triggers `_FUTURES.get` to return a done future from
    an earlier session that has since completed; (b) fast backends
    (template) that return in <5 ms; (c) tests, which can `.result()`
    the future and call back into `section_explainer` to deterministically
    drive the polling without relying on the 1-sec fragment timer.
    """
    # Synchronous promotion attempt — covers already-done futures.
    if _promote_if_done(
        placeholder=placeholder,
        key=key,
        page=page,
        section_id=section_id,
        section_title=section_title,
        persona=persona,
        data_hash=data_hash,
    ):
        return

    # Still in flight — render the spinner placeholder and return.
    # On the operator's next interaction (any widget change / persona
    # flip / filter / chart click) Streamlit reruns the page script;
    # section_explainer is called again; `_promote_if_done` picks up
    # the resolved future synchronously and renders the reply.
    #
    # NOTE: an earlier iteration used `@st.fragment(run_every=1.0)` to
    # auto-poll without requiring user interaction. Removed because
    # the 1-sec poll generated continuous Streamlit network chatter
    # that prevented Playwright's `networkidle` wait from settling —
    # the full e2e suite went from 100/100 to 15/100. The trade-off:
    # the reply lands on the next interaction rather than auto-filling
    # within 2-3 sec. For dashboards where the operator typically
    # filters / scrolls / clicks within seconds of landing, this is
    # essentially indistinguishable from auto-polling. Re-introducing
    # the auto-fill via a less-chatty mechanism (e.g. `st_autorefresh`
    # tied to a `done()` predicate, or `st.experimental_rerun()` from
    # a thread-safe broker) is a follow-up.
    with placeholder.container():
        with st.spinner(f"Generating explanation via `{backend_name}` — typically 2-3 sec…"):
            pass


def _promote_if_done(
    *,
    placeholder: Any,
    key: tuple[str, str, str, str],
    page: str,
    section_id: str,
    section_title: str,
    persona: str | None,
    data_hash: str,
) -> bool:
    """If the future for `key` is resolved (or already cached), promote
    the reply into `_PROCESS_CACHE`, fire the audit hook, and render
    inline. Returns True when the cache hit is now satisfied — caller
    can short-circuit further work.
    """
    fut = _FUTURES.get(key)
    if fut is not None and fut.done():
        try:
            reply = fut.result()
        except Exception:  # noqa: BLE001
            _FUTURES.pop(key, None)
            _FUTURE_META.pop(key, None)
            with placeholder.container():
                st.caption("Explanation unavailable")
            return True
        # Prefer the dispatched section_title (stored at dispatch) so
        # the audit row stays consistent even when the caller of
        # _promote_if_done passes a stale fallback.
        title = _FUTURE_META.get(key, {}).get("section_title", section_title)
        _cache_put(page, section_id, persona, data_hash, reply)
        _log_to_audit(reply, section_id=section_id, section_title=title)
        _FUTURES.pop(key, None)
        _FUTURE_META.pop(key, None)

    cached = _PROCESS_CACHE.get(key)
    if cached is not None:
        with placeholder.container():
            _render_reply(cached)
        return True
    return False
