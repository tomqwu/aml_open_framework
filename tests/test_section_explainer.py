"""Tests for `dashboard.section_explainer`.

The helper renders an inline `st.container()` followed by a markdown
header, a spinner, the LLM reply, and an audit-log entry. Because
Streamlit must be loaded to test the actual render path, these tests
use a stub `streamlit` module rather than the real one — sufficient to
assert the rendering plumbing + cache + audit hook without spinning up
a dashboard.

`section_explainer.py` does `import streamlit as st` at module top, so
importing it requires `streamlit` (or the test fixture's stub) to be
available in `sys.modules`. The unit-tests CI job installs only the
`[dev]` extras (no streamlit). Skip the whole file there — the same
suite re-runs under the `coverage` + `api-tests` jobs which DO install
`[dashboard]` extras and exercise these assertions.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping
from types import SimpleNamespace
from unittest import mock

import pytest

if importlib.util.find_spec("streamlit") is None:
    pytest.skip(
        "streamlit not installed (unit-tests CI installs only [dev]); "
        "section_explainer tests run under the coverage + api-tests jobs",
        allow_module_level=True,
    )


class _StubBlock:
    """Context-manager double for `st.container(...)` / `st.spinner(...)`."""

    def __init__(self, label: str, **kwargs):
        self.label = label
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _StubStreamlit:
    """Minimal stand-in for `streamlit` that records calls."""

    def __init__(self):
        self.session_state: dict = {}
        self.markdown_calls: list = []
        self.caption_calls: list = []
        self.container_calls: list = []
        self.spinner_calls: list = []
        self.error_calls: list = []

    def container(self, **kwargs):
        self.container_calls.append(kwargs)
        return _StubBlock("container", **kwargs)

    def spinner(self, label, **kwargs):
        self.spinner_calls.append((label, kwargs))
        return _StubBlock(label, **kwargs)

    def markdown(self, text, **kwargs):
        self.markdown_calls.append(text)

    def caption(self, text, **kwargs):
        self.caption_calls.append(text)

    def error(self, text, **kwargs):
        self.error_calls.append(text)

    def toast(self, *_a, **_kw):
        pass

    def fragment(self, *_a, **_kw):
        # No-op decorator factory: @st.fragment(run_every=...) → identity.
        def _wrap(fn):
            return fn

        return _wrap

    def rerun(self, *_a, **_kw):
        self.rerun_calls = getattr(self, "rerun_calls", 0) + 1


class _SyncExecutor:
    """Drop-in for the section_explainer ThreadPoolExecutor that runs
    the submitted callable inline and returns an already-resolved
    Future. Makes the async dispatch deterministic in unit tests —
    after `section_explainer` submits, the future is immediately
    `.done()` so `_promote_resolved()` drains it on the next call."""

    def submit(self, fn, *args, **kwargs):
        import concurrent.futures

        fut: concurrent.futures.Future = concurrent.futures.Future()
        try:
            fut.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001
            fut.set_exception(exc)
        return fut


def _sync_exec(mod):
    """Context-manager patching `_get_executor` to the synchronous
    executor for deterministic tests."""
    return mock.patch.object(mod, "_get_executor", return_value=_SyncExecutor())


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
    """The section_explainer cache is process-global so it survives
    across Streamlit sessions in a deployed dashboard. For tests we
    clear it before each case so cross-test pollution doesn't fake a
    pass via a cache hit from a prior test."""
    import aml_framework.dashboard.section_explainer as mod

    mod._PROCESS_CACHE.clear()
    mod._FUTURES.clear()
    mod._FUTURE_META.clear()
    mod._FAILED.clear()
    yield
    mod._PROCESS_CACHE.clear()
    mod._FUTURES.clear()
    mod._FUTURE_META.clear()
    mod._FAILED.clear()


def _fake_reply(text="ok", confidence="high"):
    from aml_framework.assistant.models import AssistantReply

    return AssistantReply(
        text=text,
        confidence=confidence,
        backend="template:v1",
        prompted_with_page="Executive Dashboard",
    )


# ---------------------------------------------------------------------------
# Render path
# ---------------------------------------------------------------------------


def test_renders_inline_container_with_header(stub_st):
    """The explainer renders inline via `st.container()` plus a
    `##### ℹ <title> — AI Explanation` markdown header. No expander."""
    from aml_framework.dashboard.section_explainer import section_explainer

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
    headers = [m for m in stub_st.markdown_calls if "Top KPIs" in m and "AI Explanation" in m]
    assert headers, (
        "expected `##### ℹ <title> — AI Explanation` markdown header inside "
        f"the container. Markdown calls were: {stub_st.markdown_calls!r}"
    )


def test_auto_fires_backend_on_first_render(stub_st, monkeypatch):
    """First render DISPATCHES the LLM call to the background pool (no
    button, no env flag, no blocking spinner) and renders a
    non-blocking placeholder. The backend runs exactly once for the
    dispatched future; the reply lands via `_promote_resolved`."""
    from aml_framework.dashboard import section_explainer as mod

    call_backend = mock.MagicMock(return_value=_fake_reply())
    with (
        _sync_exec(mod),
        mock.patch.object(mod, "_call_backend", side_effect=call_backend),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
        # First paint: future submitted, placeholder shown, NOT blocked.
        assert any("Generating explanation" in c for c in stub_st.caption_calls)
        assert mod.section_explainer_has_pending()
        # Backend ran once (on the sync-executor submit).
        assert call_backend.call_count == 1
        # Poller drains → cache; second render shows the reply.
        mod._promote_resolved()
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
        assert call_backend.call_count == 1, "backend must not re-fire after cache populated"
        assert not mod.section_explainer_has_pending()


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


def test_first_render_fires_backend_then_caches(stub_st):
    """First render → backend call → cache write. Second render with
    identical data_summary → cache hit (no additional backend call)."""
    from aml_framework.dashboard import section_explainer as mod

    call_backend = mock.MagicMock(return_value=_fake_reply())
    with (
        _sync_exec(mod),
        mock.patch.object(mod, "_call_backend", side_effect=call_backend),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        se = dict(
            page="Executive Dashboard",
            section_id="exec.kpis.headline",
            section_title="Top KPIs",
            data_summary={"alert_total": 12},
        )
        mod.section_explainer(**se)
        mod._promote_resolved()
        key = mod._cache_key(
            "Executive Dashboard", "exec.kpis.headline", None, mod._data_hash({"alert_total": 12})
        )
        assert key in mod._PROCESS_CACHE
        assert call_backend.call_count == 1

        call_backend.reset_mock()
        mod.section_explainer(**se)
        assert call_backend.call_count == 0


def test_data_change_invalidates_cache(stub_st):
    """Same (page, section_id, persona) but a different data hash →
    fresh backend call. The cache key includes a SHA-256 of the data
    summary, so filter changes invalidate cleanly."""
    from aml_framework.dashboard import section_explainer as mod

    call_backend = mock.MagicMock(return_value=_fake_reply())
    with (
        _sync_exec(mod),
        mock.patch.object(mod, "_call_backend", side_effect=call_backend),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        # Two distinct data hashes → two distinct keys → two dispatches.
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 2})
    assert call_backend.call_count == 2


def test_cache_survives_across_sessions(monkeypatch):
    """The cache is process-global, not session-scoped — so the SAME
    data summary on a NEW Streamlit session hits the cached reply
    populated by an earlier session."""
    import aml_framework.dashboard.section_explainer as mod

    stub_a = _StubStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", stub_a)
    monkeypatch.setattr(mod, "st", stub_a)
    call_a = mock.MagicMock(return_value=_fake_reply())
    with (
        _sync_exec(mod),
        mock.patch.object(mod, "_call_backend", side_effect=call_a),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
        mod._promote_resolved()  # session A's poller promotes into the shared cache
        assert call_a.call_count == 1, "first session fires the LLM call"

    stub_b = _StubStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", stub_b)
    monkeypatch.setattr(mod, "st", stub_b)
    call_b = mock.MagicMock(return_value=_fake_reply())
    with (
        _sync_exec(mod),
        mock.patch.object(mod, "_call_backend", side_effect=call_b),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
    assert call_b.call_count == 0, (
        "second session with same data should hit the process cache, not the backend"
    )


def test_cache_hit_short_circuits_render(stub_st):
    """When the cache already has a reply for this
    (section_id, data_hash, persona) triplet, the helper renders the
    cached reply inline and does NOT call the backend or show the
    spinner."""
    from aml_framework.dashboard import section_explainer as mod

    reply = _fake_reply()
    mod._PROCESS_CACHE[("P", "s", "", mod._data_hash({"v": 1}))] = reply

    fake_assistant = SimpleNamespace(reply=mock.MagicMock(return_value=_fake_reply()))
    with (
        mock.patch.object(mod, "_log_to_audit"),
        mock.patch(
            "aml_framework.assistant.factory.get_assistant", return_value=fake_assistant
        ) as get_assistant,
    ):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
    assert get_assistant.call_count == 0
    assert fake_assistant.reply.call_count == 0
    assert not stub_st.spinner_calls


# ---------------------------------------------------------------------------
# Audit hook
# ---------------------------------------------------------------------------


def test_audit_log_event_is_distinct(stub_st):
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

    with (
        _sync_exec(mod),
        mock.patch.object(mod, "_call_backend", return_value=_fake_reply()),
        mock.patch(
            "aml_framework.engine.audit.AuditLedger.append_to_run_dir", side_effect=fake_append
        ),
    ):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
        # Audit fires at promotion (the single audit point), not at dispatch.
        mod._promote_resolved()

    assert captured["row"]["event"] == "ai_section_explanation"
    assert captured["row"]["section_id"] == "s"
    assert captured["row"]["section_title"] == "t"
    assert captured["jsonl_name"] == "ai_interactions.jsonl"


# ---------------------------------------------------------------------------
# Async poller
# ---------------------------------------------------------------------------


def test_cache_hit_spawns_no_thread(stub_st):
    """A cached section must render with zero background work — no
    executor, no future. This is the <1ms fast path; regressing it
    would make every revisit pay thread-pool overhead."""
    from aml_framework.dashboard import section_explainer as mod

    reply = _fake_reply()
    mod._PROCESS_CACHE[("P", "s", "", mod._data_hash({"v": 1}))] = reply

    with mock.patch.object(mod, "_get_executor", side_effect=AssertionError("executor used")):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
    assert not mod.section_explainer_has_pending()
    assert not stub_st.error_calls


def test_promote_resolved_audits_exactly_once(stub_st):
    """`_promote_resolved` is the single audit point. Draining a future
    logs the reply once; a second drain (idempotent) must NOT re-log —
    the future was already popped."""
    from aml_framework.dashboard import section_explainer as mod

    audit = mock.MagicMock()
    with (
        _sync_exec(mod),
        mock.patch.object(mod, "_call_backend", return_value=_fake_reply()),
        mock.patch.object(mod, "_log_to_audit", side_effect=audit),
    ):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
        assert mod._promote_resolved() is True
        assert mod._promote_resolved() is False  # nothing left to drain
    assert audit.call_count == 1, "reply must be audited exactly once"


def test_audit_attributed_to_dispatching_session_run_dir(stub_st):
    """The audit entry must land in the run_dir of the session that
    ASKED, not whichever session's poller drains the future. run_dir is
    per-session `st.session_state`; any replica poller can drain any
    global future. We snapshot run_dir at dispatch into `_FUTURE_META`
    and pass it explicitly to `_log_to_audit`. Simulate: dispatch with
    session A's run_dir, then a different session (run_dir B) drains."""
    from aml_framework.dashboard import section_explainer as mod

    captured: dict = {}

    def fake_log(reply, *, section_id, section_title, run_dir=None, audit_mode=None):
        captured["run_dir"] = run_dir

    stub_st.session_state["run_dir"] = "/runs/session-A"
    stub_st.session_state["spec"] = SimpleNamespace(
        program=SimpleNamespace(ai_audit_log="hash_only")
    )
    with (
        _sync_exec(mod),
        mock.patch.object(mod, "_call_backend", return_value=_fake_reply()),
        mock.patch.object(mod, "_log_to_audit", side_effect=fake_log),
    ):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
        # A different session drains (its state points elsewhere).
        stub_st.session_state["run_dir"] = "/runs/session-B"
        mod._promote_resolved()

    assert captured["run_dir"] == "/runs/session-A", (
        "audit must use the dispatch-time run_dir of the asking session, "
        f"not the draining session's; got {captured['run_dir']!r}"
    )


