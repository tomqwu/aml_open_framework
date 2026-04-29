"""Tests for `aml propose-change` — 2LoD sign-off packet.

The audit-trail invariant guarded: every threshold change comes with
a Markdown packet that lives in the PR description. If the packet
generator breaks, the framework's "the spec PR + this packet answer
the auditor's 'who decided?' question" promise breaks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aml_framework.cli import app
from aml_framework.propose_change import (
    AlertDelta,
    ProposedChange,
    _extract_rule_yaml,
    build_review_packet,
    extract_citations,
    render_review_packet,
    render_unified_diff,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "examples" / "community_bank" / "aml.yaml"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Rule extraction from spec text
# ---------------------------------------------------------------------------


def test_extract_rule_yaml_finds_existing_rule() -> None:
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    block = _extract_rule_yaml(spec_text, "structuring_cash_deposits")
    assert block is not None
    assert "id: structuring_cash_deposits" in block
    assert "regulation_refs" in block


def test_extract_rule_yaml_returns_none_for_missing() -> None:
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    assert _extract_rule_yaml(spec_text, "rule_that_doesnt_exist") is None


def test_extract_rule_yaml_stops_at_next_rule() -> None:
    """Extraction must not bleed into the next rule's YAML."""
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    block = _extract_rule_yaml(spec_text, "structuring_cash_deposits") or ""
    # The extracted block should not contain another `- id:` line at the
    # top-level rules indent.
    next_id_lines = [
        ln for ln in block.splitlines() if ln.startswith("  - id:") and "structuring_cash" not in ln
    ]
    assert next_id_lines == []


def test_extract_rule_yaml_stops_at_top_level_key() -> None:
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    block = _extract_rule_yaml(spec_text, "structuring_cash_deposits") or ""
    assert "workflow:" not in block
    assert "reporting:" not in block


# ---------------------------------------------------------------------------
# Citation extraction
# ---------------------------------------------------------------------------


def test_extract_citations_picks_up_double_quoted() -> None:
    yaml = """  - id: x
    regulation_refs:
      - citation: "FATF R.20"
        description: "Reporting suspicious activity."
      - citation: "31 CFR 1020.320"
        description: "BSA SAR filing."
"""
    cits = extract_citations(yaml)
    assert "FATF R.20" in cits
    assert "31 CFR 1020.320" in cits


def test_extract_citations_picks_up_single_quoted() -> None:
    yaml = """  - id: x
    regulation_refs:
      - citation: 'FATF R.10'
"""
    assert extract_citations(yaml) == ["FATF R.10"]


def test_extract_citations_returns_empty_when_none() -> None:
    yaml = """  - id: x
    severity: high
"""
    assert extract_citations(yaml) == []


# ---------------------------------------------------------------------------
# Diff rendering
# ---------------------------------------------------------------------------


def test_render_unified_diff_produces_diff_format() -> None:
    a = "  - id: x\n    threshold: 10000\n"
    b = "  - id: x\n    threshold: 8500\n"
    diff = render_unified_diff(a, b)
    assert "---" in diff and "+++" in diff
    assert "-    threshold: 10000" in diff
    assert "+    threshold: 8500" in diff


def test_render_unified_diff_handles_identical_inputs() -> None:
    a = "x\ny\n"
    diff = render_unified_diff(a, a)
    assert diff == ""


# ---------------------------------------------------------------------------
# Packet rendering
# ---------------------------------------------------------------------------


def _change(spec_path: Path, **overrides) -> ProposedChange:
    base = dict(
        spec_path=spec_path,
        rule_id="structuring_cash_deposits",
        proposed_yaml="  - id: structuring_cash_deposits\n    severity: critical\n",
        proposer="Alice Analyst",
        rationale="Tighten threshold post-Q2 review.",
        expected_impact="+10-15% alert volume",
    )
    base.update(overrides)
    return ProposedChange(**base)


def test_render_review_packet_has_all_six_sections() -> None:
    pkt = render_review_packet(
        change=_change(SPEC_PATH),
        current_yaml="  - id: x\n",
        delta=None,
        citations=["FATF R.20"],
        generated_at=datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc),
    )
    assert "## 1. Rationale" in pkt
    assert "## 2. Expected impact" in pkt
    assert "## 3. Diff" in pkt
    assert "## 4. Alert delta" in pkt
    assert "## 5. Regulation citations" in pkt
    assert "## 6. 2LoD sign-off" in pkt


