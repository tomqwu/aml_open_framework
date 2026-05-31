"""Tests for scripts/check_coverage_floor.py — the coverage gate.

This gate replaced ``pytest --cov-fail-under``, which silently exited 0
below the threshold on the Linux CI runner (making the gate non-enforcing).
These tests pin the behaviour that matters: it FAILS (non-zero exit) when
coverage is below the floor, on every platform.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_coverage_floor.py"

# scripts/ is a dev/CI utility dir and is intentionally NOT shipped in the
# runtime Docker image (which runs `pytest tests/` as a smoke check). Skip the
# whole module when the script isn't on disk so the image build stays green;
# the gate itself is exercised by the coverage CI job, not this image.
if not _SCRIPT.exists():  # pragma: no cover
    pytest.skip(
        "coverage-gate script not present (stripped runtime image)",
        allow_module_level=True,
    )


def _load_module():
    spec = importlib.util.spec_from_file_location("check_coverage_floor", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load_module()


def _write_report(tmp_path: Path, percent: float) -> Path:
    report = tmp_path / "cov.json"
    report.write_text(json.dumps({"totals": {"percent_covered": percent}}), encoding="utf-8")
    return report


def test_floor_sourced_from_pyproject():
    # Single source of truth — must match pyproject [tool.coverage.report].
    assert mod.floor_from_pyproject() == 98.0


def test_floor_from_text_regex_fallback():
    # The Python-3.10-without-tomli path: regex-scan the single fail_under line.
    text = "[tool.coverage.report]\nexclude_lines = []\nfail_under = 98\n"
    assert mod._floor_from_text(text) == 98.0
    assert mod._floor_from_text("  fail_under = 95.5\n") == 95.5


def test_floor_from_text_missing_raises():
    with pytest.raises(RuntimeError, match="fail_under"):
        mod._floor_from_text("[tool.coverage.report]\n")


def test_coverage_percent_reads_totals(tmp_path):
    report = _write_report(tmp_path, 98.99)
    assert mod.coverage_percent(report) == pytest.approx(98.99)


def test_check_below_floor_fails(tmp_path):
    report = _write_report(tmp_path, 97.5)
    passed, percent = mod.check(report, floor=98.0)
    assert passed is False
    assert percent == pytest.approx(97.5)


def test_check_at_floor_passes(tmp_path):
    report = _write_report(tmp_path, 98.0)
    passed, _ = mod.check(report, floor=98.0)
    assert passed is True


def test_check_above_floor_passes(tmp_path):
    report = _write_report(tmp_path, 99.2)
    passed, _ = mod.check(report, floor=98.0)
    assert passed is True


def test_main_exits_nonzero_below_floor(tmp_path, capsys):
    report = _write_report(tmp_path, 90.0)
    rc = mod.main([str(report), "--floor", "98"])
    assert rc == 1
    assert "FAIL" in capsys.readouterr().out


def test_main_exits_zero_above_floor(tmp_path, capsys):
    report = _write_report(tmp_path, 99.0)
    rc = mod.main([str(report), "--floor", "98"])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_main_missing_report_fails(tmp_path):
    rc = mod.main([str(tmp_path / "nope.json"), "--floor", "98"])
    assert rc == 1


def test_main_uses_pyproject_floor_when_not_overridden(tmp_path):
    # 97.0 is below the pyproject floor (98) -> must fail without --floor.
    report = _write_report(tmp_path, 97.0)
    assert mod.main([str(report)]) == 1
