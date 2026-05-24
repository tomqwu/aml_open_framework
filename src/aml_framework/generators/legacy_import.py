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
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# The AML spec restricts `Rule.id` to `^[a-z][a-z0-9_]*$`. Legacy
# platforms commonly emit IDs like `R001`, `scenario-1`, or
# `CASH.STRUCT.01` that don't fit; `_sanitise_rule_id` rewrites the
# string into a schema-safe form so `aml validate` accepts the
# imported stub once the operator fills in the other TODO fields.
# The original legacy ID is preserved verbatim as a tag on the stub
# so it survives the import for traceability.
_SAFE_RULE_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_LEGACY_ID_PREFIX = "legacy_"

# Mirrors `generators/sql.py:_HAVING_AGGREGATES` — the engine raises
# "unsupported having metric '<name>'" for anything outside this set
# at compile time. Used to filter derived `having` so a vendor-blob
# sibling like `parameters` doesn't sneak in and break the rule at
# runtime.
_RECOGNISED_HAVING_METRICS = frozenset(
    {"count", "sum_amount", "max_amount", "min_amount", "avg_amount"}
)


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
    """Map a legacy column name to a `LegacyRuleRow` field, or None.

    Strips a UTF-8 BOM (``﻿``) before matching so Excel-saved
    CSVs whose first header is `﻿frule_id` still hit the alias
    table — common enough in real legacy dumps that ignoring it would
    silently break the first row of every Excel export.
    """
    key = header.lstrip("﻿").strip().lower().replace(" ", "_").replace("-", "_")
    return _CSV_ALIASES.get(key)


# Aliases higher in this set lose to aliases lower in it when both
# appear in the same CSV header (e.g. `rule_id` + `id`). `rule_id`,
# `name`, etc. are the canonical names — they always win over the
# generic fallbacks. Anything not listed here is treated as
# tied-precedence and the first non-empty value wins.
_CANONICAL_FIELDS = frozenset(
    {"rule_id", "name", "legacy_sql", "threshold_block", "narrative", "regulator_refs"}
)


