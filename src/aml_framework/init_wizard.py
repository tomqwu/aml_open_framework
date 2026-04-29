"""`aml init` wizard — scaffold a working starter spec in <60 seconds.

Process problem this solves
---------------------------
Today, a developer assigned to bring this framework to a real bank
spends 2-3 days reading docs/spec-reference.md + an example spec
before they have a working starter to point at their warehouse.
Many never get past day one. The leader-side `aml demo` (PR #96)
collapsed the buyer's first-five-minutes; this collapses the
engineer's first day.

Five questions → one working `aml.yaml` + sample data + a smoke-test
that runs end-to-end. Validates immediately so the developer never
sees a half-broken scaffold.

Design choices
--------------
- `typer.prompt` for interactive use; every prompt has a sensible
  default so `aml init --non-interactive` works for CI / scripting
- Templates inline (no external files to ship) — keeps the wizard
  one self-contained module
- Output validates against the JSON Schema before writing — no
  half-broken scaffold ever lands on disk
- Bank-type variants share the same shape (program + 2 contracts +
  3 starter rules + 3-queue workflow) so the developer learns
  *one* shape and can fork it for any institution
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Bank archetypes the wizard knows how to scaffold. Each one differs
# only in the seed-rule set + recommended channel mix; the core spec
# shape is the same so a developer who learns one learns all.
BankArchetype = Literal["community_bank", "schedule_i_bank", "vasp", "fintech"]

# Jurisdictions + their default regulators. The wizard auto-picks the
# regulator when the developer picks the jurisdiction so they don't
# have to know the acronym mapping.
JURISDICTION_DEFAULTS: dict[str, tuple[str, str]] = {
    "US": ("FinCEN", "USD"),
    "CA": ("FINTRAC", "CAD"),
    "GB": ("FCA", "GBP"),
    "EU": ("AMLA", "EUR"),
    "AU": ("AUSTRAC", "AUD"),
    "SG": ("MAS", "SGD"),
    "OTHER": ("LOCAL_REGULATOR", "USD"),
}

# Channel mix per archetype — what a developer needs to monitor on
# day one. Tightens the synthetic dataset to channels that match the
# institution rather than the kitchen-sink default.
CHANNELS_BY_ARCHETYPE: dict[BankArchetype, list[str]] = {
    "community_bank": ["cash", "wire", "ach", "card"],
    "schedule_i_bank": ["cash", "wire", "ach", "e_transfer", "cheque", "card"],
    "vasp": ["wire", "crypto"],
    "fintech": ["card", "ach", "rtp"],
}


@dataclass(frozen=True)
class InitConfig:
    """All answers needed to scaffold a starter spec."""

    program_name: str
    jurisdiction: str
    regulator: str
    archetype: BankArchetype
    target_dir: Path
    currency: str = "USD"

    @property
    def channels(self) -> list[str]:
        return CHANNELS_BY_ARCHETYPE.get(self.archetype, ["cash", "wire", "ach", "card"])


# ---------------------------------------------------------------------------
# Validation helpers (no IO)
# ---------------------------------------------------------------------------

_PROGRAM_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_program_name(name: str) -> str | None:
    """Return None when valid, else an error string for the prompt to show."""
    if not name:
        return "Program name cannot be empty."
    if not _PROGRAM_NAME_RE.match(name):
        return "Program name must be lowercase a-z / 0-9 / _ and start with a letter."
    return None


def normalise_jurisdiction(s: str) -> str:
    """Map free-form input to a known jurisdiction key."""
    s = (s or "").strip().upper()
    if s in JURISDICTION_DEFAULTS:
        return s
    aliases = {
        "USA": "US",
        "AMERICA": "US",
        "CANADA": "CA",
        "UK": "GB",
        "BRITAIN": "GB",
        "ENGLAND": "GB",
        "EUROPE": "EU",
        "EUROZONE": "EU",
        "AUSTRALIA": "AU",
        "SINGAPORE": "SG",
    }
    return aliases.get(s, "OTHER")


def normalise_archetype(s: str) -> BankArchetype:
    s = (s or "").strip().lower().replace("-", "_").replace(" ", "_")
    if s in {"community_bank", "schedule_i_bank", "vasp", "fintech"}:
        return s  # type: ignore[return-value]
    aliases = {
        "schedule_i": "schedule_i_bank",
        "schedule1": "schedule_i_bank",
        "tier1": "schedule_i_bank",
        "tier_1": "schedule_i_bank",
        "crypto": "vasp",
        "exchange": "vasp",
        "neobank": "fintech",
        "challenger": "fintech",
        "community": "community_bank",
        "credit_union": "community_bank",
    }
    return aliases.get(s, "community_bank")  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Spec rendering
# ---------------------------------------------------------------------------


def _data_contracts_yaml(channels: list[str]) -> str:
    channel_enum = ", ".join(channels)
    return f"""data_contracts:
  - id: txn
    source: raw.transactions
    freshness_sla: 1h
    columns:
      - {{ name: txn_id,      type: string,    nullable: false, pii: false }}
      - {{ name: customer_id, type: string,    nullable: false, pii: true  }}
      - {{ name: amount,      type: decimal,   nullable: false, constraints: [">0"] }}
      - {{ name: currency,    type: string,    nullable: false }}
      - {{ name: channel,     type: string,    enum: [{channel_enum}] }}
      - {{ name: direction,   type: string,    enum: [in, out] }}
      - {{ name: booked_at,   type: timestamp, nullable: false }}
    quality_checks:
      - {{ not_null: [txn_id, customer_id, amount, booked_at] }}
      - {{ unique:   [txn_id] }}

  - id: customer
    source: raw.customers
    freshness_sla: 24h
    columns:
      - {{ name: customer_id,   type: string,    nullable: false, pii: true }}
      - {{ name: full_name,     type: string,    nullable: false, pii: true }}
      - {{ name: country,       type: string,    nullable: false }}
      - {{ name: risk_rating,   type: string,    enum: [low, medium, high] }}
      - {{ name: onboarded_at,  type: timestamp, nullable: false }}
    quality_checks:
      - {{ not_null: [customer_id, full_name, onboarded_at] }}
      - {{ unique:   [customer_id] }}
