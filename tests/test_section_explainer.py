"""Tests for `dashboard.section_explainer`.

The helper renders a Streamlit popover with an "Explain this section"
button. Because Streamlit must be loaded to test the actual render
path, these tests use a stub `streamlit` module rather than the real
one — sufficient to assert the rendering plumbing + cache + audit hook
without spinning up a dashboard.
"""

from __future__ import annotations

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


class _StubStreamlit:
    """Minimal stand-in for `streamlit` that records calls."""

    def __init__(self):
        self.session_state: dict = {}
        self.markdown_calls: list = []
        self.caption_calls: list = []
        self.container_calls: list = []
        self.spinner_calls: list = []

    # Container (context manager) — inline rendering, no expander chrome.
    def container(self, **kwargs):
        self.container_calls.append(kwargs)
        return _StubBlock("container", **kwargs)

    # Spinner (context manager).
    def spinner(self, label, **kwargs):
        self.spinner_calls.append((label, kwargs))
        return _StubBlock(label, **kwargs)

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
    the very first render (no button click, no env flag)."""
    from aml_framework.dashboard import section_explainer as mod

    # Make sure no env flag is set — we're testing the always-on default.
    monkeypatch.delenv("AML_AUTO_EXPLAIN", raising=False)

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
    assert get_assistant.call_count == 1, "backend must auto-fire on first render"
    assert fake_assistant.reply.call_count == 1


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


def test_first_render_fires_backend_then_caches(stub_st, monkeypatch):
    """First render → backend call + cache write. Second render with
    identical data_summary → cache hit (no second backend call)."""
    from aml_framework.dashboard import section_explainer as mod

    fake_assistant = SimpleNamespace(reply=mock.MagicMock(return_value=_fake_reply()))

    with (
        mock.patch.object(mod, "_log_to_audit"),
        mock.patch(
            "aml_framework.assistant.factory.get_assistant", return_value=fake_assistant
        ) as get_assistant,
    ):
        mod.section_explainer(
            page="Executive Dashboard",
            section_id="exec.kpis.headline",
            section_title="Top KPIs",
            data_summary={"alert_total": 12},
        )
        assert get_assistant.call_count == 1
        assert fake_assistant.reply.call_count == 1

        # Second invocation with the same data: should NOT call backend
        # because the cached reply is returned early.
        get_assistant.reset_mock()
        fake_assistant.reply.reset_mock()
        mod.section_explainer(
            page="Executive Dashboard",
            section_id="exec.kpis.headline",
            section_title="Top KPIs",
            data_summary={"alert_total": 12},
        )
        assert get_assistant.call_count == 0
        assert fake_assistant.reply.call_count == 0


def test_data_change_invalidates_cache(stub_st, monkeypatch):
    """Same (page, section_id, persona) but a different data hash →
    fresh backend call. The cache key includes a SHA-256 of the data
    summary, so filter changes (which alter the row counts a page
    feeds in) invalidate cleanly."""
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
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 2},  # different value → different hash
        )
        assert fake_assistant.reply.call_count == 2


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

    fake_assistant = SimpleNamespace(reply=mock.MagicMock(return_value=_fake_reply()))
    with (
        mock.patch(
            "aml_framework.engine.audit.AuditLedger.append_to_run_dir", side_effect=fake_append
        ),
        mock.patch("aml_framework.assistant.factory.get_assistant", return_value=fake_assistant),
    ):
        mod.section_explainer(
            page="P",
            section_id="s",
            section_title="t",
            data_summary={"v": 1},
        )

    assert captured["row"]["event"] == "ai_section_explanation"
    assert captured["row"]["section_id"] == "s"
    assert captured["row"]["section_title"] == "t"
    assert captured["jsonl_name"] == "ai_interactions.jsonl"


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


def test_backend_error_falls_back_to_template(stub_st, monkeypatch):
    """If the configured backend (e.g. ollama) raises, the helper
    falls back to TemplateBackend so the popover still shows
    something — never re-raise."""
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
    # And the reply was cached, so a subsequent click renders without
    # hitting the backend again.
    assert any("DRAFT" in m or "review" in m for m in stub_st.markdown_calls)


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


def test_cache_hit_short_circuits_render(stub_st):
    """When the cache already has a reply for this
    (section_id, data_hash, persona) triplet, the helper renders the
    cached reply inline and does NOT call the backend or show the
    spinner. Pin that filter-state stability across reruns is free."""
    from aml_framework.dashboard import section_explainer as mod

    # Seed the cache.
    reply = _fake_reply()
    stub_st.session_state["section_explanations"] = {
        ("P", "s", "", mod._data_hash({"v": 1})): reply
    }

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
