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
# Responsive chart container — post PR-CHART-5 cleanup
# ---------------------------------------------------------------------------
# The Plotly-specific responsive_plotly_config() helper was removed
# alongside Plotly itself in PR-CHART-5. ECharts is responsive by
# default (the wrapper sets `height` and the chart auto-fits its
# container width). The mobile-CSS guard above (max-height: 60vh on
# stPlotlyChart) is preserved so any residual Plotly chart in
# downstream forks would still cap nicely.


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
