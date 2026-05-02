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
# Migrated by PR-CHART-3:
#   - 13_Model_Performance.py / 17_Customer_360.py / 21_My_Queue.py /
#     23_Tuning_Lab.py — all chart-bearing pages now use the ECharts
#     wrappers; nothing left for the Plotly polish guards to assert.
PAGES_WITH_CHART_POLISH: tuple[str, ...] = ()


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

    def test_customer360_pie_uses_chart_helper(self):
        # Post PR-CHART-3: Customer 360 pie chart routes through the
        # pie_chart() helper instead of px.pie + CHART_PALETTE wiring.
        # Palette comes from chart_theme.CATEGORICAL_PALETTE.
        body = (PAGES_DIR / "17_Customer_360.py").read_text(encoding="utf-8")
        assert "pie_chart(" in body, "Customer 360 must use the centralised pie_chart helper"


class TestRangeBandsAndAnnotations:
    # PR-CHART-3 replaced Plotly's add_vrect background bands on the
    # My Queue resolution histogram + Model Performance score histogram
    # with per-bin severity-keyed bar colouring (green ≤ SLA / amber
    # 1-2× SLA / red > 2× SLA). The contract — "the analyst sees the
    # SLA cliff at a glance" — is preserved; the implementation no
    # longer uses add_vrect.

    def test_my_queue_resolution_chart_carries_sla_signal(self):
        body = (PAGES_DIR / "21_My_Queue.py").read_text(encoding="utf-8")
        assert "bar_chart(" in body, (
            "My Queue resolution histogram must use the bar_chart helper "
            "with per-bin severity colouring (PR-CHART-3 migration)"
        )
        # The _band() local must classify against sla_hours so the
        # SLA cliff is reflected in the bar palette, not just the X axis.
        assert "sla_hours" in body and "_band" in body, (
            "Resolution histogram must derive each bar's severity-band "
            "colour from the queue's SLA window"
        )

    def test_model_performance_score_chart_carries_band_signal(self):
        body = (PAGES_DIR / "13_Model_Performance.py").read_text(encoding="utf-8")
        assert "bar_chart(" in body, (
            "Model Performance score histogram must use the bar_chart "
            "helper with per-bin severity colouring (PR-CHART-3 migration)"
        )
        # Threshold 0.65 is the documented action line — the band
        # function must reference it so the bar palette flips at the
        # right cliff.
        assert "0.65" in body, "Model Performance must keep the 0.65 action threshold"

    def test_tuning_lab_scatter_uses_rag_band_colouring(self):
        body = (PAGES_DIR / "23_Tuning_Lab.py").read_text(encoding="utf-8")
        # PR-CHART-3 replaced Plotly's continuous Viridis/RAG gradient
        # with discrete severity-band colouring via scatter_chart's
        # color= column. The Viridis literal must remain absent;
        # best-F1 callout migrated from add_annotation to a per-row
        # `label` column on the scatter.
        assert '"Viridis"' not in body, (
            "Tuning Lab P/R scatter should use the severity-band palette, not Viridis"
        )
        assert "best F1" in body, (
            "Tuning Lab scatter must annotate the best-F1 point so the eye lands there first"
        )
        assert "scatter_chart(" in body, (
            "Tuning Lab P/R scatter must use the centralised scatter_chart helper"
        )
