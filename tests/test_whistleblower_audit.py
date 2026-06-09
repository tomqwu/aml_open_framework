"""FinCEN Whistleblower internal-channel audit report (#531).

Covers:
- Pydantic model invariants (frozen + extra="forbid")
- SAR-backlog exposure: stale (open >30d, unresolved) vs fresh vs resolved
- Escalation coverage: documented reviewer+rationale vs system-auto
- Triage time: median + p95 from resolution_hours, alert-to-decision
- Board-documented decisions: tracked vs not-tracked (never fabricated)
- Ledger integrity: verified vs broken (tampered decisions.jsonl)
- Determinism: same run dir + same generated_at => identical report
- CLI: writes JSON artifact + --markdown + --format nprm-gap
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aml_framework.engine.audit import AuditLedger
from aml_framework.engine.whistleblower_audit import (
    STALE_BACKLOG_DAYS,
    SarBacklogExposure,
    TriageTime,
    WhistleblowerAuditReport,
    _parse_ts,
    _percentile,
    _read_decisions,
    build_whistleblower_audit_report,
    render_nprm_gap_markdown,
    render_whistleblower_markdown,
)

_AS_OF = datetime(2026, 5, 1, tzinfo=timezone.utc).replace(tzinfo=None)


def _make_run(tmp_path: Path, decisions: list[dict]) -> Path:
    """Materialize a finalized run dir with the given decision events.

    Uses a real `AuditLedger` so the manifest's `decisions_hash` is a
    genuine hash chain over the lines we write (so `verify_decisions`
    is exercised end to end, not stubbed).
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    spec_path = tmp_path / "aml.yaml"
    spec_path.write_text("program: {}\n", encoding="utf-8")
    ledger = AuditLedger.create(
        artifacts_root=tmp_path / "artifacts",
        spec_path=spec_path,
        spec_hash="deadbeef",
        as_of=_AS_OF,
    )
    for d in decisions:
        ts = d.pop("_ts", None)
        ledger.append_decision(d, ts=ts)
    ledger.finalize()
    return ledger.run_dir


def _opened(case_id: str, ts: datetime) -> dict:
    return {"event": "case_opened", "case_id": case_id, "rule_id": "r", "_ts": ts}


def _closed(case_id: str, ts: datetime, **extra) -> dict:
    base = {
        "event": "closed",
        "case_id": case_id,
        "rule_id": "r",
        "disposition": "closed_no_action",
        "_ts": ts,
    }
    base.update(extra)
    return base


def _event(name: str, case_id: str, ts: datetime, **extra) -> dict:
    base = {"event": name, "case_id": case_id, "rule_id": "r", "_ts": ts}
    base.update(extra)
    return base


# --------------------------------------------------------------------------
# Model invariants
# --------------------------------------------------------------------------


def test_models_are_frozen_and_extra_forbid():
    backlog = SarBacklogExposure(open_stale_alerts=1, oldest_days=40)
    with pytest.raises(Exception):
        backlog.open_stale_alerts = 2  # frozen
    with pytest.raises(Exception):
        SarBacklogExposure(open_stale_alerts=1, oldest_days=40, extra="x")  # extra forbidden
    with pytest.raises(Exception):
        TriageTime(median_days=1.0, p95_days=2.0, n_decisions=3, surprise=1)


# --------------------------------------------------------------------------
# SAR backlog exposure
# --------------------------------------------------------------------------


def test_backlog_counts_stale_unresolved_open_alerts(tmp_path):
    # C1 opened 45d before as_of, never resolved -> stale.
    # C2 opened 10d before as_of, never resolved -> fresh, not stale.
    # C3 opened 60d before as_of but resolved -> not backlog.
    stale_open = datetime(2026, 3, 17)  # 45 days before 2026-05-01
    fresh_open = datetime(2026, 4, 21)  # 10d before
    old_resolved_open = datetime(2026, 3, 2)  # 60d before
    run = _make_run(
        tmp_path,
        [
            _opened("C1", stale_open),
            _opened("C2", fresh_open),
            _opened("C3", old_resolved_open),
            _closed("C3", datetime(2026, 3, 5)),
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.sar_backlog_exposure.open_stale_alerts == 1
    assert report.sar_backlog_exposure.oldest_days == 45


def test_backlog_zero_when_all_resolved(tmp_path):
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 1, 1)),
            _closed("C1", datetime(2026, 1, 2)),
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.sar_backlog_exposure.open_stale_alerts == 0
    assert report.sar_backlog_exposure.oldest_days == 0


