"""`aml add-rule` wizard — drop a new detection rule into an existing spec.

Process problem this solves
---------------------------
Today, adding a new typology rule to an existing spec means an analyst
or detection engineer reads `docs/spec-reference.md`, finds an example
in `examples/community_bank/aml.yaml`, copies the YAML, edits it, and
hopes the indentation survives. Mistakes are silent: a typo in a
threshold gets through `aml validate` because the structure is right
but the semantics are wrong.

This wizard collapses that into ~5 prompts → one validated rule
appended to the spec, with the regulation citation, threshold, and
severity all set. Same shape used everywhere else in the framework so
the analyst never has to learn YAML.

Three rule patterns supported on day one
----------------------------------------
1. **structuring** — N transactions of channel/direction adding up
   to ≥ X within Y days; the canonical "below the reporting
   threshold" detector.
2. **velocity_burst** — count-based: N transactions of any kind
   within Y hours/days. Catches rapid funnel patterns.
3. **high_risk_jurisdiction** — countries on the institution's
   high-risk list, with optional amount floor.

These three cover the bulk of what a bank's first 10 detectors look
like. The wizard intentionally does NOT support `python_ref` rules
(those need a coded scorer) or `network_pattern` rules (those need
the entity-resolution graph and a graph-shape parameter).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RulePattern = Literal["structuring", "velocity_burst", "high_risk_jurisdiction"]
Severity = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class StructuringConfig:
    """Inputs for a structuring (aggregation_window) rule."""

    rule_id: str
    name: str
    severity: Severity
    threshold_amount: float
    window_days: int
    min_count: int
    channel: str  # cash / wire / ach / etc — must exist in the spec's channel enum
    direction: Literal["in", "out"]
    citation: str
    citation_description: str
    escalate_to: str  # queue id


@dataclass(frozen=True)
class VelocityBurstConfig:
    rule_id: str
    name: str
    severity: Severity
    min_count: int
    window_hours: int
    direction: Literal["in", "out"]
    citation: str
    citation_description: str
    escalate_to: str


@dataclass(frozen=True)
class HighRiskJurisdictionConfig:
    rule_id: str
    name: str
    severity: Severity
    countries: list[str]  # ISO 3166-1 alpha-2
    amount_floor: float
    citation: str
    citation_description: str
    escalate_to: str


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

import re

_RULE_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_rule_id(rule_id: str, existing_ids: set[str]) -> str | None:
    """Return None when valid, else an error string."""
    if not rule_id:
        return "Rule id cannot be empty."
    if not _RULE_ID_RE.match(rule_id):
        return "Rule id must be lowercase a-z / 0-9 / _ and start with a letter."
    if rule_id in existing_ids:
        return f"Rule id {rule_id!r} already exists in this spec."
    return None


def validate_country_codes(codes: list[str]) -> list[str]:
    """Normalise + filter to valid-looking ISO 3166-1 alpha-2."""
    out: list[str] = []
    for c in codes:
        c = (c or "").strip().upper()
        if len(c) == 2 and c.isalpha():
            out.append(c)
    return out


# ---------------------------------------------------------------------------
# Rule rendering — produces YAML snippets that splice into the spec
# ---------------------------------------------------------------------------


def render_structuring(c: StructuringConfig) -> str:
    return f"""  # --- Added by `aml add-rule` (structuring pattern) ---
  - id: {c.rule_id}
    name: {c.name}
    severity: {c.severity}
    regulation_refs:
      - citation: "{c.citation}"
        description: "{c.citation_description}"
    logic:
      type: aggregation_window
      source: txn
      filter:
        direction: {c.direction}
        channel: {c.channel}
      group_by: [customer_id]
      window: {c.window_days}d
      having:
        count: {{ gte: {c.min_count} }}
        sum_amount: {{ gte: {c.threshold_amount:g} }}
    escalate_to: {c.escalate_to}
    evidence:
      - matching_txns
      - customer_kyc