def _merge_aliases(mapping: dict[str, str | None], raw_row: dict[str, Any]) -> dict[str, Any]:
    """Collapse multiple aliased CSV columns into a single field map.

    When a CSV has both a canonical column (`rule_id`) and a generic
    alias (`id`) that maps to the same field, prefer the canonical
    column's value when non-empty. For two aliases that both map to
    the same field (neither canonical), the *first non-empty* value
    wins so later noisy columns can't overwrite an earlier good one.
    """
    out: dict[str, Any] = {}
    canonical_set: dict[str, bool] = {}
    for original, field in mapping.items():
        if field is None:
            continue
        value = raw_row.get(original)
        if value is None:
            continue
        # Treat empty strings as "missing" so a later column with a
        # real value can still populate the field.
        if isinstance(value, str) and not value.strip():
            continue
        is_canonical = original.strip().lower().replace(" ", "_").replace("-", "_") == field
        if field in out:
            # If we've already seen a canonical value, only a canonical
            # column can overwrite (and only the first canonical wins).
            if canonical_set.get(field):
                continue
            # Existing was non-canonical; canonical now → overwrite.
            if is_canonical:
                out[field] = value
                canonical_set[field] = True
            # Both non-canonical → keep the first.
            continue
        out[field] = value
        if is_canonical and field in _CANONICAL_FIELDS:
            canonical_set[field] = True
    return out


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
        # Skip None entries (a JSON dump can encode missing citations
        # as `[null]` — coercing those via `str(None)` would emit a
        # literal "None" citation and hide the missing-coverage flag
        # from `inventory_summary`).
        return [str(item).strip() for item in raw if item is not None and str(item).strip()]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        # Try JSON list first, then fall back to common delimiters.
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    # Skip None entries (`[null]` cells mirror the
                    # real-list None-skip above).
                    return [
                        str(item).strip()
                        for item in parsed
                        if item is not None and str(item).strip()
                    ]
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

    narrative_raw = raw.get("narrative")
    narrative = (
        narrative_raw.strip() if isinstance(narrative_raw, str) and narrative_raw.strip() else None
    )

    # SQL takes precedence over thresholds (per the documented stub
    # behaviour). When a row has both a usable SQL string AND a
    # malformed threshold cell, we keep the row + emit a warning
    # instead of dropping the SQL — legacy dumps frequently ship
    # parameter blobs alongside SQL, and a bad blob shouldn't lose
    # the importable detector. Likewise, a row with a usable
    # narrative + bad threshold is still importable as a manual-
    # conversion stub (we drop the threshold, keep the narrative).
    threshold_warning: ParseWarning | None = None
    try:
        threshold_block = _coerce_threshold_block(raw.get("threshold_block"))
    except ValueError as exc:
        threshold_block = None
        # Keep the row so migration completeness is preserved — a
        # malformed threshold cell shouldn't make a legacy rule
        # disappear from the skeleton. The operator sees the warning
        # via `aml inventory` and the resulting stub is flagged
        # `needs_manual_conversion`.
        if legacy_sql is not None:
            kept = "SQL"
        elif narrative is not None:
            kept = "narrative"
        else:
            kept = "rule_id only"
        threshold_warning = ParseWarning(
            row_index, rule_id, f"{exc}; kept {kept}, dropped threshold"
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
    return row, threshold_warning


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
    # `utf-8-sig` strips an Excel-emitted BOM on the first header so
    # otherwise-valid dumps don't silently break alias lookup.
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
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
            normalised = _merge_aliases(mapping, raw_row)
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
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as exc:
        # Mirror the CSV path's behaviour: surface a warning + return
        # an empty result instead of letting the JSON decoder's
        # traceback bubble up through the CLI.
        return ParseResult(
            rows=[],
            warnings=[ParseWarning(0, None, f"JSON decode failed: {exc}")],
        )
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
        # Use the same alias-collision resolver as CSV so a JSON
        # object with both `rule_id` and `id` keys can't silently
        # overwrite the canonical value with the alias.
        json_mapping: dict[str, str | None] = {
            str(key): _normalise_header(str(key)) for key in entry
        }
        normalised = _merge_aliases(json_mapping, {str(k): v for k, v in entry.items()})
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


def _coerce_window(value: Any) -> str:
    """Coerce a legacy `window` value into the AML spec's `^[0-9]+[smhd]$` shape.

    Common legacy shapes:
      - `30` (int days) → `"30d"`
      - `30.0` (float) → `"30d"`
      - `"30"` (string-of-int) → `"30d"`
      - `"30d"` (already valid) → unchanged
      - negative / non-finite / anything else → `"30d"` fallback so
        the operator gets a schema-valid skeleton, not a `-7d` value
        that fails the `^[0-9]+[smhd]$` pattern.
    """
    import math

    if isinstance(value, bool):
        return "30d"
    if isinstance(value, int):
        return f"{value}d" if value > 0 else "30d"
    if isinstance(value, float):
        if not math.isfinite(value) or value <= 0:
            return "30d"
        # Only accept floats that represent an exact positive integer
        # (e.g. `30.0`). Truncating `1.5` → `1d` silently shortens the
        # detector window and changes the imported rule's semantics;
        # fall back to `30d` so the operator notices and corrects.
        if not value.is_integer():
            return "30d"
        return f"{int(value)}d"
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"[0-9]+[smhd]", text):
            # Reject zero-length windows like `"0d"` / `"0h"` — see
            # the float-path comment above for why.
            if re.fullmatch(r"0+[smhd]", text):
                return "30d"
            return text
        if text.isdigit():
            if int(text) <= 0:
                return "30d"
            return f"{text}d"
    return "30d"


