"""Tests for `dashboard.section_explainer`.

The helper renders a Streamlit popover with an "Explain this section"
button. Because Streamlit must be loaded to test the actual render
path, these tests use a stub `streamlit` module rather than the real
one — sufficient to assert the rendering plumbing + cache + audit hook
without spinning up a dashboard.
"""

from __future__ import annotations

import concurrent.futures
import sys
from collections.abc import Mapping
from types import SimpleNamespace
from unittest import mock

import pytest


class _StubBlock:
    """Context-manager double for `st.expander(...)` / `st.popover(...)`."""

    def __init__(self, label: str, **kwargs):
        self.label = label
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _StubEmpty:
    """`st.empty()` returns a slot that can be populated later. Provides
    its own `.container()` so `placeholder.container():` works."""

    def __init__(self, owner):
        self.owner = owner

    def container(self, **kwargs):
        self.owner.container_calls.append(kwargs)
        return _StubBlock("placeholder-container", **kwargs)


class _StubStreamlit:
    """Minimal stand-in for `streamlit` that records calls."""

    def __init__(self):
        self.session_state: dict = {}
        self.markdown_calls: list = []
        self.caption_calls: list = []
        self.container_calls: list = []
        self.spinner_calls: list = []
        self.empty_calls: list = []
        self.fragment_calls: list = []

    # Container (context manager) — inline rendering, no expander chrome.
    def container(self, **kwargs):
        self.container_calls.append(kwargs)
        return _StubBlock("container", **kwargs)

    def empty(self, **kwargs):
        self.empty_calls.append(kwargs)
        return _StubEmpty(self)

    # Spinner (context manager).
    def spinner(self, label, **kwargs):
        self.spinner_calls.append((label, kwargs))
        return _StubBlock(label, **kwargs)

    def fragment(self, *args, **kwargs):
        """`st.fragment` is used as `@st.fragment(run_every=1.0)`. The
        decorator returns a wrapper that calls the wrapped function
        exactly once for tests (no actual polling — the test triggers
        re-runs by calling `section_explainer` again)."""
        self.fragment_calls.append((args, kwargs))

        def _wrap(fn):
            # Invoke immediately so the test sees the placeholder fill
            # behavior as a single render pass.
            fn()
            return fn

        return _wrap

    # Plain widgets.
    def markdown(self, text, **kwargs):
        self.markdown_calls.append(text)

    def caption(self, text, **kwargs):
        self.caption_calls.append(text)

    def toast(self, *_a, **_kw):
        pass


@pytest.fixture
def stub_st(monkeypatch):
    stub = _StubStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    # The section_explainer module captures `st` at import time, so we
    # also rebind its module-global reference.
    import aml_framework.dashboard.section_explainer as mod

    monkeypatch.setattr(mod, "st", stub)
    return stub


@pytest.fixture(autouse=True)
def _clear_process_cache():
    """The section_explainer cache + future registry are process-global
    so they survive across Streamlit sessions in a deployed dashboard.
    For tests we clear them before each case so cross-test pollution
    doesn't fake a pass via a cache hit from a prior test."""
    import aml_framework.dashboard.section_explainer as mod

    mod._PROCESS_CACHE.clear()
    mod._FUTURES.clear()
    mod._FUTURE_META.clear()
    yield
    mod._PROCESS_CACHE.clear()
    mod._FUTURES.clear()
    mod._FUTURE_META.clear()


# ---------------------------------------------------------------------------
# Render path — no backend call unless the operator clicks the button
# ---------------------------------------------------------------------------


def test_renders_inline_container_with_header(stub_st):
    """The explainer renders inline via `st.container()` plus a
    `##### ℹ <title> — AI Explanation` markdown header. No expander."""
    from aml_framework.dashboard.section_explainer import section_explainer

    # Stub the backend so render doesn't actually call out.
    fake_assistant = SimpleNamespace(reply=mock.MagicMock(return_value=_fake_reply()))
    with (
        mock.patch("aml_framework.dashboard.section_explainer._log_to_audit"),
        mock.patch("aml_framework.assistant.factory.get_assistant", return_value=fake_assistant),
    ):
        section_explainer(
            page="Executive Dashboard",
            section_id="exec.kpis.headline",
            section_title="Top KPIs",
            data_summary={"alert_total": 12},
        )
    assert stub_st.container_calls, "expected st.container() to be invoked (inline render)"
    # The inline header carries the section title.
    headers = [m for m in stub_st.markdown_calls if "Top KPIs" in m and "AI Explanation" in m]
    assert headers, (
        "expected `##### ℹ <title> — AI Explanation` markdown header inside "
        f"the container. Markdown calls were: {stub_st.markdown_calls!r}"
    )


