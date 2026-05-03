from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace


def _reload_with_streamlit(monkeypatch, module_name: str, streamlit):
    monkeypatch.setitem(sys.modules, "streamlit", streamlit)
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


class RaisingQueryParams(dict):
    def __contains__(self, key):
        raise RuntimeError("query params unavailable")

    def __setitem__(self, key, value):
        raise RuntimeError("query params unavailable")


class TestQueryParamRuntime:
    def test_read_prefers_url_then_session_then_default(self, monkeypatch):
        st = SimpleNamespace(
            query_params={"case_id": "CASE-1"}, session_state={"selected_case_id": "CASE-2"}
        )
        mod = _reload_with_streamlit(monkeypatch, "aml_framework.dashboard.query_params", st)

        assert mod.read_param("case_id", "fallback") == "CASE-1"
        assert mod.read_param("customer_id", "fallback") == "fallback"

    def test_read_falls_back_when_query_params_raise(self, monkeypatch):
        st = SimpleNamespace(
            query_params=RaisingQueryParams(),
            session_state={"selected_customer_id": "C-1"},
        )
        mod = _reload_with_streamlit(monkeypatch, "aml_framework.dashboard.query_params", st)

        assert mod.read_param("customer_id") == "C-1"

    def test_set_consume_and_clear_keep_session_mirror_consistent(self, monkeypatch):
        st = SimpleNamespace(query_params={}, session_state={})
        mod = _reload_with_streamlit(monkeypatch, "aml_framework.dashboard.query_params", st)

        mod.set_param("rule_id", "R-1")
        assert st.query_params["rule_id"] == "R-1"
        assert st.session_state["selected_rule_id"] == "R-1"
        assert mod.consume_param("rule_id") == "R-1"
        assert "selected_rule_id" not in st.session_state

        mod.set_param("metric_id", "M-1")
        mod.clear_param("metric_id")
        assert "metric_id" not in st.query_params
        assert "selected_metric_id" not in st.session_state

    def test_set_and_clear_tolerate_query_param_runtime_errors(self, monkeypatch):
        st = SimpleNamespace(
            query_params=RaisingQueryParams({"case_id": "CASE-1"}), session_state={}
        )
        mod = _reload_with_streamlit(monkeypatch, "aml_framework.dashboard.query_params", st)

        mod.set_param("case_id", "CASE-1")
        assert st.session_state["selected_case_id"] == "CASE-1"
        mod.clear_param("case_id")
        assert "selected_case_id" not in st.session_state


class FakeJsCode(str):
    pass


class FakeGridOptionsBuilder:
    last = None

    def __init__(self, columns):
        self.columns = columns
        self.calls = []

    @classmethod
    def from_dataframe(cls, df):
        cls.last = cls(list(df.columns))
        return cls.last

    def configure_default_column(self, **kwargs):
        self.calls.append(("default", kwargs))

    def configure_column(self, col, **kwargs):
        self.calls.append(("column", col, kwargs))

    def configure_pagination(self, **kwargs):
        self.calls.append(("pagination", kwargs))

    def configure_selection(self, **kwargs):
        self.calls.append(("selection", kwargs))

    def build(self):
        return {"columns": self.columns}


class FakeInputFrame:
    def __init__(self, columns):
        self.columns = columns


class FakeSelectedFrame:
    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self._rows


def _install_aggrid(monkeypatch, response):
    fake_aggrid = ModuleType("st_aggrid")

    def aggrid(*args, **kwargs):
        fake_aggrid.last_call = {"args": args, "kwargs": kwargs}
        return response

    fake_aggrid.AgGrid = aggrid
    fake_aggrid.GridOptionsBuilder = FakeGridOptionsBuilder
    fake_aggrid.JsCode = FakeJsCode
    monkeypatch.setitem(sys.modules, "st_aggrid", fake_aggrid)
    return fake_aggrid


class TestDataGridRuntime:
    def test_style_js_helpers_include_palette_and_thresholds(self):
        from aml_framework.dashboard.data_grid import _cell_style_js, _gradient_style_js

        js = _cell_style_js({"high": "#ff0000"})
        assert "'high': '#ff0000'" in js
        assert "backgroundColor" in js

        gradient = _gradient_style_js(low=0.25, high=0.75, invert=True)
        assert "v >= 0.75" in gradient
        assert "#dc2626" in gradient
        assert "#16a34a" in gradient

    def test_data_grid_configures_columns_and_returns_response(self, monkeypatch):
        response = {"selected_rows": []}
        fake_aggrid = _install_aggrid(monkeypatch, response)
        st = SimpleNamespace(
            captions=[], session_state={}, caption=lambda text: st.captions.append(text)
        )
        df = FakeInputFrame(columns=["severity", "rag", "risk", "score", "case_id"])

        mod = _reload_with_streamlit(monkeypatch, "aml_framework.dashboard.data_grid", st)
        result = mod.data_grid(
            df,
            key="cases",
            severity_col="severity",
            rag_col="rag",
            risk_col="risk",
            gradient_cols=["score", "missing"],
            palette_cols={"case_id": {"CASE-1": "#123456"}, "missing": {"x": "#000"}},
            pinned_left=["case_id", "missing"],
            pinned_right=["score"],
            drill_target="pages/17_Customer_360.py",
            drill_param="case_id",
            drill_column="case_id",
            hint="Case queue",
        )

        assert result is response
        assert st.captions == ["Case queue"]
        assert fake_aggrid.last_call["kwargs"]["allow_unsafe_jscode"] is True
        calls = FakeGridOptionsBuilder.last.calls
        configured_columns = [call[1] for call in calls if call[0] == "column"]
        assert configured_columns.count("severity") == 1
        assert configured_columns.count("rag") == 1
        assert configured_columns.count("risk") == 1
        assert configured_columns.count("score") >= 1
        assert ("selection", {"selection_mode": "single", "use_checkbox": False}) in calls

    def test_data_grid_drills_through_list_selection(self, monkeypatch):
        switched = []
        _install_aggrid(monkeypatch, {"selected_rows": [{"case_id": "CASE-42"}]})
        st = SimpleNamespace(
            session_state={},
            caption=lambda text: None,
            switch_page=lambda target: switched.append(target),
        )
        mod = _reload_with_streamlit(monkeypatch, "aml_framework.dashboard.data_grid", st)

        mod.data_grid(
            FakeInputFrame(columns=["case_id"]),
            key="cases",
            drill_target="pages/17_Customer_360.py",
            drill_param="case_id",
            drill_column="case_id",
        )

        assert st.session_state["selected_case_id"] == "CASE-42"
        assert switched == ["pages/17_Customer_360.py"]

    def test_data_grid_drills_through_dataframe_selection(self, monkeypatch):
        switched = []
        _install_aggrid(monkeypatch, {"selected_rows": FakeSelectedFrame([{"customer_id": "C-7"}])})
        st = SimpleNamespace(
            session_state={},
            caption=lambda text: None,
            switch_page=lambda target: switched.append(target),
        )
        mod = _reload_with_streamlit(monkeypatch, "aml_framework.dashboard.data_grid", st)

        mod.data_grid(
            FakeInputFrame(columns=["customer_id"]),
            key="customers",
            drill_target="pages/17_Customer_360.py",
            drill_param="customer_id",
            drill_column="customer_id",
        )

        assert st.session_state["selected_customer_id"] == "C-7"
        assert switched == ["pages/17_Customer_360.py"]