def test_promote_resolved_routes_exception_to_failed(stub_st):
    """A worker exception is captured into `_FAILED` (not cached, not
    success-audited). It IS recorded as a distinct failure audit event
    — a compliance framework must prove the AI was *asked* and did not
    answer, not just log successes. The key is removed from `_FUTURES`
    so the poller stops re-promoting it."""
    from aml_framework.dashboard import section_explainer as mod

    success_audit = mock.MagicMock()
    failure_audit = mock.MagicMock()
    with (
        _sync_exec(mod),
        mock.patch.object(mod, "_call_backend", side_effect=RuntimeError("model 'x' not found")),
        mock.patch.object(mod, "_log_to_audit", side_effect=success_audit),
        mock.patch.object(mod, "_log_failure_to_audit", side_effect=failure_audit),
    ):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
        mod._promote_resolved()
    key = mod._cache_key("P", "s", None, mod._data_hash({"v": 1}))
    assert key in mod._FAILED
    assert key not in mod._PROCESS_CACHE
    assert not mod.section_explainer_has_pending()
    # Success audit NOT called; failure audit called exactly once with
    # the section + the underlying error.
    assert success_audit.call_count == 0
    assert failure_audit.call_count == 1
    _, kw = failure_audit.call_args
    assert kw["section_id"] == "s"
    assert "model 'x' not found" in str(failure_audit.call_args[0][0])


