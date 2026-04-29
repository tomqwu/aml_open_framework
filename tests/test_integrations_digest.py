"""Tests for `aml notify-digest` — Slack/Teams digest aggregator.

The supervisor-visibility invariant guarded: when an escalation or
SLA breach happens, a periodic push to the team's chat channel
surfaces it before end-of-day. If the rollup logic breaks, the only
way to learn about the breach is opening the dashboard — back to
square one.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from aml_framework.cli import app
from aml_framework.integrations.digest import (
    DigestEntry,
    DigestPayload,
    build_digest,
    post_digest,
    render_slack_text,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _write_decisions(run_dir: Path, rows: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "decisions.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Building the digest
# ---------------------------------------------------------------------------


def test_build_digest_empty_when_no_events(tmp_path: Path) -> None:
    p = build_digest(tmp_path, program_name="x", window_hours=24, as_of=datetime(2026, 4, 28))
    assert p.total == 0


def test_build_digest_includes_escalations_in_window(tmp_path: Path) -> None:
    as_of = datetime(2026, 4, 28, 12, 0)
    _write_decisions(
        tmp_path,
        [
            {
                "event": "escalated",
                "ts": (as_of - timedelta(hours=2)).isoformat(),
                "case_id": "C-1",
                "customer_id": "CUST-1",
                "rule_id": "rule_a",
                "severity": "high",
            },
        ],
    )
    p = build_digest(tmp_path, program_name="x", window_hours=24, as_of=as_of)
    assert p.total == 1
    assert p.entries[0].kind == "escalation"


def test_build_digest_excludes_events_outside_window(tmp_path: Path) -> None:
    as_of = datetime(2026, 4, 28, 12, 0)
    _write_decisions(
        tmp_path,
        [
            {
                "event": "escalated",
                "ts": (as_of - timedelta(hours=72)).isoformat(),  # 3 days ago
                "case_id": "C-old",
                "severity": "high",
                "rule_id": "r",
                "customer_id": "c",
            },
            {
                "event": "escalated",
                "ts": (as_of - timedelta(hours=2)).isoformat(),
                "case_id": "C-new",
                "severity": "high",
                "rule_id": "r",
                "customer_id": "c",
            },
        ],
    )
    p = build_digest(tmp_path, program_name="x", window_hours=24, as_of=as_of)
    assert {e.case_id for e in p.entries} == {"C-new"}


def test_build_digest_includes_sla_breaches(tmp_path: Path) -> None:
    as_of = datetime(2026, 4, 28, 12, 0)
    _write_decisions(
        tmp_path,
        [
            {
                "event": "sla_breach",
                "ts": (as_of - timedelta(hours=1)).isoformat(),
                "case_id": "C-1",
                "severity": "high",
                "rule_id": "r",
                "customer_id": "c",
            }
        ],
    )
    p = build_digest(tmp_path, program_name="x", window_hours=24, as_of=as_of)
    assert p.total == 1
    assert p.entries[0].kind == "sla_breach"


def test_build_digest_picks_up_critical_alerts_even_without_escalation(
    tmp_path: Path,
) -> None:
    """Supervisors want eyes on critical-severity alerts even when the
    case-management workflow hasn't escalated yet."""
    as_of = datetime(2026, 4, 28, 12, 0)
    _write_decisions(
        tmp_path,
        [
            {
                "event": "case_opened",
                "ts": (as_of - timedelta(hours=1)).isoformat(),
                "case_id": "C-1",
                "severity": "critical",
                "rule_id": "r",
                "customer_id": "c",
            },
            {
                "event": "case_opened",
                "ts": (as_of - timedelta(hours=2)).isoformat(),
                "case_id": "C-2",
                "severity": "low",  # ignored — not critical
                "rule_id": "r",
                "customer_id": "c",
            },
        ],
    )
    p = build_digest(tmp_path, program_name="x", window_hours=24, as_of=as_of)
    assert {e.case_id for e in p.entries} == {"C-1"}
    assert p.entries[0].kind == "alert"
    assert p.entries[0].severity == "critical"


def test_build_digest_falls_back_to_max_ts_when_as_of_omitted(tmp_path: Path) -> None:
    last = datetime(2026, 4, 28, 10, 0)
    _write_decisions(
        tmp_path,
        [
            {
                "event": "escalated",
                "ts": last.isoformat(),
                "case_id": "C-1",
                "severity": "high",
                "rule_id": "r",
                "customer_id": "c",
            }
        ],
    )
    p = build_digest(tmp_path, program_name="x", window_hours=24)
    # Window end should be the max-ts in ledger (deterministic) not
    # wall-clock.
    assert p.window_end.startswith("2026-04-28T10:00")


def test_build_digest_tolerates_missing_ledger(tmp_path: Path) -> None:
    p = build_digest(
        tmp_path / "no-ledger-here",
        program_name="x",
        window_hours=24,
        as_of=datetime(2026, 4, 28),
    )
    assert p.total == 0


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_render_slack_says_all_clear_when_empty() -> None:
    p = DigestPayload(program_name="x", window_hours=24, window_end="2026-04-28T12:00")
    text = render_slack_text(p)
    assert "All clear" in text


