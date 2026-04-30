"""Sibling-run-dir history helpers for sparklines + delta-vs-prior-run.

The Executive Dashboard hero KPIs render trend sparklines under each
metric. The data substrate for those is the set of run directories the
engine has produced over time — typically `runs/<timestamp>/` next to
the active run.

Why a separate module
---------------------
- The dashboard pages stay declarative; this module owns the
  filesystem walk + JSON parse.
- Unit-testable without Streamlit (pure stdlib).
- Cached at the module level — Streamlit's `@st.cache_data` is fine
  but adds a Streamlit dependency that tests would have to mock; a
  plain function returning a dataclass is simpler and re-runs are
  cheap (≤ 16 file reads per call).

What it returns
---------------
- `recent_runs(active_run_dir, n=8)` → list of `Path` (oldest→newest,
  active included as the last element)
- `metric_value_history(run_dirs, metric_id)` → list of `float`
  parallel to `run_dirs`; missing values become `None`
- `manifest_field_history(run_dirs, field)` → same shape, for top-level
  manifest fields (`total_alerts`, `output_hash`, etc.)
- `delta_pct(history)` → signed pct change of the last vs. the
  second-to-last value, or `None` when fewer than 2 numeric values.

The helpers degrade gracefully — missing `manifest.json`, malformed
metrics, or directories without sibling runs all return empty lists
or `None` rather than raise. The dashboard is the consumer; it must
never crash because a prior run got moved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def recent_runs(active_run_dir: Path, n: int = 8) -> list[Path]:
    """Return up to N sibling run directories sorted oldest→newest.

    The active run is included as the last element; older runs come
    first. If `active_run_dir` has no siblings, returns just
    `[active_run_dir]`. If `active_run_dir` doesn't exist, returns `[]`.
    """
    active_run_dir = Path(active_run_dir)
    if not active_run_dir.exists():
        return []
    parent = active_run_dir.parent
    if not parent.exists():
        return [active_run_dir]

    siblings = []
    for child in parent.iterdir():
        if not child.is_dir():
            continue
        # Only consider dirs that look like real runs (contain a manifest).
        if (child / "manifest.json").exists():
            siblings.append(child)
        elif child == active_run_dir:
            # Include the active run even if its manifest hasn't been
            # written yet — sparklines should at least render the
            # current value at the rightmost end of the line.
            siblings.append(child)

    if not siblings:
        return [active_run_dir]

    siblings.sort(key=lambda p: p.stat().st_mtime)
    return siblings[-n:]


def _load_manifest(run_dir: Path) -> dict[str, Any] | None:
    """Return parsed manifest or None on any error."""
    path = run_dir / "manifest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def manifest_field_history(run_dirs: list[Path], field: str) -> list[float | None]:
    """Return numeric values of a top-level manifest field across runs.

    Parallel-indexed with `run_dirs`. Non-numeric or missing values
    become `None`. Useful for `total_alerts`, run counts, etc.
    """
    out: list[float | None] = []
    for d in run_dirs:
        manifest = _load_manifest(d)
        if manifest is None:
            out.append(None)
            continue
        v = manifest.get(field)
        if isinstance(v, (int, float)):
            out.append(float(v))
        else:
            out.append(None)
    return out


def metric_value_history(run_dirs: list[Path], metric_id: str) -> list[float | None]:
    """Return the value of one metric across runs.

    Reads `metrics.json` if present, else falls back to `manifest.json`'s
    `metrics` array. Missing or non-numeric → `None` for that run.
    """
    out: list[float | None] = []
    for d in run_dirs:
        # Prefer explicit metrics.json — it's the engine's primary
        # output for metric details.
        metrics_path = d / "metrics.json"
        rec: dict[str, Any] | None = None
        if metrics_path.exists():
            try:
                metrics_data = json.loads(metrics_path.read_text(encoding="utf-8"))
                if isinstance(metrics_data, list):
                    for m in metrics_data:
                        if isinstance(m, dict) and m.get("id") == metric_id:
                            rec = m
                            break
                elif isinstance(metrics_data, dict):
                    rec = metrics_data.get(metric_id)
            except (json.JSONDecodeError, OSError):
                rec = None

        if rec is None:
            # Fallback: manifest may have a metrics array
            manifest = _load_manifest(d)
            if manifest:
                metrics_arr = manifest.get("metrics")
                if isinstance(metrics_arr, list):
                    for m in metrics_arr:
                        if isinstance(m, dict) and m.get("id") == metric_id:
                            rec = m
                            break

        if rec is None:
            out.append(None)
            continue

        v = rec.get("value")
        if isinstance(v, (int, float)):
            out.append(float(v))
        else:
            out.append(None)
    return out


def delta_pct(history: list[float | None]) -> float | None:
    """Signed pct change of the last vs. second-to-last numeric value.

    Returns ``None`` when fewer than 2 numeric values are present, or
    when the second-to-last value is zero (avoid division by zero;
    "100% increase from zero" is not meaningful for board-pack
    framing).
    """
    numeric = [v for v in history if v is not None]
    if len(numeric) < 2:
        return None
    current = numeric[-1]
    previous = numeric[-2]
    if previous == 0:
        return None
    return ((current - previous) / abs(previous)) * 100.0


def numeric_only(history: list[float | None]) -> list[float]:
    """Drop ``None`` entries — useful for passing to the sparkline."""
    return [v for v in history if v is not None]
