"""Phase A — dashboard component helpers + query-param plumbing.

Source-level tests so they run on the unit-test CI image without
streamlit installed. The full rendering paths get covered by the
e2e-dashboard suite when Phase B/C wire these helpers into pages.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENTS_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "components.py"
QUERY_PARAMS_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "query_params.py"


# ---------------------------------------------------------------------------
# components.py — new helpers
# ---------------------------------------------------------------------------


class TestSeverityColorHelper:
    def test_function_exists(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "def severity_color" in body, "severity_color helper missing"

    def test_resolves_known_severities(self):
        # Source check — verify all 4 severities have entries in
        # SEVERITY_COLORS that severity_color reads from.
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        m = re.search(r"SEVERITY_COLORS\s*=\s*\{([^}]+)\}", body)
        assert m, "SEVERITY_COLORS dict not found"
        contents = m.group(1)
        for sev in ("critical", "high", "medium", "low"):
            assert f'"{sev}"' in contents, f"SEVERITY_COLORS missing {sev!r}"

    def test_falls_back_for_unknown(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # The fallback hex must be in the function body.
        m = re.search(
            r"def severity_color.*?return SEVERITY_COLORS\.get\(.*?,\s*\"#[0-9a-f]{6}\"\)",
            body,
            re.DOTALL,
        )
        assert m, "severity_color must have a hex fallback"


class TestSLABandColorHelper:
    def test_function_exists(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "def sla_band_color" in body, "sla_band_color helper missing"

    def test_constant_exists(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "SLA_BAND_COLORS" in body, "SLA_BAND_COLORS constant missing"

    def test_constant_covers_cases_sla_states(self):
        # The 4 states are defined in cases/sla.py: green / amber / red / breached.
        # Plus 'unknown' as the safe default.
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        m = re.search(r"SLA_BAND_COLORS\s*=\s*\{([^}]+)\}", body)
        assert m, "SLA_BAND_COLORS literal not found"
        contents = m.group(1)
        for state in ("green", "amber", "red", "breached", "unknown"):
            assert f'"{state}"' in contents, f"SLA_BAND_COLORS missing {state!r}"


class TestEmptyStateHelper:
    def test_function_exists(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "def empty_state" in body, "empty_state helper missing"

    def test_signature_supports_message_icon_detail_stop(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        m = re.search(r"def empty_state\((.*?)\)", body, re.DOTALL)
        assert m, "empty_state signature not parseable"
        sig = m.group(1)
        # All four documented args present.
        for arg in ("message", "icon", "detail", "stop"):
            assert arg in sig, f"empty_state missing arg {arg!r}"

    def test_calls_st_stop_only_when_stop_true(self):
        # Source-level grep: there's a conditional `if stop:` then `st.stop()`
        # — never an unconditional `st.stop()` inside empty_state.
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        m = re.search(r"def empty_state.*?(?=\n\ndef |\nclass )", body, re.DOTALL)
        assert m
        fn = m.group(0)
        assert "if stop" in fn
        assert "st.stop()" in fn


class TestLinkToPageHelper:
    def test_function_exists(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "def link_to_page" in body, "link_to_page helper missing"

    def test_uses_st_page_link(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        m = re.search(r"def link_to_page.*?(?=\n\ndef |\nclass |\Z)", body, re.DOTALL)
        assert m
        fn = m.group(0)
        assert "st.page_link" in fn, (
            "link_to_page must use st.page_link so it benefits from Streamlit's "
            "built-in page-routing rather than rendering a raw <a href>"
        )

    def test_mirrors_query_params_to_session_state(self):
        # Streamlit's st.page_link doesn't pass query params on navigation,
        # so the helper writes them to session_state under selected_<key>
        # so destination pages can read them via query_params.read_param().
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        m = re.search(r"def link_to_page.*?(?=\n\ndef |\nclass |\Z)", body, re.DOTALL)
        assert m
        fn = m.group(0)
        assert "session_state" in fn
        assert "selected_" in fn


# ---------------------------------------------------------------------------
# query_params.py — module exists + has the four documented functions
# ---------------------------------------------------------------------------


class TestQueryParamsModule:
    def test_module_exists(self):
        assert QUERY_PARAMS_FILE.exists(), f"query_params.py missing at {QUERY_PARAMS_FILE}"

    def test_exports_four_functions(self):
        body = QUERY_PARAMS_FILE.read_text(encoding="utf-8")
        for fname in ("read_param", "set_param", "consume_param", "clear_param"):
            assert f"def {fname}(" in body, f"query_params.py missing {fname!r}"

    def test_all_includes_four_functions(self):
        body = QUERY_PARAMS_FILE.read_text(encoding="utf-8")
        m = re.search(r"__all__\s*=\s*\[([^\]]+)\]", body)
        assert m, "__all__ not found"
        listed = m.group(1)
        for fname in ("read_param", "set_param", "consume_param", "clear_param"):
            assert f'"{fname}"' in listed, f"__all__ missing {fname!r}"

    def test_session_key_namespace_is_selected(self):
        # Convention from the plan: session_state[f"selected_{name}"]
        body = QUERY_PARAMS_FILE.read_text(encoding="utf-8")
        assert 'f"selected_{name}"' in body, (
            "query_params.py should namespace session-state mirrors as "
            "f'selected_{{name}}' to match link_to_page in components.py"
        )

    def test_read_param_falls_back_to_session_state(self):
        body = QUERY_PARAMS_FILE.read_text(encoding="utf-8")
        # The function should check query_params first, then session_state.
        m = re.search(r"def read_param.*?(?=\n\ndef |\Z)", body, re.DOTALL)
        assert m
        fn = m.group(0)
        assert "st.query_params" in fn
        assert "session_state" in fn

    def test_read_param_handles_query_params_exception(self):
        # Older Streamlit + edge runtime states can raise on query_params
        # access during reruns; the function should fall through, not crash.
        body = QUERY_PARAMS_FILE.read_text(encoding="utf-8")
        m = re.search(r"def read_param.*?(?=\n\ndef |\Z)", body, re.DOTALL)
        assert m
        fn = m.group(0)
        assert "try:" in fn and "except" in fn

    def test_consume_param_clears_session_state(self):
        body = QUERY_PARAMS_FILE.read_text(encoding="utf-8")
        m = re.search(r"def consume_param.*?(?=\n\ndef |\Z)", body, re.DOTALL)
        assert m
        fn = m.group(0)
        assert ".pop(" in fn, "consume_param must remove the session-state mirror"

    def test_clear_param_removes_url_param(self):
        body = QUERY_PARAMS_FILE.read_text(encoding="utf-8")
        m = re.search(r"def clear_param.*?(?=\n\ndef |\Z)", body, re.DOTALL)
        assert m
        fn = m.group(0)
        assert "del st.query_params" in fn or "st.query_params.pop" in fn


# ---------------------------------------------------------------------------
# Cross-module consistency
# ---------------------------------------------------------------------------


class TestNamespaceConsistency:
    def test_components_link_to_page_and_query_params_use_same_prefix(self):
        # Both write to / read from session_state under "selected_<name>".
        # Drift between them = silent broken deep links.
        comp_body = COMPONENTS_FILE.read_text(encoding="utf-8")
        qp_body = QUERY_PARAMS_FILE.read_text(encoding="utf-8")
        comp_m = re.search(r"def link_to_page.*?(?=\n\ndef |\nclass |\Z)", comp_body, re.DOTALL)
        assert comp_m
        # link_to_page writes selected_<key>; query_params reads selected_<name>.
        assert 'f"selected_{key}"' in comp_m.group(0)
        assert 'f"selected_{name}"' in qp_body