def test_failure_audit_row_shape(stub_st):
    """`_log_failure_to_audit` writes a row with the distinct event,
    an `error_type` class field separate from the `error` message
    (so an auditor can filter CancelledError/TimeoutError/API errors
    without substring-matching), the section, backend and model. This
    is the compliance contract Codex flagged."""
    from aml_framework.dashboard import section_explainer as mod

    captured: dict = {}

    def fake_append(_run_dir, row, jsonl_name=None):
        captured["row"] = row
        captured["jsonl"] = jsonl_name

    with mock.patch(
        "aml_framework.engine.audit.AuditLedger.append_to_run_dir", side_effect=fake_append
    ):
        mod._log_failure_to_audit(
            TimeoutError("ollama timed out after 60s"),
            section_id="exec.kpis",
            section_title="Top KPIs",
            run_dir="/runs/session-A",
            backend="ollama",
            model="deepseek-v4-pro",
        )

    row = captured["row"]
    assert row["event"] == "ai_section_explanation_failed"
    assert row["section_id"] == "exec.kpis"
    assert row["error_type"] == "TimeoutError"
    assert "ollama timed out" in row["error"]
    assert row["backend"] == "ollama"
    assert row["model"] == "deepseek-v4-pro"
    assert captured["jsonl"] == "ai_interactions.jsonl"