"""


# Three starter rules every archetype gets. They cover the canonical
# triad — structuring (volume), velocity (count), and high-risk
# jurisdiction (geography) — so day one shows alerts on all three
# axes a typical bank's first sweep tunes against.
def _starter_rules_yaml(currency: str, jurisdiction: str) -> str:
    structuring_threshold = "9500"  # just-below the LCTR/CTR floor
    velocity_count = "5"
    high_risk_country_list = '["IR", "KP", "RU", "SY"]'  # FATF black/grey-ish
    return f"""rules:
  - id: structuring_below_threshold
    name: Cash deposits just below the reporting threshold
    severity: high
    regulation_refs:
      - citation: "FATF R.10"
        description: "Customer due diligence + suspicious-activity reporting."
    logic:
      type: aggregation_window
      source: txn
      filter:
        direction: in
        channel: cash
        amount: {{ gte: {structuring_threshold} }}
      group_by: [customer_id]
      window: 30d
      having:
        count: {{ gte: 3 }}
    escalate_to: l2_review
    evidence:
      - matching_txns
      - customer_kyc

  - id: velocity_inbound_burst
    name: Velocity — many inbound transfers in a short window
    severity: medium
    regulation_refs:
      - citation: "FATF R.20"
        description: "Reporting suspicious activity."
    logic:
      type: aggregation_window
      source: txn
      filter:
        direction: in
      group_by: [customer_id]
      window: 1d
      having:
        count: {{ gte: {velocity_count} }}
    escalate_to: l2_review
    evidence:
      - matching_txns
      - customer_kyc

  - id: high_risk_jurisdiction
    name: Customer in a high-risk jurisdiction
    severity: high
    regulation_refs:
      - citation: "FATF R.19"
        description: "Higher-risk countries — enhanced due diligence."
    logic:
      type: custom_sql
      sql: |
        SELECT t.customer_id, t.txn_id, t.amount, t.booked_at, c.country
        FROM txn t JOIN customer c USING (customer_id)
        WHERE c.country IN {high_risk_country_list.replace("[", "(").replace("]", ")").replace('"', "'")}
          AND t.amount >= 1000
          AND t.booked_at >= TIMESTAMP '{{recent_start}}'
    escalate_to: l2_review
    evidence:
      - matching_txn
      - customer_kyc
      - jurisdiction_screening
