"""Trigger model — a single event flagging a customer for re-review."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

TriggerKind = Literal[
    "sanctions_hit",
    "adverse_media",
    "country_risk",
    "transaction_pattern",
    "stale_kyc",
]

Severity = Literal["low", "medium", "high", "critical"]
RecommendedAction = Literal["re_review", "escalate", "monitor"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Trigger(_Base):
    """One pKYC event tied to a single customer.

    `evidence` carries the detector-specific facts (matched name, list
    source, country code, alert count, days overdue, etc.). It's a free
    dict so each detector is self-contained — no schema changes when
    a new detector ships.
    """

    customer_id: str
    kind: TriggerKind
    severity: Severity
    detected_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommended_action: RecommendedAction = "re_review"
    detector: str = ""  # populated by the detector for traceability
    rule_refs: list[str] = Field(default_factory=list)
