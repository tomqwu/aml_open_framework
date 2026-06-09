"""Pillar-2 defect-ticket lifecycle — issue #529 (Sub-feature A).

The frozen ``defect_log.jsonl`` is the minted defect artifact; this
suite pins the mutable, append-only companion ``defect_lifecycle.jsonl``
and the ``aml defect-update`` CLI that writes it:

  * a valid lifecycle event appends one canonical-JSON line;
  * the three status transitions (acknowledged/resolved/closed) all work;
  * the companion file is append-only (a second action does not rewrite
    the first line);
  * resolved/closed require a non-empty resolution;
  * a defect id not in the frozen log is rejected;
  * the event timestamp derives from the run's manifest as_of, not
    wall-clock (determinism).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aml_framework.cli import app
from aml_framework.engine.defect_lifecycle import (
    DEFECT_LIFECYCLE_FILENAME,
    DefectLifecycleEvent,
    LifecycleStatus,
    append_lifecycle_event,
    read_defect_ids,
    read_lifecycle_events,
)

runner = CliRunner()

_AS_OF = "2026-01-15T00:00:00"


def _make_run_dir(tmp_path: Path, defect_ids: list[str]) -> Path:
    """Build a minimal run dir with a frozen defect_log.jsonl + manifest."""
    run_dir = tmp_path / "run-test"
    run_dir.mkdir()
    lines = [
        json.dumps(
            {
                "id": did,
                "category": "data_quality",
                "classification": "data",
                "severity": "high",
                "summary": "x",
                "detected_by": "dq.evaluator",
                "source_run_id": "abc",
                "created_at": f"{_AS_OF}+00:00",
                "status": "open",
            },
            sort_keys=True,
        )
        for did in defect_ids
    ]
    (run_dir / "defect_log.jsonl").write_text("\n".join(lines) + ("\n" if lines else ""))
    (run_dir / "manifest.json").write_text(json.dumps({"as_of": _AS_OF}))
    return run_dir


class TestLifecycleEventModel:
    def test_acknowledged_allows_empty_resolution(self):
        evt = DefectLifecycleEvent(
            defect_id="d1",
            lifecycle_status=LifecycleStatus.ACKNOWLEDGED,
            reviewer="r1",
            timestamp=datetime.fromisoformat(_AS_OF),
        )
        assert evt.resolution == ""

    @pytest.mark.parametrize("status", [LifecycleStatus.RESOLVED, LifecycleStatus.CLOSED])
    def test_terminal_requires_resolution(self, status):
        with pytest.raises(ValueError):
            DefectLifecycleEvent(
                defect_id="d1",
                lifecycle_status=status,
                reviewer="r1",
                timestamp=datetime.fromisoformat(_AS_OF),
                resolution="   ",  # whitespace-only is rejected
            )

    def test_extra_field_forbidden(self):
        with pytest.raises(ValueError):
            DefectLifecycleEvent(
                defect_id="d1",
                lifecycle_status=LifecycleStatus.ACKNOWLEDGED,
                reviewer="r1",
                timestamp=datetime.fromisoformat(_AS_OF),
                bogus="nope",
            )


class TestAppendOnlyCompanion:
    def test_append_creates_and_reads_back(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        evt = DefectLifecycleEvent(
            defect_id="d1",
            lifecycle_status=LifecycleStatus.ACKNOWLEDGED,
            reviewer="r1",
            timestamp=datetime.fromisoformat(_AS_OF),
        )
        append_lifecycle_event(run_dir, evt)
        events = read_lifecycle_events(run_dir)
        assert len(events) == 1
        assert events[0].defect_id == "d1"
        assert events[0].lifecycle_status is LifecycleStatus.ACKNOWLEDGED

    def test_second_append_does_not_rewrite_first(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        first = DefectLifecycleEvent(
            defect_id="d1",
            lifecycle_status=LifecycleStatus.ACKNOWLEDGED,
            reviewer="r1",
            timestamp=datetime.fromisoformat(_AS_OF),
        )
        append_lifecycle_event(run_dir, first)
        line1 = (run_dir / DEFECT_LIFECYCLE_FILENAME).read_bytes()

        second = DefectLifecycleEvent(
            defect_id="d1",
            lifecycle_status=LifecycleStatus.RESOLVED,
            reviewer="r2",
            timestamp=datetime.fromisoformat(_AS_OF),
            resolution="fixed the feed",
        )
        append_lifecycle_event(run_dir, second)
        both = (run_dir / DEFECT_LIFECYCLE_FILENAME).read_bytes()

        # Append-only: the first line's bytes are a prefix of the file
        # after the second write — the original line was not rewritten.
        assert both.startswith(line1)
        events = read_lifecycle_events(run_dir)
        assert [e.lifecycle_status for e in events] == [
            LifecycleStatus.ACKNOWLEDGED,
            LifecycleStatus.RESOLVED,
        ]

    def test_read_defect_ids_from_frozen_log(self, tmp_path):
        run_dir = _make_run_dir(tmp_path, ["defect:abc:0000:c1", "defect:abc:0001:c2"])
        assert read_defect_ids(run_dir) == {"defect:abc:0000:c1", "defect:abc:0001:c2"}

    def test_read_defect_ids_missing_log_is_empty(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        assert read_defect_ids(run_dir) == set()

    def test_read_defect_ids_skips_blank_lines(self, tmp_path):
        run_dir = _make_run_dir(tmp_path, ["defect:abc:0000:c1"])
        # Append a trailing blank line — must be skipped, not parsed.
        with (run_dir / "defect_log.jsonl").open("a") as f:
            f.write("\n")
        assert read_defect_ids(run_dir) == {"defect:abc:0000:c1"}

    def test_read_lifecycle_events_missing_file_is_empty(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        assert read_lifecycle_events(run_dir) == []

    def test_read_lifecycle_events_skips_blank_lines(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        append_lifecycle_event(
            run_dir,
            DefectLifecycleEvent(
                defect_id="d1",
                lifecycle_status=LifecycleStatus.ACKNOWLEDGED,
                reviewer="r1",
                timestamp=datetime.fromisoformat(_AS_OF),
            ),
        )
        with (run_dir / DEFECT_LIFECYCLE_FILENAME).open("a") as f:
            f.write("\n")
        assert len(read_lifecycle_events(run_dir)) == 1


class TestDefectUpdateCLI:
    def test_acknowledge_appends_valid_event(self, tmp_path):
        run_dir = _make_run_dir(tmp_path, ["defect:abc:0000:c1"])
        result = runner.invoke(
            app,
            [
                "defect-update",
                str(run_dir),
                "defect:abc:0000:c1",
                "--status",
                "acknowledged",
                "--reviewer",
                "alice",
            ],
        )
        assert result.exit_code == 0, result.output
        events = read_lifecycle_events(run_dir)
        assert len(events) == 1
        assert events[0].reviewer == "alice"
        assert events[0].lifecycle_status is LifecycleStatus.ACKNOWLEDGED

    @pytest.mark.parametrize("status", ["acknowledged", "resolved", "closed"])
    def test_all_transitions(self, tmp_path, status):
        run_dir = _make_run_dir(tmp_path, ["defect:abc:0000:c1"])
        args = [
            "defect-update",
            str(run_dir),
            "defect:abc:0000:c1",
            "--status",
            status,
            "--reviewer",
            "bob",
        ]
        if status in ("resolved", "closed"):
            args += ["--resolution", "addressed"]
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        events = read_lifecycle_events(run_dir)
        assert events[-1].lifecycle_status.value == status

    def test_timestamp_derives_from_manifest_as_of(self, tmp_path):
        run_dir = _make_run_dir(tmp_path, ["defect:abc:0000:c1"])
        runner.invoke(
            app,
            [
                "defect-update",
                str(run_dir),
                "defect:abc:0000:c1",
                "--status",
                "acknowledged",
                "--reviewer",
                "alice",
            ],
        )
        events = read_lifecycle_events(run_dir)
        # Deterministic — the event timestamp is the run's as_of, not now().
        assert events[0].timestamp == datetime.fromisoformat(_AS_OF)

    def test_unknown_defect_id_rejected(self, tmp_path):
        run_dir = _make_run_dir(tmp_path, ["defect:abc:0000:c1"])
        result = runner.invoke(
            app,
            [
                "defect-update",
                str(run_dir),
                "defect:abc:9999:nope",
                "--status",
                "acknowledged",
                "--reviewer",
                "alice",
            ],
        )
        assert result.exit_code == 1
        assert not (run_dir / DEFECT_LIFECYCLE_FILENAME).exists()

    def test_unknown_status_rejected(self, tmp_path):
        run_dir = _make_run_dir(tmp_path, ["defect:abc:0000:c1"])
        result = runner.invoke(
            app,
            [
                "defect-update",
                str(run_dir),
                "defect:abc:0000:c1",
                "--status",
                "wont_fix",  # not an offline lifecycle transition
                "--reviewer",
                "alice",
            ],
        )
        assert result.exit_code == 1

    def test_resolved_without_resolution_rejected(self, tmp_path):
        run_dir = _make_run_dir(tmp_path, ["defect:abc:0000:c1"])
        result = runner.invoke(
            app,
            [
                "defect-update",
                str(run_dir),
                "defect:abc:0000:c1",
                "--status",
                "resolved",
                "--reviewer",
                "alice",
            ],
        )
        assert result.exit_code == 1
