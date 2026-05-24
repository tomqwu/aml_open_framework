"""PR-D3 (#376) — environment promotion model.

Specs declare the lane they currently run in via `Program.environment`
(`dev` / `test` / `uat` / `prod`). Each rule declares which lanes have
signed off on it via `Rule.environments`. The runner asks
`is_rule_approved_for_environment(rule, program)` before firing a rule;
when the rule is not approved for the program's lane, the runner emits a
WARN (and, when `Program.strict_environment_gating` is True, raises
`EnvironmentGatingError`).

`SignoffEvent` + `EnvironmentPromotion` are an immutable in-memory
projection of promotion sign-offs. They are NOT persisted by the engine
(the spec itself is the source of truth — `Rule.environments` is the
materialised result of past sign-offs). The model exists so an operator
can record sign-off events in a wrapper script and audit them via
`promotion_audit_event(...)`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aml_framework.spec.models import Environment, Program, Rule


class EnvironmentGatingError(RuntimeError):
    """Raised when a rule fires in an unapproved environment AND the
    program declares `strict_environment_gating: true`. The runner
    catches this only at run time; spec validation never raises it (a
    spec with mismatched lanes is valid — strict gating is a runtime
    posture, not a spec contract)."""

    def __init__(self, rule_id: str, environment: str, approved: list[str]) -> None:
        self.rule_id = rule_id
        self.environment = environment
        self.approved = list(approved)
        super().__init__(
            f"rule '{rule_id}' is not approved for environment '{environment}' "
            f"(approved lanes: {self.approved or ['<none>']})"
        )


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SignoffEvent(_Base):
    """A single promotion sign-off — "person X signed off rule R for
    environment E at time T". Immutable; ordered chronologically by
    `signed_off_at`. The engine never materialises these on disk; they
    are emitted as audit events via `promotion_audit_event(...)`."""

    rule_id: str = Field(min_length=1)
    environment: Environment
    signed_off_by: str = Field(min_length=1)
    signed_off_at: datetime
    note: str = ""


class EnvironmentPromotion(_Base):
    """Projection of promotion state for a single rule. Captures the
    lane the rule lives in (`current_environment`, mirroring
    `Rule.environments[-1]` for the highest lane), the lanes already
    signed off (mirrors `Rule.environments`), and the chronological list
    of sign-off events that got it there. Pure metadata — the engine
    does not consume this directly; `is_rule_approved_for_environment`
    works straight off `Rule.environments`."""

    rule_id: str = Field(min_length=1)
    current_environment: Environment
    approved_environments: list[Environment]
    signoffs: list[SignoffEvent] = Field(default_factory=list)


def is_rule_approved_for_environment(rule: Rule, program: Program) -> bool:
    """Return True if `rule` is approved to fire in `program.environment`.

    Pure function — no I/O, no side effects. The runner calls this once
    per rule per run; tests exercise the matrix of (rule_envs,
    program_env) combinations directly.
    """
    return program.environment in rule.environments


def promotion_audit_event(
    rule: Rule,
    program: Program,
    *,
    approved: bool,
    strict: bool | None = None,
) -> dict[str, Any]:
    """Build the audit-ledger event dict for a promotion-gate check.

    Always emitted — once per rule per run, regardless of outcome — so
    the audit trail proves the engine consulted the gate (not just that
    blocked rules existed). `strict` defaults to
    `program.strict_environment_gating`; passing it explicitly lets
    tests pin the rendered event without mutating the program.
    """
    strict_flag = program.strict_environment_gating if strict is None else strict
    return {
        "event": "environment_gate_check",
        "rule_id": rule.id,
        "program_environment": program.environment,
        "approved_environments": list(rule.environments),
        "approved": approved,
        "strict": strict_flag,
        "outcome": ("approved" if approved else ("blocked" if strict_flag else "warn_only")),
    }
