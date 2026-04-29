"""Tests for `aml today` — per-persona morning checklist.

The unified-picture promise this guards: a leader runs one command
and gets a tailored, ordered list of what needs their attention. If
the persona routing or signal extraction breaks, leaders fall back
to the four-dashboard scramble.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aml_framework.cli import app
from aml_framework.spec import load_spec
from aml_framework.today_checklist import (
    PERSONA_SIGNALS,
    Checklist,
    ChecklistItem,
    build_checklist,
    render_checklist_text,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def empty_run(tmp_path: Path) -> Path:
    """Run dir with empty decisions + no cases — exercises the
    "all-clear" path."""
    run = tmp_path / "run-empty"
    run.mkdir()
    (run / "decisions.jsonl").write_text("", encoding="utf-8")
    (run / "manifest.json").write_text("{}", encoding="utf-8")
    return run


def _write_run_with_decisions(tmp_path: Path, rows: list[dict]) -> Path:
    run = tmp_path / "run"
    run.mkdir(parents=True, exist_ok=True)
    (run / "decisions.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    (run / "manifest.json").write_text("{}", encoding="utf-8")
    return run


# ---------------------------------------------------------------------------
# Persona signal mix
# ---------------------------------------------------------------------------


def test_every_persona_has_a_signal_mix() -> None:
    for persona in ("cco", "mlro", "director", "manager", "analyst", "auditor", "cto", "svp"):
        assert persona in PERSONA_SIGNALS
        assert PERSONA_SIGNALS[persona], f"persona {persona!r} has empty signals"


def test_cco_signal_mix_includes_exam_readiness() -> None:
    assert "exam" in PERSONA_SIGNALS["cco"]
    assert "regwatch" in PERSONA_SIGNALS["cco"]


def test_mlro_signal_mix_focuses_on_model_challenge() -> None:
    assert "challenge" in PERSONA_SIGNALS["mlro"]


# ---------------------------------------------------------------------------
# Build — empty / clean state
# ---------------------------------------------------------------------------


def test_build_checklist_no_run_returns_hints_only() -> None:
    spec = load_spec(SPEC_PATH)
    cl = build_checklist(persona="cco", spec=spec, run_dir=None)
    assert isinstance(cl, Checklist)
    assert cl.items, "Empty checklist would leave a new bank with nothing"
    assert cl.persona == "cco"


def test_build_checklist_clean_state_has_all_clear(empty_run: Path) -> None:
    spec = load_spec(SPEC_PATH)
    cl = build_checklist(persona="manager", spec=spec, run_dir=empty_run)
    # Manager only has [sla, aging, critical] signals — none of which fire
    # on an empty run; should fall through to all_clear.
    assert any("All clear" in item.headline for item in cl.items)


# ---------------------------------------------------------------------------
# Build — signal extraction
# ---------------------------------------------------------------------------


def test_build_checklist_surfaces_critical_alerts(tmp_path: Path) -> None:
    spec = load_spec(SPEC_PATH)
    last = datetime(2026, 4, 28, 10, 0)
    run = _write_run_with_decisions(
        tmp_path,
        [
            {
                "ts": (last - timedelta(hours=2)).isoformat(),
                "event": "case_opened",
                "severity": "critical",
                "case_id": "C-1",
                "rule_id": "r",
                "customer_id": "x",
            }
        ],
    )
    cl = build_checklist(persona="cco", spec=spec, run_dir=run)
    assert any(i.kind == "exam_readiness" and i.severity == "critical" for i in cl.items)


def test_build_checklist_surfaces_sla_breaches(tmp_path: Path) -> None:
    spec = load_spec(SPEC_PATH)
    run = _write_run_with_decisions(
        tmp_path,
        [
            {
                "ts": "2026-04-28T11:00:00",
                "event": "sla_breach",
                "severity": "high",
                "case_id": "C-1",
                "rule_id": "r",
                "customer_id": "x",
            }
        ],
    )
    cl = build_checklist(persona="director", spec=spec, run_dir=run)
    breach_items = [i for i in cl.items if "breach" in i.headline.lower()]
    assert breach_items


def test_build_checklist_orders_critical_first(tmp_path: Path) -> None:
    spec = load_spec(SPEC_PATH)
    last = datetime(2026, 4, 28, 10, 0)
    run = _write_run_with_decisions(
        tmp_path,
        [
            {
                "ts": (last - timedelta(hours=2)).isoformat(),
                "event": "case_opened",
                "severity": "critical",
                "case_id": "C-1",
                "rule_id": "r",
                "customer_id": "x",
            },
            {
                "ts": "2026-04-28T11:00:00",
                "event": "sla_breach",
                "severity": "high",
                "case_id": "C-2",
                "rule_id": "r",
                "customer_id": "x",
            },
        ],
    )
    cl = build_checklist(persona="cco", spec=spec, run_dir=run)
    severities = [i.severity for i in cl.items]
    # First non-info item should be critical (or there are no critical items)
    if "critical" in severities:
        first_actionable = next(s for s in severities if s != "info")
        assert first_actionable == "critical"


def test_mlro_checklist_includes_backtest_hint() -> None:
    spec = load_spec(SPEC_PATH)
    cl = build_checklist(persona="mlro", spec=spec, run_dir=None)
    assert any("backtest" in i.suggested_action.lower() for i in cl.items)


def test_auditor_checklist_includes_chain_verification() -> None:
    spec = load_spec(SPEC_PATH)
    cl = build_checklist(persona="auditor", spec=spec, run_dir=None)
    assert any(i.kind == "audit_chain" for i in cl.items)


def test_build_checklist_dedupes_kinds() -> None:
    """If a persona's signal mix would generate two items of the same
    kind, only the first should appear — keeps the checklist short."""
    spec = load_spec(SPEC_PATH)
    cl = build_checklist(persona="cco", spec=spec, run_dir=None)
    kinds = [i.kind for i in cl.items]
    assert len(kinds) == len(set(kinds))


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------


def test_render_checklist_includes_persona_and_program() -> None:
    spec = load_spec(SPEC_PATH)
    cl = build_checklist(persona="cco", spec=spec, run_dir=None)
    text = render_checklist_text(cl)
    assert "CCO" in text
    assert spec.program.name in text


def test_render_checklist_includes_suggested_actions_when_present() -> None:
    cl = Checklist(
        persona="cco",
        program_name="x",
        generated_at="2026-04-28",
        items=[
            ChecklistItem(
                kind="audit_chain",
                headline="Test",
                detail="Detail",
                severity="info",
                suggested_action="aml verify",
            )
        ],
    )
    text = render_checklist_text(cl)
    assert "→ aml verify" in text


def test_render_checklist_omits_action_arrow_when_empty() -> None:
    cl = Checklist(
        persona="manager",
        program_name="x",
        generated_at="2026-04-28",
        items=[
            ChecklistItem(
                kind="queue_health",
                headline="All good",
                detail="Nothing",
                severity="info",
            )
        ],
    )
    text = render_checklist_text(cl)
    assert "→" not in text


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_today_no_run_works(runner: CliRunner) -> None:
    result = runner.invoke(app, ["today", str(SPEC_PATH), "--persona", "cco", "--no-run"])
    assert result.exit_code == 0, result.output
    assert "CCO" in result.output


def test_cli_today_with_real_artifacts(runner: CliRunner, tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    run = artifacts / "run-x"
    _write_run_with_decisions(
        artifacts, [{"event": "sla_breach", "ts": "2026-04-28T10:00", "severity": "high"}]
    )
    # Move the test run into the expected subdir
    import shutil

    shutil.move(str(artifacts / "run"), str(run))
    result = runner.invoke(
        app,
        ["today", str(SPEC_PATH), "--persona", "director", "--artifacts", str(artifacts)],
    )
    assert result.exit_code == 0, result.output


def test_cli_today_rejects_unknown_persona(runner: CliRunner) -> None:
    result = runner.invoke(app, ["today", str(SPEC_PATH), "--persona", "ceo", "--no-run"])
    assert result.exit_code == 2
    assert "Unknown persona" in result.output


def test_cli_today_silently_falls_back_when_no_run_dir_exists(
    runner: CliRunner, tmp_path: Path
) -> None:
    """A new bank running `aml today` before they've ever run the engine
    should get hints, not a crash."""
    artifacts = tmp_path / "empty-artifacts"
    artifacts.mkdir()
    result = runner.invoke(app, ["today", str(SPEC_PATH), "--artifacts", str(artifacts)])
    assert result.exit_code == 0, result.output