def test_sar_resolution_clears_backlog(tmp_path):
    # An alert escalated_to_str (SAR) is resolved even though it's old.
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 1, 1)),
            {
                "event": "escalated_to_str",
                "case_id": "C1",
                "rule_id": "r",
                "disposition": "sar_filing",
                "_ts": datetime(2026, 1, 3),
            },
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.sar_backlog_exposure.open_stale_alerts == 0


def test_old_escalated_case_still_counts_as_backlog(tmp_path):
    # P1-2: an `escalated` event is NOT terminal (mirrors sla.py) — an old
    # in-flight escalation must still count toward the SAR backlog.
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 1, 1)),  # 120d before as_of
            _event("escalated", "C1", datetime(2026, 1, 2), disposition="l2_investigator"),
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.sar_backlog_exposure.open_stale_alerts == 1
    assert report.sar_backlog_exposure.oldest_days == 120


def test_old_manual_review_case_still_counts_as_backlog(tmp_path):
    # P1-2: `manual_review` is likewise in-flight, not terminal.
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 1, 1)),
            _event("manual_review", "C1", datetime(2026, 1, 5)),
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.sar_backlog_exposure.open_stale_alerts == 1


def test_backlog_age_boundary_exactly_30_days_not_stale(tmp_path):
    # P2-2: the code uses `age_days > STALE_BACKLOG_DAYS`, so EXACTLY 30 days
    # is NOT stale; 30 days + epsilon IS. as_of = 2026-05-01 00:00:00.
    on_boundary = _AS_OF - timedelta(days=STALE_BACKLOG_DAYS)  # exactly 30d old
    just_over = _AS_OF - timedelta(days=STALE_BACKLOG_DAYS, seconds=1)  # 30d + 1s

    run_boundary = _make_run(tmp_path / "a", [_opened("C1", on_boundary)])
    assert (
        build_whistleblower_audit_report(
            run_boundary, generated_at=_AS_OF
        ).sar_backlog_exposure.open_stale_alerts
        == 0
    )

    run_over = _make_run(tmp_path / "b", [_opened("C1", just_over)])
    assert (
        build_whistleblower_audit_report(
            run_over, generated_at=_AS_OF
        ).sar_backlog_exposure.open_stale_alerts
        == 1
    )


# --------------------------------------------------------------------------
# Escalation coverage
# --------------------------------------------------------------------------


def test_escalation_coverage_system_auto_is_zero(tmp_path):
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 4, 1)),
            _closed("C1", datetime(2026, 4, 2)),
            _opened("C2", datetime(2026, 4, 1)),
            _closed("C2", datetime(2026, 4, 2)),
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.n_disposition_decisions == 2
    assert report.escalation_coverage_pct == 0.0


def test_escalation_coverage_documented_reviewer_and_rationale(tmp_path):
    # One documented (reviewer + rationale), one auto -> 50%.
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 4, 1)),
            _closed(
                "C1",
                datetime(2026, 4, 2),
                reviewer="analyst.jane",
                rationale="reviewed KYC, benign",
            ),
            _opened("C2", datetime(2026, 4, 1)),
            _closed("C2", datetime(2026, 4, 2)),
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.escalation_coverage_pct == 50.0


def test_dashboard_source_counts_as_reviewer(tmp_path):
    # The dashboard stamps source=dashboard_ui; with a rationale that is a
    # documented human decision.
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 4, 1)),
            _closed(
                "C1",
                datetime(2026, 4, 2),
                source="dashboard_ui",
                rationale="false positive",
            ),
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.escalation_coverage_pct == 100.0


def test_reviewer_without_rationale_is_not_documented(tmp_path):
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 4, 1)),
            _closed("C1", datetime(2026, 4, 2), reviewer="jane"),
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.escalation_coverage_pct == 0.0


# --------------------------------------------------------------------------
# Triage time
# --------------------------------------------------------------------------


