"""Source-level tests for the Audit & Evidence terminal aesthetic (PR 4).

The huashu-design review picked this page as the candidate for "120%
execution" — auditors and regulators look at it first, and the
framework's evidence-chain claim has to feel trustworthy. Guards:

  - terminal_block helper exists and supports hash/ok/warn/bad kinds
  - .terminal-block CSS lives in CUSTOM_CSS (mono font, dark bg)
  - Rule Output Hashes uses terminal_block (not the old st.dataframe)
  - Verify-chain button wires session-state timestamp
  - Page imports + uses kpi_card_rag (no rainbow-hex regressions)
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPONENTS_FILE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "components.py"
AUDIT_PAGE = PROJECT_ROOT / "src" / "aml_framework" / "dashboard" / "pages" / "7_Audit_Evidence.py"


# ---------------------------------------------------------------------------
# components.py — terminal_block helper + CSS
# ---------------------------------------------------------------------------


class TestTerminalBlockHelper:
    def test_helper_defined(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert "def terminal_block(" in body, "terminal_block helper missing"

    def test_helper_takes_rows_list(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        sig = re.search(r"def terminal_block\([^)]+\)", body)
        assert sig
        assert "rows" in sig.group(0)


class TestTerminalCSS:
    def test_block_class_present(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        assert ".terminal-block" in body, "terminal-block CSS class missing"

    def test_uses_dark_background(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        block = re.search(r"\.terminal-block\s*\{[^}]+\}", body, flags=re.DOTALL)
        assert block, "terminal-block rule body not found"
        # Slate-900 / similar — page mood shifts toward terminal.
        assert "#0f172a" in block.group(0), "terminal-block needs dark background"

    def test_uses_mono_font_stack(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        block = re.search(r"\.terminal-block\s*\{[^}]+\}", body, flags=re.DOTALL)
        assert block
        text = block.group(0).lower()
        # Must include at least one popular mono font.
        assert any(fnt in text for fnt in ("monospace", "menlo", "consolas", "jetbrains")), (
            "terminal-block must use a mono font stack so hashes are scannable"
        )

    def test_kind_classes_present(self):
        body = COMPONENTS_FILE.read_text(encoding="utf-8")
        # The four kinds carry semantics: hash (cyan), ok/warn/bad
        # (green/amber/red). Without them the rows can't tell apart
        # "verified" from "tampered" visually.
        for kind in (".hash", ".ok", ".warn", ".bad"):
            assert kind in body, f"terminal-block missing kind class {kind!r}"


# ---------------------------------------------------------------------------
# Audit & Evidence page — uses the new helpers
# ---------------------------------------------------------------------------


class TestAuditPageMigrated:
    def test_imports_terminal_block_and_rag_helper(self):
        body = AUDIT_PAGE.read_text(encoding="utf-8")
        assert "terminal_block" in body, "Audit page must import terminal_block"
        assert "kpi_card_rag" in body, "Audit page must import kpi_card_rag"

    def test_no_legacy_kpi_card_rainbow_hex(self):
        body = AUDIT_PAGE.read_text(encoding="utf-8")
        rainbow_hexes = [
            r'kpi_card\([^)]+"#dc2626"',  # red
            r'kpi_card\([^)]+"#d97706"',  # orange
            r'kpi_card\([^)]+"#7c3aed"',  # purple
            r'kpi_card\([^)]+"#0891b2"',  # teal
            r'kpi_card\([^)]+"#059669"',  # emerald
            r'kpi_card\([^)]+"#2563eb"',  # blue
            r'kpi_card\([^)]+"#6b7280"',  # grey
        ]
        offenders = [pat for pat in rainbow_hexes if re.search(pat, body)]
        assert not offenders, (
            f"Audit page still has rainbow-hex KPIs: {offenders}. "
            "Use kpi_card_rag(..., rag=...) instead."
        )

    def test_rule_output_hashes_use_terminal_block(self):
        body = AUDIT_PAGE.read_text(encoding="utf-8")
        # Pre-PR-4 used st.dataframe(pd.DataFrame(hash_rows), ...)
        # which renders the hashes in proportional font. The migration
        # has to use terminal_block so SHA-256 hashes display in mono
        # cyan and 0/O / 1/l/I aren't ambiguous.
        m = re.search(
            r'terminal_block\s*\(\s*\[\s*\(rid,\s*h,\s*"hash"\s*\)\s*for',
            body,
        )
        assert m, (
            "Rule Output Hashes section must render via terminal_block "
            "with kind='hash', not a generic dataframe"
        )

    def test_verify_chain_button_wires_session_state(self):
        body = AUDIT_PAGE.read_text(encoding="utf-8")
        assert "Re-verify chain" in body, (
            "Audit page must surface an explicit 'Re-verify chain' button — "
            "auditors need an explicit ritual, not just an auto-load check"
        )
        # Must write a timestamp so the verification leaves a visible
        # proof on the page after the click.
        assert "audit_last_verified" in body, (
            "Verify-chain button must persist the verification timestamp"
        )

    def test_run_identity_terminal_block_present(self):
        body = AUDIT_PAGE.read_text(encoding="utf-8")
        # Top-of-page run identity (Spec Hash, Output Hash, Engine, Run At)
        # must be in a single terminal block so the page opens with the
        # "this is the receipt" feel rather than a 4-up SaaS card row.
        assert "Spec Hash" in body
        assert "terminal_block(" in body
        # Spec / Output / Engine / Run At should all appear before the
        # first KPI row so the page hierarchy reads identity → counts.
        assert body.index("terminal_block(") < body.index("kpi_card_rag(")


class TestKpiCardsAreRagBound:
    def test_baseline_kpi_uses_rag(self):
        body = AUDIT_PAGE.read_text(encoding="utf-8")
        # Baseline missing = red (drift detection unavailable).
        # Present = green. Regex spans the multi-line call form ruff
        # produces; we check that "Baseline" KPI passes a band variable.
        assert 'kpi_card_rag(\n            "Baseline"' in body or (
            re.search(r'kpi_card_rag\(\s*"Baseline"', body)
        ), "Baseline KPI must use kpi_card_rag"
        # Band computation must exist before the call.
        assert "baseline_rag" in body, (
            "Need a computed baseline_rag variable so the KPI's band "
            "is derived (missing → red, present → green)"
        )
        # And it must be threaded into a kpi_card_rag call.
        assert "rag=baseline_rag" in body