def test_render_slack_includes_severity_breakdown() -> None:
    p = DigestPayload(
        program_name="x",
        window_hours=24,
        window_end="2026-04-28T12:00",
        entries=[
            DigestEntry(
                kind="escalation",
                severity="critical",
                case_id="C-1",
                customer_id="CUST-1",
                rule_id="r1",
                occurred_at="t",
            ),
            DigestEntry(
                kind="sla_breach",
                severity="high",
                case_id="C-2",
                customer_id="CUST-2",
                rule_id="r2",
                occurred_at="t",
            ),
        ],
    )
    text = render_slack_text(p)
    assert "critical: 1" in text
    assert "high: 1" in text


def test_render_slack_lists_critical_first() -> None:
    p = DigestPayload(
        program_name="x",
        window_hours=24,
        window_end="2026-04-28T12:00",
        entries=[
            DigestEntry(
                kind="escalation",
                severity="medium",
                case_id="C-med",
                customer_id="c",
                rule_id="r",
                occurred_at="t",
            ),
            DigestEntry(
                kind="escalation",
                severity="critical",
                case_id="C-crit",
                customer_id="c",
                rule_id="r",
                occurred_at="t",
            ),
        ],
    )
    text = render_slack_text(p)
    assert text.index("C-crit") < text.index("C-med")


def test_render_slack_truncates_after_10_with_more_link() -> None:
    entries = [
        DigestEntry(
            kind="escalation",
            severity="high",
            case_id=f"C-{i}",
            customer_id="c",
            rule_id="r",
            occurred_at="t",
        )
        for i in range(15)
    ]
    p = DigestPayload(
        program_name="x", window_hours=24, window_end="2026-04-28T12:00", entries=entries
    )
    text = render_slack_text(p)
    assert "and 5 more" in text


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------


def test_post_digest_sends_to_both_platforms_when_both_succeed() -> None:
    p = DigestPayload(
        program_name="x",
        window_hours=24,
        window_end="t",
        entries=[
            DigestEntry(
                kind="escalation",
                severity="high",
                case_id="C-1",
                customer_id="c",
                rule_id="r",
                occurred_at="t",
            )
        ],
    )
    with (
        patch("aml_framework.integrations.notifications._send_slack") as slack,
        patch("aml_framework.integrations.notifications._send_teams") as teams,
    ):
        sent = post_digest(p)
    assert sent == {"slack": True, "teams": True}
    slack.assert_called_once()
    teams.assert_called_once()


def test_post_digest_suppress_empty_skips_send() -> None:
    p = DigestPayload(program_name="x", window_hours=24, window_end="t")
    with (
        patch("aml_framework.integrations.notifications._send_slack") as slack,
        patch("aml_framework.integrations.notifications._send_teams") as teams,
    ):
        sent = post_digest(p, suppress_when_empty=True)
    assert sent == {"slack": False, "teams": False}
    slack.assert_not_called()
    teams.assert_not_called()


def test_post_digest_handles_per_platform_failure() -> None:
    p = DigestPayload(
        program_name="x",
        window_hours=24,
        window_end="t",
        entries=[
            DigestEntry(
                kind="escalation",
                severity="high",
                case_id="C-1",
                customer_id="c",
                rule_id="r",
                occurred_at="t",
            )
        ],
    )
    with (
        patch(
            "aml_framework.integrations.notifications._send_slack",
            side_effect=RuntimeError("boom"),
        ),
        patch("aml_framework.integrations.notifications._send_teams"),
    ):
        sent = post_digest(p)
    assert sent["slack"] is False
    assert sent["teams"] is True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


SPEC_PATH = (
    Path(__file__).resolve().parent.parent / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
)


def test_cli_notify_digest_dry_run_renders_preview(runner: CliRunner, tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    run = artifacts / "run-dry"
    _write_decisions(
        run,
        [
            {
                "event": "escalated",
                "ts": "2026-04-28T11:00:00",
                "case_id": "C-1",
                "severity": "high",
                "rule_id": "r",
                "customer_id": "c",
            }
        ],
    )
    result = runner.invoke(
        app,
        [
            "notify-digest",
            str(SPEC_PATH),
            "--artifacts",
            str(artifacts),
            "--dry-run",
            "--since-hours",
            "48",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Digest preview" in result.output
    assert "Dry run" in result.output


def test_cli_notify_digest_emits_all_clear_message(runner: CliRunner, tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    run = artifacts / "run-empty"
    _write_decisions(run, [])
    result = runner.invoke(
        app,
        [
            "notify-digest",
            str(SPEC_PATH),
            "--artifacts",
            str(artifacts),
            "--dry-run",
        ],
    )
    assert "All clear" in result.output