def test_auto_fires_backend_on_first_render(stub_st, monkeypatch):
    """Auto-fire is the only behavior now — the LLM call must invoke on
    the very first render (no button click, no env flag). The call runs
    in a background worker; we patch `_do_llm_call` and wait for the
    submitted future to complete so the assertion is deterministic."""
    from aml_framework.dashboard import section_explainer as mod

    monkeypatch.delenv("AML_AUTO_EXPLAIN", raising=False)

    do_llm = mock.MagicMock(return_value=_fake_reply())
    with (
        mock.patch.object(mod, "_do_llm_call", side_effect=do_llm),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
        )
        # Wait for the background worker to fire.
        key = mod._cache_key("P", "s", None, mod._data_hash({"v": 1}))
        fut = mod._FUTURES.get(key)
        if fut is not None:
            fut.result(timeout=5)
    assert do_llm.call_count == 1, "backend must auto-fire on first render"


# ---------------------------------------------------------------------------
# Backend interaction when the operator clicks
# ---------------------------------------------------------------------------


def _fake_reply(text="ok", confidence="high"):
    from aml_framework.assistant.models import AssistantReply

    return AssistantReply(
        text=text,
        confidence=confidence,
        backend="template:v1",
        prompted_with_page="Executive Dashboard",
    )


def _wait_for_future(mod, key):
    """Block until the background worker resolves the future for `key`,
    then trigger one more `_promote_if_done` poll so the cache gets
    populated synchronously. In production, Streamlit's
    `@st.fragment(run_every=1.0)` would handle this on its own; in
    tests the stub fragment fires only once per `section_explainer`
    call, so we drive the second poll manually.
    """
    fut = mod._FUTURES.get(key)
    if fut is not None:
        fut.result(timeout=5)
    # Synchronously promote the resolved future into the cache.
    mod._promote_if_done(
        placeholder=mod.st.empty(),
        key=key,
        page=key[0],
        section_id=key[1],
        section_title=key[1],  # title irrelevant for the cache-promotion path
        persona=key[2] or None,
        data_hash=key[3],
    )


def test_first_render_fires_backend_then_caches(stub_st, monkeypatch):
    """First render → backend call submitted to worker → cache write.
    Second render with identical data_summary → cache hit (no
    additional backend call)."""
    from aml_framework.dashboard import section_explainer as mod

    do_llm = mock.MagicMock(return_value=_fake_reply())
    with (
        mock.patch.object(mod, "_do_llm_call", side_effect=do_llm),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        mod.section_explainer(
            page="Executive Dashboard",
            section_id="exec.kpis.headline",
            section_title="Top KPIs",
            data_summary={"alert_total": 12},
        )
        key = mod._cache_key(
            "Executive Dashboard", "exec.kpis.headline", None, mod._data_hash({"alert_total": 12})
        )
        _wait_for_future(mod, key)
        # The polling fragment fired synchronously in our stub, so
        # by now the reply should be cached and the future cleared.
        assert key in mod._PROCESS_CACHE
        assert do_llm.call_count == 1

        # Second render with same data_summary: cache hit, no new call.
        do_llm.reset_mock()
        mod.section_explainer(
            page="Executive Dashboard",
            section_id="exec.kpis.headline",
            section_title="Top KPIs",
            data_summary={"alert_total": 12},
        )
        assert do_llm.call_count == 0


def test_data_change_invalidates_cache(stub_st, monkeypatch):
    """Same (page, section_id, persona) but a different data hash →
    fresh backend call. The cache key includes a SHA-256 of the data
    summary, so filter changes (which alter the row counts a page
    feeds in) invalidate cleanly."""
    from aml_framework.dashboard import section_explainer as mod

    do_llm = mock.MagicMock(return_value=_fake_reply())

    with (
        mock.patch.object(mod, "_do_llm_call", side_effect=do_llm),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
        )
        _wait_for_future(mod, mod._cache_key("P", "s", None, mod._data_hash({"v": 1})))
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 2},  # different value → different hash
        )
        _wait_for_future(mod, mod._cache_key("P", "s", None, mod._data_hash({"v": 2})))
        assert do_llm.call_count == 2


