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
    yield
    mod._PROCESS_CACHE.clear()


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
    """The LLM call must invoke synchronously on the first render — no
    button, no env flag, no future to wait on."""
    from aml_framework.dashboard import section_explainer as mod

    call_backend = mock.MagicMock(return_value=_fake_reply())
    with (
        mock.patch.object(mod, "_call_backend", side_effect=call_backend),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
        )
    assert call_backend.call_count == 1, "backend must fire synchronously on first render"


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


def test_first_render_fires_backend_then_caches(stub_st):
    """First render → backend call → cache write. Second render with
    identical data_summary → cache hit (no additional backend call)."""
    from aml_framework.dashboard import section_explainer as mod

    call_backend = mock.MagicMock(return_value=_fake_reply())
    with (
        mock.patch.object(mod, "_call_backend", side_effect=call_backend),
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
        assert key in mod._PROCESS_CACHE
        assert call_backend.call_count == 1

        call_backend.reset_mock()
        mod.section_explainer(
            page="Executive Dashboard",
            section_id="exec.kpis.headline",
            section_title="Top KPIs",
            data_summary={"alert_total": 12},
        )
        assert call_backend.call_count == 0


def test_data_change_invalidates_cache(stub_st):
    """Same (page, section_id, persona) but a different data hash →
    fresh backend call. The cache key includes a SHA-256 of the data
    summary, so filter changes invalidate cleanly."""
    from aml_framework.dashboard import section_explainer as mod

    call_backend = mock.MagicMock(return_value=_fake_reply())
    with (
        mock.patch.object(mod, "_call_backend", side_effect=call_backend),
        mock.patch.object(mod, "_log_to_audit"),
    ):
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
        mock.patch.object(mod, "_call_backend", side_effect=call_a),
        mock.patch.object(mod, "_log_to_audit"),
    ):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
        assert call_a.call_count == 1, "first session fires the LLM call"

    stub_b = _StubStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", stub_b)
    monkeypatch.setattr(mod, "st", stub_b)
    call_b = mock.MagicMock(return_value=_fake_reply())
    with (
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
        mock.patch.object(mod, "_call_backend", return_value=_fake_reply()),
        mock.patch(
            "aml_framework.engine.audit.AuditLedger.append_to_run_dir", side_effect=fake_append
        ),
    ):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})

    assert captured["row"]["event"] == "ai_section_explanation"
    assert captured["row"]["section_id"] == "s"
    assert captured["row"]["section_title"] == "t"
    assert captured["jsonl_name"] == "ai_interactions.jsonl"


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
        mock.patch.object(mod, "_log_to_audit"),
        mock.patch(
            "aml_framework.assistant.factory.get_assistant",
            side_effect=RuntimeError("ollama down"),
        ),
    ):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
    # The error message must include the underlying exception text so
    # the operator can diagnose the failure.
    assert any("ollama down" in e for e in stub_st.error_calls)
    # No template reply should have been cached as a fake success.
    assert mod._cache_key("P", "s", None, mod._data_hash({"v": 1})) not in mod._PROCESS_CACHE


def test_missing_api_key_surfaces_error(stub_st, monkeypatch):
    """OLLAMA_API_KEY unset + AML_AI_BACKEND=ollama → factory raises;
    helper must surface the error rather than propagate. No exception
    escapes the section_explainer call (host page keeps rendering)."""
    from aml_framework.dashboard import section_explainer as mod

    monkeypatch.setenv("AML_AI_BACKEND", "ollama")
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

    with mock.patch.object(mod, "_log_to_audit"):
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
# UX — visible spinner during the LLM call
# ---------------------------------------------------------------------------


def test_spinner_renders_during_backend_call(stub_st):
    """The synchronous LLM call is wrapped in st.spinner so the page
    doesn't appear to hang. The spinner label names the backend so the
    operator can sanity-check what's running."""
    from aml_framework.dashboard import section_explainer as mod

    fake_assistant = SimpleNamespace(reply=mock.MagicMock(return_value=_fake_reply()))

    with (
        mock.patch.object(mod, "_log_to_audit"),
        mock.patch("aml_framework.assistant.factory.get_assistant", return_value=fake_assistant),
    ):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})
    assert stub_st.spinner_calls, "expected st.spinner() during the backend call"
    label, _ = stub_st.spinner_calls[0]
    assert "Generating explanation" in label
    assert "template" in label.lower() or "ollama" in label.lower()


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
    with mock.patch.object(mod, "_log_to_audit"):
        mod.section_explainer(page="P", section_id="s", section_title="t", data_summary={"v": 1})

    # No error banner — the template backend handled the request.
    assert not stub_st.error_calls, f"template backend should not error; got: {stub_st.error_calls}"
    # And a reply was cached.
    assert mod._cache_key("P", "s", None, mod._data_hash({"v": 1})) in mod._PROCESS_CACHE