def _coerce_group_by(value: Any) -> list[str]:
    """Coerce a legacy `group_by` value into the AML spec's `list[str]` shape.

    Common legacy shapes:
      - `"customer_id"` → `["customer_id"]`
      - `"customer_id, account_id"` → `["customer_id", "account_id"]`
      - `["customer_id"]` (already valid) → unchanged
      - anything else → `["customer_id"]` fallback
    """
    if isinstance(value, list):
        # Skip None entries (`[null]` in a JSON dump would otherwise
        # stringify to the literal column name `"None"`, generating
        # a runtime-invalid grouping clause).
        out = [str(item).strip() for item in value if item is not None and str(item).strip()]
        return out if out else ["customer_id"]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ["customer_id"]
        for sep in (",", "|", ";"):
            if sep in text:
                parts = [part.strip() for part in text.split(sep) if part.strip()]
                # A delimiter-only string (`","`, `" ; "`) splits to
                # an empty list; the spec requires `min_length=1`, so
                # fall back to the default rather than emit an
                # invalid skeleton.
                return parts if parts else ["customer_id"]
        return [text]
    return ["customer_id"]


def _sanitise_rule_id(raw: str) -> str:
    """Rewrite a legacy ID into the AML spec's `^[a-z][a-z0-9_]*$` shape.

    The AML spec validates `Rule.id` against `^[a-z][a-z0-9_]*$`.
    Legacy IDs like `R001`, `scenario-1`, or `CASH.STRUCT.01` would
    fail validation even after the operator fills in the TODOs. We
    rewrite to lowercase, replace any non-`[a-z0-9_]` with `_`, and
    prefix with `legacy_` when the result would otherwise start with
    a digit. The original ID is preserved on the stub via a tag so
    nothing is lost.

    Already-valid IDs (incl. ones with trailing or repeated
    underscores like `rule_` or `cash__struct_01`) pass through
    untouched — collapsing `__` to `_` would create artificial
    collisions with a different, legitimate ID.
    """
    if _SAFE_RULE_ID_RE.match(raw):
        return raw
    safe = re.sub(r"[^a-z0-9_]", "_", raw.lower())
    safe = re.sub(r"_+", "_", safe).strip("_")
    if not safe:
        return f"{_LEGACY_ID_PREFIX}unknown"
    if not _SAFE_RULE_ID_RE.match(safe):
        # Must start with a letter — prefix with `legacy_`.
        safe = f"{_LEGACY_ID_PREFIX}{safe}"
    return safe


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
    safe_id = _sanitise_rule_id(row.rule_id)
    tags = ["legacy_import"]
    if safe_id != row.rule_id:
        # Preserve the original legacy identifier so `grep` finds it.
        tags.append(f"legacy_id:{row.rule_id}")
    stub: dict[str, Any] = {
        "id": safe_id,
        "name": row.name,
        "severity": "medium",
        "regulation_refs": _regulation_refs_for(row),
        "escalate_to": "l2_review",
        "evidence": [],
        "tags": tags,
    }

    if row.legacy_sql is not None:
        stub["logic"] = {"type": "custom_sql", "sql": row.legacy_sql}
        if row.narrative:
            # SQL + narrative is a common shape — preserve the
            # rationale so the operator can reconcile the imported
            # stub against the legacy export.
            stub["business_intent"] = row.narrative
        if row.threshold_block is not None:
            # SQL-bearing rows can also ship parameter blobs (e.g.
            # parameterised SQL). Preserve them as a tag so the
            # operator can reconcile against the source dump.
            stub["tags"] = [
                *stub["tags"],
                f"legacy_threshold_block:{json.dumps(row.threshold_block, sort_keys=True)}",
            ]
        return stub

    if row.threshold_block is not None:
        # Build the aggregation_window block from a permissive merge:
        # legacy `having` / `window` / `group_by` / `source` / `filter`
        # keys (if present) override the defaults. Any remaining
        # sibling keys are preserved as a JSON-serialised tag so the
        # spec stays schema-valid (Rule.extra="forbid") while nothing
        # from the source dump is silently dropped — the operator can
        # `grep` for `legacy_threshold_block:` in the skeleton to audit.
        block = row.threshold_block if isinstance(row.threshold_block, dict) else {}
        raw_having = block.get("having")
        # Keep only the entries whose value is a real (non-empty)
        # operator dict. An all-or-nothing fallback would silently
        # drop a valid `count >= 5` metric when an unrelated sibling
        # like `sum_amount: {}` is also present in the legacy blob.
        if isinstance(raw_having, dict) and raw_having:
            kept = {k: v for k, v in raw_having.items() if _is_real_metric(v)}
            explicit_having = kept if kept else None
        else:
            explicit_having = None
        # `filter` lifts straight into the logic block too (it's a
        # documented AggregationWindowLogic field). Excluding it from
        # the derived `having` set below prevents the engine from
        # treating it as an aggregate metric and crashing with
        # "unsupported having metric 'filter'".
        filter_block = block.get("filter") if isinstance(block.get("filter"), dict) else None
        # When no explicit `having` is supplied, derive one from the
        # block but exclude the documented logic-block metadata
        # (`source` / `window` / `group_by` / `filter`) — otherwise
        # the engine treats them as aggregate metrics and
        # `compile_rule_sql` fails at runtime with "unsupported having
        # metric 'source'". Empty operator values are also dropped so
        # they don't make it through as a fake-real metric.
        _METADATA_KEYS = {"source", "window", "group_by", "filter", "having"}
        # Vendor-shape blobs commonly include unknown dict siblings
        # (e.g. `parameters: {...}`) that the engine rejects at
        # compile time with "unsupported having metric ...". Restrict
        # the derived `having` to the engine's recognised aggregates
        # so the stub stays runtime-valid; everything else is still
        # preserved on the `legacy_threshold_block:` tag.
        derived_having: dict[str, Any] = {
            k: v
            for k, v in block.items()
            if k not in _METADATA_KEYS and k in _RECOGNISED_HAVING_METRICS and _is_real_metric(v)
        }
        # A metric-less block (only metadata, or `having: {}` /
        # `{"count": {}}`) has no real threshold to import — flag it
        # as needing manual conversion so the operator doesn't
        # accidentally promote a `count >= 1` placeholder into
        # production. The placeholder still emits so `aml validate`
        # passes; the tag makes it discoverable via
        # `grep needs_manual_conversion`.
        metric_less = _threshold_is_metric_less(row.threshold_block)
        if not derived_having and explicit_having is None:
            # Legacy block had only metadata + no metric → emit a
            # safe placeholder so the stub validates and the operator
            # gets pointed at the right rule by `aml validate`.
            derived_having = {"count": {"gte": 1}}
        # Coerce metadata so common legacy scalar shapes
        # (`group_by: "customer_id"`, `window: 30`) emit schema-valid
        # output instead of forcing `aml validate` failures even after
        # the operator fills the TODO source/queue fields.
        source_raw = block.get("source")
        # Strip whitespace so the emitted `source` matches a data
        # contract ID exactly — `" txn "` vs `"txn"` would otherwise
        # fail cross-reference validation after the operator merges.
        source_value = (
            source_raw.strip()
            if isinstance(source_raw, str) and source_raw.strip()
            else "TODO_source_contract"
        )
        logic: dict[str, Any] = {
            "type": "aggregation_window",
            "source": source_value,
            "group_by": _coerce_group_by(block.get("group_by", ["customer_id"])),
            "window": _coerce_window(block.get("window", "30d")),
            "having": explicit_having if explicit_having is not None else derived_having,
        }
        if filter_block is not None:
            logic["filter"] = filter_block
        stub["logic"] = logic
        # Preserve the original blob as a tag (allowed by the Rule
        # schema) so the spec validates as-is once the TODO source/
        # queue/regulation fields are filled in.
        new_tags = [
            *stub["tags"],
            f"legacy_threshold_block:{json.dumps(row.threshold_block, sort_keys=True)}",
        ]
        if metric_less:
            # No real metric in the source block → flag for manual
            # conversion AND set `status: experimental` so the
            # engine ignores the rule until the operator finishes
            # the manual conversion + promotes to `active`.
            new_tags.append("needs_manual_conversion")
            stub["status"] = "experimental"
        stub["tags"] = new_tags
        if row.narrative:
            stub["business_intent"] = row.narrative
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
    # Append `needs_manual_conversion` so the operator can filter for
    # rules that still need narrative-to-rule translation. Also set
    # `status: experimental` so the runner doesn't pick this rule up
    # for production execution until the operator promotes it after
    # finishing the manual conversion. (The runner skips
    # non-`active` rules, see engine/runner.py.)
    stub["tags"] = [*tags, "needs_manual_conversion"]
    stub["status"] = "experimental"
    if row.narrative:
        # Persist the human prose so it isn't lost between formats.
        stub["business_intent"] = f"# TODO: convert narrative -> {row.narrative}"
    else:
        stub["business_intent"] = "# TODO: convert narrative -> (none supplied)"
    return stub