def test_triage_time_from_ledger_timestamps(tmp_path):
    # ts deltas: 1d, 2d, 3d -> median 2d, p95 3d. Ledger ts is the primary
    # (authoritative) signal.
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 4, 1)),
            _closed("C1", datetime(2026, 4, 2)),
            _opened("C2", datetime(2026, 4, 1)),
            _closed("C2", datetime(2026, 4, 3)),
            _opened("C3", datetime(2026, 4, 1)),
            _closed("C3", datetime(2026, 4, 4)),
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.triage_time.n_decisions == 3
    assert report.triage_time.median_days == 2.0
    assert report.triage_time.p95_days == 3.0


def test_triage_time_prefers_ledger_ts_over_resolution_hours(tmp_path):
    # P2-1: ledger ts (2 days) wins over a divergent resolution_hours
    # (which would imply 10 days) — the ts is the authoritative signal.
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 4, 1)),
            _closed("C1", datetime(2026, 4, 3), resolution_hours=240.0),  # 10d if used
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.triage_time.median_days == 2.0


def test_triage_time_falls_back_to_resolution_hours_when_open_ts_absent(tmp_path):
    # No `case_opened` event (so no open ts) but a terminal event with
    # resolution_hours -> the fallback path computes from resolution_hours.
    run = _make_run(
        tmp_path,
        [_closed("C1", datetime(2026, 4, 3), resolution_hours=48.0)],  # 2 days
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.triage_time.n_decisions == 1
    assert report.triage_time.median_days == 2.0


def test_triage_time_none_when_no_dispositions(tmp_path):
    run = _make_run(tmp_path, [_opened("C1", datetime(2026, 4, 1))])
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.triage_time.median_days is None
    assert report.triage_time.p95_days is None
    assert report.triage_time.n_decisions == 0


# --------------------------------------------------------------------------
# Board-documented decisions
# --------------------------------------------------------------------------


def test_board_reporting_not_tracked_when_no_board_events(tmp_path):
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 4, 1)),
            _closed("C1", datetime(2026, 4, 2)),
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.board_reporting_tracked is False
    assert report.board_documented_decisions == 0


def test_board_documented_decisions_counted_when_tracked(tmp_path):
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 4, 1)),
            _closed("C1", datetime(2026, 4, 2)),
            {
                "event": "board_report",
                "case_id": "C1",
                "rule_id": "r",
                "_ts": datetime(2026, 4, 3),
            },
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.board_reporting_tracked is True
    assert report.board_documented_decisions == 1


# --------------------------------------------------------------------------
# Ledger integrity
# --------------------------------------------------------------------------


def test_ledger_integrity_verified_on_clean_run(tmp_path):
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 4, 1)),
            _closed("C1", datetime(2026, 4, 2)),
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.ledger_integrity == "verified"


def test_ledger_integrity_broken_on_tampered_decisions(tmp_path):
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 4, 1)),
            _closed("C1", datetime(2026, 4, 2)),
        ],
    )
    # Tamper: rewrite a decision line after finalize.
    dpath = run / "decisions.jsonl"
    lines = dpath.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[-1])
    tampered["disposition"] = "sar_filing"
    lines[-1] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
    dpath.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.ledger_integrity == "broken"


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_report_is_deterministic(tmp_path):
    decisions = [
        _opened("C1", datetime(2026, 4, 1)),
        _closed("C1", datetime(2026, 4, 2), resolution_hours=24.0),
        _opened("C2", datetime(2026, 1, 1)),
    ]
    run = _make_run(tmp_path, [dict(d) for d in decisions])
    r1 = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    r2 = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert r1.model_dump_json() == r2.model_dump_json()


# --------------------------------------------------------------------------
# Markdown renderers
# --------------------------------------------------------------------------


def test_markdown_renders_signals(tmp_path):
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 4, 1)),
            _closed("C1", datetime(2026, 4, 2), resolution_hours=24.0),
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    md = render_whistleblower_markdown(report)
    assert "Whistleblower internal-channel audit" in md
    assert "SAR backlog" in md
    assert "2026-06271" in md


