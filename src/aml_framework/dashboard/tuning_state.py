"""Helpers for the Tuning Lab Streamlit page.

Every piece of non-trivial logic lives here so the page stays
declarative and the helpers can be unit-tested without importing
streamlit (CI's unit-test job doesn't install dashboard deps).
"""

from __future__ import annotations

import csv
import io
from typing import Any

import yaml

from aml_framework.engine.tuning import TuningRun
from aml_framework.spec.models import AMLSpec


def parse_labels_csv(csv_text: str) -> dict[str, bool]:
    """Parse a labels CSV (columns: customer_id, is_true_positive).

    Tolerates 1/0/true/false/yes/no values for the flag column. Empty
    or missing rows are skipped silently.
    """
    labels: dict[str, bool] = {}
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        cid = (row.get("customer_id") or "").strip()
        if not cid:
            continue
        flag = str(row.get("is_true_positive", "")).strip().lower()
        labels[cid] = flag in ("1", "true", "yes", "y", "t")
    return labels


def rules_with_tuning_grid(spec: AMLSpec) -> list[str]:
    """Return ids of rules that declare a `tuning_grid` — the page
    only offers tunable rules in its selector."""
    return [r.id for r in spec.rules if r.tuning_grid]


def scenarios_to_table(run: TuningRun) -> list[dict[str, Any]]:
    """Flatten TuningRun scenarios for st.dataframe rendering.

    Stable column order; deltas displayed as signed strings; metrics
    only emitted when labels were supplied (precision/recall/f1
    columns omitted when None).
    """
    has_metrics = any(s.precision is not None for s in run.scenarios)
    out: list[dict[str, Any]] = []
    for s in run.scenarios:
        row: dict[str, Any] = {
            "params": _format_params(s.parameters),
            "alerts": s.alert_count,
            "delta_alerts": s.alert_count - run.baseline.alert_count,
            "added_vs_baseline": s.added_vs_baseline,
            "removed_vs_baseline": s.removed_vs_baseline,
        }
        if has_metrics:
            row["precision"] = round(s.precision, 4) if s.precision is not None else None
            row["recall"] = round(s.recall, 4) if s.recall is not None else None
            row["f1"] = round(s.f1, 4) if s.f1 is not None else None
        out.append(row)
    return out


def _format_params(params: dict[str, Any]) -> str:
    """Render parameter dict as `path=value, path=value` for the table cell."""
    parts: list[str] = []
    for k, v in sorted(params.items()):
        if isinstance(v, dict) and len(v) == 1:
            op, val = next(iter(v.items()))
            parts.append(f"{_short(k)} {op}={val}")
        else:
            parts.append(f"{_short(k)}={v}")
    return ", ".join(parts)


def _short(path: str) -> str:
    """`logic.having.count` → `count` for tighter table cells."""
    return path.rsplit(".", 1)[-1] if "." in path else path


def best_scenario(run: TuningRun, metric: str = "f1") -> int | None:
    """Index of the scenario with the highest `metric` value, or None."""
    candidates = [(i, getattr(s, metric, None)) for i, s in enumerate(run.scenarios)]
    candidates = [(i, v) for i, v in candidates if v is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda iv: iv[1])[0]


def render_spec_patch(rule_id: str, parameters: dict[str, Any]) -> str:
    """Render the chosen scenario as a YAML spec patch the MLRO can apply.

    The output is intentionally minimal — only the rule fragment with
    the patched fields, matching the existing `aml.yaml` shape. An
    operator drops it into the spec under `rules:` to promote.
    """
    fragment: dict[str, Any] = {"id": rule_id}
    for path, value in parameters.items():
        _set_nested(fragment, path.split("."), value)
    rule_block = {"rules": [fragment]}
    header = (
        "# Spec patch produced by the Tuning Lab.\n"
        "# Apply by merging the patched fields into the existing rule\n"
        f"# `{rule_id}` in your aml.yaml. Re-run `aml validate` afterward.\n"
    )
    return header + yaml.safe_dump(rule_block, sort_keys=False)


def _set_nested(d: dict[str, Any], path_parts: list[str], value: Any) -> None:
    head = path_parts[0]
    if len(path_parts) == 1:
        d[head] = value
        return
    if head not in d or not isinstance(d[head], dict):
        d[head] = {}
    _set_nested(d[head], path_parts[1:], value)
