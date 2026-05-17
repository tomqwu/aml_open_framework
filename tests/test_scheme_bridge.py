"""Unit tests for the client `prefers-color-scheme` bridge.

`dashboard/scheme.py` resolves the OS colour scheme into
session_state so canvas-rendered ECharts follows the SAME signal as
the dark CSS (`@media (prefers-color-scheme: dark)`) instead of
`st.context.theme` (which Codex flagged can desync). Streamlit must
be importable to test it, so use the stubbed-Streamlit pattern. This
file sorts after `test_dashboard_tuning_state.py` alphabetically
(test_s* > test_d*), so importing streamlit here doesn't trip that
file's "streamlit not yet imported" autouse fixture.
"""

from __future__ import annotations

import importlib.util
import sys

import pytest

if importlib.util.find_spec("streamlit") is None:
    pytest.skip(
        "streamlit not installed (unit-tests CI installs only [dev])",
        allow_module_level=True,
    )


class _StubQueryParams(dict):
    pass


class _StubComponentsV1:
    def __init__(self):
        self.html_calls: list = []

    def html(self, body, **kwargs):
        self.html_calls.append((body, kwargs))


class _StubStreamlit:
    def __init__(self):
        self.session_state: dict = {}
        self.query_params = _StubQueryParams()

        class _C:
            v1 = _StubComponentsV1()

        self.components = _C()


@pytest.fixture
def stub_st(monkeypatch):
    stub = _StubStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", stub)
    comps = type(sys)("streamlit.components")
    comps_v1 = stub.components.v1
    monkeypatch.setitem(sys.modules, "streamlit.components", comps)
    monkeypatch.setitem(sys.modules, "streamlit.components.v1", comps_v1)
    import aml_framework.dashboard.scheme as mod

    monkeypatch.setattr(mod, "st", stub)
    return stub


def test_defaults_to_light_before_any_report(stub_st):
    from aml_framework.dashboard import scheme as mod

    assert mod.current_color_scheme() == "light"


def test_query_param_dark_is_captured(stub_st):
    from aml_framework.dashboard import scheme as mod

    stub_st.query_params["_cs"] = "dark"
    mod.ensure_color_scheme_detected()
    assert stub_st.session_state["_color_scheme"] == "dark"
    assert mod.current_color_scheme() == "dark"


def test_query_param_light_is_captured(stub_st):
    from aml_framework.dashboard import scheme as mod

    stub_st.query_params["_cs"] = "light"
    mod.ensure_color_scheme_detected()
    assert mod.current_color_scheme() == "light"


def test_garbage_param_ignored_default_holds(stub_st):
    from aml_framework.dashboard import scheme as mod

    stub_st.query_params["_cs"] = "chartreuse"
    mod.ensure_color_scheme_detected()
    # Unrecognised value must not be stored; reader stays default.
    assert "_color_scheme" not in stub_st.session_state
    assert mod.current_color_scheme() == "light"


def test_bridge_html_injected_and_loop_safe(stub_st):
    from aml_framework.dashboard import scheme as mod

    mod.ensure_color_scheme_detected()
    calls = stub_st.components.v1.html_calls
    assert calls, "client bridge <script> must be injected"
    body, kwargs = calls[-1]
    assert kwargs.get("height") == 0  # invisible chrome
    assert "prefers-color-scheme" in body
    assert "matchMedia" in body
    # Reloads ONLY on mismatch (loop-safe), and must NOT strip the
    # param (stripping → re-add → infinite reload).
    assert "!== want" in body
    assert "searchParams.delete" not in body
    # Re-bridges on a live OS theme flip.
    assert "addEventListener('change'" in body
