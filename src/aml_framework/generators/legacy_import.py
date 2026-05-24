"""PR-A1 — legacy rule inventory + import wizard.

Process problem this solves
---------------------------
When a bank decides to move off SAS / Oracle FCCM / IMS / Actimize /
Mantas, the first 2-3 weeks are spent staring at a legacy rule export
(usually a CSV or JSON dump) and re-typing each detector into the
`aml.yaml` spec by hand. That is mechanical work that should be
automated. This module turns the legacy dump into a *starter* AML spec
block — every rule gets a stub, every threshold is preserved, every
human-described rule is flagged with a TODO so the operator knows
where manual conversion is still required.

The wizard is intentionally **tolerant**: legacy exports never have a
clean schema. A SAS dump might be `(rule_id, name, sql_text)`; an
Actimize export might be `(rule_id, threshold_block_json)`; an IMS
spreadsheet might have a single `narrative` column. Each is handled,
malformed rows are surfaced as warnings (not crashes), and the
`inventory_summary` rolls up exactly how many rules are ready-to-
import vs how many need manual attention.

What this module is NOT
-----------------------
- It does not *execute* legacy SQL. The framework's reference engine
  has its own discriminated rule logic; legacy SQL is preserved as
  `logic.type: custom_sql` and left as-is — the operator is expected
  to tune and re-validate against the data contracts.
- It does not infer `escalate_to`, `severity`, or `regulation_refs`.
  Those are governance decisions that the legacy system rarely
  encodes. The stub fills them with safe defaults + a TODO comment
  the spec author replaces.
- It is not a "spec writer". The output is a *skeleton* the operator
  iterates on; it intentionally fails `aml validate` if poured raw
  into the engine (TODO placeholders are syntactically valid but
  semantically incomplete — by design).

Design choices
--------------
- Pydantic v2 with `frozen=True` + `extra="forbid"` so a row is
  immutable once parsed and a malformed legacy export with extra
  columns surfaces as a validation error instead of silent drift.
- Best-effort CSV header normalisation (lowercase, underscores) so
  the same code handles `rule_id` / `Rule ID` / `RULE_ID` / `rule id`.
- JSON loader accepts both `[{...}, {...}]` and `{"rules": [...]}`
  shapes — the two most common dumps in the wild.
- `to_aml_rule_stub` always returns a dict with a `logic` block the
  schema will accept (so the operator can immediately run
  `aml validate` to see what's missing) — even when the input row is
  pure narrative, the stub emits an `aggregation_window` placeholder
  with a TODO so the validator points at the right rule.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    """Match the spec models' frozen/extra-forbid posture."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class LegacyRuleRow(_Base):
    """One row from a legacy rule export.

    Exactly one of `legacy_sql`, `threshold_block`, or `narrative` is
    typically populated; all three may be present in unusual dumps.
    A row with none of them is still a valid object (e.g. a name-only
    placeholder) but `to_aml_rule_stub` will classify it as
    needs-manual.
    """

    rule_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    legacy_sql: str | None = None
    threshold_block: dict[str, Any] | None = None
    narrative: str | None = None
    regulator_refs: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing helpers — both formats normalise to LegacyRuleRow lists.
# ---------------------------------------------------------------------------


_CSV_ALIASES: dict[str, str] = {
    # rule id
    "rule_id": "rule_id",
    "ruleid": "rule_id",
    "rule": "rule_id",
    "id": "rule_id",
    "scenario_id": "rule_id",
    # name / label
    "name": "name",
    "rule_name": "name",
    "scenario_name": "name",
    "label": "name",
    "title": "name",
    # sql
    "sql": "legacy_sql",
    "sql_string": "legacy_sql",
    "sql_text": "legacy_sql",
    "legacy_sql": "legacy_sql",
    "query": "legacy_sql",
    # thresholds (json blob)
    "threshold": "threshold_block",
    "thresholds": "threshold_block",
    "threshold_block": "threshold_block",
    "threshold_json": "threshold_block",
    "parameters": "threshold_block",
    "params": "threshold_block",
    # narrative
    "narrative": "narrative",
    "description": "narrative",
    "rule_description": "narrative",
    "notes": "narrative",
    "comment": "narrative",
    # regulator refs
    "regulator_refs": "regulator_refs",
    "regulator_ref": "regulator_refs",
    "regulation_refs": "regulator_refs",
    "regulations": "regulator_refs",
    "citations": "regulator_refs",
}