def test_nprm_gap_marks_gaps(tmp_path):
    # A stale backlog of 1 + verified ledger + a fast triage + no board.
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 1, 1)),  # 120d, unresolved -> stale
            _opened("C2", datetime(2026, 4, 1)),
            _closed("C2", datetime(2026, 4, 2), resolution_hours=24.0),
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    gap = render_nprm_gap_markdown(report)
    assert "Internal reporting channel documented | ✓" in gap
    assert "✗" in gap  # the backlog row is a gap (1 stale > 0 threshold)
    assert "⚠" in gap  # board not tracked
    assert "FR 2026-06271" in gap


# --------------------------------------------------------------------------
# Robustness / helper edge cases
# --------------------------------------------------------------------------


def test_read_decisions_missing_file(tmp_path):
    assert _read_decisions(tmp_path) == []


def test_read_decisions_skips_blank_and_malformed_lines(tmp_path):
    (tmp_path / "decisions.jsonl").write_text(
        '\n  \n{"event":"closed","case_id":"C1"}\nnot json\n[1,2,3]\n',
        encoding="utf-8",
    )
    rows = _read_decisions(tmp_path)
    # Only the well-formed dict line survives (list line is not a dict).
    assert rows == [{"event": "closed", "case_id": "C1"}]


def test_parse_ts_edge_cases():
    assert _parse_ts(None) is None
    assert _parse_ts(123) is None
    assert _parse_ts("") is None
    assert _parse_ts("not-a-date") is None
    # tz-aware input is normalized to naive UTC.
    naive = _parse_ts("2026-05-01T00:00:00+00:00")
    assert naive == datetime(2026, 5, 1)
    assert naive.tzinfo is None


def test_percentile_single_value():
    assert _percentile([4.2], 95.0) == 4.2


def test_percentile_empty_raises():
    with pytest.raises(ValueError):
        _percentile([], 95.0)


def test_decision_without_case_id_is_ignored(tmp_path):
    # An event with no case_id (e.g. environment_gate_check) must not crash
    # nor count toward backlog/triage.
    run = _make_run(
        tmp_path,
        [
            {"event": "environment_gate_check", "approved": True, "_ts": datetime(2026, 4, 1)},
            _opened("C1", datetime(2026, 4, 1)),
            _closed("C1", datetime(2026, 4, 2), resolution_hours=24.0),
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.n_disposition_decisions == 1
    assert report.triage_time.n_decisions == 1


def test_negative_ts_delta_excluded_from_triage(tmp_path):
    # A terminal decision stamped BEFORE the case opened (clock skew) and no
    # resolution_hours -> the negative delta is dropped, not counted.
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 4, 5)),
            _closed("C1", datetime(2026, 4, 1)),  # before open, no resolution_hours
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.triage_time.n_decisions == 0
    assert report.triage_time.median_days is None


def test_render_markdown_handles_none_triage(tmp_path):
    run = _make_run(tmp_path, [_opened("C1", datetime(2026, 4, 1))])
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    md = render_whistleblower_markdown(report)
    assert "n/a" in md
    gap = render_nprm_gap_markdown(report)
    assert "n/a (no disposition decisions)" in gap


def test_nprm_gap_all_pass_path(tmp_path):
    # Documented board + reviewer + fast triage + zero backlog -> all ✓.
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 4, 1)),
            _closed(
                "C1",
                datetime(2026, 4, 2),
                resolution_hours=24.0,
                reviewer="jane",
                rationale="benign",
            ),
            {
                "event": "board_report",
                "case_id": "C1",
                "rule_id": "r",
                "_ts": datetime(2026, 4, 3),
            },
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    gap = render_nprm_gap_markdown(report)
    # Inspect only the table rows (the footer legend line names every glyph).
    table_rows = [ln for ln in gap.splitlines() if ln.startswith("| ") and "Status" not in ln]
    assert all("✗" not in r and "⚠" not in r for r in table_rows)
    assert "Board-level escalation documented | ✓" in gap


def test_nprm_gap_board_tracked_but_zero_documented(tmp_path):
    # A board_report event exists (tracked) but ties to a case with no
    # disposition decision -> board_documented_decisions=0 -> ✗ gap.
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 4, 1)),
            _closed("C1", datetime(2026, 4, 2), resolution_hours=24.0),
            {
                "event": "board_review",
                "case_id": "C2",  # different case, no disposition
                "rule_id": "r",
                "_ts": datetime(2026, 4, 3),
            },
        ],
    )
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.board_reporting_tracked is True
    assert report.board_documented_decisions == 0
    gap = render_nprm_gap_markdown(report)
    assert "Board-level escalation documented | ✗" in gap


