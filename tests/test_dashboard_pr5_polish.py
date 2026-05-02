"""Source-level tests for PR 5: Network filters + geography stacking +
KPI semantic migration on Risk Assessment / Network Explorer.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NETWORK = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages" / "10_Network_Explorer.py"
RISK = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages" / "6_Risk_Assessment.py"


# ---------------------------------------------------------------------------
# Network Explorer — alerted-only filter + KPI migration
# ---------------------------------------------------------------------------


class TestNetworkAlertedFilter:
    def test_show_alerted_only_toggle_present(self):
        body = NETWORK.read_text(encoding="utf-8")
        assert "show_alerted_only" in body, (
            "Network Explorer must expose an alerted-only filter so the "
            "graph stays legible past ~25 customers"
        )
        assert "st.toggle" in body, "Filter must be a toggle widget"

    def test_min_fan_in_slider_present(self):
        body = NETWORK.read_text(encoding="utf-8")
        assert "min_fan_in" in body
        assert "st.slider" in body

    def test_filter_keeps_counterparties_of_alerted(self):
        body = NETWORK.read_text(encoding="utf-8")
        # The filter must include direct counterparties of alerted nodes —
        # showing an isolated alerted node with no edges defeats the
        # graph's purpose.
        assert (
            "counterparties" in body
            or "counterparty" in body
            or ("for c1, c2 in edge_weights:" in body and "alerted_ids" in body)
        ), "Alerted-only filter must include direct counterparties of alerted nodes"


class TestNetworkKpiMigration:
    def test_imports_kpi_card_rag(self):
        body = NETWORK.read_text(encoding="utf-8")
        assert "kpi_card_rag" in body
        # Old kpi_card import must be gone.
        assert (
            re.search(
                r"from aml_framework.dashboard.components import \([^)]*\bkpi_card\b(?!_)",
                body,
                flags=re.DOTALL,
            )
            is None
        )

    def test_alerted_nodes_kpi_uses_red_when_alerts(self):
        body = NETWORK.read_text(encoding="utf-8")
        assert (
            'kpi_card_rag(\n        "Alerted Nodes"' in body
            or 'kpi_card_rag("Alerted Nodes"' in body
        )
        assert 'rag="red" if alerted_ids else None' in body

    def test_fan_in_kpi_uses_red_when_suspects(self):
        body = NETWORK.read_text(encoding="utf-8")
        assert "fan_in_suspects" in body
        assert 'rag="red" if fan_in_suspects else None' in body


# ---------------------------------------------------------------------------
# Risk Assessment — stacked geography + KPI migration
# ---------------------------------------------------------------------------


class TestRiskGeographyStacked:
    def test_no_more_blue_continuous_scale(self):
        body = RISK.read_text(encoding="utf-8")
        # Pre-PR-5 the Customer Geography chart used a monochrome blue
        # continuous scale on raw count — telling no story beyond bar
        # height. Migration must remove it.
        assert 'color_continuous_scale="Blues"' not in body, (
            "Customer Geography must group by risk rating, not be a monochrome blue gradient"
        )

    def test_groups_by_risk_rating(self):
        body = RISK.read_text(encoding="utf-8")
        # Stacked bar: groupby (country, risk_rating).
        assert 'groupby(["country", "risk_rating"])' in body, (
            "Customer Geography must aggregate by (country, risk_rating) "
            "so the chart shows where risk concentrates"
        )

    def test_uses_risk_rating_colors(self):
        # PR-CHART-3 swapped px.bar(color_discrete_map=...) for the
        # bar_chart() helper, which routes "high"/"medium"/"low"
        # series names through the severity palette resolver in
        # chart_theme.py — same colours, derived from one source.
        # Either pattern is acceptable — the invariant is that the
        # risk-rating segments stay severity-coloured.
        body = RISK.read_text(encoding="utf-8")
        ok = "color_discrete_map=RISK_RATING_COLORS" in body or (
            "bar_chart(" in body and 'y=[c for c in ["high", "medium", "low"]' in body
        )
        assert ok, (
            "Risk Geography stacked bars must keep severity colouring — "
            "either via px.bar color_discrete_map=RISK_RATING_COLORS or "
            "via bar_chart with the severity-keyed series names"
        )

    def test_stack_mode_explicit(self):
        # PR-CHART-3 wraps the stack mode behind bar_chart(stacked=True).
        body = RISK.read_text(encoding="utf-8")
        assert ('barmode="stack"' in body) or ("stacked=True" in body), (
            "Bars must explicitly stack (px.bar barmode='stack' or bar_chart stacked=True)"
        )


class TestRiskKpiMigration:
    def test_imports_kpi_card_rag(self):
        body = RISK.read_text(encoding="utf-8")
        assert "kpi_card_rag" in body

    def test_high_risk_kpi_red_when_present(self):
        body = RISK.read_text(encoding="utf-8")
        assert 'kpi_card_rag("High Risk", high_risk, rag=high_risk_rag)' in body
        assert 'high_risk_rag = "red" if high_risk else None' in body

    def test_medium_risk_kpi_amber_when_present(self):
        body = RISK.read_text(encoding="utf-8")
        assert 'kpi_card_rag("Medium Risk", medium_risk, rag=medium_risk_rag)' in body
        assert 'medium_risk_rag = "amber" if medium_risk else None' in body

    def test_no_legacy_rainbow_hex(self):
        body = RISK.read_text(encoding="utf-8")
        rainbow_hexes = [
            r'kpi_card\([^)]+"#dc2626"',
            r'kpi_card\([^)]+"#d97706"',
            r'kpi_card\([^)]+"#7c3aed"',
            r'kpi_card\([^)]+"#0891b2"',
            r'kpi_card\([^)]+"#059669"',
            r'kpi_card\([^)]+"#2563eb"',
        ]
        offenders = [pat for pat in rainbow_hexes if re.search(pat, body)]
        assert not offenders, f"Risk Assessment still has rainbow-hex KPI calls: {offenders}"