"""


def render_velocity_burst(c: VelocityBurstConfig) -> str:
    return f"""  # --- Added by `aml add-rule` (velocity_burst pattern) ---
  - id: {c.rule_id}
    name: {c.name}
    severity: {c.severity}
    regulation_refs:
      - citation: "{c.citation}"
        description: "{c.citation_description}"
    logic:
      type: aggregation_window
      source: txn
      filter:
        direction: {c.direction}
      group_by: [customer_id]
      window: {c.window_hours}h
      having:
        count: {{ gte: {c.min_count} }}
    escalate_to: {c.escalate_to}
    evidence:
      - matching_txns
      - customer_kyc
"""


def render_high_risk_jurisdiction(c: HighRiskJurisdictionConfig) -> str:
    countries_yaml = ", ".join(f"'{cc}'" for cc in c.countries)
    return f"""  # --- Added by `aml add-rule` (high_risk_jurisdiction pattern) ---
  - id: {c.rule_id}
    name: {c.name}
    severity: {c.severity}
    regulation_refs:
      - citation: "{c.citation}"
        description: "{c.citation_description}"
    logic:
      type: custom_sql
      sql: |
        SELECT t.customer_id, t.txn_id, t.amount, t.booked_at, c.country
        FROM txn t JOIN customer c USING (customer_id)
        WHERE c.country IN ({countries_yaml})
          AND t.amount >= {c.amount_floor:g}
          AND t.booked_at >= TIMESTAMP '{{recent_start}}'
    escalate_to: {c.escalate_to}
    evidence:
      - matching_txn
      - customer_kyc
      - jurisdiction_screening
"""


# ---------------------------------------------------------------------------
# Spec mutation — splice rule into the spec's `rules:` block
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SplicedSpec:
    """What `splice_rule` produced — for the CLI to narrate."""

    spec_path: Path
    rule_id: str
    inserted_yaml: str
    line_number: int  # roughly where the rule landed (for the diff narration)


def splice_rule(spec_path: Path, rule_yaml: str, rule_id: str) -> SplicedSpec:
    """Append `rule_yaml` to the `rules:` list in the spec.

    Approach: read the file as text, find the line that starts the
    `rules:` block, append the new rule YAML at the end of that block
    (i.e., just before the next top-level key like `workflow:` or
    `metrics:`).

    Why not use a YAML round-trip? PyYAML's default emitter destroys
    the operator's manual formatting (indentation, comment placement,
    quote style). Spec files are reviewed in PRs by 2LoD; preserving
    the existing layout matters more than canonical reformatting.

    Validates the result against the loader before saving.
    """
    text = spec_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=False)

    # 1. Find the `rules:` line.
    rules_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^rules:\s*$", line):
            rules_idx = i
            break
    if rules_idx is None:
        raise ValueError(
            "Spec has no top-level `rules:` block — wizard can't splice. "
            "Add `rules:` (with at least one entry) and re-run."
        )

    # 2. Find the end of the rules block — first top-level (column-0
    # non-comment, non-blank) line after rules_idx.
    insert_idx = len(lines)  # default: end of file
    for i in range(rules_idx + 1, len(lines)):
        line = lines[i]
        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            insert_idx = i
            break

    # 3. Insert the rule YAML — strip trailing newline, leave a blank
    # line on each side for readability.
    new_block = "\n" + rule_yaml.rstrip() + "\n\n"
    new_text = "\n".join(lines[:insert_idx]) + new_block + "\n".join(lines[insert_idx:])

    # 4. Validate before writing.
    backup = spec_path.read_text(encoding="utf-8")
    spec_path.write_text(new_text, encoding="utf-8")
    try:
        from aml_framework.spec import load_spec

        spec = load_spec(spec_path)
        if rule_id not in {r.id for r in spec.rules}:
            # Loader silently dropped our rule — restore + raise.
            spec_path.write_text(backup, encoding="utf-8")
            raise ValueError(
                f"Loader did not register {rule_id!r} after splice. Check the YAML manually."
            )
    except Exception:
        spec_path.write_text(backup, encoding="utf-8")
        raise

    return SplicedSpec(
        spec_path=spec_path,
        rule_id=rule_id,
        inserted_yaml=rule_yaml.rstrip(),
        line_number=insert_idx + 1,
    )