def test_nprm_gap_broken_ledger_and_late_triage(tmp_path):
    # 45-day ledger gap between open and close -> triage 45d > 30d threshold.
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 4, 1)),
            _closed("C1", datetime(2026, 5, 16)),  # 45 days after open
        ],
    )
    dpath = run / "decisions.jsonl"
    dpath.write_text(dpath.read_text(encoding="utf-8") + '{"x":1}\n', encoding="utf-8")
    report = build_whistleblower_audit_report(run, generated_at=_AS_OF)
    assert report.triage_time.median_days == 45.0
    gap = render_nprm_gap_markdown(report)
    assert "ledger_integrity=broken" in gap
    assert "Median triage < 30d | ✗" in gap


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_cli_writes_artifact_and_formats(tmp_path):
    from typer.testing import CliRunner

    from aml_framework.cli import app

    # Build a run with a real (non-trivial) spec so load_spec succeeds.
    run = _make_run(
        tmp_path,
        [
            _opened("C1", datetime(2026, 4, 1)),
            _closed("C1", datetime(2026, 4, 2), resolution_hours=24.0),
        ],
    )
    # Use the bundled example spec (load_spec needs a valid spec).
    spec_path = Path("examples/community_bank/aml.yaml")
    md_path = tmp_path / "wb.md"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "whistleblower-audit",
            str(spec_path),
            str(run),
            "--markdown",
            str(md_path),
        ],
    )
    assert result.exit_code == 0, result.output
    artifact = run / "whistleblower_audit_report.json"
    assert artifact.exists()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["ledger_integrity"] == "verified"
    assert payload["generated_at"] == _AS_OF.isoformat()
    assert md_path.exists()
    assert "Whistleblower internal-channel audit" in md_path.read_text(encoding="utf-8")

    # nprm-gap format prints the gap table to stdout.
    result2 = runner.invoke(
        app,
        ["whistleblower-audit", str(spec_path), str(run), "--format", "nprm-gap"],
    )
    assert result2.exit_code == 0, result2.output
    assert "NPRM readiness gap" in result2.output
    assert "FR 2026-06271" in result2.output


def test_cli_rejects_unknown_format(tmp_path):
    from typer.testing import CliRunner

    from aml_framework.cli import app

    run = _make_run(tmp_path, [_opened("C1", datetime(2026, 4, 1))])
    spec_path = Path("examples/community_bank/aml.yaml")
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["whistleblower-audit", str(spec_path), str(run), "--format", "bogus"],
    )
    assert result.exit_code == 1


def test_cli_fails_closed_when_manifest_missing(tmp_path):
    # P1-1: no manifest.json -> refuse rather than invent a wall-clock as_of.
    from typer.testing import CliRunner

    from aml_framework.cli import app

    run = _make_run(tmp_path, [_opened("C1", datetime(2026, 4, 1))])
    (run / "manifest.json").unlink()  # remove the as_of anchor
    spec_path = Path("examples/community_bank/aml.yaml")
    runner = CliRunner()
    result = runner.invoke(app, ["whistleblower-audit", str(spec_path), str(run)])
    assert result.exit_code == 1
    assert "as_of" in result.output
    assert not (run / "whistleblower_audit_report.json").exists()


def test_cli_fails_closed_when_manifest_has_no_as_of(tmp_path):
    # P1-1: manifest present but no `as_of` key -> still refuse.
    from typer.testing import CliRunner

    from aml_framework.cli import app

    run = _make_run(tmp_path, [_opened("C1", datetime(2026, 4, 1))])
    (run / "manifest.json").write_text('{"engine_version": "x"}', encoding="utf-8")
    spec_path = Path("examples/community_bank/aml.yaml")
    runner = CliRunner()
    result = runner.invoke(app, ["whistleblower-audit", str(spec_path), str(run)])
    assert result.exit_code == 1
    assert not (run / "whistleblower_audit_report.json").exists()


def test_stale_backlog_days_constant():
    assert STALE_BACKLOG_DAYS == 30
    assert isinstance(WhistleblowerAuditReport.model_fields["enabled"].annotation, type)
