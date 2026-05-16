"""Per-section GenAI explanations — inline, auto-loaded.

The sidebar `ai_panel()` in `components.py` answers freeform questions
about the *whole page*. This module gives every visual section
(KPI card, chart, table) its own AI explanation that fires
automatically on page render, scoped to *that specific section's data*.

Design:

- **Inline.** Renders directly into the page flow via `st.container()`
  + a `#####` markdown header. No expander, no click.
- **Auto-fire, non-blocking.** Every `section_explainer()` call
  dispatches the LLM call to a background thread pool and returns
  immediately with a "Generating…" placeholder — the page is fully
  usable at t=0, never blocked waiting on the model. A polling
  fragment (`render_explainer_poller`, mounted once per page by
  `page_header`) auto-fills each box ~2-3 sec later with NO user
  interaction. The `(page, section_id, persona, data_hash)` cache
  key short-circuits repeat visits — only the first paint per
  filter-state pays the LLM cost; cache hits render <1 ms with no
  thread. Operators can switch to `AML_AI_BACKEND=template` for
  zero-cost canned scaffolding.
- **e2e-safe.** The poll fragment ticks every ~1.2 s while work is
  pending. The Playwright suite was moved off `wait_until=
  "networkidle"` onto a deterministic page-shell selector so the
  poll chatter no longer starves it (the regression that forced
  PR #306 to revert the earlier async attempt).
- **Audit-logged.** Every reply appended to the run's
  `ai_interactions.jsonl` with `event="ai_section_explanation"`;
  attempted-but-failed calls get a distinct
  `event="ai_section_explanation_failed"` row. An auditor can trace
  exactly which sections were explained AND which were asked but did
  not answer. The audit destination is snapshotted at dispatch from
  the asking session, and the drain is lock-serialized so a reply is
  logged exactly once even with multiple concurrent session pollers.
- **Failure-visible.** Outer try/except catches any error (backend
  down, no key, JSON parse failure) and renders a visible
  `st.error(...)` banner naming the backend, model, and underlying
  exception so the operator can diagnose. Previously this swallowed
  errors and rendered a canned TemplateBackend reply, which masked
  ollama / openai bugs behind text that looked correct.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import threading
from collections.abc import Mapping
from typing import Any, Literal

import streamlit as st

# Default model identifiers for the two complexity tiers. Operators
# override via `AML_OLLAMA_MODEL_FAST` / `AML_OLLAMA_MODEL_DEEP` env
# vars on the Container App; if those are unset, fall back to
# `AML_OLLAMA_MODEL` (the historical single-model env). The defaults
# below match the Ollama Cloud catalog — DeepSeek V4 Flash for
# cheap/fast summaries and DeepSeek V4 Pro for deep reasoning.
#
# NOTE: the tag separator is a HYPHEN, not a colon. Ollama Cloud
# serves these as `deepseek-v4-flash` / `deepseek-v4-pro`. The earlier
# `deepseek-v4:flash` / `deepseek-v4:pro` values 404'd on
# https://ollama.com/api/chat ("model not found"); verified against
# the live `/api/tags` + a 1-token probe on 2026-05-15. Only
# `gpt-oss:120b` worked before this fix because that was the legacy
# single-model env value.
_DEFAULT_MODEL_FAST = "deepseek-v4-flash"
_DEFAULT_MODEL_DEEP = "deepseek-v4-pro"


def _resolve_model(complexity: Literal["fast", "deep"]) -> str:
    """Pick the model name for this complexity tier.

    Resolution order:
      1. `AML_OLLAMA_MODEL_FAST` / `AML_OLLAMA_MODEL_DEEP` (per-tier).
      2. `AML_OLLAMA_MODEL` (global single-model fallback).
      3. Hardcoded defaults: deepseek-v4-flash / deepseek-v4-pro.
    """
    tier_var = "AML_OLLAMA_MODEL_DEEP" if complexity == "deep" else "AML_OLLAMA_MODEL_FAST"
    tier_default = _DEFAULT_MODEL_DEEP if complexity == "deep" else _DEFAULT_MODEL_FAST
    return os.environ.get(tier_var) or os.environ.get("AML_OLLAMA_MODEL") or tier_default


# --------------------------------------------------------------------
# Async dispatch — keep the page non-blocking on first paint.
# --------------------------------------------------------------------
# The LLM call runs on a background thread pool so `section_explainer`
# returns in ~5 ms and the page hero/tables/charts are usable
# immediately. A polling fragment (`render_explainer_poller`, mounted
# once per page by `page_header`) auto-fills each AI box ~2-3 sec later
# with NO user interaction. The earlier sync `st.spinner` blocked the
# whole script for ~2-3 sec/section; the even-earlier #304 async attempt
# only surfaced the reply on the next manual interaction (spinner
# forever) and its 1-sec poll fragment starved Playwright's
# `networkidle`. This revision keeps async + restores the auto-poll,
# and the e2e suite was moved off `networkidle` onto a deterministic
# page-shell selector so the poll chatter no longer breaks it.
_EXECUTOR: concurrent.futures.ThreadPoolExecutor | None = None

# In-flight futures keyed by the `_cache_key` tuple
# (page, section_id, persona, data_hash). The poller drains these.
_FUTURES: dict[tuple[str, str, str, str], concurrent.futures.Future] = {}

# Per-future metadata the audit hook needs but the future's return
# value doesn't carry (section_title is a human label; backend/model
# are for the error banner). Populated at dispatch, drained on resolve.
_FUTURE_META: dict[tuple[str, str, str, str], dict[str, str]] = {}

# Keys whose LLM call raised. The next `section_explainer` render for
# that key surfaces an `st.error(...)` banner (post-#311 posture: real
# errors are visible, never masked by a canned template reply) and
# clears the entry so a later navigation can retry.
_FAILED: dict[tuple[str, str, str, str], BaseException] = {}

# Serializes the poller drain. Multiple Streamlit sessions/tabs on one
# replica each mount their own poller fragment over these shared
# globals; without this, two pollers can both observe the same
# `.done()` future before either pops it and `_log_to_audit` fires
# twice for one reply (a duplicate compliance-audit entry). The lock
# makes "claim (pop) + promote" atomic so exactly one poller handles
# each future. Held briefly on a ~1.2 s cadence — negligible
# contention.
_DRAIN_LOCK = threading.Lock()


def _get_executor() -> concurrent.futures.ThreadPoolExecutor:
    """Lazily build the shared worker pool. Bounded at 4 — at most 4
    concurrent backend calls per replica; later submits queue. Shared
    across all Streamlit sessions on this container (same model as
    `_PROCESS_CACHE`)."""
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="aml-explain"
        )
    return _EXECUTOR


def _do_llm_call(*, question: str, context: Any, backend_name: str, model: str | None) -> Any:
    """Worker-thread entry point. Delegates to `_call_backend` and lets
    any exception propagate into the `Future` — it is NOT swallowed
    into a TemplateBackend reply here. The poller captures the
    exception into `_FAILED` so the operator sees the real error (the
    #311 contract: a failing ollama/openai backend must be visible,
    not masked by canned scaffolding)."""
    return _call_backend(question=question, context=context, backend_name=backend_name, model=model)


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


def _audit_ctx() -> tuple[Any, str]:
    """Snapshot the audit destination from the CURRENT session's state.

    Called on the main thread of the originating session at DISPATCH
    time and stored in `_FUTURE_META`, so the reply is later attributed
    to the run_dir of the session that asked — not whichever session's
    poller happens to drain the future (`run_dir` is per-session
    `st.session_state`; any replica poller can drain any global
    future). Returns `(run_dir, audit_mode)`."""
    run_dir = st.session_state.get("run_dir")
    spec = st.session_state.get("spec")
    audit_mode = getattr(getattr(spec, "program", None), "ai_audit_log", "hash_only")
    return run_dir, audit_mode


def _log_to_audit(
    reply: Any,
    *,
    section_id: str,
    section_title: str,
    run_dir: Any = None,
    audit_mode: str | None = None,
) -> None:
    """Append the section-explanation reply to `ai_interactions.jsonl`
    under `event="ai_section_explanation"`. Best-effort: any failure
    (no run_dir, write error) is swallowed so the page never breaks.

    `run_dir`/`audit_mode` are passed explicitly from the dispatch-time
    snapshot (`_FUTURE_META`) so the entry lands in the asking
    session's run dir. They fall back to the current session's state
    when omitted (direct synchronous callers / the sidebar advisor)."""
    try:
        from pathlib import Path

        from aml_framework.assistant.models import reply_to_audit_dict
        from aml_framework.engine.audit import AuditLedger

        if run_dir is None:
            run_dir, audit_mode = _audit_ctx()
        if run_dir is None:
            return
        if audit_mode is None:
            audit_mode = "hash_only"
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


def _log_failure_to_audit(
    exc: BaseException,
    *,
    section_id: str,
    section_title: str,
    run_dir: Any,
    backend: str,
    model: str,
) -> None:
    """Record an attempted-but-failed section explanation under
    `event="ai_section_explanation_failed"`. A compliance framework
    must be able to prove the AI was *asked* — and that it did not
    answer — not just log successes. Distinct event so it never
    pollutes the success audit trail. Best-effort like
    `_log_to_audit`."""
    try:
        from datetime import datetime, timezone
        from pathlib import Path

        from aml_framework.engine.audit import AuditLedger

        if run_dir is None:
            return
        AuditLedger.append_to_run_dir(
            Path(run_dir),
            {
                "event": "ai_section_explanation_failed",
                "ts": datetime.now(tz=timezone.utc).isoformat(),
                "section_id": section_id,
                "section_title": section_title,
                "backend": backend,
                "model": model,
                "error": str(exc)[:500],
            },
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
    KPI card). On first paint the LLM call is dispatched to a
    background thread and the function returns immediately with a
    non-blocking placeholder; `render_explainer_poller` (mounted by
    `page_header`) auto-fills the reply ~2-3 sec later with no user
    interaction. The `(page, section_id, persona, data_hash)` cache
    short-circuits repeat renders — only the first paint per
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
        # explanation is part of the page flow. On first paint of an
        # uncached section the LLM call is dispatched to a background
        # thread and the function returns immediately with a
        # non-blocking "Generating…" placeholder — the page hero,
        # tables and charts are usable at t=0. `render_explainer_poller`
        # (mounted once per page by `page_header`) auto-fills the box
        # ~2-3 sec later with no user interaction. Subsequent reruns
        # hit the (page, section_id, persona, data_hash)
        # `_PROCESS_CACHE` and render in <1 ms with no thread.
        key = _cache_key(page, section_id, effective_persona, data_hash)
        with st.container():
            st.markdown(f"##### ℹ {section_title} — AI Explanation")
            if effective_persona:
                st.caption(f"Tailored for persona: `{effective_persona}`")

            if cached_reply is not None:
                _render_reply(cached_reply)
                return

            # The worker raised on a prior poll. Surface the real
            # error (post-#311: never mask a failing backend with a
            # canned reply) and clear it so a later navigation retries.
            failed = _FAILED.pop(key, None)
            if failed is not None:
                st.error(
                    f"AI Explanation failed via `{backend_name}` (model `{model}`): {failed!s}"
                )
                return

            # Dispatch once per key; concurrent sessions share the
            # future (same model as the shared cache).
            if key not in _FUTURES:
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
                # Snapshot the audit destination NOW, on this session's
                # main thread, so the reply is attributed to the run_dir
                # of the session that asked — not whichever session's
                # poller drains the future (run_dir is per-session
                # session_state; any replica poller can drain any
                # global future).
                ctx_run_dir, ctx_audit_mode = _audit_ctx()
                _FUTURES[key] = _get_executor().submit(
                    _do_llm_call,
                    question=question,
                    context=context,
                    backend_name=backend_name,
                    model=model,
                )
                _FUTURE_META[key] = {
                    "section_title": section_title,
                    "backend_name": backend_name,
                    "model": model or "",
                    "run_dir": ctx_run_dir,
                    "audit_mode": ctx_audit_mode,
                }

            # Non-blocking placeholder. NOT `st.spinner` (that blocks
            # the script). The poller replaces this on the next rerun.
            st.caption("⟳ Generating explanation…")
    except Exception as exc:  # noqa: BLE001
        # Don't break the page (the host section already rendered) but
        # surface the actual error so the operator can diagnose instead
        # of a silent failure.
        try:
            st.error(f"AI Explanation failed via `{backend_name}` (model `{model}`): {exc!s}")
        except Exception:  # noqa: BLE001
            return


def section_explainer_has_pending() -> bool:
    """True when at least one section's LLM call is still in flight.

    Introspection helper for tests/observability — NOT used to gate
    the poller mount (the poller is mounted unconditionally because
    `page_header` runs before any `section_explainer` call; see the
    comment there)."""
    return bool(_FUTURES)


def _promote_resolved() -> bool:
    """Drain every `.done()` future into `_PROCESS_CACHE` (+ exactly one
    `_log_to_audit` call) or record its exception into `_FAILED` (+ one
    `_log_failure_to_audit`). Returns True if anything resolved.

    Concurrency: the whole drain runs under `_DRAIN_LOCK`, and each
    future is *claimed* (popped from `_FUTURES`/`_FUTURE_META`) before
    its result is processed. So when N session pollers tick over the
    shared globals, exactly one promotes a given future — no duplicate
    audit entries. Audit destination comes from the dispatch-time
    snapshot in `_FUTURE_META` (the asking session's run_dir), not the
    draining session's state. No `st.*` calls — unit-testable without
    a fragment/run context."""
    promoted = False
    with _DRAIN_LOCK:
        for key in list(_FUTURES.keys()):
            fut = _FUTURES.get(key)
            if fut is None or not fut.done():
                continue
            # Claim atomically: pop BEFORE processing so a concurrent
            # poller can't also pick up this future.
            meta = _FUTURE_META.pop(key, {})
            _FUTURES.pop(key, None)
            run_dir = meta.get("run_dir")
            try:
                reply = fut.result()
            except BaseException as exc:  # noqa: BLE001 — surface ALL failures
                _FAILED[key] = exc
                _log_failure_to_audit(
                    exc,
                    section_id=key[1],
                    section_title=meta.get("section_title", key[1]),
                    run_dir=run_dir,
                    backend=meta.get("backend_name", ""),
                    model=meta.get("model", ""),
                )
                promoted = True
                continue
            page, section_id, persona, data_hash = key
            _cache_put(page, section_id, persona or None, data_hash, reply)
            _log_to_audit(
                reply,
                section_id=section_id,
                section_title=meta.get("section_title", section_id),
                run_dir=run_dir,
                audit_mode=meta.get("audit_mode"),
            )
            promoted = True
    return promoted


@st.fragment(run_every="1.2s")
def render_explainer_poller() -> None:
    """Thin fragment wrapper around `_promote_resolved`. Mounted once
    per page by `page_header`, unconditionally (it runs before any
    `section_explainer` call, so a "pending?" gate would never arm on
    first paint — see the page_header comment). It therefore ticks
    every ~1.2 s for the page's lifetime; the body is a cheap no-op
    over an empty `_FUTURES` when nothing is in flight.

    Each tick promotes resolved futures; if anything resolved it calls
    `st.rerun()` so `section_explainer` re-runs and renders the reply
    (or the error banner) in place via the cache-hit fast path. The
    body is a no-op while nothing is done yet, so the only cost while
    waiting is a cheap 1.2-sec partial rerun. e2e no longer waits on
    `networkidle`, so this ticking is safe.

    Coverage: Streamlit's real `@st.fragment` decorator no-ops the body
    outside a script-run context, so these two lines can't execute in
    unit tests. All logic is in `_promote_resolved` (fully covered);
    this wrapper is exercised by the Playwright e2e suite."""
    if _promote_resolved():  # pragma: no cover
        st.rerun()  # pragma: no cover


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
    either send `deepseek-v4-pro` to the OpenAI API (400) or pass an
    unsupported kwarg to AzureOpenAIBackend. OpenAI reads its own
    `AML_OPENAI_MODEL` env in its backend constructor, and the Azure
    backend reads its deployment name from `AML_AZURE_OPENAI_DEPLOYMENT`.
    """
    from aml_framework.assistant.factory import get_assistant

    kwargs: dict[str, Any] = {}
    if model and backend_name == "ollama":
        kwargs["model"] = model
    return get_assistant(backend_name, **kwargs).reply(question, context)
