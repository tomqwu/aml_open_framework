"""Pydantic models for the AML spec.

These mirror schema/aml-spec.schema.json. The JSON Schema is the canonical
contract (that's what external tooling will validate against); these models
exist to give the framework typed access and sensible defaults.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

Severity = Literal["low", "medium", "high", "critical"]
RuleStatus = Literal["active", "experimental", "deprecated"]
EvaluationMode = Literal["batch", "streaming", "both"]
ColumnType = Literal["string", "integer", "decimal", "boolean", "date", "timestamp"]

# FinCEN AML/CFT National Priorities (June 2021, reaffirmed in 2026 NPRM).
# Used by `generators/effectiveness.py` to compute coverage-by-priority for
# the Effectiveness Evidence Pack mandated by FinCEN's April 2026 NPRM.
# Adding "other" as the catch-all for typologies not yet codified by FinCEN
# (e.g. AMLA-specific or jurisdiction-specific). The pack reports unmapped
# rules under "other" so the MLRO can decide whether to refile against a
# new priority once FinCEN updates the list.
AmlPriority = Literal[
    "corruption",
    "cybercrime",
    "terrorist_financing",
    "fraud",
    "transnational_criminal_organization",
    "drug_trafficking",
    "human_trafficking",
    "proliferation_financing",
    "other",
]

# Model-risk tiering used by the MRM bundle generator (`generators/mrm.py`)
# — institutions tier rules by materiality so the SR 26-2 / 2021
# Interagency Statement validation cadence is risk-proportional.
ModelTier = Literal["high", "medium", "low"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


AiAuditLogMode = Literal["hash_only", "full_text"]


SaltRotationCadence = Literal["daily", "weekly", "monthly", "quarterly"]


class InformationSharingPartner(_Base):
    """One cross-border / cross-bank information-sharing partner.

    PR-DATA-10 (DATA-10 in the data-problem whitepaper). Declares intent
    to share obfuscated network-pattern fingerprints with another FI
    under a per-pair, per-period salt arrangement managed by
    `compliance/sandbox.py`. The spec block is opt-in; the engine does
    not contact partners — it only records that the institution has
    declared this partnership and what scope it covers.
    """

    fi_id: str = Field(min_length=1)  # LEI / BIC of the partner FI
    label: str = ""  # human-readable partner name for the dashboard
    jurisdictions: list[str] = Field(default_factory=list)  # e.g. ["US", "CA"]
    typology_scope: list[str] = Field(default_factory=list)  # rule_family slugs
    salt_rotation: SaltRotationCadence = "monthly"


class InformationSharing(_Base):
    """Cross-bank / cross-border AML information-sharing declaration.

    Backs FATF Recommendation 18 / Wolfsberg CBDDQ / FinCEN 314(b) /
    AMLA cross-border infrastructure (see DATA-10 in the data-problem
    whitepaper). When `enabled=False` (the default), the spec carries
    a zero-cost record of "we considered this and opted out"; when
    True, the listed partners are actively in scope.

    The sandbox at `compliance/sandbox.py` consumes this block via the
    `aml share-pattern` CLI command. Production-grade cross-FI exchange
    is out of scope; this is the *reference surface* the whitepaper's
    DATA-10 describes.
    """

    enabled: bool = False
    partners: list[InformationSharingPartner] = Field(default_factory=list)
    notes: str = ""


class Program(_Base):
    name: str
    jurisdiction: str
    regulator: str
    owner: str
    effective_date: date
    # Controls what the GenAI assistant logs to `ai_interactions.jsonl`.
    # `hash_only` (default) writes a SHA-256 of the reply text — bounds
    # PII transit to disk. `full_text` logs the entire reply for forensic
    # recall; institutions opt into this only after clearing it against
    # their privacy posture (the spec change is itself the paper trail).
    ai_audit_log: AiAuditLogMode = "hash_only"


class Column(_Base):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: ColumnType
    nullable: bool = True
    pii: bool = False
    enum: list[str] | None = None
    constraints: list[str] | None = None
    # Per-attribute freshness pinning (DATA-2 in the data-problem
    # whitepaper). When set, the engine runs a freshness scan after
    # warehouse build and emits a `pkyc_trigger` audit event for any row
    # whose `last_refreshed_at_column` is older than `max_staleness_days`
    # from `as_of`. Both fields must be set together (validated at the
    # contract level); `last_refreshed_at_column` must reference another
    # column on the same contract typed `timestamp` or `date`.
    max_staleness_days: int | None = Field(default=None, ge=1)
    last_refreshed_at_column: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")


class DataContract(_Base):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    source: str
    freshness_sla: str | None = Field(default=None, pattern=r"^[0-9]+[smhd]$")
    columns: list[Column]
    quality_checks: list[dict[str, Any]] = Field(default_factory=list)


class RegulationRef(_Base):
    citation: str
    description: str
    # Optional canonical URL for the cited regulation. When present, the
    # `aml regwatch` command can fetch + SHA-256 the page content to detect
    # silent drift (FinCEN BOI March 2025 narrowing was the canonical
    # example: page changed without notice; downstream specs went stale).
    # When omitted, regwatch falls back to its built-in citation→URL
    # resolver covering common US/CA/EU/UK/FATF/Wolfsberg sources.
    url: str | None = None


class AggregationWindowLogic(_Base):
    type: Literal["aggregation_window"]
    source: str
    filter: dict[str, Any] | None = None
    group_by: list[str]
    window: str = Field(pattern=r"^[0-9]+[smhd]$")
    having: dict[str, Any]


class ListMatchLogic(_Base):
    type: Literal["list_match"]
    source: str
    field: str
    list: str
    match: Literal["exact", "fuzzy"]
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class CustomSQLLogic(_Base):
    type: Literal["custom_sql"]
    sql: str


class PythonRefLogic(_Base):
    type: Literal["python_ref"]
    callable: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")
    model_id: str
    model_version: str


class NetworkPatternLogic(_Base):
    """Detect patterns over the entity-resolution graph.

    The engine maintains `resolved_entity_link` (pairs of customers sharing a
    linking attribute). This rule type runs a recursive CTE up to `max_hops`
    away from each customer and flags those whose subgraph satisfies a
    `having` condition (typically minimum component size or shared-attribute
    count).
    """

    type: Literal["network_pattern"]
    source: str = "customer"  # source contract used as the seed entity table
    pattern: Literal["component_size", "common_counterparty"] = "component_size"
    max_hops: int = Field(default=2, ge=1, le=5)
    having: dict[str, Any]  # e.g. {"component_size": {"gte": 3}}


RuleLogic = Annotated[
    Union[
        AggregationWindowLogic,
        ListMatchLogic,
        CustomSQLLogic,
        PythonRefLogic,
        NetworkPatternLogic,
    ],
    Field(discriminator="type"),
]


class Rule(_Base):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    severity: Severity
    status: RuleStatus = "active"
    # Declares whether the rule is meant to run as a batch sweep, against
    # a streaming source (Kafka/Kinesis), or both. The reference engine in
    # v1 only executes batch; the field records institution intent so an
    # operator can route at deployment time. `both` means the same logic
    # is valid for either mode.
    evaluation_mode: EvaluationMode = "batch"
    regulation_refs: list[RegulationRef] = Field(min_length=1)
    logic: RuleLogic
    escalate_to: str
    evidence: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # Optional sweep grid consumed by `aml tune`. Keys are dot-paths into
    # the rule (e.g. `logic.having.count`); values are lists of candidate
    # values to try. The tuner runs the engine once per Cartesian
    # combination over a fixed dataset, then reports alert-count delta
    # vs the production thresholds. Pure metadata; the runtime engine
    # ignores this field, so it's a strictly additive change.
    tuning_grid: dict[str, list[Any]] | None = None
    # FinCEN AML/CFT priority this rule contributes to detecting. Consumed
    # by `generators/effectiveness.py` to compute coverage-by-priority for
    # the Effectiveness Evidence Pack required by the April 2026 NPRM.
    # Defaults to None — rules without an explicit priority get bucketed
    # under "other" in the pack so the MLRO sees the gap.
    aml_priority: AmlPriority | None = None
    # Model-risk-management tier (SR 26-2 / 2021 Interagency Statement).
    # Consumed by `generators/mrm.py` to drive validation cadence and
    # materiality classification in the per-rule MRM dossier. Defaults
    # to None — rules without a tier get bucketed as "low" by the
    # generator with a flag asking the second-line model-validation team
    # to classify explicitly.
    model_tier: ModelTier | None = None
    # Required validation cadence in months. SR 26-2 expects high-tier
    # models annually (12), medium every 18-24, low every 24-36.
    # If unset, the MRM generator picks a default by tier.
    validation_cadence_months: int | None = Field(default=None, ge=1, le=60)


class Queue(_Base):
    id: str
    sla: str = Field(pattern=r"^[0-9]+[smhd]$")
    next: list[str] = Field(default_factory=list)
    regulator_form: str | None = None


class Workflow(_Base):
    queues: list[Queue]


class ReportingForm(_Base):
    model_config = ConfigDict(extra="allow", frozen=True)
    template: str
    mandatory_fields: list[str] | None = None
    trigger: dict[str, Any] | None = None


class Reporting(_Base):
    forms: dict[str, ReportingForm] = Field(default_factory=dict)


Audience = Literal[
    "svp",
    "vp",
    "director",
    "manager",
    "pm",
    "developer",
    "business",
    "auditor",
    "analyst",
]
MetricCategory = Literal["operational", "effectiveness", "risk", "regulatory", "delivery"]
Cadence = Literal["daily", "weekly", "monthly", "quarterly", "annual", "on_demand"]


class CountFormula(_Base):
    type: Literal["count"]
    source: Literal["alerts", "cases", "decisions", "rules", "txn", "customer"]
    filter: dict[str, Any] | None = None
    distinct_by: str | None = None


class SumFormula(_Base):
    type: Literal["sum"]
    source: Literal["alerts", "cases", "txn"]
    field: str
    filter: dict[str, Any] | None = None


class RatioFormula(_Base):
    type: Literal["ratio"]
    numerator: "MetricFormula"
    denominator: "MetricFormula"


class CoverageFormula(_Base):
    type: Literal["coverage"]
    universe: Literal["typologies", "jurisdictions", "products"]
    covered_by: Literal["rule_tags", "regulation_refs"]


class SQLFormula(_Base):
    type: Literal["sql"]
    sql: str


MetricFormula = Annotated[
    Union[CountFormula, SumFormula, RatioFormula, CoverageFormula, SQLFormula],
    Field(discriminator="type"),
]
RatioFormula.model_rebuild()


class Metric(_Base):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    description: str | None = None
    category: MetricCategory
    audience: list[Audience] = Field(min_length=1)
    owner: str | None = None
    unit: str | None = None
    formula: MetricFormula
    target: dict[str, Any] | None = None
    thresholds: dict[str, dict[str, Any]] | None = None


class ReportSection(_Base):
    title: str
    metrics: list[str]
    commentary: str | None = None


class Report(_Base):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    title: str | None = None
    audience: Audience
    cadence: Cadence
    sections: list[ReportSection]


class AMLSpec(_Base):
    version: Literal[1]
    program: Program
    data_contracts: list[DataContract]
    rules: list[Rule]
    workflow: Workflow
    reporting: Reporting | None = None
    retention_policy: dict[str, str] | None = None
    metrics: list[Metric] = Field(default_factory=list)
    reports: list[Report] = Field(default_factory=list)
    # PR-DATA-10: cross-bank / cross-border AML information-sharing
    # declaration (FATF R.18 / Wolfsberg CBDDQ / FinCEN 314(b) / AMLA).
    # Defaults to disabled; opt-in by setting `enabled: true` and
    # listing partners. The framework's `compliance/sandbox.py` consumes
    # this block via `aml share-pattern`.
    information_sharing: InformationSharing | None = None

    @model_validator(mode="after")
    def _check_cross_references(self) -> "AMLSpec":
        contract_ids = {c.id for c in self.data_contracts}
        queue_ids = {q.id for q in self.workflow.queues}

        for rule in self.rules:
            if hasattr(rule.logic, "source") and rule.logic.source not in contract_ids:
                raise ValueError(
                    f"rule '{rule.id}' references unknown data_contract '{rule.logic.source}'"
                )
            if rule.escalate_to not in queue_ids:
                raise ValueError(
                    f"rule '{rule.id}' escalates to unknown queue '{rule.escalate_to}'"
                )

        # Freshness-pinning cross-reference: a column with
        # `max_staleness_days` set must also point at a sibling column
        # on the same contract via `last_refreshed_at_column`, and that
        # sibling must be typed `timestamp` or `date`. Validates at spec
        # load time so the engine doesn't have to defensively re-check.
        for contract in self.data_contracts:
            cols_by_name = {c.name: c for c in contract.columns}
            for col in contract.columns:
                pinned = col.max_staleness_days is not None
                ref = col.last_refreshed_at_column
                if pinned and not ref:
                    raise ValueError(
                        f"contract '{contract.id}' column '{col.name}' has "
                        f"`max_staleness_days` but no `last_refreshed_at_column` — "
                        f"both fields must be set together"
                    )
                if ref and not pinned:
                    raise ValueError(
                        f"contract '{contract.id}' column '{col.name}' has "
                        f"`last_refreshed_at_column` but no `max_staleness_days` — "
                        f"both fields must be set together"
                    )
                if ref:
                    if ref not in cols_by_name:
                        raise ValueError(
                            f"contract '{contract.id}' column '{col.name}' references "
                            f"unknown `last_refreshed_at_column` '{ref}'"
                        )
                    sibling = cols_by_name[ref]
                    if sibling.type not in ("timestamp", "date"):
                        raise ValueError(
                            f"contract '{contract.id}' column '{col.name}' references "
                            f"`last_refreshed_at_column` '{ref}' which is type "
                            f"'{sibling.type}', not `timestamp` or `date`"
                        )

        metric_ids = {m.id for m in self.metrics}
        for report in self.reports:
            for section in report.sections:
                for m_id in section.metrics:
                    if m_id not in metric_ids:
                        raise ValueError(
                            f"report '{report.id}' section '{section.title}' "
                            f"references unknown metric '{m_id}'"
                        )
        return self