def test_audit_log_event_is_distinct(stub_st, monkeypatch):
    """The audit ledger entry must carry `event="ai_section_explanation"`
    so it's distinguishable from sidebar `ai_interaction` events when
    an auditor reviews the run."""
    from aml_framework.dashboard import section_explainer as mod

    captured: dict = {}

    def fake_append(_run_dir, row, jsonl_name=None):
        captured["row"] = row
        captured["jsonl_name"] = jsonl_name

    stub_st.session_state["run_dir"] = "/tmp/fake_run_dir"
    stub_st.session_state["spec"] = SimpleNamespace(
        program=SimpleNamespace(ai_audit_log="hash_only")
    )

    do_llm = mock.MagicMock(return_value=_fake_reply())
    with (
        mock.patch.object(mod, "_do_llm_call", side_effect=do_llm),
        mock.patch(
            "aml_framework.engine.audit.AuditLedger.append_to_run_dir", side_effect=fake_append
        ),
    ):
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
        )
        _wait_for_future(mod, mod._cache_key("P", "s", None, mod._data_hash({"v": 1})))

    assert captured["row"]["event"] == "ai_section_explanation"
    assert captured["row"]["section_id"] == "s"
    assert captured["row"]["section_title"] == "t"
    assert captured["jsonl_name"] == "ai_interactions.jsonl"


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


def test_backend_error_falls_back_to_template(stub_st, monkeypatch):
    """If the configured backend (e.g. ollama) raises, the worker
    catches it and falls back to TemplateBackend so the polling
    fragment always sees a valid reply, never an unhandled exception."""
    from aml_framework.dashboard import section_explainer as mod

    with (
        mock.patch.object(mod, "_log_to_audit"),
        mock.patch(
            "aml_framework.assistant.factory.get_assistant",
            side_effect=RuntimeError("ollama down"),
        ),
    ):
        # Must not raise.
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
        )
        _wait_for_future(mod, mod._cache_key("P", "s", None, mod._data_hash({"v": 1})))
    # The worker's fallback fired (template backend) and the reply was
    # cached. The next render hits the cache and shows the DRAFT banner.
    assert mod._cache_key("P", "s", None, mod._data_hash({"v": 1})) in mod._PROCESS_CACHE


def test_missing_api_key_is_graceful(stub_st, monkeypatch):
    """OLLAMA_API_KEY unset + AML_AI_BACKEND=ollama → factory raises;
    helper still renders something. No exception propagates."""
    from aml_framework.dashboard import section_explainer as mod

    monkeypatch.setenv("AML_AI_BACKEND", "ollama")
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

    with mock.patch.object(mod, "_log_to_audit"):
        # Should not raise even if get_assistant routes to a backend
        # that fails on construction.
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
        )


def test_caption_when_outer_failure(stub_st, monkeypatch):
    """If something in the helper's own body raises (e.g. broken
    data_summary that hashing can't handle), the host page must not
    crash — a single 'Explanation unavailable' caption is the
    contract."""
    from aml_framework.dashboard import section_explainer as mod

    # Force _data_hash to raise.
    with mock.patch.object(mod, "_data_hash", side_effect=RuntimeError("boom")):
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
        )
    assert any("unavailable" in c for c in stub_st.caption_calls)


# ---------------------------------------------------------------------------
# Helper internals
# ---------------------------------------------------------------------------


def test_data_hash_stable_for_same_dict():
    from aml_framework.dashboard.section_explainer import _data_hash

    a = _data_hash({"x": 1, "y": 2})
    b = _data_hash({"y": 2, "x": 1})  # different insertion order
    assert a == b


def test_data_hash_changes_with_values():
    from aml_framework.dashboard.section_explainer import _data_hash

    assert _data_hash({"x": 1}) != _data_hash({"x": 2})


