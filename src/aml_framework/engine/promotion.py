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

    def __init__(
        self,
        rule_id: str,
        environment: str,
        approved: list[str],
        *,
        reason: str | None = None,
    ) -> None:
        self.rule_id = rule_id
        self.environment = environment
        self.approved = list(approved)
        self.reason = reason
        # #529 (Pillar 7): the model-risk approval gate reuses this same
        # error class but with a `reason` so the message is accurate for
        # an approval block (vs a lane-promotion block).
        if reason is not None:
            super().__init__(
                f"rule '{rule_id}' is blocked in environment '{environment}': {reason}"
            )
        else:
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


# Model-risk tiers that carry an approval-gate expectation. `low` is
# immaterial — tier-1 in SR 26-2 terms — so it is never gated; only the
# material tiers (medium/high = tiers 2/3) require approval before prod.
_MATERIAL_MODEL_TIERS = frozenset({"medium", "high"})


def model_approval_gate_applies(rule: Rule, program: Program) -> bool:
    """Return True when the model-risk approval gate is in force for `rule`.

    The gate fires only when ALL of the following hold (#529, Pillar 7):
      * `program.model_risk_monitoring.require_approval_before_prod` is on;
      * `program.environment == "prod"`;
      * `program.strict_environment_gating` is on (the gate raises the
        same `EnvironmentGatingError`, so it shares the strict posture);
      * the rule is a material model tier (`model_tier` medium/high).

    Pure — no I/O. Whether the rule is actually BLOCKED additionally
    depends on its `approval_status` (see `is_rule_model_approved`).
    """
    mrm = getattr(program, "model_risk_monitoring", None)
    if mrm is None or not getattr(mrm, "require_approval_before_prod", False):
        return False
    if program.environment != "prod":
        return False
    if not program.strict_environment_gating:
        return False
    return rule.model_tier in _MATERIAL_MODEL_TIERS


def is_rule_model_approved(rule: Rule) -> bool:
    """Return True when the rule has cleared model-risk approval.

    Only `approved` clears the gate; `pending` (the default) and
    `rejected` do not. Pure function.
    """
    return rule.approval_status == "approved"


def model_approval_audit_event(rule: Rule, program: Program, *, approved: bool) -> dict[str, Any]:
    """Build the `approval_gate_check` audit-ledger event dict.

    Emitted once per rule per run WHEN the gate applies (mirrors the
    `environment_gate_check` event), so the regulator pack can prove the
    model-risk approval gate was consulted, not just that blocked rules
    existed. `approved` is the gate outcome for this rule.
    """
    return {
        "event": "approval_gate_check",
        "rule_id": rule.id,
        "program_environment": program.environment,
        "model_tier": rule.model_tier,
        "approval_status": rule.approval_status,
        "approved": approved,
        "outcome": "approved" if approved else "blocked",
    }


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