@dataclass(frozen=True)
class ParseWarning:
    """A non-fatal issue surfaced by the parser.

    Surfaced separately from the parsed rows so the CLI can render a
    "your dump had N problems" summary without dropping the good rows.
    """

    row_index: int
    rule_id: str | None
    reason: str


def _normalise_header(header: str) -> str | None:
    """Map a legacy column name to a `LegacyRuleRow` field, or None."""
    key = header.strip().lower().replace(" ", "_").replace("-", "_")
    return _CSV_ALIASES.get(key)


def _coerce_threshold_block(raw: Any) -> dict[str, Any] | None:
    """Accept dict (already parsed) or JSON string. Returns None on empty."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw if raw else None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"threshold_block is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("threshold_block must parse to a JSON object")
        return parsed if parsed else None
    raise ValueError(f"threshold_block has unsupported type: {type(raw).__name__}")


def _coerce_regulator_refs(raw: Any) -> list[str]:
    """Accept list, pipe/semicolon/comma-separated string, or empty."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        # Try JSON list first, then fall back to common delimiters.
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except (json.JSONDecodeError, ValueError):
                pass
        for sep in ("|", ";", ","):
            if sep in text:
                return [part.strip() for part in text.split(sep) if part.strip()]
        return [text]
    return []


def _row_from_mapping(
    raw: dict[str, Any], *, row_index: int
) -> tuple[LegacyRuleRow | None, ParseWarning | None]:
    """Build a row from a normalised mapping. Never raises — returns warnings."""
    rule_id = (raw.get("rule_id") or "").strip() if isinstance(raw.get("rule_id"), str) else ""
    if not rule_id and raw.get("rule_id") is not None:
        rule_id = str(raw["rule_id"]).strip()
    name_raw = raw.get("name")
    name = str(name_raw).strip() if name_raw is not None else ""

    if not rule_id:
        return None, ParseWarning(row_index, None, "missing rule_id")
    if not name:
        # Fall back to rule_id so a name-less dump still imports — the
        # operator can rename in the spec.
        name = rule_id

    legacy_sql_raw = raw.get("legacy_sql")
    legacy_sql = (
        legacy_sql_raw.strip()
        if isinstance(legacy_sql_raw, str) and legacy_sql_raw.strip()
        else None
    )

    try:
        threshold_block = _coerce_threshold_block(raw.get("threshold_block"))
    except ValueError as exc:
        return None, ParseWarning(row_index, rule_id, str(exc))

    narrative_raw = raw.get("narrative")
    narrative = (
        narrative_raw.strip() if isinstance(narrative_raw, str) and narrative_raw.strip() else None
    )

    regulator_refs = _coerce_regulator_refs(raw.get("regulator_refs"))

    try:
        row = LegacyRuleRow(
            rule_id=rule_id,
            name=name,
            legacy_sql=legacy_sql,
            threshold_block=threshold_block,
            narrative=narrative,
            regulator_refs=regulator_refs,
        )
    except Exception as exc:  # pragma: no cover — defensive, validation above is tight
        return None, ParseWarning(row_index, rule_id, f"pydantic rejected row: {exc}")
    return row, None


@dataclass(frozen=True)
class ParseResult:
    """Container so callers see warnings alongside good rows."""

    rows: list[LegacyRuleRow]
    warnings: list[ParseWarning]


def parse_legacy_csv(path: Path) -> list[LegacyRuleRow]:
    """Parse a legacy CSV dump into LegacyRuleRow objects.

    Tolerant of header casing/spacing and ignores columns that don't
    map to a known field. Malformed rows become warnings (visible via
    `parse_legacy_csv_with_warnings`) instead of crashing the parse.
    """
    return parse_legacy_csv_with_warnings(path).rows


