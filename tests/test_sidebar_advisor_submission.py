"""Behavior tests for the sidebar advisor's submission handler.

`_handle_ai_submission` lives in `dashboard.components` next to
`ai_panel`. It's the function that fires when the operator clicks the
sidebar's `Ask` button. The contract here is small but failure-mode
sensitive — a stale reply rendered alongside a fresh error banner is
confusing at best, audit-noise at worst.

These tests run under the stubbed-Streamlit pattern (the same
`_StubStreamlit` shape used in `test_section_explainer`) because the
real `streamlit` runtime cannot be exercised in unit-test CI which only
installs `[dev]` extras.
"""

from __future__ import annotations

import importlib.util
from types import SimpleNamespace
from unittest import mock

import pytest

if importlib.util.find_spec("streamlit") is None:
    pytest.skip(
        "streamlit not installed (unit-tests CI installs only [dev]); "
        "ai_panel behavior tests run under the coverage + api-tests jobs",
        allow_module_level=True,
    )


class _StubStreamlit:
    def __init__(self):
        self.session_state: dict = {"ai_transcript": {}}
        self.error_calls: list = []
        self.toast_calls: list = []

    def error(self, text, **_kw):
        self.error_calls.append(text)

    def toast(self, text, **_kw):
        self.toast_calls.append(text)


@pytest.fixture
def stub_st(monkeypatch):
    """Patch only the `st` attribute on `dashboard.components`. We do
    NOT swap `sys.modules['streamlit']` because `components.py` imports
    enough of the dashboard package to drag a lot of transitive
    streamlit-touching code through; a global swap leaks the stub into
    other tests in the same session (notably `test_startup_log` reloads
    `dashboard.app` and ends up with our stub instead of real streamlit).
    The module-attribute patch is scoped + reverted by monkeypatch and
    suffices because `_handle_ai_submission` references `st` via the
    module global.
    """
    stub = _StubStreamlit()
    import aml_framework.dashboard.components as mod

    monkeypatch.setattr(mod, "st", stub)
    return stub


def _fake_reply(text="ok", confidence="high"):
    from aml_framework.assistant.models import AssistantReply

    return AssistantReply(
        text=text,
        confidence=confidence,
        backend="ollama:deepseek-v4:pro",
        prompted_with_page="Today",
    )


def test_handle_failure_clears_stale_transcript(stub_st):
    """If a previous question on this page succeeded, then a new
    question fails, the panel must not render the old reply alongside
    the new error banner — operators would otherwise mistake the
    successful prior reply for an answer to the (failed) new question.
    Contract: failure path removes any prior transcript entry for the
    page so only the `st.error` shows.
    """
    from aml_framework.dashboard import components as mod

    # Seed a previous successful reply for the page.
    stub_st.session_state["ai_transcript"]["Today"] = _fake_reply(text="prior reply")

    with mock.patch(
        "aml_framework.assistant.factory.get_assistant",
        side_effect=RuntimeError("ollama down"),
    ):
        mod._handle_ai_submission(page="Today", question="new q", backend_name="ollama")

    assert stub_st.error_calls, "expected st.error to surface the backend failure"
    assert "ollama down" in stub_st.error_calls[0]
    assert "Today" not in stub_st.session_state["ai_transcript"], (
        "failure path must drop the stale reply for this page so the panel "
        "doesn't render the prior answer below the error banner"
    )


def test_handle_success_writes_new_reply(stub_st):
    """Happy path: a successful reply lands in
    `session_state['ai_transcript'][page]`. Audit-log call may raise
    silently (no run_dir in test) but the transcript write must
    happen before the audit attempt.
    """
    from aml_framework.dashboard import components as mod

    fake_assistant = SimpleNamespace(reply=lambda *_: _fake_reply(text="fresh"))
    with mock.patch("aml_framework.assistant.factory.get_assistant", return_value=fake_assistant):
        mod._handle_ai_submission(page="Today", question="what's up", backend_name="ollama")

    stored = stub_st.session_state["ai_transcript"]["Today"]
    assert stored.text == "fresh"
    assert not stub_st.error_calls


def test_ollama_backend_receives_deep_model(stub_st):
    """When backend is ollama, `_handle_ai_submission` must thread the
    deep-tier model into `get_assistant(..., model=...)`. Without this,
    the sidebar falls back to `AML_OLLAMA_MODEL` (the legacy env), so
    the per-tier routing (PR #304) is silently bypassed for the
    advisor — which is the surface that benefits from Pro the most.
    """
    from aml_framework.dashboard import components as mod

    captured: dict = {}

    def fake_get_assistant(name, **kwargs):
        captured["name"] = name
        captured["kwargs"] = kwargs
        return SimpleNamespace(reply=lambda *_: _fake_reply())

    with mock.patch(
        "aml_framework.assistant.factory.get_assistant", side_effect=fake_get_assistant
    ):
        mod._handle_ai_submission(page="Today", question="q", backend_name="ollama")

    assert captured["name"] == "ollama"
    assert "model" in captured["kwargs"], (
        "ollama backend must receive the resolved deep-tier model kwarg"
    )


def test_openai_backend_does_not_receive_ollama_model(stub_st):
    """`_resolve_model("deep")` returns an ollama model string
    (`deepseek-v4:pro` by default). Passing it as `model=` to
    OpenAIBackend overrides `AML_OPENAI_MODEL` with that string and
    the OpenAI API rejects it with a 400. Contract: when backend is
    openai, no `model=` kwarg is forwarded — OpenAI picks its model
    from its own env in its constructor.
    """
    from aml_framework.dashboard import components as mod

    captured: dict = {}

    def fake_get_assistant(name, **kwargs):
        captured["name"] = name
        captured["kwargs"] = kwargs
        return SimpleNamespace(reply=lambda *_: _fake_reply())

    with mock.patch(
        "aml_framework.assistant.factory.get_assistant", side_effect=fake_get_assistant
    ):
        mod._handle_ai_submission(page="Today", question="q", backend_name="openai")

    assert captured["name"] == "openai"
    assert "model" not in captured["kwargs"], (
        f"openai backend must not receive an ollama-tier model kwarg; got {captured['kwargs']!r}"
    )
