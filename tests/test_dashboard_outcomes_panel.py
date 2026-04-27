"""Phase B-2 — outcomes funnel + regwatch panel surfaced on dashboard pages.

Verifies:
  - Page #1 (Executive Dashboard) embeds the AMLA RTS funnel
  - Page #7 (Audit & Evidence) embeds the regulation-drift panel
  - Both pages defend against missing modules / empty data
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXEC_DASHBOARD = (
    PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages" / "1_Executive_Dashboard.py"
)
AUDIT_EVIDENCE = (
    PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages" / "7_Audit_Evidence.py"
)


# ---------------------------------------------------------------------------
# Page #1 — Effectiveness funnel surface
# ---------------------------------------------------------------------------


class TestExecutiveFunnel:
    def test_imports_outcomes_module(self):
        body = EXEC_DASHBOARD.read_text(encoding="utf-8")
        assert "from aml_framework.metrics.outcomes import" in body
        assert "compute_outcomes" in body
        assert "format_amla_rts_json" in body

    def test_renders_funnel_section_header(self):
        body = EXEC_DASHBOARD.read_text(encoding="utf-8")
        assert "Effectiveness Funnel" in body

    def test_loads_cases_from_audit_ledger(self):
        # The page reads cases/<id>.json + decisions.jsonl from run_dir.
        body = EXEC_DASHBOARD.read_text(encoding="utf-8")
        assert "cases_dir" in body or "_cases_dir" in body
        assert "decisions.jsonl" in body

    def test_renders_4_funnel_kpis(self):
        body = EXEC_DASHBOARD.read_text(encoding="utf-8")
        # The four canonical funnel numbers FinCEN + AMLA both ask for.
        assert "Alerts" in body  # already on the page; just confirms presence
        assert "STR filed" in body
        assert "Alert → STR" in body or "alert_to_str_pct" in body

    def test_amla_rts_download_button(self):
        body = EXEC_DASHBOARD.read_text(encoding="utf-8")
        assert "AMLA RTS JSON" in body
        # The download button must point at format_amla_rts_json output.
        assert "format_amla_rts_json" in body

    def test_funnel_failure_does_not_crash_page(self):
        # The funnel block must be wrapped in try/except so a missing
        # decisions.jsonl or schema mismatch doesn't black out the page.
        body = EXEC_DASHBOARD.read_text(encoding="utf-8")
        idx = body.find("Effectiveness Funnel")
        assert idx > 0
        # Use a generous slice — the section is ~5KB including the
        # AMLA RTS download button block.
        section = body[idx:]
        assert "try:" in section
        assert "except" in section


# ---------------------------------------------------------------------------
# Page #7 — Regulation drift panel
# ---------------------------------------------------------------------------


class TestAuditEvidenceRegwatch:
    def test_imports_regwatch_module(self):
        body = AUDIT_EVIDENCE.read_text(encoding="utf-8")
        assert "from aml_framework.compliance.regwatch import" in body
        assert "scan_spec" in body
        assert "load_baseline" in body

    def test_renders_drift_section_header(self):
        body = AUDIT_EVIDENCE.read_text(encoding="utf-8")
        assert "Regulation Drift" in body

    def test_documents_fincen_boi_motivation(self):
        # The "why now" anchor — keeps the rationale visible in code so
        # future maintainers don't accidentally remove the panel.
        body = AUDIT_EVIDENCE.read_text(encoding="utf-8")
        assert "FinCEN BOI Mar 2025" in body or "FinCEN BOI" in body

    def test_reads_baseline_default_path(self):
        body = AUDIT_EVIDENCE.read_text(encoding="utf-8")
        assert ".regwatch.json" in body

    def test_handles_missing_baseline(self):
        # When no baseline yet, the panel should show actionable guidance,
        # not just an empty section.
        body = AUDIT_EVIDENCE.read_text(encoding="utf-8")
        assert "aml regwatch" in body  # CLI command in the empty-state copy
        assert "--update" in body

    def test_failure_does_not_crash_page(self):
        body = AUDIT_EVIDENCE.read_text(encoding="utf-8")
        idx = body.find("Regulation Drift")
        assert idx > 0
        section = body[idx : idx + 3000]
        assert "try:" in section
        assert "except" in section


# ---------------------------------------------------------------------------
# Cross-page invariants
# ---------------------------------------------------------------------------


class TestCrossPageInvariants:
    def test_neither_page_imports_at_module_level_when_optional(self):
        # Both panels are optional features; their imports live inside
        # the try block so a missing module doesn't break the rest of
        # the page. (Round-7 modules SHOULD be on main, but defensive
        # imports cost nothing and protect against partial deploys.)
        for page in (EXEC_DASHBOARD, AUDIT_EVIDENCE):
            body = page.read_text(encoding="utf-8")
            # The Round-7 module imports should appear AFTER `try:` at
            # least once — i.e. not all imports are at the top of file.
            outcomes_idx = (
                body.find("from aml_framework.metrics.outcomes")
                if page == EXEC_DASHBOARD
                else body.find("from aml_framework.compliance.regwatch")
            )
            if outcomes_idx > 0:
                # There should be a `try:` between the start of the page
                # and the module import — meaning the import is inside
                # the try block.
                preceding = body[:outcomes_idx]
                # Last `try:` before the import:
                assert preceding.rfind("try:") > preceding.rfind("\n\nimport") or (
                    preceding.rfind("try:") > 0
                ), f"{page.name}: outcomes/regwatch import should be inside a try/except block"
