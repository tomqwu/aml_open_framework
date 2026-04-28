"""Phase B-3 — audit-pack download button + VoP enrichment surfaced.

Verifies:
  - Page #7 (Audit & Evidence) embeds the FINTRAC audit-pack download
    button (gated on jurisdiction == "CA")
  - Page #12 (Sanctions Screening) embeds the VoP outcomes panel when
    txn data carries `confirmation_of_payee_status`
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDIT_EVIDENCE = (
    PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages" / "7_Audit_Evidence.py"
)
SANCTIONS = (
    PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages" / "12_Sanctions_Screening.py"
)


# ---------------------------------------------------------------------------
# Page #7 — FINTRAC audit-pack download button
# ---------------------------------------------------------------------------


class TestAuditPackButton:
    def test_imports_audit_pack_module(self):
        body = AUDIT_EVIDENCE.read_text(encoding="utf-8")
        assert "from aml_framework.generators.audit_pack import build_audit_pack" in body

    def test_renders_section_header(self):
        body = AUDIT_EVIDENCE.read_text(encoding="utf-8")
        assert "Pre-Examination Audit Pack" in body

    def test_download_button_present(self):
        body = AUDIT_EVIDENCE.read_text(encoding="utf-8")
        assert "FINTRAC Audit Pack" in body
        # Two download buttons on the page now (decisions CSV + audit pack);
        # confirm count is at least 2.
        assert body.count("st.download_button(") >= 2

    def test_jurisdiction_gated(self):
        # Pack only ships for CA in v1; non-CA specs should see an
        # informative caption rather than a non-functional button.
        body = AUDIT_EVIDENCE.read_text(encoding="utf-8")
        assert "spec_for_pack.program.jurisdiction" in body
        assert '== "CA"' in body
        # Non-CA path explains the planned UK / EU / US templates.
        assert "UK FCA" in body or "EU AMLA" in body

    def test_calls_build_audit_pack_with_canada_jurisdiction(self):
        body = AUDIT_EVIDENCE.read_text(encoding="utf-8")
        assert 'jurisdiction="CA-FINTRAC"' in body

    def test_failure_does_not_crash_page(self):
        body = AUDIT_EVIDENCE.read_text(encoding="utf-8")
        idx = body.find("Pre-Examination Audit Pack")
        assert idx > 0
        section = body[idx:]
        assert "try:" in section
        assert "except" in section


# ---------------------------------------------------------------------------
# Page #12 — VoP outcomes section
# ---------------------------------------------------------------------------


class TestVoPOutcomes:
    def test_renders_section_header(self):
        body = SANCTIONS.read_text(encoding="utf-8")
        assert "Verification of Payee" in body

    def test_documents_psd3_and_cop_compatibility(self):
        # The cross-regulator vocabulary is the design point — keep it
        # visible in code so future maintainers don't fork the column.
        body = SANCTIONS.read_text(encoding="utf-8")
        assert "PSD3" in body
        assert "UK CoP" in body or "Confirmation of Payee" in body

    def test_handles_missing_column_gracefully(self):
        # When the txn frame doesn't carry confirmation_of_payee_status
        # (most existing specs), the panel should explain how to populate
        # it rather than rendering an empty table.
        body = SANCTIONS.read_text(encoding="utf-8")
        assert "confirmation_of_payee_status" in body
        assert "not in df_txns.columns" in body or "data/psd3" in body

    def test_renders_5_psd3_outcome_kpis(self):
        # The 5 outcomes from data/psd3/parser.py:VOP_OUTCOMES.
        body = SANCTIONS.read_text(encoding="utf-8")
        for outcome in ("match", "close_match", "no_match", "not_checked", "outside_scope"):
            assert f'"{outcome}"' in body

    def test_handles_empty_txn_frame(self):
        # No txn data at all (degenerate spec or empty source) — should
        # caption "no data" rather than crash.
        body = SANCTIONS.read_text(encoding="utf-8")
        # The guard pattern.
        assert "df_txns.empty" in body or "df_txns is None" in body