def test_failure_audit_noop_without_run_dir(stub_st):
    """No run_dir (e.g. dispatched before the engine initialised) →
    no write attempt, no crash. Best-effort, page never breaks."""
    from aml_framework.dashboard import section_explainer as mod

    with mock.patch(
        "aml_framework.engine.audit.AuditLedger.append_to_run_dir",
        side_effect=AssertionError("must not write without run_dir"),
    ):
        mod._log_failure_to_audit(
            RuntimeError("x"),
            section_id="s",
            section_title="t",
            run_dir=None,
            backend="ollama",
            model="m",
        )  # no exception = pass


# NOTE: `render_explainer_poller` itself is a 2-line `@st.fragment`
# wrapper (`if _promote_resolved(): st.rerun()`). Streamlit's real
# fragment decorator no-ops the body outside a script-run context, so
# it can't be exercised in unit tests — it carries a `# pragma: no
# cover`. All of its logic lives in `_promote_resolved`, covered
# above (audit-once, exception→_FAILED, idempotent re-drain).


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


def test_backend_error_surfaces_no_silent_template(stub_st):
    """When the configured backend (e.g. ollama) raises, the helper
    must render an `st.error(...)` with the underlying message — NOT
    silently fall back to TemplateBackend. Caching a template reply on
    failure used to mask auth/model bugs by making the panel look like
    it was working on ollama when it wasn't."""
    from aml_framework.dashboard import section_explainer as mod

    with (
        _sync_exec(mod),
        mock.patch.object(mod, "_log_to_audit"),
        mock.patch(
            "aml_framework.assistant.factory.get_assistant",
            side_effect=RuntimeError("ollama down"),
        ),
    ):
        # Dispatch (sync executor runs the failing call into the future).
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
        # Poller moves the exception into _FAILED (NOT a cached template).
        mod._promote_resolved()
        # Next render surfaces the real error banner.
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
    assert any("ollama down" in e for e in stub_st.error_calls)
    # No template reply should have been cached as a fake success.
    assert mod._cache_key("P", "s", None, mod._data_hash({"v": 1})) not in mod._PROCESS_CACHE
    # _FAILED cleared after surfacing so a later navigation can retry.
    assert mod._cache_key("P", "s", None, mod._data_hash({"v": 1})) not in mod._FAILED


