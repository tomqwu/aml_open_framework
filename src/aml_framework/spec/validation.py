"""Spec-level advisory validation passes — issue #529 (Sub-feature B/C).

The two-layer load (`loader.load_spec`: JSON Schema -> Pydantic) is
structural + cross-reference. This module adds *governance* passes that
are advisory by default and promotable to hard failures under a strict
flag — mirroring the runtime environment-gating posture
(`engine/promotion.py`: WARN by default, raise when
`program.strict_environment_gating`).

Pass 1 — `risk_tier` coverage (Pillars 4 + 5):
  Every `active` rule is *expected* to declare a first-class `risk_tier`
  (low/medium/high). The pydantic field stays OPTIONAL so a legacy spec
  without it still LOADS (additive contract — see
  `tests/test_spec_risk_tier.py`). This pass enforces the *expectation*:
  an active rule missing `risk_tier` is a WARN in non-strict mode and an
  ERROR (validation failure) in strict mode.

Why a validation pass, not a required pydantic field: making the field
`required` would hard-crash `load_spec` on any historical spec / fixture
that omits it (every determinism/diff/hash test builds rules without it),
breaking the "loading a legacy spec doesn't hard-crash" contract the
issue calls out explicitly. The strict/non-strict layer gives the same
enforcement leverage without that breakage.
"""

from __future__ import annotations

from aml_framework.spec.models import AMLSpec


class SpecValidationError(ValueError):
    """Raised by a strict validation pass when an advisory expectation is
    violated. A plain `ValueError` subclass so callers that already catch
    `ValueError` from `load_spec` keep working."""


def collect_risk_tier_warnings(spec: AMLSpec) -> list[str]:
    """Return one warning string per `active` rule missing `risk_tier`.

    Pure function — no I/O. Only `active` rules are checked: an
    `experimental` / `deprecated` / `pending_promotion` rule is not yet
    (or no longer) a governed production control, so it carries no
    risk-tier expectation. Empty list means full coverage.
    """
    warnings: list[str] = []
    for rule in spec.rules:
        if rule.status != "active":
            continue
        if rule.risk_tier is None:
            warnings.append(
                f"rule '{rule.id}' is active but has no risk_tier "
                "(expected one of low/medium/high — Pillar 5 risk-based controls)"
            )
    return warnings


def validate_risk_tier_coverage(spec: AMLSpec, *, strict: bool) -> list[str]:
    """Check active-rule risk_tier coverage.

    Returns the list of warnings (always). When `strict` is True and any
    warning exists, raises `SpecValidationError` instead — the same
    WARN-by-default / raise-under-strict posture as the runtime
    environment gate.
    """
    warnings = collect_risk_tier_warnings(spec)
    if strict and warnings:
        raise SpecValidationError(
            f"strict validation: {len(warnings)} active rule(s) missing risk_tier:\n"
            + "\n".join(f"  - {w}" for w in warnings)
        )
    return warnings
