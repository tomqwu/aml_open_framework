"""Source-level tests for the RAG-bound KPI card migration (PR 2).

Guards the design decision that KPI border color must carry semantic
meaning (RAG band) rather than decorative-rainbow per-card slot. The
old pattern was ``kpi_card("Total Alerts", n, "#dc2626")`` where the
hex was hardcoded per card without any link to the metric's actual
state — making "red border" mean nothing reproducibly.

These tests are file-as-text assertions so they run on the minimal CI
image without streamlit installed.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENTS_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "components.py"
EXEC_PAGE = (
    PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages" / "1_Executive_Dashboard.py"
)


# ---------------------------------------------------------------------------
# components.py — kpi_card_rag helper exists with the right contract
# ---------------------------------------------------------------------------


class TestKpiCardRagHelper:
    def test_function_defined(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "def kpi_card_rag(" in body, "kpi_card_rag helper missing"

    def test_signature_takes_optional_rag(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        sig = re.search(r"def kpi_card_rag\([^)]*\)", body)
        assert sig, "kpi_card_rag signature not found"
        assert "rag" in sig.group(0), "kpi_card_rag must accept a 'rag' parameter"
        assert "None" in sig.group(0), "rag parameter must default to None (neutral)"

    def test_neutral_border_constant_exists(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "KPI_NEUTRAL_BORDER" in body, (
            "Need a documented neutral-border color so 'fact KPIs' "
            "(counts, totals) don't borrow RAG colors and confuse readers"
        )

    def test_helper_uses_rag_colors_dict(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # Implementation must pull from the central RAG_COLORS dict — not
        # redeclare its own hex codes — so changes to the palette
        # propagate everywhere.
        body_after_def = body.split("def kpi_card_rag(", 1)[1]
        body_func = body_after_def.split("\ndef ", 1)[0]
        assert "RAG_COLORS" in body_func, (
            "kpi_card_rag must source colors from RAG_COLORS, not a "
            "private hex map (would drift from the rest of the system)"
        )

    def test_unset_treated_as_neutral(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # The string "unset" is a real RAG band the metrics engine emits
        # when no thresholds are declared. It must render as neutral
        # (not as the literal string "unset" looked up in RAG_COLORS,
        # which gives the grey "unset" hex but reads as semantic state
        # rather than absence-of-state).
        body_after_def = body.split("def kpi_card_rag(", 1)[1]
        body_func = body_after_def.split("\ndef ", 1)[0]
        assert "unset" in body_func, "kpi_card_rag must explicitly handle 'unset' RAG"


# ---------------------------------------------------------------------------
# Executive Dashboard — fully migrated to kpi_card_rag
# ---------------------------------------------------------------------------


class TestExecutiveDashboardMigrated:
    def test_imports_kpi_card_rag(self):
        body = EXEC_PAGE.read_text(encoding="utf-8")
        assert "kpi_card_rag" in body, "Executive Dashboard must import kpi_card_rag"

    def test_no_more_rainbow_hex_codes_on_main_kpis(self):
        body = EXEC_PAGE.read_text(encoding="utf-8")
        # The pre-PR-2 pattern was kpi_card(...,"#dc2626") /
        # kpi_card(...,"#d97706") / kpi_card(...,"#7c3aed") with the
        # hex chosen for visual variety, not state. The migration must
        # have removed all such *literal* per-card hex args.
        rainbow_hexes = [
            r'kpi_card\([^)]+"#dc2626"',  # red
            r'kpi_card\([^)]+"#d97706"',  # orange
            r'kpi_card\([^)]+"#7c3aed"',  # purple
            r'kpi_card\([^)]+"#0891b2"',  # teal
            r'kpi_card\([^)]+"#059669"',  # emerald
            r'kpi_card\([^)]+"#2563eb"',  # blue
        ]
        offenders = [pat for pat in rainbow_hexes if re.search(pat, body)]
        assert not offenders, (
            f"Executive Dashboard still has decorative-rainbow KPI hex "
            f"codes: {offenders}. Use kpi_card_rag(..., rag=...) instead."
        )

    def test_typology_coverage_uses_metric_rag(self):
        body = EXEC_PAGE.read_text(encoding="utf-8")
        # The typology_coverage MetricResult has a real .rag band — it
        # must be threaded through, not replaced with a static color.
        m = re.search(
            r'kpi_card_rag\(\s*"Typology Coverage"[^)]*rag=(?:tc\.rag|metrics_by_id)',
            body,
            flags=re.DOTALL,
        )
        assert m, (
            "Typology Coverage KPI must bind border color to metric.rag — not a hardcoded green hex"
        )

    def test_funnel_alert_to_str_uses_threshold_band(self):
        body = EXEC_PAGE.read_text(encoding="utf-8")
        # The Alert → STR conversion KPI is the FinCEN NPRM /
        # AMLA RTS effectiveness measure. Its border must be banded.
        assert "funnel_rag" in body, (
            "Alert → STR conversion KPI must compute a RAG band from "
            "the conversion %, not use a static green hex."
        )
        # Bands must reference the FinCEN typical 5–10% range.
        assert ">= 10" in body and ">= 5" in body, (
            "Funnel band thresholds should match the FinCEN NPRM "
            "typical-conversion-rate commentary (5%/10% breakpoints)."
        )