def test_missing_api_key_surfaces_error(stub_st, monkeypatch):
    """OLLAMA_API_KEY unset + AML_AI_BACKEND=ollama → factory raises;
    helper must surface the error rather than propagate. No exception
    escapes the section_explainer call (host page keeps rendering)."""
    from aml_framework.dashboard import section_explainer as mod

    monkeypatch.setenv("AML_AI_BACKEND", "ollama")
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

    with _sync_exec(mod), mock.patch.object(mod, "_log_to_audit"):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
        mod._promote_resolved()
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
    assert stub_st.error_calls, "expected st.error to surface the backend failure"


def test_error_banner_when_outer_failure(stub_st):
    """If something in the helper's body raises (e.g. backend call
    fails or hashing breaks), the host page must not crash — instead
    a visible `st.error(...)` banner with the actual exception text
    is rendered so the operator can diagnose."""
    from aml_framework.dashboard import section_explainer as mod

    with mock.patch.object(mod, "_data_hash", side_effect=RuntimeError("boom")):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
    assert any("boom" in e for e in stub_st.error_calls)


# ---------------------------------------------------------------------------
# Helper internals
# ---------------------------------------------------------------------------


def test_data_hash_stable_for_same_dict():
    from aml_framework.dashboard.section_explainer import _data_hash

    a = _data_hash({"x": 1, "y": 2})
    b = _data_hash({"y": 2, "x": 1})
    assert a == b


def test_data_hash_changes_with_values():
    from aml_framework.dashboard.section_explainer import _data_hash

    assert _data_hash({"x": 1}) != _data_hash({"x": 2})


def test_data_hash_tolerates_non_json_native_types():
    """Pandas / numpy scalars must not crash the hash function —
    `default=str` fallback."""
    from aml_framework.dashboard.section_explainer import _data_hash

    class Weird:
        def __repr__(self):
            return "weird-thing"

    assert _data_hash({"x": Weird()})


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
# Coverage-gap closers
# ---------------------------------------------------------------------------


def test_persona_caption_renders_when_persona_set(stub_st):
    """When `selected_audience` is set, the explainer shows a `Tailored
    for persona: <p>` caption."""
    from aml_framework.dashboard.section_explainer import section_explainer

    stub_st.session_state["selected_audience"] = "cco"
    fake_assistant = SimpleNamespace(reply=mock.MagicMock(return_value=_fake_reply()))
    with (
        mock.patch("aml_framework.dashboard.section_explainer._log_to_audit"),
        mock.patch("aml_framework.assistant.factory.get_assistant", return_value=fake_assistant),
    ):
        section_explainer(
            page="Executive Dashboard",
            section_id="exec.kpis",
            section_title="KPIs",
            data_summary={"v": 1},
        )
    assert any("cco" in c for c in stub_st.caption_calls)


def test_log_to_audit_skips_when_no_run_dir(stub_st):
    """The audit hook short-circuits when `run_dir` isn't in
    session_state."""
    from aml_framework.dashboard.section_explainer import _log_to_audit

    stub_st.session_state.pop("run_dir", None)
    _log_to_audit(object(), section_id="s", section_title="t")