def test_packet_includes_proposer_and_rule_id() -> None:
    pkt = render_review_packet(
        change=_change(SPEC_PATH),
        current_yaml="",
    )
    assert "Alice Analyst" in pkt
    assert "structuring_cash_deposits" in pkt


def test_packet_signoff_block_has_three_rows() -> None:
    """1LoD proposer + 2LoD reviewer + MLRO sign-off — three rows."""
    pkt = render_review_packet(change=_change(SPEC_PATH), current_yaml="")
    sign_off_section = pkt[pkt.index("## 6.") :]
    assert "Proposer (1LoD)" in sign_off_section
    assert "2LoD Reviewer" in sign_off_section
    assert "MLRO Sign-off" in sign_off_section


def test_packet_renders_alert_delta_table_when_present() -> None:
    delta = AlertDelta(
        baseline_alert_count=12,
        proposed_alert_count=18,
        added_customers=["C001", "C002", "C003"],
        removed_customers=["C999"],
        precision_baseline=0.5,
        precision_proposed=0.6,
    )
    pkt = render_review_packet(change=_change(SPEC_PATH), current_yaml="", delta=delta)
    assert "| Alerts | 12 | 18 | +6 |" in pkt
    assert "| Precision | 0.500 | 0.600 | +0.100 |" in pkt
    assert "C001" in pkt and "C999" in pkt


def test_packet_explains_when_delta_omitted() -> None:
    pkt = render_review_packet(change=_change(SPEC_PATH), current_yaml="", delta=None)
    assert "no delta computed" in pkt.lower()


def test_packet_falls_back_when_no_citations() -> None:
    pkt = render_review_packet(change=_change(SPEC_PATH), current_yaml="", citations=None)
    assert "no citations parsed" in pkt.lower()


# ---------------------------------------------------------------------------
# build_review_packet (top-level convenience)
# ---------------------------------------------------------------------------


def test_build_review_packet_extracts_citations_from_spec() -> None:
    """End-to-end: read the real spec, extract the rule, render the packet,
    and the citations block should pick up the rule's citations."""
    change = ProposedChange(
        spec_path=SPEC_PATH,
        rule_id="structuring_cash_deposits",
        proposed_yaml="  - id: structuring_cash_deposits\n    severity: critical\n",
        proposer="Alice",
        rationale="Test",
    )
    pkt = build_review_packet(change=change)
    # Community bank's structuring rule cites 31 CFR 1010.314 and 1020.320
    assert "31 CFR" in pkt or "FATF" in pkt or "FinCEN" in pkt or "BSA" in pkt


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_propose_change_writes_packet(runner: CliRunner, tmp_path: Path) -> None:
    proposed = tmp_path / "proposed.yaml"
    proposed.write_text(
        "  - id: structuring_cash_deposits\n"
        "    name: Tighter\n"
        "    severity: high\n"
        "    regulation_refs:\n"
        '      - citation: "FATF R.20"\n'
        '        description: "x"\n'
        "    logic:\n"
        "      type: aggregation_window\n"
        "      source: txn\n",
        encoding="utf-8",
    )
    out = tmp_path / "packet.md"
    result = runner.invoke(
        app,
        [
            "propose-change",
            str(SPEC_PATH),
            "--rule",
            "structuring_cash_deposits",
            "--proposed-yaml",
            str(proposed),
            "--rationale",
            "Test rationale.",
            "--proposer",
            "Alice",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    assert "Alice" in text
    assert "Test rationale." in text


def test_cli_propose_change_falls_back_to_git_user_when_no_proposer(
    runner: CliRunner, tmp_path: Path, monkeypatch
) -> None:
    """When --proposer is omitted, the wizard reads git user.name. We
    can't assume the test env has git configured, so just verify the
    wizard doesn't crash and produces some proposer field."""
    proposed = tmp_path / "p.yaml"
    proposed.write_text("  - id: x\n", encoding="utf-8")
    out = tmp_path / "packet.md"
    result = runner.invoke(
        app,
        [
            "propose-change",
            str(SPEC_PATH),
            "--rule",
            "structuring_cash_deposits",
            "--proposed-yaml",
            str(proposed),
            "--rationale",
            "Test.",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    # Either real git user.name or the fallback string
    assert "Proposer:" in text


def test_cli_propose_change_requires_proposed_yaml_to_exist(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(
        app,
        [
            "propose-change",
            str(SPEC_PATH),
            "--rule",
            "structuring_cash_deposits",
            "--proposed-yaml",
            str(tmp_path / "missing.yaml"),
            "--rationale",
            "x",
        ],
    )
    assert result.exit_code != 0
