"""End-to-end smoke test for the 5-year-lookback demo (PR-LOOKBACK-3).

Drives the three legs the runbook stitches together:

1. ``scripts/generate_lookback_dataset.py`` produces month-end slices
   under both ``parquet/`` and ``csv/`` subdirectories.
2. ``aml run`` against one slice produces a deterministic
   ``decisions_hash`` in ``manifest.json``.
3. ``aml equivalence`` against the run's ``alerts/*.jsonl`` and a tiny
   hand-crafted ``legacy-alerts.csv`` produces the expected
   MATCH / NEW_ONLY / LEGACY_ONLY classification counts.

Tagged ``@pytest.mark.slow`` because the 3-month generation + one
``aml run`` invocation takes ~3-5s end-to-end. The smoke test is the
last line of defence — if the demo command surface drifts away from the
runbook, this test fires.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aml_framework.cli import app

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOKBACK_SPEC = REPO_ROOT / "examples" / "community_bank_lookback" / "aml.yaml"
GENERATOR_SCRIPT = REPO_ROOT / "scripts" / "generate_lookback_dataset.py"


# Skip the whole module in environments that can't run the demo end-to-
# end — codex P1 review on PR-LOOKBACK-3: the default unit-tests CI job
# installs only `[dev]` (no pyarrow), and the docker-build job runs
# `pytest tests/` inside an image that doesn't `COPY scripts/`. The
# `slow` marker by itself does NOT skip tests — pytest still collects +
# runs them — so we gate via runtime probes. The full smoke test fires
# under `make ci-coverage` (which installs `[dev,dashboard]`) and
# under any developer-loop pytest run from a real checkout.
_PYARROW_AVAILABLE = True
try:
    import pyarrow  # noqa: F401
except ImportError:
    _PYARROW_AVAILABLE = False

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not GENERATOR_SCRIPT.exists(),
        reason="scripts/generate_lookback_dataset.py not present in this checkout "
        "(e.g. Docker image build that excludes scripts/)",
    ),
    pytest.mark.skipif(
        not _PYARROW_AVAILABLE,
        reason="pyarrow not installed (lookback dataset generator's default "
        "--formats both writes parquet); install `[dashboard]` extras to run",
    ),
]


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _generate_dataset(tmp_path: Path) -> Path:
    """Run the generator for 3 months ending 2025-12-31. Returns the out dir.

    3 months is the smallest range that still exercises the loop +
    manifest aggregation; running fewer would skip the multi-month
    code path. Keeps the test under ~5s on a laptop.
    """
    out_dir = tmp_path / "data"
    result = subprocess.run(
        [
            sys.executable,
            str(GENERATOR_SCRIPT),
            "--months",
            "3",
            "--end",
            "2025-12-31",
            "--out",
            str(out_dir),
            "--seed",
            "42",
            "--spec",
            str(LOOKBACK_SPEC),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"generate_lookback_dataset.py failed (exit={result.returncode})\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return out_dir


class TestLookbackDemoSmoke:
    def test_generator_produces_manifest_with_three_months(self, tmp_path: Path) -> None:
        """Generator wrote the manifest + per-month slice dirs."""
        out_dir = _generate_dataset(tmp_path)
        manifest_path = out_dir / "_manifest.json"
        assert manifest_path.exists(), f"missing {manifest_path}"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["month_count"] == 3
        assert manifest["months"][-1] == "2025-12"
        # Both formats should be present per month (default --formats both).
        assert (out_dir / "parquet" / "2025-12" / "txn.parquet").exists()
        assert (out_dir / "csv" / "2025-12" / "customer.csv").exists()

        # Row counts in the manifest match the contract-projected output.
        last = manifest["row_counts"][-1]
        assert last["month"] == "2025-12"
        # Lookback spec declares 4 channel enum values; synthetic generator
        # emits ~1220 txns/month after the channel filter. Manifest mirrors
        # whatever the script produced; just assert it's non-zero so the
        # test doesn't pin an exact count (the generator's planted-positive
        # band may drift across releases).
        assert last["txn"] > 0
        assert last["customer"] > 0

    def test_run_then_equivalence_against_tiny_legacy_csv(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Full demo loop end-to-end: generate → run → equivalence."""
        out_dir = _generate_dataset(tmp_path)
        parquet_slice = out_dir / "parquet" / "2025-12"
        artifacts = tmp_path / "artifacts"

        # Leg 2: aml run against the December slice. We use the CliRunner
        # for the engine invocation so the test stays in-process and a
        # stack trace from a regression surfaces in pytest output. The
        # alternative — `subprocess.run([..., "aml", "run", ...])` — would
        # mask exceptions behind the typer exit-code wrapper.
        run_result = runner.invoke(
            app,
            [
                "run",
                str(LOOKBACK_SPEC),
                "--as-of",
                "2026-01-01T00:00:00",
                "--data-source",
                "parquet",
                "--data-dir",
                str(parquet_slice),
                "--seed",
                "42",
                "--artifacts",
                str(artifacts),
            ],
        )
        assert run_result.exit_code == 0, f"`aml run` crashed:\nstdout:\n{run_result.output}"

        # The runner writes one run-<ISO> subdir under --artifacts.
        run_dirs = sorted(artifacts.glob("run-*"))
        assert len(run_dirs) == 1, f"expected exactly one run dir, got {run_dirs}"
        run_dir = run_dirs[0]
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        decisions_hash = manifest.get("decisions_hash", "")
        # Determinism contract — the exact hash is pinned by
        # test_run_is_reproducible in tests/test_engine.py; this smoke
        # test only confirms the demo *runs* end-to-end and emits a
        # well-formed hash. Don't hard-code the value here.
        assert isinstance(decisions_hash, str)
        assert len(decisions_hash) == 64
        assert all(c in "0123456789abcdef" for c in decisions_hash)

        # Find a real (customer_id, window_start, window_end, rule_id)
        # tuple from the run's alerts so the legacy CSV can produce a
        # known MATCH. Without a real alert to pair against, the test
        # would only exercise LEGACY_ONLY + NEW_ONLY.
        #
        # Codex pass 5 P2: use `unmask_alerts()` instead of reading
        # `alerts/*.jsonl` directly so the anchor's `customer_id` is
        # always plaintext. Under `AML_PII_MASKING=1`, the raw JSONL
        # carries hashed IDs; the CLI's `aml equivalence` un-hashes
        # via `unmask_alerts()` before joining. If the test wrote the
        # raw hash to the legacy CSV, the "MATCH" would only occur by
        # coincidence (plaintext vs hash never matches).
        from aml_framework.engine.audit import unmask_alerts

        alerts_dir = run_dir / "alerts"
        assert alerts_dir.exists()
        unmasked = unmask_alerts(run_dir)
        anchor: dict | None = None
        anchor_rule: str | None = None
        for rule_id, rows in sorted(unmasked.items()):
            for row in rows:
                # Need the canonical cell-key fields to write a paired
                # legacy row. Some custom_sql alerts in the spec may
                # omit window_start/window_end; skip those.
                if all(
                    row.get(k) is not None for k in ("customer_id", "window_start", "window_end")
                ):
                    anchor = row
                    anchor_rule = rule_id
                    break
            if anchor is not None:
                break
        assert anchor is not None and anchor_rule is not None, (
            "expected at least one alert with the canonical (customer_id, "
            "window_start, window_end) keys to anchor the equivalence test"
        )

        # Leg 3: build the tiny legacy CSV — three rows produce a known
        # MATCH + LEGACY_ONLY + (implicit) NEW_ONLY split. NEW_ONLY
        # comes for free because the run emits dozens of alerts and the
        # legacy CSV only references one of them.
        legacy_csv = tmp_path / "legacy-alerts.csv"
        legacy_csv.write_text(
            "customer_id,period_start,period_end,rule_id_legacy,severity\n"
            # MATCH — same (customer, period, rule) as the anchor alert.
            f"{anchor['customer_id']},{anchor['window_start']},{anchor['window_end']},"
            f"LEGACY_{anchor_rule.upper()},high\n"
            # LEGACY_ONLY — a customer / rule the engine didn't alert on.
            "C9999_NOT_REAL,2025-12-01T00:00:00,2025-12-31T23:59:59,"
            "LEGACY_NOT_REAL,medium\n"
            "C9998_NOT_REAL,2025-12-01T00:00:00,2025-12-31T23:59:59,"
            "LEGACY_NOT_REAL,low\n",
            encoding="utf-8",
        )

        # Rule-map YAML: pair the anchor's new rule_id with the synthetic
        # legacy id we wrote above. The two "NOT_REAL" rows have no new
        # counterpart on purpose, so they bucket as LEGACY_ONLY.
        rule_map_yaml = tmp_path / "rule-map.yaml"
        rule_map_yaml.write_text(f"{anchor_rule}: LEGACY_{anchor_rule.upper()}\n", encoding="utf-8")

        out_json = tmp_path / "equivalence.json"
        out_md = tmp_path / "equivalence.md"
        # Intentionally omit --spec to exercise the codex-pass-2 fix:
        # the CLI must auto-load `spec_snapshot.yaml` from the run dir so
        # `rule_severities` populates and same-cell severity mismatches
        # surface as DIFF (not silent MATCH). The run dir always carries
        # `spec_snapshot.yaml` from `engine/runner.py`.
        eq_result = runner.invoke(
            app,
            [
                "equivalence",
                str(run_dir),
                "--legacy",
                str(legacy_csv),
                "--rule-map",
                str(rule_map_yaml),
                "--out",
                str(out_json),
                "--markdown",
                str(out_md),
            ],
        )
        assert eq_result.exit_code == 0, f"`aml equivalence` crashed:\nstdout:\n{eq_result.output}"
        assert out_json.exists()
        assert out_md.exists()

        cells = json.loads(out_json.read_text(encoding="utf-8"))
        # Group by classification — the table-driven assertion is what we
        # care about (one MATCH, two LEGACY_ONLY, ≥1 NEW_ONLY).
        by_class: dict[str, int] = {}
        for cell in cells:
            by_class[cell["classification"]] = by_class.get(cell["classification"], 0) + 1

        # Anchor row → MATCH.
        assert by_class.get("MATCH", 0) >= 1, (
            f"expected at least 1 MATCH; got {by_class}\noutput:\n{eq_result.output}"
        )
        # Two synthetic "NOT_REAL" rows → LEGACY_ONLY (no engine alert
        # against C9999/C9998 because they're not in the synthetic dataset).
        assert by_class.get("LEGACY_ONLY", 0) >= 2, (
            f"expected at least 2 LEGACY_ONLY; got {by_class}\noutput:\n{eq_result.output}"
        )
        # The run produces many more alerts than the 1 we paired —
        # everything else buckets as NEW_ONLY.
        assert by_class.get("NEW_ONLY", 0) >= 1, (
            f"expected at least 1 NEW_ONLY; got {by_class}\noutput:\n{eq_result.output}"
        )

        # Markdown report has the counts table header.
        md_text = out_md.read_text(encoding="utf-8")
        assert "# Equivalence report" in md_text
        assert "| MATCH |" in md_text
        assert "| LEGACY_ONLY |" in md_text