def test_explicit_none_run_dir_does_not_fall_back_to_session(stub_st):
    """Codex compliance race: `_promote_resolved` passes the dispatch
    snapshot explicitly. If the snapshot had no run_dir it passes
    `run_dir=None` — `_log_to_audit` must NOT then fall back to the
    CURRENT (draining) session's run_dir (that would mis-attribute the
    audit row to the wrong run). Explicit None → warn + drop. Omitted
    (`_UNSET`) → fall back (direct sync callers). This test pins the
    sentinel distinction."""
    from aml_framework.dashboard import section_explainer as mod

    # The draining session HAS a run_dir — the explicit-None call must
    # ignore it, not write there.
    stub_st.session_state["run_dir"] = "/runs/WRONG-draining-session"
    stub_st.session_state["spec"] = SimpleNamespace(
        program=SimpleNamespace(ai_audit_log="hash_only")
    )
    wrote: list = []
    with mock.patch(
        "aml_framework.engine.audit.AuditLedger.append_to_run_dir",
        side_effect=lambda *a, **k: wrote.append((a, k)),
    ):
        # Explicit None (simulates a None dispatch snapshot).
        mod._log_to_audit(_fake_reply(), section_id="s", section_title="t", run_dir=None)
        assert wrote == [], (
            "explicit run_dir=None must NOT fall back to the draining "
            f"session — would mis-attribute; wrote: {wrote!r}"
        )
        # Omitted → _UNSET → DOES fall back to the current session.
        mod._log_to_audit(_fake_reply(), section_id="s", section_title="t")
        assert len(wrote) == 1, "omitted run_dir must fall back to session state"
        assert "WRONG-draining-session" in str(wrote[0][0][0])


def test_concurrent_dispatch_shares_one_future(stub_st):
    """Codex race: the `key not in _FUTURES` check + submit + publish
    must be atomic under `_DRAIN_LOCK`. Two `section_explainer` calls
    for the same key (same data) must result in exactly ONE future /
    ONE backend submission — never two, where the second publish
    orphans the first (an untracked, never-audited backend call)."""
    from aml_framework.dashboard import section_explainer as mod

    submits: list = []

    class _CountingExecutor:
        def submit(self, fn, *a, **kw):
            import concurrent.futures

            submits.append(1)
            f: concurrent.futures.Future = concurrent.futures.Future()
            f.set_result(_fake_reply())
            return f

    with (
        mock.patch.object(mod, "_get_executor", return_value=_CountingExecutor()),
        mock.patch.object(mod, "_call_backend", return_value=_fake_reply()),
    ):
        se = dict(page="P", section_id="s", section_title="t", data_summary={"v": 1})
        mod.section_explainer(**se)
        mod.section_explainer(**se)  # same key, before drain
    assert sum(submits) == 1, f"same key must dispatch exactly one backend call; got {sum(submits)}"
    assert len(mod._FUTURES) == 1


def test_log_to_audit_swallows_audit_ledger_failure(stub_st):
    """If `AuditLedger.append_to_run_dir` raises, the helper must
    swallow — never break the page."""
    from aml_framework.dashboard import section_explainer as mod

    stub_st.session_state["run_dir"] = "/tmp/fake_run_dir"
    stub_st.session_state["spec"] = SimpleNamespace(
        program=SimpleNamespace(ai_audit_log="hash_only")
    )

    with mock.patch(
        "aml_framework.engine.audit.AuditLedger.append_to_run_dir",
        side_effect=PermissionError("read-only"),
    ):
        mod._log_to_audit(_fake_reply(), section_id="s", section_title="t")


def test_error_fallback_also_swallows(monkeypatch):
    """The outermost try/except calls st.error() as the last-resort
    surface for backend failures. If that itself raises, we must not
    propagate — the host page is already rendered and a busted
    Streamlit primitive can't be allowed to abort the request."""
    import sys
    from aml_framework.dashboard import section_explainer as mod

    class _BadStreamlit:
        session_state = {}

        @staticmethod
        def container(*_a, **_kw):
            raise RuntimeError("context lost")

        @staticmethod
        def error(*_a, **_kw):
            raise RuntimeError("context also lost")

    monkeypatch.setitem(sys.modules, "streamlit", _BadStreamlit)
    monkeypatch.setattr(mod, "st", _BadStreamlit)
    mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})


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
    no section_id set."""
    from aml_framework.assistant.models import AssistantContext
    from aml_framework.assistant.ollama import _build_prompt

    ctx = AssistantContext(page="Run History")
    prompt = _build_prompt("How many runs?", ctx)
    assert "Section:" not in prompt


def test_ollama_build_prompt_truncates_oversized_section_data():
    """The builder truncates oversized section_data at ~2000 chars +
    appends '(truncated)' so context windows don't explode."""
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
# UX — non-blocking placeholder on first paint (NOT a blocking spinner)
# ---------------------------------------------------------------------------


