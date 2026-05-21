"""Emit a shields.io endpoint-badge JSON to stdout.

Called from `.github/workflows/ci.yml` test jobs to write per-type
badge JSON to `.github/badges/<label>.json`. The shields.io
endpoint badge in the README reads the raw GitHub URL of that
file and renders `<label> · <message>` with the color we emit.

Schema reference:
https://shields.io/badges/endpoint-badge

Stdlib-only on purpose so it runs in the CI image without an
install step. CI invokes it as `python scripts/_make_badge_json.py
--label unit --count 2417 --status success`.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Final

# Status → color map. Mirrors what shields.io itself uses for its
# native build-status badges so the visual reads "GitHub-native".
_COLOR_BY_STATUS: Final[dict[str, str]] = {
    "success": "brightgreen",
    "failure": "red",
    "cancelled": "lightgrey",
    "skipped": "lightgrey",
}


def coverage_color(percent: float) -> str:
    """Color for a coverage percent. Thresholds:
    - ≥98 → brightgreen (matches the Makefile's effective floor)
    - ≥90 → yellow (warning band — coverage slipping but not red)
    - <90 → red (regression)
    """
    if percent >= 98:
        return "brightgreen"
    if percent >= 90:
        return "yellow"
    return "red"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--label",
        required=True,
        help="Badge label, e.g. 'unit', 'api', 'e2e', 'coverage'.",
    )
    p.add_argument(
        "--status",
        required=True,
        choices=sorted(_COLOR_BY_STATUS),
        help="GitHub Actions job result.",
    )
    p.add_argument(
        "--count",
        type=int,
        help="Test count for unit/api/e2e badges (integer).",
    )
    p.add_argument(
        "--coverage",
        type=float,
        help="Coverage percent for the coverage badge (float, 0-100).",
    )
    args = p.parse_args(argv)

    # Message + color depend on what kind of badge this is.
    if args.coverage is not None:
        message = f"{args.coverage:.0f}%"
        # Coverage color reflects the percent band, NOT the job
        # status — a "passing" job at 89% is yellow because the
        # number itself is the signal, not the gate.
        color = (
            coverage_color(args.coverage)
            if args.status == "success"
            else _COLOR_BY_STATUS[args.status]
        )
    elif args.status == "success" and args.count is not None:
        message = f"{args.count} passing"
        color = _COLOR_BY_STATUS["success"]
    else:
        # Failure / cancellation: still surface the count if we
        # have one, so the badge reads `unit · 2417 failing` not
        # just `failing` — operator can see whether the suite was
        # truncated or fully ran.
        message = (
            f"{args.count} failing"
            if (args.count is not None and args.status == "failure")
            else args.status
        )
        color = _COLOR_BY_STATUS[args.status]

    payload = {
        "schemaVersion": 1,
        "label": args.label,
        "message": message,
        "color": color,
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
