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
ColumnType = Literal["string", "integer", "decimal", "boolean", "date", "timestamp"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Program(_Base):
    name: str
    jurisdiction: str
    regulator: str
    owner: str
    effective_date: date


class Column(_Base):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    type: ColumnType
    nullable: bool = True
    pii: bool = False
    enum: list[str] | None = None
    constraints: list[str] | None = None


class DataContract(_Base):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    source: str
    freshness_sla: str | None = Field(default=None, pattern=r"^[0-9]+[smhd]$")
    columns: list[Column]
    quality_checks: list[dict[str, Any]] = Field(default_factory=list)


class RegulationRef(_Base):
    citation: str
    description: str


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


RuleLogic = Annotated[
    Union[AggregationWindowLogic, ListMatchLogic, CustomSQLLogic, PythonRefLogic],
    Field(discriminator="type"),
]


class Rule(_Base):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    severity: Severity
    status: RuleStatus = "active"
    regulation_refs: list[RegulationRef] = Field(min_length=1)
    logic: RuleLogic
    escalate_to: str
    evidence: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


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


class AMLSpec(_Base):
    version: Literal[1]
    program: Program
    data_contracts: list[DataContract]
    rules: list[Rule]
    workflow: Workflow
    reporting: Reporting | None = None
    retention_policy: dict[str, str] | None = None

    @model_validator(mode="after")
    def _check_cross_references(self) -> "AMLSpec":
        contract_ids = {c.id for c in self.data_contracts}
        queue_ids = {q.id for q in self.workflow.queues}

        for rule in self.rules:
            if hasattr(rule.logic, "source") and rule.logic.source not in contract_ids:
                raise ValueError(
                    f"rule '{rule.id}' references unknown data_contract "
                    f"'{rule.logic.source}'"
                )
            if rule.escalate_to not in queue_ids:
                raise ValueError(
                    f"rule '{rule.id}' escalates to unknown queue "
                    f"'{rule.escalate_to}'"
                )
        return self