def test_placeholder_renders_and_does_not_block(stub_st):
    """First paint must NOT use `st.spinner` (which blocks the whole
    script ~2-3 sec). It dispatches to the background pool and renders
    a lightweight non-blocking `st.caption` placeholder instead — the
    page stays interactive at t=0. This is the core 'do not make the
    user wait' contract."""
    from aml_framework.dashboard import section_explainer as mod

    fake_assistant = SimpleNamespace(reply=mock.MagicMock(return_value=_fake_reply()))

    with (
        _sync_exec(mod),
        mock.patch.object(mod, "_log_to_audit"),
        mock.patch("aml_framework.assistant.factory.get_assistant", return_value=fake_assistant),
    ):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})

    assert not stub_st.spinner_calls, "first paint must NOT block on st.spinner"
    assert any("Generating explanation" in c for c in stub_st.caption_calls), (
        "expected a non-blocking '⟳ Generating explanation…' caption placeholder"
    )


# ---------------------------------------------------------------------------
# Model routing — fast / deep tiers
# ---------------------------------------------------------------------------


def test_complexity_fast_uses_fast_model(stub_st, monkeypatch):
    """`complexity="fast"` (the default) picks `AML_OLLAMA_MODEL_FAST`
    when set."""
    import aml_framework.dashboard.section_explainer as mod

    monkeypatch.setenv("AML_OLLAMA_MODEL_FAST", "deepseek-v4:flash-override")
    monkeypatch.setenv("AML_OLLAMA_MODEL_DEEP", "deepseek-v4:pro")
    monkeypatch.delenv("AML_OLLAMA_MODEL", raising=False)

    captured = []

    def fake_call(*, question, context, backend_name, model):
        captured.append({"model": model})
        return _fake_reply()

    with (
        _sync_exec(mod),
        mock.patch.object(mod, "_call_backend", side_effect=fake_call),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
            complexity="fast",
        )
    assert captured[0]["model"] == "deepseek-v4:flash-override"


def test_complexity_deep_uses_deep_model(stub_st, monkeypatch):
    """`complexity="deep"` picks `AML_OLLAMA_MODEL_DEEP` — the heavier
    reasoning tier reserved for lineage / investigation pages."""
    import aml_framework.dashboard.section_explainer as mod

    monkeypatch.setenv("AML_OLLAMA_MODEL_FAST", "deepseek-v4:flash")
    monkeypatch.setenv("AML_OLLAMA_MODEL_DEEP", "deepseek-v4:pro-override")
    monkeypatch.delenv("AML_OLLAMA_MODEL", raising=False)

    captured = []

    def fake_call(*, question, context, backend_name, model):
        captured.append({"model": model})
        return _fake_reply()

    with (
        _sync_exec(mod),
        mock.patch.object(mod, "_call_backend", side_effect=fake_call),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
            complexity="deep",
        )
    assert captured[0]["model"] == "deepseek-v4:pro-override"


def test_resolve_model_falls_back_through_chain(monkeypatch):
    """Resolution chain: per-tier env → AML_OLLAMA_MODEL → hardcoded
    default."""
    import aml_framework.dashboard.section_explainer as mod

    monkeypatch.setenv("AML_OLLAMA_MODEL_FAST", "tier-fast")
    monkeypatch.setenv("AML_OLLAMA_MODEL", "global")
    assert mod._resolve_model("fast") == "tier-fast"

    monkeypatch.delenv("AML_OLLAMA_MODEL_FAST", raising=False)
    monkeypatch.delenv("AML_OLLAMA_MODEL_DEEP", raising=False)
    assert mod._resolve_model("fast") == "global"
    assert mod._resolve_model("deep") == "global"

    monkeypatch.delenv("AML_OLLAMA_MODEL", raising=False)
    # Tag separator is a HYPHEN — Ollama Cloud serves these as
    # `deepseek-v4-flash` / `deepseek-v4-pro`. The colon form
    # (`deepseek-v4:flash`) 404'd on the live endpoint; this
    # assertion is the regression guard for that bug.
    assert mod._resolve_model("fast") == "deepseek-v4-flash"
    assert mod._resolve_model("deep") == "deepseek-v4-pro"


