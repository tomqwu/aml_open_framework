"""PR-LIN-7: Data Integration page — Source→Contract→Table section.

Source-level checks that the new section surfaces the input_manifest
fields PR-LIN-2 added (source_path, schema_columns, schema_hash) and
that DATA-3 / DATA-4 status flags flip from 'stub' to 'shipped'.

Avoids importing Streamlit (not on the unit-test CI image).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAGE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages" / "30_Data_Integration.py"


class TestSourceContractTableSection:
    def test_section_header_present(self):
        body = PAGE.read_text(encoding="utf-8")
        assert "### Source → Contract → Table" in body, "lineage mapping section header missing"

    def test_reads_input_manifest(self):
        body = PAGE.read_text(encoding="utf-8")
        assert "input_manifest.json" in body, (
            "section must read input_manifest.json for the per-contract source mapping"
        )

    def test_surfaces_new_pr_lin_2_fields(self):
        body = PAGE.read_text(encoding="utf-8")
        # Each must appear so the auditor sees Source / Schema hash /
        # Columns alongside the existing Contract / Rows / Content hash.
        for col in ('"Source"', '"Schema hash"', '"Columns"', '"DuckDB table"'):
            assert col in body, f"Source→Contract→Table grid must surface {col} column"

    def test_data_3_and_4_marked_shipped(self):
        body = PAGE.read_text(encoding="utf-8")
        # Round 11 closed these; flip the status flags so the DATA-N
        # → artifact map matches what the dashboard now renders.
        assert "DATA-3 · Cross-system reconciliation" in body
        assert "DATA-4 · Lineage walk-back from KPI" in body
        # The "Stub" / "richer view planned" copy must be gone for
        # both rows.
        assert "Stub — surfaced via `audit_evidence` page" not in body, (
            "DATA-3 status copy still says Stub; PR-LIN-7 ships the richer view"
        )
        # And the new copy must reference the shipped surface.
        assert "Shipped" in body, "DATA-3 / DATA-4 status must reference shipped surface"