def classify_row(row: LegacyRuleRow) -> str:
    """Return one of `ready_sql`, `ready_threshold`, or `needs_manual`."""
    if row.legacy_sql is not None:
        return "ready_sql"
    if row.threshold_block is not None:
        # A threshold block with only metadata (no real metric) is a
        # placeholder the operator must still author manually — don't
        # let it count as ready.
        if _threshold_is_metric_less(row.threshold_block):
            return "needs_manual"
        return "ready_threshold"
    return "needs_manual"


_METADATA_KEYS_FOR_CLASSIFICATION = frozenset({"source", "window", "group_by", "filter", "having"})


def _is_real_metric(value: Any) -> bool:
    """A metric value is real when it's a non-empty dict of operators.

    The AML spec's `having` accepts `{<metric>: {<op>: <value>}}`. An
    empty operator dict (`{"count": {}}`) passes schema validation
    but produces a dangling `WHERE` at compile time. Treating it as
    real-metric here would cause the importer to skip
    `needs_manual_conversion`.
    """
    return isinstance(value, dict) and bool(value)


def _threshold_is_metric_less(block: dict[str, Any] | None) -> bool:
    """Return True when a threshold block has no real metric.

    Mirrors the logic in `to_aml_rule_stub`: a block is metric-less
    when neither `having` nor a non-metadata sibling carries a real
    metric. Centralised so `classify_row` and `inventory_summary`
    agree with the stub's `needs_manual_conversion` tagging.

    A "real metric" is a non-empty operator dict — and, for the
    sibling case, the key must also be one of the engine-recognised
    aggregates so a vendor blob like `parameters: {...}` doesn't
    fool the readiness check.
    """
    if not isinstance(block, dict):
        return True
    raw_having = block.get("having")
    if isinstance(raw_having, dict) and raw_having:
        # `having` keys aren't sanity-checked against
        # `_RECOGNISED_HAVING_METRICS` here because the operator may
        # be importing an explicit having block that mostly works;
        # the runtime engine will surface unsupported metrics
        # downstream. What we care about is whether at least one
        # value is a real operator dict.
        if any(_is_real_metric(v) for v in raw_having.values()):
            return False
    siblings = {
        k: v
        for k, v in block.items()
        if k not in _METADATA_KEYS_FOR_CLASSIFICATION
        and k in _RECOGNISED_HAVING_METRICS
        and _is_real_metric(v)
    }
    return not siblings


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
    # Track raw and sanitised separately: raw catches literal dupes,
    # sanitised catches dupes the importer would generate (e.g. `R-1`
    # + `R_1` both sanitise to `r_1`) so the operator sees them
    # *before* the import generates a numeric suffix.
    raw_to_rows: dict[str, list[str]] = {}
    sanitised_to_raws: dict[str, list[str]] = {}
    for row in rows:
        if row.legacy_sql is not None:
            counts["sql"] += 1
            ready += 1
        elif row.threshold_block is not None:
            counts["threshold"] += 1
            # A metric-less threshold block emits a placeholder that
            # the importer flags `needs_manual_conversion`; the
            # summary should agree so the operator sees the real
            # migration workload.
            if _threshold_is_metric_less(row.threshold_block):
                manual += 1
            else:
                ready += 1
        elif row.narrative is not None:
            counts["narrative"] += 1
            manual += 1
        else:
            counts["empty"] += 1
            manual += 1
        if not row.regulator_refs:
            missing_regs += 1
        raw_to_rows.setdefault(row.rule_id, []).append(row.rule_id)
        sanitised_to_raws.setdefault(_sanitise_rule_id(row.rule_id), []).append(row.rule_id)

    duplicates: list[str] = []
    for rule_id, occurrences in raw_to_rows.items():
        if len(occurrences) > 1:
            duplicates.append(rule_id)
    # Surface sanitised collisions even when raw IDs differ, so the
    # operator sees the post-import collision in the summary.
    for safe_id, raw_ids in sanitised_to_raws.items():
        if len(raw_ids) > 1 and len(set(raw_ids)) > 1:
            label = f"{safe_id} ← {', '.join(sorted(set(raw_ids)))}"
            duplicates.append(label)
    return {
        "total": len(rows),
        "by_shape": counts,
        "ready_to_import": ready,
        "needs_manual": manual,
        "missing_regulator_refs": missing_regs,
        "duplicate_rule_ids": sorted(duplicates),
    }


