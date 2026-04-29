"""`aml typology-import` — install curated typology rules into an existing spec.

Process problem this solves
---------------------------
"We don't know what rules to start with" and "we want what RBC ships"
are the two questions every new AML program lead asks in week one.
Today the answer is "go read the FATF papers, the FinCEN advisories,
your peers' enforcement orders, and translate them into spec YAML
yourself." That takes weeks, and the resulting rules are
inconsistently cited, inconsistently parameterised, and quietly drift
from peer practice.

This module ships a vetted catalogue (`spec/library/typologies/`)
where each typology is one YAML file containing:

- `metadata` — id, name, plain-English description, jurisdictions the
  rule applies in, regulation citations, source attribution,
  recommended severity, and any dependencies (other typologies that
  must be installed first).
- `rule` — the full Rule block that drops into the spec's `rules:`
  list. Same shape the loader expects, so installation is splice +
  validate, not transformation.

`aml typology-list` shows the catalogue. `aml typology-import <id>`
splices the rule into the supplied spec, validates against the loader
(JSON Schema + Pydantic + cross-reference), and rolls back atomically
on any failure. The audit trail in `decisions.jsonl` records the
typology id and source attribution so a regulator inspecting the spec
can trace any rule back to its citation.

Why a catalogue, not auto-include
---------------------------------
The framework's defensibility story is "every line of the spec was
written by a human who can defend it in front of a regulator." An
auto-include directive would let rules silently appear on a library
bump — eroding that story. Splice-once is the right ergonomic: the
operator owns the rule once it lands.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aml_framework.spec.library import LIBRARY_ROOT

TYPOLOGY_DIR = LIBRARY_ROOT / "typologies"


# ---------------------------------------------------------------------------
# Catalogue listing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TypologyMetadata:
    """Metadata sidecar for one curated typology.

    Mirrors the `metadata:` block of each YAML in the catalogue.
    """

    id: str
    name: str
    description: str
    jurisdictions: tuple[str, ...]
    regulations: tuple[str, ...]
    source: str
    recommended_severity: str
    dependencies: tuple[str, ...]
    path: Path

    @property
    def description_short(self) -> str:
        """First sentence of the description, for table rows."""
        first_paragraph = self.description.strip().split("\n\n")[0]
        sentences = re.split(r"(?<=[.!?])\s+", first_paragraph.replace("\n", " "))
        return sentences[0].strip() if sentences else first_paragraph.strip()


def list_typologies(typology_dir: Path | None = None) -> list[TypologyMetadata]:
    """Scan the catalogue directory and return one TypologyMetadata per file.

    Sorted by id for stable CLI output.
    """
    directory = typology_dir or TYPOLOGY_DIR
    if not directory.exists():
        return []

    out: list[TypologyMetadata] = []
    for yaml_path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        meta = raw.get("metadata") or {}
        if not meta.get("id"):
            continue  # malformed file — skip rather than crash listing
        out.append(
            TypologyMetadata(
                id=meta["id"],
                name=meta.get("name", meta["id"]),
                description=meta.get("description", "").strip(),
                jurisdictions=tuple(meta.get("jurisdictions") or []),
                regulations=tuple(meta.get("regulations") or []),
                source=meta.get("source", ""),
                recommended_severity=meta.get("recommended_severity", "medium"),
                dependencies=tuple(meta.get("dependencies") or []),
                path=yaml_path,
            )
        )
    return out


def load_typology(typology_id: str, typology_dir: Path | None = None) -> dict[str, Any]:
    """Load one typology YAML by id; return the parsed dict."""
    directory = typology_dir or TYPOLOGY_DIR
    yaml_path = directory / f"{typology_id}.yaml"
    if not yaml_path.exists():
        raise KeyError(
            f"Typology {typology_id!r} not found in catalogue. "
            f"Run `aml typology-list` to see available ids."
        )
    return yaml.safe_load(yaml_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Spec mutation — splice typology rule into the spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImportedTypology:
    """What `import_typology` produced — for the CLI to narrate."""

    spec_path: Path
    typology_id: str
    rule_id: str
    source: str
    line_number: int
    escalate_to: str
    escalate_to_remapped_from: str | None = None


def _render_rule_yaml(rule: dict[str, Any]) -> str:
    """Render a Rule dict back to YAML matching the spec's existing style.

    Uses `default_flow_style=False`, `sort_keys=False` to preserve
    field order from the catalogue YAML, and indents 2 spaces (the
    convention across all shipped specs). Wraps in `  - ` so it
    drops directly into the `rules:` list.
    """
    body = yaml.dump(rule, default_flow_style=False, sort_keys=False, indent=2)
    # Re-indent to 4 spaces so each field sits at column 4 under `  - `.
    indented_lines: list[str] = []
    for i, line in enumerate(body.splitlines()):
        if not line:
            indented_lines.append("")
            continue
        if i == 0:
            indented_lines.append(f"  - {line}")
        else:
            indented_lines.append(f"    {line}")
    return "\n".join(indented_lines).rstrip() + "\n"


def _extract_rules_section(text: str) -> str:
    """Return the substring of `text` covering the top-level `rules:` block.

    Defined as: the line starting `rules:` through (exclusive of) the
    next top-level (column-0 non-comment, non-blank) line. Used so
    we only scan for rule-id collisions inside the rules block, not
    in `workflow.queues:` or `metrics:` ids that happen to look like
    rule ids.
    """
    lines = text.splitlines(keepends=False)
    rules_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^rules:\s*$", line):
            rules_idx = i
            break
    if rules_idx is None:
        return ""
    end_idx = len(lines)
    for j in range(rules_idx + 1, len(lines)):
        line = lines[j]
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            end_idx = j
            break
    return "\n".join(lines[rules_idx:end_idx])


def _detect_spec_queues(text: str) -> list[str]:
    """Pull queue ids out of a spec's `workflow.queues:` block via regex.

    Avoids round-tripping through PyYAML — keeps the function pure
    string-in / list-out so it can be unit-tested without a full spec.
    """
    in_queues = False
    queue_block_indent: int | None = None
    queue_ids: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if re.match(r"^\s*queues:\s*$", line):
            in_queues = True
            queue_block_indent = len(line) - len(line.lstrip())
            continue
        if not in_queues:
            continue
        # Empty / comment lines do not break the block.
        if not line or line.lstrip().startswith("#"):
            continue
        cur_indent = len(line) - len(line.lstrip())
        # If we're back at or shallower than the queues: keyword's
        # indent, we've left the block.
        if queue_block_indent is not None and cur_indent <= queue_block_indent:
            break
        m = re.match(r"^\s+-\s+id:\s+([a-z][a-z0-9_]*)\s*$", line)
        if m:
            queue_ids.append(m.group(1))
    return queue_ids


def _pick_fallback_queue(severity: str, queues: list[str]) -> str | None:
    """Choose a sensible escalate_to when the typology's preferred id is missing.

    Strategy:
      - high/critical severity → prefer queue matching `l2*` or
        containing 'investigator'
      - low/medium severity → prefer queue matching `l1*` or
        containing 'analyst'
      - fall back to the first queue id in the spec
    """
    if not queues:
        return None
    sev = severity.lower()
    high_pri = sev in {"high", "critical"}

    def _match(predicate) -> str | None:
        for q in queues:
            if predicate(q):
                return q
        return None

    if high_pri:
        candidate = _match(lambda q: q.startswith("l2")) or _match(lambda q: "investigator" in q)
    else:
        candidate = _match(lambda q: q.startswith("l1")) or _match(lambda q: "analyst" in q)
    return candidate or queues[0]


def import_typology(
    typology_id: str,
    spec_path: Path,
    typology_dir: Path | None = None,
    *,
    allow_duplicate_rule_id: bool = False,
    escalate_to_override: str | None = None,
) -> ImportedTypology:
    """Splice the typology's rule into the spec's `rules:` list.

    Validates the resulting spec against the loader (JSON Schema +
    Pydantic). Rolls back atomically if validation fails — operators
    never end up with a half-broken spec on disk.

    If the typology's `escalate_to` queue does not exist in the spec
    (different institutions name their queues differently), the
    importer remaps it to a same-tier queue that does exist (or the
    first queue, as a last resort). Pass `escalate_to_override` to
    skip detection and force a specific queue.

    Raises:
        KeyError: typology id not in catalogue.
        ValueError: rule id collision (unless `allow_duplicate_rule_id=True`),
            spec missing top-level `rules:` block, or post-splice
            validation failure.
    """
    typology = load_typology(typology_id, typology_dir=typology_dir)
    metadata = typology.get("metadata") or {}
    rule = typology.get("rule") or {}

    if not rule.get("id"):
        raise ValueError(f"Typology {typology_id!r} is missing a `rule.id` field.")
    rule_id = rule["id"]

    text = spec_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=False)

    # 1. Pre-flight: check rule id doesn't already exist (only checks
    # existing rules, since the queue block is matched separately
    # below — but we narrow the scan to the rules block to avoid
    # matching queue ids by accident).
    rules_section = _extract_rules_section(text)
    existing_rule_ids = re.findall(
        r"^\s+-\s+id:\s+([a-z][a-z0-9_]*)\s*$", rules_section, re.MULTILINE
    )
    if not allow_duplicate_rule_id and rule_id in existing_rule_ids:
        raise ValueError(
            f"Rule id {rule_id!r} already present in {spec_path}. "
            f"Remove the existing rule or pass `allow_duplicate_rule_id=True`."
        )

    # 2. Remap escalate_to if needed: if the typology's preferred
    # queue doesn't exist in the spec, fall back to a same-tier queue
    # that does. Operators get a clear narration via the returned
    # ImportedTypology.
    spec_queues = _detect_spec_queues(text)
    preferred_queue = rule.get("escalate_to", "")
    remapped_from: str | None = None
    if escalate_to_override:
        if escalate_to_override != preferred_queue:
            remapped_from = preferred_queue
        rule = {**rule, "escalate_to": escalate_to_override}
    elif spec_queues and preferred_queue not in spec_queues:
        fallback = _pick_fallback_queue(
            rule.get("severity", "medium"),
            spec_queues,
        )
        if fallback is not None:
            remapped_from = preferred_queue
            rule = {**rule, "escalate_to": fallback}

    # 3. Find the `rules:` line.
    rules_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^rules:\s*$", line):
            rules_idx = i
            break
    if rules_idx is None:
        raise ValueError(
            f"Spec {spec_path} has no top-level `rules:` block — cannot install typology."
        )

    # 4. Find the end of the rules block — first top-level
    # (column-0 non-comment, non-blank) line after rules_idx.
    insert_idx = len(lines)
    for i in range(rules_idx + 1, len(lines)):
        line = lines[i]
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            insert_idx = i
            break

    # 5. Build the rendered rule block, with a comment preserving
    # source attribution so the audit trail can trace it back.
    rule_yaml = _render_rule_yaml(rule)
    source_comment = (
        f"\n  # Installed via `aml typology-import {typology_id}`.\n"
        f"  # Source: {metadata.get('source', 'curated catalogue')}\n"
    )
    new_block = source_comment + rule_yaml + "\n"
    new_text = "\n".join(lines[:insert_idx]) + new_block + "\n".join(lines[insert_idx:])

    # 6. Validate before writing — atomic rollback on failure.
    backup = text
    spec_path.write_text(new_text, encoding="utf-8")
    try:
        from aml_framework.spec import load_spec

        spec = load_spec(spec_path)
        if rule_id not in {r.id for r in spec.rules}:
            spec_path.write_text(backup, encoding="utf-8")
            raise ValueError(
                f"Loader did not register {rule_id!r} after splice — "
                f"check typology YAML for missing fields."
            )
    except Exception:
        spec_path.write_text(backup, encoding="utf-8")
        raise

    return ImportedTypology(
        spec_path=spec_path,
        typology_id=typology_id,
        rule_id=rule_id,
        source=metadata.get("source", ""),
        line_number=insert_idx + 1,
        escalate_to=rule["escalate_to"],
        escalate_to_remapped_from=remapped_from,
    )