def test_call_backend_passes_model_through_to_assistant(monkeypatch):
    """`_call_backend(model=...)` must thread the model kwarg into
    `get_assistant(backend_name, model=...)` — that's how per-tier
    routing actually reaches the Ollama client."""
    from aml_framework.dashboard import section_explainer as mod

    captured: dict = {}

    def fake_get_assistant(name, **kwargs):
        captured["name"] = name
        captured["kwargs"] = kwargs
        return SimpleNamespace(reply=lambda *_: _fake_reply())

    with mock.patch(
        "aml_framework.assistant.factory.get_assistant", side_effect=fake_get_assistant
    ):
        mod._call_backend(
            question="q",
            context=object(),
            backend_name="ollama",
            model="deepseek-v4:flash",
        )

    assert captured["name"] == "ollama"
    assert captured["kwargs"]["model"] == "deepseek-v4:flash"


def test_call_backend_does_not_pass_model_to_openai(monkeypatch):
    """`_resolve_model` reads `AML_OLLAMA_MODEL_*` env vars whose values
    name **ollama** models (e.g. `deepseek-v4:flash`). Threading that
    kwarg into OpenAIBackend would override `AML_OPENAI_MODEL` with an
    ollama model string, then the OpenAI API rejects the call with a
    400. The factory call must only forward `model=` when the backend
    is ollama; other backends pick their own model from their own env.
    """
    from aml_framework.dashboard import section_explainer as mod

    captured: dict = {}

    def fake_get_assistant(name, **kwargs):
        captured["name"] = name
        captured["kwargs"] = kwargs
        return SimpleNamespace(reply=lambda *_: _fake_reply())

    with mock.patch(
        "aml_framework.assistant.factory.get_assistant", side_effect=fake_get_assistant
    ):
        mod._call_backend(
            question="q",
            context=object(),
            backend_name="openai",
            model="deepseek-v4:flash",  # the ollama-tier resolution
        )

    assert captured["name"] == "openai"
    assert "model" not in captured["kwargs"], (
        f"openai backend must not receive the ollama model kwarg; got {captured['kwargs']!r}"
    )


def test_call_backend_does_not_pass_model_to_azure_openai(monkeypatch):
    """Azure OpenAI uses a deployment name (not a model name), so the
    ollama tier model must be filtered out for that backend too.
    """
    from aml_framework.dashboard import section_explainer as mod

    captured: dict = {}

    def fake_get_assistant(name, **kwargs):
        captured["name"] = name
        captured["kwargs"] = kwargs
        return SimpleNamespace(reply=lambda *_: _fake_reply())

    with mock.patch(
        "aml_framework.assistant.factory.get_assistant", side_effect=fake_get_assistant
    ):
        mod._call_backend(
            question="q",
            context=object(),
            backend_name="azure_openai",
            model="deepseek-v4:flash",
        )

    assert captured["name"] == "azure_openai"
    assert "model" not in captured["kwargs"]


def test_template_backend_accepts_model_kwarg_end_to_end(stub_st, monkeypatch):
    """With AML_AI_BACKEND=template (the default), section_explainer must
    still render a real reply — not an `st.error` banner. `_resolve_model`
    always returns a non-empty string and `_call_backend` always threads
    it through `get_assistant(name, model=...)`. If the template backend
    rejects the kwarg, every page on a vanilla dev install renders an
    error instead of the canned explanation.
    """
    from aml_framework.dashboard import section_explainer as mod

    monkeypatch.setenv("AML_AI_BACKEND", "template")
    with _sync_exec(mod), mock.patch.object(mod, "_log_to_audit"):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
        mod._promote_resolved()
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})

    # No error banner — the template backend handled the request.
    assert not stub_st.error_calls, f"template backend should not error; got: {stub_st.error_calls}"
    # And a reply was cached.
    assert mod._cache_key("P", "s", None, mod._data_hash({"v": 1})) in mod._PROCESS_CACHE
