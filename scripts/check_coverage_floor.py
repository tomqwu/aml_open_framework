#!/usr/bin/env python3
"""Enforce the coverage floor from a coverage JSON report.

Why this exists: ``pytest --cov-fail-under`` has historically *silently
exited 0* even when coverage was below the threshold on the Linux CI
runner (a pytest-cov/coverage plugin quirk), which made the coverage gate
non-enforcing — CI advertised a 99% floor while main sat below it. This
script reads ``totals.percent_covered`` straight out of the coverage JSON
report and exits non-zero when it is under the floor. It is a plain
``sys.exit`` on a plain integer comparison, so it cannot silently pass on
any platform.

The floor is sourced from a SINGLE place — ``[tool.coverage.report]``
``fail_under`` in ``pyproject.toml`` — so the Makefile, the CI workflow,
and the local mirror can never drift apart. Pass ``--floor`` to override
(used only for tests).

Usage:
    python scripts/check_coverage_floor.py .coverage_report.json
    python scripts/check_coverage_floor.py .coverage_report.json --floor 95
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def floor_from_pyproject(pyproject: Path | None = None) -> float:
    """Read the single-source-of-truth coverage floor from pyproject.toml."""
    path = pyproject or (_REPO_ROOT / "pyproject.toml")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return float(data["tool"]["coverage"]["report"]["fail_under"])


def coverage_percent(report_json: Path) -> float:
    """Read ``totals.percent_covered`` from a coverage JSON report."""
    data = json.loads(report_json.read_text(encoding="utf-8"))
    return float(data["totals"]["percent_covered"])


def check(report_json: Path, floor: float) -> tuple[bool, float]:
    """Return (passed, percent). Passed when percent >= floor (with epsilon)."""
    percent = coverage_percent(report_json)
    # 1e-9 epsilon so an exact-equal float comparison never trips on rounding.
    return (percent + 1e-9 >= floor, percent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "report_json",
        type=Path,
        help="Path to the coverage JSON report (coverage json -o ...).",
    )
    parser.add_argument(
        "--floor",
        type=float,
        default=None,
        help="Override floor; defaults to pyproject [tool.coverage.report] fail_under.",
    )
    args = parser.parse_args(argv)

    if not args.report_json.exists():
        print(f"coverage gate: report not found: {args.report_json}", file=sys.stderr)
        return 1

    floor = args.floor if args.floor is not None else floor_from_pyproject()
    passed, percent = check(args.report_json, floor)
    status = "OK" if passed else "FAIL"
    print(f"coverage gate [{status}]: {percent:.2f}% (floor {floor:.2f}%)")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