def test_data_hash_tolerates_non_json_native_types():
    """Pandas / numpy scalars must not crash the hash function —
    `default=str` fallback. Use a custom non-serializable object."""
    from aml_framework.dashboard.section_explainer import _data_hash

    class Weird:
        def __repr__(self):
            return "weird-thing"

    assert _data_hash({"x": Weird()})  # doesn't raise


# ---------------------------------------------------------------------------
# AssistantContext back-compat
# ---------------------------------------------------------------------------


def test_assistant_context_section_fields_optional():
    """Existing call sites (`ai_panel`, `_handle_ai_submission`) don't
    set section fields. Pin that the new fields are all optional and
    default to None / empty dict."""
    from aml_framework.assistant.models import AssistantContext

    ctx = AssistantContext(page="Today")
    assert ctx.section_id is None
    assert ctx.section_title is None
    assert ctx.section_data == {}


def test_assistant_context_section_fields_set():
    from aml_framework.assistant.models import AssistantContext

    ctx = AssistantContext(
        page="Executive Dashboard",
        section_id="exec.kpis",
        section_title="KPIs",
        section_data={"alert_total": 12},
    )
    assert ctx.section_id == "exec.kpis"
    assert ctx.section_data == {"alert_total": 12}


# ---------------------------------------------------------------------------
# Coverage-gap closers — exercise the defensive branches CI flagged
# ---------------------------------------------------------------------------


def test_persona_caption_renders_when_persona_set(stub_st):
    """When `selected_audience` is set, the expander shows a `Tailored
    for persona: <p>` caption. Pinning ensures the persona context is
    visibly surfaced (otherwise the operator can't tell the reply
    is persona-scoped)."""
    from aml_framework.dashboard.section_explainer import section_explainer

    stub_st.session_state["selected_audience"] = "cco"
    section_explainer(
        page="Executive Dashboard",
        section_id="exec.kpis",
        section_title="KPIs",
        data_summary={"v": 1},
    )
    assert any("cco" in c for c in stub_st.caption_calls)


def test_log_to_audit_skips_when_no_run_dir(stub_st):
    """The audit hook short-circuits when `run_dir` isn't in
    session_state (cold dashboard before the engine has produced a
    run). Path must not raise."""
    from aml_framework.dashboard.section_explainer import _log_to_audit

    stub_st.session_state.pop("run_dir", None)
    # Must not raise.
    _log_to_audit(object(), section_id="s", section_title="t")


def test_log_to_audit_swallows_audit_ledger_failure(stub_st):
    """If `AuditLedger.append_to_run_dir` raises (e.g. read-only
    artifacts root), the helper must swallow — never break the page."""
    from aml_framework.dashboard import section_explainer as mod

    stub_st.session_state["run_dir"] = "/tmp/fake_run_dir"
    stub_st.session_state["spec"] = SimpleNamespace(
        program=SimpleNamespace(ai_audit_log="hash_only")
    )

    with mock.patch(
        "aml_framework.engine.audit.AuditLedger.append_to_run_dir",
        side_effect=PermissionError("read-only"),
    ):
        # Must not raise.
        mod._log_to_audit(_fake_reply(), section_id="s", section_title="t")


def test_caption_fallback_also_swallows(monkeypatch):
    """The outermost try/except calls st.caption() as the last-resort
    fallback. If that itself raises (Streamlit context lost), we must
    not propagate — the host page already rendered, the explainer
    chrome is just absent. Pin that the function returns silently."""
    import sys
    from aml_framework.dashboard import section_explainer as mod

    # A stub st where caption itself raises — simulates a torn-down
    # Streamlit context.
    class _BadStreamlit:
        session_state = {}

        @staticmethod
        def expander(*_a, **_kw):
            raise RuntimeError("context lost")

        @staticmethod
        def caption(*_a, **_kw):
            raise RuntimeError("context also lost")

    monkeypatch.setitem(sys.modules, "streamlit", _BadStreamlit)
    monkeypatch.setattr(mod, "st", _BadStreamlit)
    # Must not raise even though both expander() and caption() blow up.
    mod.section_explainer(
        page="P",
        section_id="s",
        section_title="t",
        data_summary={"v": 1},
    )


# ---------------------------------------------------------------------------
# Prompt builder picks up section context
# ---------------------------------------------------------------------------