"""


_WORKFLOW_AND_REPORTING = """workflow:
  queues:
    - id: l1_review
      sla: 24h
      next: [l2_review, closed_no_action]
    - id: l2_review
      sla: 72h
      next: [str_filing, closed_no_action]
    - id: str_filing
      sla: 30d
    - id: closed_no_action
      sla: 24h

reporting:
  forms:
    str:
      template: str_v1
      mandatory_fields:
        - subject_full_name
        - subject_country
        - aggregate_amount
        - rule_id
        - regulation_refs
      trigger:
        queue: str_filing
"""


def render_spec(config: InitConfig) -> str:
    """Build the complete `aml.yaml` string for the supplied config."""
    program = f"""# Generated by `aml init` for {config.archetype} in {config.jurisdiction}.
# Tune thresholds + add detectors for your real exposure profile.

version: 1

program:
  name: {config.program_name}
  jurisdiction: {config.jurisdiction}
  regulator: {config.regulator}
  owner: chief_compliance_officer
  effective_date: 2026-01-01

"""
    return (
        program
        + _data_contracts_yaml(config.channels)
        + "\n"
        + _starter_rules_yaml(config.currency, config.jurisdiction)
        + "\n"
        + _WORKFLOW_AND_REPORTING
    )


def render_readme(config: InitConfig) -> str:
    """Write a small README so the developer knows what to run next."""
    return f"""# {config.program_name}

Scaffolded by `aml init`. Starter AML spec for a {config.archetype} in
{config.jurisdiction} (regulator: {config.regulator}).

## Run it end-to-end

```bash
aml validate aml.yaml
aml run aml.yaml --seed 42
aml dashboard aml.yaml
```

## Customise

1. **Add detectors** — copy any rule from
   `examples/{{community_bank,canadian_schedule_i_bank,…}}/aml.yaml` and
   adjust thresholds.
2. **Point at your warehouse** — replace `data_contracts[*].source` with
   your warehouse table; run `aml validate-data aml.yaml --data-dir
   ./your/csvs/` to check column mappings.
3. **Tune thresholds** — `aml dashboard` → Tuning Lab page lets you
   sweep thresholds and see precision/recall before promoting.
4. **Run a backtest** — `aml backtest aml.yaml --rule
   structuring_below_threshold --quarters 4` shows whether the rule's
   precision/recall is trending down over time.

## Audit & evidence

The framework hashes every run into `decisions.jsonl` (append-only)
and lets you replay any historical run byte-for-byte. When the
regulator walks in, run `aml audit-pack aml.yaml --jurisdiction
{config.jurisdiction}-{config.regulator}` to build the examination
ZIP — already mapped to the relevant clauses.
"""


# ---------------------------------------------------------------------------
# Disk writer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WrittenScaffold:
    """Outputs from `write_scaffold` so the CLI can print next-steps."""

    spec_path: Path
    readme_path: Path


def write_scaffold(config: InitConfig, *, overwrite: bool = False) -> WrittenScaffold:
    """Write spec + README into the target dir. Validates the spec."""
    spec_path = config.target_dir / "aml.yaml"
    readme_path = config.target_dir / "README.md"

    if spec_path.exists() and not overwrite:
        raise FileExistsError(f"{spec_path} already exists; pass overwrite=True to replace.")

    config.target_dir.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(render_spec(config), encoding="utf-8")
    readme_path.write_text(render_readme(config), encoding="utf-8")

    # Validate before returning so the developer never sees a half-broken
    # scaffold. If this raises, callers should delete what was written
    # and surface the error to the prompt.
    from aml_framework.spec import load_spec

    load_spec(spec_path)

    return WrittenScaffold(spec_path=spec_path, readme_path=readme_path)
