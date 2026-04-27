"""Unit tests for the mobile-responsive overlay (issue #66).

The full e2e mobile suite (`test_e2e_dashboard_mobile.py`) needs
Playwright + a running Streamlit server. This file covers the
"CSS injected" + "responsive helper exists" invariants in a way
that runs on the minimal unit-test CI image — fast guard against
the CSS or helper being accidentally removed.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENTS_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "components.py"
APP_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "app.py"


# ---------------------------------------------------------------------------
# Source-level checks — no streamlit import required
# ---------------------------------------------------------------------------


class TestMobileCSSPresent:
    def test_components_file_has_768px_breakpoint(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "@media (max-width: 768px)" in body, (
            "Tablet/large-phone breakpoint missing from CUSTOM_CSS"
        )

    def test_components_file_has_480px_breakpoint(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "@media (max-width: 480px)" in body, "Phone breakpoint missing from CUSTOM_CSS"

    def test_columns_stack_rule_present(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # The rule that forces stHorizontalBlock to flex-direction: column
        # is the load-bearing change for mobile layouts.
        assert "stHorizontalBlock" in body
        assert "flex-direction: column" in body

    def test_touch_target_min_height_present(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # Apple HIG / Material Design 44px minimum.
        assert "min-height: 44px" in body, (
            "Touch-target min-height missing — buttons/inputs will be too small to tap"
        )

    def test_table_horizontal_scroll_guard_present(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "overflow-x: auto" in body, (
            "Table overflow rule missing — wide dataframes will blow out the page width"
        )

    def test_plotly_chart_max_height_present(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "stPlotlyChart" in body
        assert "max-height: 60vh" in body


# ---------------------------------------------------------------------------
# responsive_plotly_config helper
# ---------------------------------------------------------------------------


class TestResponsivePlotlyConfig:
    def test_components_module_exports_helper(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "def responsive_plotly_config" in body, (
            "responsive_plotly_config helper missing from components module"
        )

    def test_helper_returns_responsive_true(self):
        # Source-level static check — avoids importing the components
        # module here to keep the test pure (the helper is tiny and
        # importing pulls in pandas + plotly + streamlit, which we
        # don't want as a dependency of this unit test). The full
        # behavioral check happens in the e2e mobile suite.
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # Verify the helper body returns the two responsive flags.
        # Match the dict keys + values literally; if the helper is
        # ever rewritten to compute these dynamically the test should
        # be updated to import + call it.
        assert '"responsive": True' in body
        assert '"displayModeBar": False' in body


# ---------------------------------------------------------------------------
# app.py page-config check
# ---------------------------------------------------------------------------


class TestAppSidebarAuto:
    def test_initial_sidebar_state_is_auto(self):
        body = APP_FILE.read_text(encoding="utf-8")
        # "auto" lets Streamlit collapse the sidebar on small viewports.
        # "expanded" would defeat the mobile overlay.
        assert 'initial_sidebar_state="auto"' in body, (
            "app.py must set initial_sidebar_state='auto' for mobile-responsive "
            "behavior — 'expanded' hijacks the screen on phone viewports"
        )

    def test_no_explicit_expanded(self):
        body = APP_FILE.read_text(encoding="utf-8")
        # Defensive — catch a future regression where someone reverts to "expanded"
        # without removing the comment.
        assert 'initial_sidebar_state="expanded"' not in body