def parse_legacy_csv_with_warnings(path: Path) -> ParseResult:
    """Variant that also returns parse warnings for the CLI summary."""
    rows: list[LegacyRuleRow] = []
    warnings: list[ParseWarning] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return ParseResult(rows=[], warnings=[ParseWarning(0, None, "empty CSV")])
        mapping = {name: _normalise_header(name) for name in reader.fieldnames}
        if not any(mapping.values()):
            return ParseResult(
                rows=[],
                warnings=[ParseWarning(0, None, "no recognised columns in CSV header")],
            )
        for idx, raw_row in enumerate(reader, start=1):
            normalised: dict[str, Any] = {}
            for original, field in mapping.items():
                if field is None:
                    continue
                value = raw_row.get(original)
                if value is None:
                    continue
                normalised[field] = value
            row, warning = _row_from_mapping(normalised, row_index=idx)
            if row is not None:
                rows.append(row)
            if warning is not None:
                warnings.append(warning)
    return ParseResult(rows=rows, warnings=warnings)


def parse_legacy_json(path: Path) -> list[LegacyRuleRow]:
    """Parse a legacy JSON dump. Accepts a top-level list or {'rules': [...]}."""
    return parse_legacy_json_with_warnings(path).rows


def parse_legacy_json_with_warnings(path: Path) -> ParseResult:
    """Variant that also returns parse warnings for the CLI summary."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        if "rules" in payload and isinstance(payload["rules"], list):
            entries = payload["rules"]
        else:
            return ParseResult(
                rows=[],
                warnings=[
                    ParseWarning(
                        0,
                        None,
                        "JSON object missing 'rules' key — expected list or {'rules': [...]}",
                    )
                ],
            )
    elif isinstance(payload, list):
        entries = payload
    else:
        return ParseResult(
            rows=[],
            warnings=[
                ParseWarning(0, None, f"JSON root is {type(payload).__name__}, expected list")
            ],
        )

    rows: list[LegacyRuleRow] = []
    warnings: list[ParseWarning] = []
    for idx, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            warnings.append(
                ParseWarning(idx, None, f"entry is {type(entry).__name__}, expected object")
            )
            continue
        # JSON dumps typically already have the right field names, but
        # normalise so callers can supply `sql_text` etc. as in CSVs.
        normalised: dict[str, Any] = {}
        for key, value in entry.items():
            field = _normalise_header(str(key))
            if field is None:
                continue
            normalised[field] = value
        row, warning = _row_from_mapping(normalised, row_index=idx)
        if row is not None:
            rows.append(row)
        if warning is not None:
            warnings.append(warning)
    return ParseResult(rows=rows, warnings=warnings)


# ---------------------------------------------------------------------------
# Stub rendering — turn a LegacyRuleRow into an AML-spec rule dict.
# ---------------------------------------------------------------------------


_TODO_REGULATION = {
    "citation": "TODO: cite regulation",
    "description": "TODO: replace with the regulation this rule satisfies.",
}


def _regulation_refs_for(row: LegacyRuleRow) -> list[dict[str, str]]:
    if not row.regulator_refs:
        return [dict(_TODO_REGULATION)]
    return [
        {"citation": ref, "description": f"Imported from legacy export ({ref})."}
        for ref in row.regulator_refs
    ]


def to_aml_rule_stub(row: LegacyRuleRow) -> dict[str, Any]:
    """Produce a dict shaped like one entry of `rules:` in the AML spec.

    - SQL-bearing rows → `logic.type: custom_sql`, SQL preserved verbatim.
    - threshold-bearing rows → `logic.type: aggregation_window` skeleton
      with the legacy threshold block tucked into `having` so the
      operator can see what the source thresholds were.
    - narrative-only / empty rows → `logic.type: aggregation_window`
      placeholder with a `# TODO: convert narrative` marker and the
      narrative captured under `tags` so it survives the import.
    """
    stub: dict[str, Any] = {
        "id": row.rule_id,
        "name": row.name,
        "severity": "medium",
        "regulation_refs": _regulation_refs_for(row),
        "escalate_to": "l2_review",
        "evidence": [],
        "tags": ["legacy_import"],
    }

    if row.legacy_sql is not None:
        stub["logic"] = {"type": "custom_sql", "sql": row.legacy_sql}
        return stub

    if row.threshold_block is not None:
        having = (
            row.threshold_block.get("having") if isinstance(row.threshold_block, dict) else None
        )
        stub["logic"] = {
            "type": "aggregation_window",
            "source": "TODO_source_contract",
            "group_by": ["customer_id"],
            "window": "30d",
            "having": having if isinstance(having, dict) else row.threshold_block,
        }
        return stub

    # Narrative-only or empty — emit a placeholder so `aml validate`
    # points the operator at the right rule.
    stub["logic"] = {
        "type": "aggregation_window",
        "source": "TODO_source_contract",
        "group_by": ["customer_id"],
        "window": "30d",
        "having": {"count": {"gte": 1}},
    }
    if row.narrative:
        stub["tags"] = ["legacy_import", "needs_manual_conversion"]
        # Persist the human prose so it isn't lost between formats.
        stub["business_intent"] = f"# TODO: convert narrative -> {row.narrative}"
    else:
        stub["tags"] = ["legacy_import", "needs_manual_conversion"]
        stub["business_intent"] = "# TODO: convert narrative -> (none supplied)"
    return stub


def classify_row(row: LegacyRuleRow) -> str:
    """Return one of `ready_sql`, `ready_threshold`, or `needs_manual`."""
    if row.legacy_sql is not None:
        return "ready_sql"
    if row.threshold_block is not None:
        return "ready_threshold"
    return "needs_manual"


def inventory_summary(rows: list[LegacyRuleRow]) -> dict[str, Any]:
    """Roll up a parsed inventory into shape-counts + readiness buckets.

    Shape:
      {
        "total": int,
        "by_shape": {"sql": int, "threshold": int, "narrative": int, "empty": int},
        "ready_to_import": int,
        "needs_manual": int,
        "missing_regulator_refs": int,
        "duplicate_rule_ids": [str, ...],
      }
    """
    counts = {"sql": 0, "threshold": 0, "narrative": 0, "empty": 0}
    ready = 0
    manual = 0
    missing_regs = 0
    seen: dict[str, int] = {}
    duplicates: list[str] = []
    for row in rows:
        if row.legacy_sql is not None:
            counts["sql"] += 1
            ready += 1
        elif row.threshold_block is not None:
            counts["threshold"] += 1
            ready += 1
        elif row.narrative is not None:
            counts["narrative"] += 1
            manual += 1
        else:
            counts["empty"] += 1
            manual += 1
        if not row.regulator_refs:
            missing_regs += 1
        seen[row.rule_id] = seen.get(row.rule_id, 0) + 1
    for rule_id, count in seen.items():
        if count > 1 and rule_id not in duplicates:
            duplicates.append(rule_id)
    return {
        "total": len(rows),
        "by_shape": counts,
        "ready_to_import": ready,
        "needs_manual": manual,
        "missing_regulator_refs": missing_regs,
        "duplicate_rule_ids": sorted(duplicates),
    }


def build_spec_skeleton(rows: list[LegacyRuleRow]) -> dict[str, Any]:
    """Wrap a list of stubs in the minimal envelope `aml validate` expects.

    Returns a dict ready to be `yaml.safe_dump`-ed. The envelope is
    intentionally thin — the operator is expected to merge it into
    their existing spec, not run it raw.
    """
    return {
        "version": 1,
        "program": {
            "name": "TODO_program_name",
            "jurisdiction": "TODO",
            "regulator": "TODO",
            "owner": "TODO",
            "effective_date": "2026-01-01",
        },
        "data_contracts": [],
        "rules": [to_aml_rule_stub(row) for row in rows],
        "workflow": {"queues": []},
        "reporting": {"forms": {}},
    }
