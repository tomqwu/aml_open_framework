"""Spec-only model-population inventory (SR 26-2 / OCC 2026-13).

Distinct from `generators/mrm.py:build_inventory` (rule-tier, run-aware,
wall-clock-stamped): this is the deterministic, spec-only view of EVERY model
in the programme — each rule, each `python_ref` external model, and the N1
prioritization scorer (which is not a rule). One command answers the MLRO's
"what is our model population?" without needing a run.

Pure + deterministic: sorted output, no wall-clock timestamp, so two calls on
the same spec are byte-identical.
"""

from __future__ import annotations

from typing import Any

from aml_framework.generators.mrm import (
    GUIDANCE_EFFECTIVE_DATE,
    GUIDANCE_VERSION,
    _resolve_cadence,
    _resolve_tier,
)
from aml_framework.spec.models import AMLSpec

_TIER_ORDER = {"high": 0, "medium": 1, "low": 2}


def _md_cell(value: str) -> str:
    """Escape a value for a GitHub-markdown table cell so spec-controlled text
    (a rule name / business_intent / citation containing `|`, `\\`, or a
    newline) can't break column alignment."""
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _rule_entry(rule: Any, program_owner: str) -> dict[str, Any]:
    is_pyref = rule.logic.type == "python_ref"
    external = None
    if is_pyref:
        external = {
            "model_id": rule.logic.model_id,
            "model_version": rule.logic.model_version,
            "callable": rule.logic.callable,
        }
    return {
        "model_key": rule.id,
        "kind": "python_ref" if is_pyref else "rule",
        "name": rule.name,
        "purpose": rule.business_intent or rule.name,
        "tier": _resolve_tier(rule),
        "cadence_months": _resolve_cadence(rule),
        # Rules have no per-rule owner field — accountability rolls up to the
        # programme's designated AML/CFT officer (Program.owner).
        "owner": program_owner,
        "conceptual_soundness": [r.citation for r in rule.regulation_refs],
        "logic_type": rule.logic.type,
        "external_model": external,
        "last_outcome_analysis": None,
    }


def _scorer_entry(spec: AMLSpec) -> dict[str, Any] | None:
    """The N1 prioritization scorer as a governed model — only when enabled."""
    prio = getattr(spec.program, "prioritization", None)
    if prio is None or not prio.enabled:
        return None
    w = prio.weights
    return {
        "model_key": "prioritization_scorer",
        "kind": "scorer",
        "name": "Alert Prioritization Scorer (N1)",
        "purpose": (
            "Advisory SAR-likelihood triage score; re-orders queues, never changes disposition."
        ),
        "tier": "high",  # touches every alert; advisory but material to triage
        "cadence_months": 12,
        "owner": spec.program.owner,
        "conceptual_soundness": ["transparent weighted-linear; score=sigmoid(Σ weight·feature)"],
        "logic_type": "weighted_linear",
        "external_model": None,
        "last_outcome_analysis": None,
        "weights": {
            "severity": w.severity,
            "risk_tier": w.risk_tier,
            "amount": w.amount,
            "volume": w.volume,
        },
    }


def build_model_inventory(spec: AMLSpec) -> dict[str, Any]:
    """Deterministic SR-26-2 model-population inventory for the whole spec."""
    program_owner = spec.program.owner
    models: list[dict[str, Any]] = [_rule_entry(r, program_owner) for r in spec.rules]
    scorer = _scorer_entry(spec)
    if scorer is not None:
        models.append(scorer)

    models.sort(key=lambda m: (_TIER_ORDER[m["tier"]], m["model_key"]))

    by_kind: dict[str, int] = {}
    by_tier = {"high": 0, "medium": 0, "low": 0}
    for m in models:
        by_kind[m["kind"]] = by_kind.get(m["kind"], 0) + 1
        by_tier[m["tier"]] += 1

    return {
        "_guidance": GUIDANCE_VERSION,
        "_guidance_effective": GUIDANCE_EFFECTIVE_DATE,
        "programme": {
            "name": spec.program.name,
            "jurisdiction": spec.program.jurisdiction,
            "regulator": spec.program.regulator,
            "owner": program_owner,
        },
        "summary": {
            "total_models": len(models),
            "by_kind": by_kind,
            "by_tier": by_tier,
        },
        "models": models,
    }


def render_model_inventory_markdown(inv: dict[str, Any]) -> str:
    """Render the inventory as an MRM-review markdown table."""
    p = inv["programme"]
    lines = [
        f"# Model Inventory — {p['name']}",
        "",
        f"*{inv['_guidance']} (effective {inv['_guidance_effective']}) · "
        f"{p['jurisdiction']} · {p['regulator']} · owner: {p['owner']}*",
        "",
        f"**{inv['summary']['total_models']} models** — "
        + ", ".join(f"{k}: {v}" for k, v in sorted(inv["summary"]["by_kind"].items())),
        "",
        "| Model | Kind | Tier | Cadence (mo) | Owner | Purpose | Conceptual soundness |",
        "|---|---|---|---|---|---|---|",
    ]
    for m in inv["models"]:
        refs = _md_cell("; ".join(m["conceptual_soundness"]))
        lines.append(
            f"| `{_md_cell(m['model_key'])}` | {m['kind']} | {m['tier']} | {m['cadence_months']} "
            f"| {_md_cell(m['owner'])} | {_md_cell(m['purpose'])} | {refs} |"
        )
    return "\n".join(lines) + "\n"