def test_ollama_build_prompt_includes_section_block_when_set():
    from aml_framework.assistant.models import AssistantContext
    from aml_framework.assistant.ollama import _build_prompt

    ctx = AssistantContext(
        page="Executive Dashboard",
        section_id="exec.kpis.headline",
        section_title="Top KPIs",
        section_data={"alert_total": 12, "severity_red": 3},
    )
    prompt = _build_prompt("Explain this section.", ctx)
    assert "Section: Top KPIs" in prompt
    assert "alert_total" in prompt
    assert "Answer specifically about this section's data" in prompt


def test_ollama_build_prompt_omits_section_block_when_unset():
    """Backward compat: sidebar `ai_panel` invokes the backend with
    no section_id set. The block must not appear (no leading 'Section:'
    line) so the existing prompt shape is unchanged."""
    from aml_framework.assistant.models import AssistantContext
    from aml_framework.assistant.ollama import _build_prompt

    ctx = AssistantContext(page="Run History")
    prompt = _build_prompt("How many runs?", ctx)
    assert "Section:" not in prompt


def test_ollama_build_prompt_truncates_oversized_section_data():
    """A careless page author might pass a 5000-char dict. The builder
    truncates at ~2000 chars + appends '(truncated)' so context windows
    don't explode."""
    from aml_framework.assistant.models import AssistantContext
    from aml_framework.assistant.ollama import _build_prompt

    big_payload: Mapping[str, str] = {f"k{i}": "x" * 50 for i in range(200)}
    ctx = AssistantContext(
        page="P",
        section_id="s",
        section_title="t",
        section_data=dict(big_payload),
    )
    prompt = _build_prompt("explain", ctx)
    assert "(truncated)" in prompt
    assert len(prompt) < 5000


# ---------------------------------------------------------------------------
# UX — visible spinner during the LLM call + opt-in pre-population
# ---------------------------------------------------------------------------


def test_spinner_renders_during_backend_call(stub_st):
    """When the operator clicks Generate, st.spinner wraps the LLM
    call so the page doesn't appear to hang. The spinner label names
    the backend so the operator can sanity-check what's running."""
    from aml_framework.dashboard import section_explainer as mod

    fake_assistant = SimpleNamespace(reply=mock.MagicMock(return_value=_fake_reply()))

    with (
        mock.patch.object(mod, "_log_to_audit"),
        mock.patch("aml_framework.assistant.factory.get_assistant", return_value=fake_assistant),
    ):
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
        )
    assert stub_st.spinner_calls, "expected st.spinner() during the backend call"
    label, _ = stub_st.spinner_calls[0]
    assert "Generating explanation" in label
    # The backend name appears in the label so the operator knows
    # whether they're hitting `template` (canned) or `ollama` (real LLM).
    assert "template" in label.lower() or "ollama" in label.lower()


def test_cache_survives_across_sessions(monkeypatch):
    """The cache is process-global, not session-scoped — so the SAME
    data summary on a NEW Streamlit session hits the cached reply
    populated by an earlier session. This is the regression user
    flagged: a page refresh creates a new session, but should not
    re-fire the LLM call if the underlying data is unchanged."""
    import aml_framework.dashboard.section_explainer as mod

    # Session A — fresh stub, no session_state cache entry.
    stub_a = _StubStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", stub_a)
    monkeypatch.setattr(mod, "st", stub_a)
    do_llm = mock.MagicMock(return_value=_fake_reply())
    with (
        mock.patch.object(mod, "_do_llm_call", side_effect=do_llm),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
        )
        _wait_for_future(mod, mod._cache_key("P", "s", None, mod._data_hash({"v": 1})))
        assert do_llm.call_count == 1, "first session fires the LLM call"

    # Session B — completely new stub object, empty session_state.
    # Should hit the process-global cache populated by session A.
    stub_b = _StubStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", stub_b)
    monkeypatch.setattr(mod, "st", stub_b)
    do_llm_b = mock.MagicMock(return_value=_fake_reply())
    with (
        mock.patch.object(mod, "_do_llm_call", side_effect=do_llm_b),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
        )
    assert do_llm_b.call_count == 0, (
        "second session with same data should hit the process cache, not the backend"
    )