def _disambiguate_rule_ids(stubs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append `_<n>` to colliding `id` values so each stub is unique.

    Legacy dumps occasionally contain duplicate rule IDs, and distinct
    legacy IDs can sanitise to the same spec ID (e.g. `R-1` and `R_1`
    both become `r_1`). The runner uses `rule.id` as a dict key and as
    part of alert filenames, so collisions would silently overwrite
    one rule with another after the skeleton is merged. Disambiguation
    happens here (at skeleton-build time) rather than per-stub so a
    caller using `to_aml_rule_stub` directly still gets the natural
    ID, while the persisted skeleton is collision-free.

    Two-pass: first reserve every natural sanitised ID (so a later
    `r_1_2` row keeps its name), then walk the stubs and only rewrite
    those whose natural ID collides with an earlier stub.
    """
    # Pass 1: reserve every natural ID. Use a multiset so a stub that
    # appears N times is still counted, and only the *first occurrence*
    # of each natural ID is allowed to keep it.
    natural_ids = [stub["id"] for stub in stubs]
    natural_counts: dict[str, int] = {}
    for nid in natural_ids:
        natural_counts[nid] = natural_counts.get(nid, 0) + 1
    reserved: set[str] = set(natural_ids)

    used: set[str] = set()
    out: list[dict[str, Any]] = []
    for stub in stubs:
        base = stub["id"]
        if base not in used:
            used.add(base)
            out.append(stub)
            continue
        # Collision — pick the smallest `_n` suffix that isn't already
        # used AND isn't reserved for a later natural ID, so a stub
        # with natural ID `r_1_2` is never displaced by a disambiguated
        # duplicate of `r_1`.
        n = 2
        while True:
            candidate = f"{base}_{n}"
            if candidate not in used and (
                candidate not in reserved or natural_counts.get(candidate, 0) == 0
            ):
                break
            n += 1
        used.add(candidate)
        disambiguated = dict(stub)
        disambiguated["id"] = candidate
        tags = list(disambiguated.get("tags", []))
        tags.append(f"legacy_dup_of:{base}")
        disambiguated["tags"] = tags
        out.append(disambiguated)
    return out


def build_spec_skeleton(rows: list[LegacyRuleRow]) -> dict[str, Any]:
    """Wrap a list of stubs in the minimal envelope `aml validate` expects.

    Returns a dict ready to be `yaml.safe_dump`-ed. The envelope is
    intentionally thin — the operator is expected to merge it into
    their existing spec, not run it raw. Duplicate generated rule
    IDs (from a noisy legacy dump or sanitisation collisions) are
    disambiguated with a numeric suffix; the original ID is preserved
    on the stub's `tags`.
    """
    stubs = [to_aml_rule_stub(row) for row in rows]
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
        "rules": _disambiguate_rule_ids(stubs),
        "workflow": {"queues": []},
        "reporting": {"forms": {}},
    }
