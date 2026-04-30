"""Source-level tests for PR-B: severity + RAG cell colouring on read-only tables.

Six pages had `st.dataframe(df, ...)` calls with no semantic colour on
columns that *should* carry it (severity, RAG, F1, event_type). PR-B
adds Styler.map() calls using the centralised colour tokens via the
new helpers in `components.py` (`severity_cell_style`,
`rag_cell_style`, `metric_gradient_style`, `event_type_cell_style`).

Run as text-only assertions so they pass on the lint-only CI image.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENTS_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "components.py"
PAGES_DIR = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages"


# ---------------------------------------------------------------------------
# Helper functions exist in components.py
# ---------------------------------------------------------------------------


class TestStylerHelpers:
    def test_severity_cell_style_defined(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "def severity_cell_style(" in body, "severity_cell_style helper missing"
        assert (
            "SEVERITY_COLORS" in body.split("def severity_cell_style(", 1)[1].split("\ndef ", 1)[0]
        ), "severity_cell_style must source colours from SEVERITY_COLORS"

    def test_rag_cell_style_defined(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "def rag_cell_style(" in body
        # rag_cell_style must accept SLA_BAND_COLORS too — SLA breach
        # state is a real RAG-shaped column on Investigations.
        func_body = body.split("def rag_cell_style(", 1)[1].split("\ndef ", 1)[0]
        assert "RAG_COLORS" in func_body
        assert "SLA_BAND_COLORS" in func_body

    def test_metric_gradient_style_factory(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "def metric_gradient_style(" in body
        # Must take low/high thresholds so callers can tune for their
        # metric's natural break points (0.5/0.8 default for F1; risk
        # scores use 0.65/0.85 etc).
        sig = body.split("def metric_gradient_style(", 1)[1].split(")", 1)[0]
        assert "low_threshold" in sig
        assert "high_threshold" in sig

    def test_event_type_cell_style_defined(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "def event_type_cell_style(" in body


# ---------------------------------------------------------------------------
# Each migrated page applies at least one Styler.map call from the helpers
# ---------------------------------------------------------------------------


class TestPagesUseStylerHelpers:
    def test_comparative_analytics_uses_rag_style(self):
        body = (PAGES_DIR / "19_Comparative_Analytics.py").read_text(encoding="utf-8")
        assert "rag_cell_style" in body, "Comparative Analytics must colour the RAG column"
        assert ".style.map(rag_cell_style" in body or "styled_runs.map(rag_cell_style" in body

    def test_run_history_uses_rag_style(self):
        body = (PAGES_DIR / "15_Run_History.py").read_text(encoding="utf-8")
        assert "rag_cell_style" in body, "Run History must colour the RAG column"
        # total_alerts column gets a gradient when present
        assert "metric_gradient_style" in body, (
            "Run History total_alerts gradient (incident-shape detection) is required"
        )

    def test_investigations_uses_severity_and_rag_styles(self):
        body = (PAGES_DIR / "24_Investigations.py").read_text(encoding="utf-8")
        assert "severity_cell_style" in body, (
            "Investigations list table must colour the severity column"
        )
        assert "rag_cell_style" in body, (
            "Investigations constituent cases must colour the sla_state column"
        )

    def test_model_performance_uses_severity_style(self):
        body = (PAGES_DIR / "13_Model_Performance.py").read_text(encoding="utf-8")
        assert "severity_cell_style" in body, "Model inventory must colour Severity"
        assert "metric_gradient_style" in body, (
            "Model alert detail risk_score must use the metric gradient"
        )

    def test_tuning_lab_uses_metric_gradient(self):
        body = (PAGES_DIR / "23_Tuning_Lab.py").read_text(encoding="utf-8")
        assert "metric_gradient_style" in body, (
            "Tuning Lab scenarios precision/recall/F1 must be colour-graded"
        )

    def test_audit_evidence_uses_event_type_style(self):
        body = (PAGES_DIR / "7_Audit_Evidence.py").read_text(encoding="utf-8")
        assert "event_type_cell_style" in body, (
            "Decision log event column must carry escalation/closure colour"
        )