def test_cache_hit_short_circuits_render(stub_st):
    """When the cache already has a reply for this
    (section_id, data_hash, persona) triplet, the helper renders the
    cached reply inline and does NOT call the backend or show the
    spinner. Pin that filter-state stability across reruns is free."""
    from aml_framework.dashboard import section_explainer as mod

    # Seed the process-global cache (the new shared cache surface).
    reply = _fake_reply()
    mod._PROCESS_CACHE.clear()
    mod._PROCESS_CACHE[("P", "s", "", mod._data_hash({"v": 1}))] = reply

    fake_assistant = SimpleNamespace(reply=mock.MagicMock(return_value=_fake_reply()))
    with (
        mock.patch.object(mod, "_log_to_audit"),
        mock.patch(
            "aml_framework.assistant.factory.get_assistant", return_value=fake_assistant
        ) as get_assistant,
    ):
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
        )
    # No backend call, no spinner — cache hit short-circuited.
    assert get_assistant.call_count == 0
    assert fake_assistant.reply.call_count == 0
    assert not stub_st.spinner_calls


# ---------------------------------------------------------------------------
# Deferred render — page renders first, LLM call runs in background
# ---------------------------------------------------------------------------


def test_first_render_returns_before_backend_resolves(stub_st):
    """The LLM call must run in a background worker — the script
    returns immediately after submitting the future. Pin that by
    making the worker block forever; assert section_explainer
    completes synchronously and the spinner placeholder rendered."""
    import time
    import threading

    import aml_framework.dashboard.section_explainer as mod

    # Replace the LLM-call worker with one that blocks forever.
    blocker = threading.Event()
    monkey_calls = []

    def _block_forever(question, context, backend_name):
        monkey_calls.append((question, backend_name))
        blocker.wait()
        return _fake_reply()

    with mock.patch.object(mod, "_do_llm_call", side_effect=_block_forever):
        t0 = time.perf_counter()
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
        )
        elapsed = time.perf_counter() - t0

    # The worker is still blocked, but section_explainer must have
    # returned in well under a second (we measure < 0.5s as a generous
    # bound — the synchronous path runs in ~5ms in practice).
    assert elapsed < 0.5, f"section_explainer blocked for {elapsed:.3f}s (must return immediately)"
    # A future was registered for this key.
    key = mod._cache_key("P", "s", None, mod._data_hash({"v": 1}))
    assert key in mod._FUTURES
    # The polling fragment fired (synchronously in our stub) and
    # rendered the spinner because the future isn't done yet.
    assert stub_st.spinner_calls, "expected spinner during the pending state"
    # Release the worker so it cleans up.
    blocker.set()


def test_polling_fragment_renders_reply_when_future_done(stub_st):
    """When the future has resolved between renders, the polling
    fragment promotes the result into the cache and renders the reply
    in place of the spinner."""
    import aml_framework.dashboard.section_explainer as mod

    # Pre-seed a resolved future for the cache key.
    key = mod._cache_key("P", "s", None, mod._data_hash({"v": 1}))
    fut = concurrent.futures.Future()
    fut.set_result(_fake_reply(text="done"))
    mod._FUTURES[key] = fut

    # The submit path shouldn't fire — the future is already present.
    submitted = []
    original_submit = mod._get_executor().submit

    def _track_submit(*args, **kwargs):
        submitted.append((args, kwargs))
        return original_submit(*args, **kwargs)

    with mock.patch.object(mod._get_executor(), "submit", side_effect=_track_submit):
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
        )

    assert not submitted, "section_explainer must not submit when a future is already in flight"
    # The reply was promoted to the process cache.
    assert key in mod._PROCESS_CACHE
    assert mod._PROCESS_CACHE[key].text == "done"
    # The future was cleaned up.
    assert key not in mod._FUTURES


def test_executor_is_singleton():
    """Multiple section_explainer calls share one ThreadPoolExecutor —
    don't leak a new pool per call."""
    import aml_framework.dashboard.section_explainer as mod

    e1 = mod._get_executor()
    e2 = mod._get_executor()
    assert e1 is e2


# ---------------------------------------------------------------------------
# Model routing — fast / deep tiers
# ---------------------------------------------------------------------------


