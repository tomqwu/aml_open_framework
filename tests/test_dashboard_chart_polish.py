"""Source-level tests for PR-E: chart polish.

Five pages had charts using ad-hoc colour palettes (`#2563eb` literal,
`color_continuous_scale="Viridis"`) instead of the centralised
``CHART_PALETTE`` token, no hover tooltips, and no SLA-band shading.
PR-E unifies palettes, adds `hovertemplate`, threads
`responsive_plotly_config()` to every chart, and adds SLA / threshold
band shading on My Queue + Model Performance.

PR-CHART-2 (and the rest of the PR-CHART series) migrates pages off
Plotly to ECharts via the wrapper helpers in ``dashboard/charts.py``.
The migrated pages drop out of the polish guards below — palette /
hover / responsive concerns move into the wrapper layer (and are
covered by ``test_chart_helpers.py``).

Run as text-only assertions.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages"


# Plotly polish guards — applies only to pages still on Plotly.
# Migrated pages (PR-CHART-2 onwards) drop out of this list as they
# move to the ECharts wrappers in dashboard/charts.py.
#
# Migrated by PR-CHART-2:
#   - 11_Live_Monitor.py  (charts → bar_chart / line_chart)
PAGES_WITH_CHART_POLISH = (
    "13_Model_Performance.py",
    "17_Customer_360.py",
    "21_My_Queue.py",
    "23_Tuning_Lab.py",
)


class TestChartsUseCentralisedConfig:
    def test_each_page_passes_responsive_config(self):
        for page in PAGES_WITH_CHART_POLISH:
            body = (PAGES_DIR / page).read_text(encoding="utf-8")
            assert "responsive_plotly_config" in body, (
                f"{page} must pass responsive_plotly_config() to st.plotly_chart"
            )

    def test_each_page_has_hovertemplate(self):
        for page in PAGES_WITH_CHART_POLISH:
            body = (PAGES_DIR / page).read_text(encoding="utf-8")
            assert "hovertemplate" in body, (
                f"{page} must add at least one hovertemplate so charts are tooltip-readable"
            )


class TestPaletteUnification:
    def test_live_monitor_uses_chart_helpers(self):
        # Post PR-CHART-2: Live Monitor calls bar_chart() / line_chart()
        # from dashboard.charts. Those helpers source colours from the
        # ECharts theme (chart_theme.echarts_theme()), not CHART_PALETTE.
        # Old hand-coded channel colour dict must remain absent.
        body = (PAGES_DIR / "11_Live_Monitor.py").read_text(encoding="utf-8")
        assert "bar_chart(" in body and "line_chart(" in body, (
            "Live Monitor must use the centralised bar_chart / line_chart "
            "helpers (PR-CHART-2 migration), not raw plotly calls"
        )
        assert "ch_colors = {" not in body, (
            "Hand-coded channel colour map should be replaced by the centralised ECharts theme"
        )

    def test_customer360_pie_uses_chart_palette(self):
        body = (PAGES_DIR / "17_Customer_360.py").read_text(encoding="utf-8")
        assert "color_discrete_sequence=CHART_PALETTE" in body, (
            "Customer 360 channel pie must use CHART_PALETTE"
        )


class TestRangeBandsAndAnnotations:
    def test_my_queue_has_sla_band_shading(self):
        body = (PAGES_DIR / "21_My_Queue.py").read_text(encoding="utf-8")
        # 3 add_vrect calls — green ≤ SLA, amber 1-2× SLA, red > 2× SLA
        assert body.count("add_vrect(") >= 3, (
            "My Queue resolution histogram must have green/amber/red SLA-band shading"
        )

    def test_model_performance_has_score_band_shading(self):
        body = (PAGES_DIR / "13_Model_Performance.py").read_text(encoding="utf-8")
        # 3 add_vrect calls for the 0–0.65 / 0.65–0.85 / 0.85+ score bands
        assert body.count("add_vrect(") >= 3, (
            "Model Performance score histogram must have score-band shading"
        )

    def test_tuning_lab_scatter_uses_rag_gradient(self):
        body = (PAGES_DIR / "23_Tuning_Lab.py").read_text(encoding="utf-8")
        # The Viridis colour scale is replaced with a RAG-aligned scale.
        assert '"Viridis"' not in body, (
            "Tuning Lab P/R scatter should use a RAG-aligned colour scale, not Viridis"
        )
        # Best-F1 annotation must be present.
        assert "best F1" in body, (
            "Tuning Lab scatter must annotate the best-F1 point so the eye lands there first"
        )