def test_complexity_fast_uses_fast_model(stub_st, monkeypatch):
    """`complexity="fast"` (the default) picks `AML_OLLAMA_MODEL_FAST`
    when set. Operator can flip the fast tier without touching the
    deep tier."""
    import aml_framework.dashboard.section_explainer as mod

    monkeypatch.setenv("AML_OLLAMA_MODEL_FAST", "deepseek-v4:flash-override")
    monkeypatch.setenv("AML_OLLAMA_MODEL_DEEP", "deepseek-v4:pro")
    monkeypatch.delenv("AML_OLLAMA_MODEL", raising=False)

    captured = []

    def fake_do(question, context, backend_name, model=None):
        captured.append({"model": model})
        return _fake_reply()

    with (
        mock.patch.object(mod, "_do_llm_call", side_effect=fake_do),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
            complexity="fast",
        )
        _wait_for_future(mod, mod._cache_key("P", "s", None, mod._data_hash({"v": 1})))
    assert captured[0]["model"] == "deepseek-v4:flash-override"


def test_complexity_deep_uses_deep_model(stub_st, monkeypatch):
    """`complexity="deep"` picks `AML_OLLAMA_MODEL_DEEP` — the heavier
    reasoning tier reserved for lineage / investigation pages."""
    import aml_framework.dashboard.section_explainer as mod

    monkeypatch.setenv("AML_OLLAMA_MODEL_FAST", "deepseek-v4:flash")
    monkeypatch.setenv("AML_OLLAMA_MODEL_DEEP", "deepseek-v4:pro-override")
    monkeypatch.delenv("AML_OLLAMA_MODEL", raising=False)

    captured = []

    def fake_do(question, context, backend_name, model=None):
        captured.append({"model": model})
        return _fake_reply()

    with (
        mock.patch.object(mod, "_do_llm_call", side_effect=fake_do),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
            complexity="deep",
        )
        _wait_for_future(mod, mod._cache_key("P", "s", None, mod._data_hash({"v": 1})))
    assert captured[0]["model"] == "deepseek-v4:pro-override"


def test_resolve_model_falls_back_through_chain(monkeypatch):
    """Resolution chain: per-tier env → AML_OLLAMA_MODEL → hardcoded
    default. Pin all three rungs so an operator unsetting one var
    doesn't blow up the model name."""
    import aml_framework.dashboard.section_explainer as mod

    # Rung 1: tier-specific env wins.
    monkeypatch.setenv("AML_OLLAMA_MODEL_FAST", "tier-fast")
    monkeypatch.setenv("AML_OLLAMA_MODEL", "global")
    assert mod._resolve_model("fast") == "tier-fast"

    # Rung 2: tier-specific env unset → fall back to AML_OLLAMA_MODEL.
    monkeypatch.delenv("AML_OLLAMA_MODEL_FAST", raising=False)
    monkeypatch.delenv("AML_OLLAMA_MODEL_DEEP", raising=False)
    assert mod._resolve_model("fast") == "global"
    assert mod._resolve_model("deep") == "global"

    # Rung 3: everything unset → hardcoded DeepSeek defaults.
    monkeypatch.delenv("AML_OLLAMA_MODEL", raising=False)
    assert mod._resolve_model("fast") == "deepseek-v4:flash"
    assert mod._resolve_model("deep") == "deepseek-v4:pro"


def test_future_meta_records_resolved_model(stub_st, monkeypatch):
    """`_FUTURE_META[key]` carries the resolved model so the audit
    trail can see which tier was actually used (post-resolution,
    after the env-var chain). Pin it for forensic clarity."""
    import aml_framework.dashboard.section_explainer as mod

    monkeypatch.setenv("AML_OLLAMA_MODEL_FAST", "fast-tier-foo")

    with (
        mock.patch.object(mod, "_do_llm_call", return_value=_fake_reply()),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
            complexity="fast",
        )
        key = mod._cache_key("P", "s", None, mod._data_hash({"v": 1}))
        # Read meta BEFORE wait_for_future drains it.
        meta = mod._FUTURE_META.get(key, {}).copy()
    assert meta.get("complexity") == "fast"
    assert meta.get("model") == "fast-tier-foo"
    assert meta.get("section_title") == "t"
