"""MRM bundle — Model Risk Management dossier per SR 26-2 / Interagency Statement.

The Federal Reserve, FDIC, and OCC formally rescinded SR 11-7 on
**2026-04-17**, replacing it with **OCC Bulletin 2026-13 / SR 26-2** —
a more risk-based, principles-driven model-risk-management framework.
The new guidance explicitly re-confirms that AML transaction-monitoring
rules and sanctions-screening tools meet the "model" definition.
Banks have a 12-month implementation window to re-baseline their model
inventory under the new guidance.

This generator emits the per-rule MRM dossier the bank's second-line
model-validation team needs:

    Section 1 — Inventory metadata        (id, owner, tier, cadence)
    Section 2 — Conceptual soundness       (rule logic + citations)
    Section 3 — Implementation evidence    (run_dir hash, code path)
    Section 4 — Validation report          (Tuning Lab outputs, if any)
    Section 5 — Ongoing monitoring         (next-validation date,
                                             alert volume drift cues)
    Section 6 — Audit-trail anchor         (spec hash + decisions hash)

Each dossier is a single Markdown document plus a structured JSON
sidecar. Determinism: identical inputs → identical bytes (the JSON
sidecar is sorted; Markdown is fully derivable from it).

Pairs with `generators/effectiveness.py` (PR #52): Effectiveness Pack
speaks to the first line + senior management ("does the programme
work?"); MRM bundle speaks to the second-line model-validation team
("how was each rule validated?"). Both are regulator-facing, but for
different examiner audiences and different review paths.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from aml_framework import __version__ as ENGINE_VERSION
from aml_framework.spec.models import AMLSpec, ModelTier, Rule

GUIDANCE_VERSION = "SR-26-2 / OCC-Bulletin-2026-13"
GUIDANCE_EFFECTIVE_DATE = "2026-04-17"

# Default validation cadence per tier (months). Operators can override
# per-rule via `validation_cadence_months` on the spec.
DEFAULT_CADENCE_MONTHS: dict[ModelTier, int] = {
    "high": 12,
    "medium": 18,
    "low": 24,
}


@dataclass(frozen=True)
class ValidationEvidence:
    """One slice of validation evidence — typically a Tuning Lab sweep."""

    source: str  # e.g. "tuning_run", "shadow_diff", "external_audit"
    recorded_at: str  # ISO timestamp from the audit ledger
    summary: dict[str, Any]


@dataclass(frozen=True)
class MRMDossier:
    """Per-rule MRM dossier."""

    rule_id: str
    rule_name: str
    tier: ModelTier
    cadence_months: int
    inventory: dict[str, Any]
    conceptual_soundness: dict[str, Any]
    implementation: dict[str, Any]
    validation_evidence: list[ValidationEvidence] = field(default_factory=list)
    ongoing_monitoring: dict[str, Any] = field(default_factory=dict)
    audit_trail_anchor: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "tier": self.tier,
            "cadence_months": self.cadence_months,
            "inventory": self.inventory,
            "conceptual_soundness": self.conceptual_soundness,
            "implementation": self.implementation,
            "validation_evidence": [
                {
                    "source": e.source,
                    "recorded_at": e.recorded_at,
                    "summary": e.summary,
                }
                for e in self.validation_evidence
            ],
            "ongoing_monitoring": self.ongoing_monitoring,
            "audit_trail_anchor": self.audit_trail_anchor,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_tier(rule: Rule) -> ModelTier:
    """Pick the rule's MRM tier, defaulting to 'low' when unset.

    The dossier's `inventory.tier_classification_status` records whether
    the tier was explicit or defaulted, so model-validation teams see
    where they need to step in.
    """
    return rule.model_tier or "low"


def _resolve_cadence(rule: Rule) -> int:
    if rule.validation_cadence_months is not None:
        return rule.validation_cadence_months
    return DEFAULT_CADENCE_MONTHS[_resolve_tier(rule)]


def _conceptual_soundness(rule: Rule) -> dict[str, Any]:
    """Auto-generated conceptual soundness narrative from rule logic + refs."""
    logic = rule.logic
    logic_summary: dict[str, Any] = {"type": logic.type}

    if logic.type == "aggregation_window":
        logic_summary.update(
            {
                "source": logic.source,
                "group_by": list(logic.group_by),
                "window": logic.window,
                "filter": logic.filter or {},
                "having": logic.having,
            }
        )
    elif logic.type == "list_match":
        logic_summary.update(
            {
                "source": logic.source,
                "field": logic.field,
                "list": logic.list,
                "match": logic.match,
                "threshold": logic.threshold,
            }
        )
    elif logic.type == "custom_sql":
        logic_summary.update({"sql_excerpt": (logic.sql or "")[:240]})
    elif logic.type == "python_ref":
        logic_summary.update(
            {
                "callable": logic.callable,
                "model_id": logic.model_id,
                "model_version": logic.model_version,
            }
        )
    elif logic.type == "network_pattern":
        logic_summary.update(
            {
                "pattern": logic.pattern,
                "max_hops": logic.max_hops,
                "having": logic.having,
            }
        )

    return {
        "narrative": (
            f"Rule '{rule.id}' detects {rule.name.lower()} "
            f"using a {logic.type.replace('_', ' ')} approach. "
            f"Severity: {rule.severity}. "
            f"Tags: {', '.join(rule.tags) if rule.tags else 'none'}."
        ),
        "logic": logic_summary,
        "regulation_refs": [
            {"citation": r.citation, "description": r.description} for r in rule.regulation_refs
        ],
    }


def _implementation(rule: Rule, manifest: dict[str, Any]) -> dict[str, Any]:
    """Where the rule actually runs in the codebase + which version."""
    logic_path = {
        "aggregation_window": "src/aml_framework/engine/runner.py (compile_rule_sql + DuckDB)",
        "list_match": "src/aml_framework/engine/runner.py:_execute_list_match",
        "custom_sql": "src/aml_framework/engine/runner.py (compile_rule_sql passthrough)",
        "python_ref": f"loaded dynamically from `{getattr(rule.logic, 'callable', '?')}`",
        "network_pattern": "src/aml_framework/engine/runner.py:_execute_network_pattern",
    }.get(rule.logic.type, "unknown")

    return {
        "engine_version": ENGINE_VERSION,
        "code_path": logic_path,
        "spec_content_hash": manifest.get("spec_content_hash"),
        "as_of": manifest.get("as_of"),
        "evaluation_mode": rule.evaluation_mode,
    }


def _validation_evidence(rule_id: str, decisions: list[dict[str, Any]]) -> list[ValidationEvidence]:
    """Pull tuning_run events that touched this rule."""
    out: list[ValidationEvidence] = []
    for d in decisions:
        if d.get("event") != "tuning_run":
            continue
        if d.get("rule_id") != rule_id:
            continue
        out.append(
            ValidationEvidence(
                source="tuning_run",
                recorded_at=d.get("ts", ""),
                summary={
                    "grid_size": d.get("grid_size"),
                    "baseline_alerts": d.get("baseline_alerts"),
                    "scenarios_with_more_alerts": d.get("scenarios_with_more_alerts"),
                    "scenarios_with_fewer_alerts": d.get("scenarios_with_fewer_alerts"),
                    "best_f1": d.get("best_f1"),
                },
            )
        )
    return out


def _ongoing_monitoring(
    rule: Rule,
    alerts_by_rule: dict[str, list[dict[str, Any]]],
    as_of: datetime,
) -> dict[str, Any]:
    cadence = _resolve_cadence(rule)
    next_validation = (as_of + timedelta(days=cadence * 30)).date().isoformat()
    return {
        "alert_count_this_run": len(alerts_by_rule.get(rule.id, [])),
        "cadence_months": cadence,
        "next_validation_due": next_validation,
        "drift_signal": "monitor alert-volume vs the run history baseline",
    }


def _audit_anchor(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "spec_content_hash": manifest.get("spec_content_hash"),
        "decisions_hash": manifest.get("decisions_hash"),
        "as_of": manifest.get("as_of"),
        "run_dir": manifest.get("run_dir"),
    }


# ---------------------------------------------------------------------------
# Top-level builders
# ---------------------------------------------------------------------------


def build_dossier(
    rule: Rule,
    *,
    decisions: list[dict[str, Any]] | None = None,
    alerts_by_rule: dict[str, list[dict[str, Any]]] | None = None,
    manifest: dict[str, Any] | None = None,
    as_of: datetime | None = None,
) -> MRMDossier:
    """Build one rule's MRM dossier."""
    decisions = decisions or []
    alerts_by_rule = alerts_by_rule or {}
    manifest = manifest or {}
    as_of = as_of or datetime.now(tz=timezone.utc)

    tier = _resolve_tier(rule)
    cadence = _resolve_cadence(rule)
    classification_status = "explicit" if rule.model_tier is not None else "defaulted_to_low"

    return MRMDossier(
        rule_id=rule.id,
        rule_name=rule.name,
        tier=tier,
        cadence_months=cadence,
        inventory={
            "id": rule.id,
            "name": rule.name,
            "severity": rule.severity,
            "tier": tier,
            "tier_classification_status": classification_status,
            "evaluation_mode": rule.evaluation_mode,
            "tags": list(rule.tags),
            "status": rule.status,
        },
        conceptual_soundness=_conceptual_soundness(rule),
        implementation=_implementation(rule, manifest),
        validation_evidence=_validation_evidence(rule.id, decisions),
        ongoing_monitoring=_ongoing_monitoring(rule, alerts_by_rule, as_of),
        audit_trail_anchor=_audit_anchor(manifest),
    )


def build_dossier_json(rule: Rule, **kwargs: Any) -> bytes:
    return json.dumps(
        build_dossier(rule, **kwargs).to_dict(),
        indent=2,
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def render_dossier_markdown(dossier: MRMDossier) -> str:
    """Render the dossier as a Markdown document for the model-validation team."""
    lines: list[str] = []
    lines.append(f"# MRM Dossier — {dossier.rule_name} (`{dossier.rule_id}`)")
    lines.append("")
    lines.append(f"**Guidance**: {GUIDANCE_VERSION} (effective {GUIDANCE_EFFECTIVE_DATE})")
    lines.append(f"**Engine version**: `{ENGINE_VERSION}`")
    lines.append("")

    lines.append("## 1. Inventory")
    inv = dossier.inventory
    for k, v in sorted(inv.items()):
        lines.append(f"- **{k}**: `{v}`")
    lines.append("")

    lines.append("## 2. Conceptual soundness")
    cs = dossier.conceptual_soundness
    lines.append(cs.get("narrative", ""))
    lines.append("")
    lines.append("**Logic**:")
    lines.append("```json")
    lines.append(json.dumps(cs.get("logic", {}), indent=2, sort_keys=True, default=str))
    lines.append("```")
    lines.append("")
    lines.append("**Regulation references**:")
    for ref in cs.get("regulation_refs", []):
        lines.append(f"- **{ref['citation']}** — {ref['description']}")
    lines.append("")

    lines.append("## 3. Implementation")
    impl = dossier.implementation
    for k, v in sorted(impl.items()):
        lines.append(f"- **{k}**: `{v}`")
    lines.append("")

    lines.append("## 4. Validation evidence")
    if dossier.validation_evidence:
        for e in dossier.validation_evidence:
            lines.append(f"- {e.source} @ {e.recorded_at}")
            lines.append("  ```json")
            lines.append(
                "  "
                + json.dumps(e.summary, indent=2, sort_keys=True, default=str).replace("\n", "\n  ")
            )
            lines.append("  ```")
    else:
        lines.append(
            "_No tuning_run evidence recorded for this rule. Run `aml tune --rule "
            f"{dossier.rule_id} --audit-run-dir <run>` to generate validation evidence._"
        )
    lines.append("")

    lines.append("## 5. Ongoing monitoring")
    om = dossier.ongoing_monitoring
    for k, v in sorted(om.items()):
        lines.append(f"- **{k}**: `{v}`")
    lines.append("")

    lines.append("## 6. Audit-trail anchor")
    a = dossier.audit_trail_anchor
    for k, v in sorted(a.items()):
        lines.append(f"- **{k}**: `{v}`")
    lines.append("")

    if dossier.inventory.get("tier_classification_status") == "defaulted_to_low":
        lines.append(
            "> ⚠️  Tier was defaulted to `low`. The second-line model-"
            "validation team should classify this rule explicitly via "
            "`Rule.model_tier` in the spec."
        )

    return "\n".join(lines)


def build_inventory(spec: AMLSpec) -> dict[str, Any]:
    """Aggregate inventory for the whole spec — all rules with tier + cadence.

    Useful for the bank's second-line dashboard ("show me every model
    we have, sorted by tier").
    """
    rows: list[dict[str, Any]] = []
    for r in spec.rules:
        tier = _resolve_tier(r)
        rows.append(
            {
                "rule_id": r.id,
                "name": r.name,
                "severity": r.severity,
                "tier": tier,
                "cadence_months": _resolve_cadence(r),
                "tier_classification_status": "explicit"
                if r.model_tier is not None
                else "defaulted_to_low",
                "evaluation_mode": r.evaluation_mode,
                "logic_type": r.logic.type,
            }
        )
    rows.sort(key=lambda r: ({"high": 0, "medium": 1, "low": 2}[r["tier"]], r["rule_id"]))

    by_tier = {"high": 0, "medium": 0, "low": 0}
    by_status: dict[str, int] = {}
    for r in rows:
        by_tier[r["tier"]] += 1
        by_status[r["tier_classification_status"]] = (
            by_status.get(r["tier_classification_status"], 0) + 1
        )

    return {
        "_guidance": GUIDANCE_VERSION,
        "_guidance_effective": GUIDANCE_EFFECTIVE_DATE,
        "_generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "programme": {
            "name": spec.program.name,
            "jurisdiction": spec.program.jurisdiction,
            "regulator": spec.program.regulator,
        },
        "summary": {
            "total_rules": len(rows),
            "by_tier": by_tier,
            "by_classification_status": by_status,
        },
        "rules": rows,
    }


def export_bundle_from_run_dir(
    spec: AMLSpec,
    run_dir: Path,
    out_dir: Path,
    *,
    rule_ids: list[str] | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Read a finalised run dir, write per-rule MRM dossiers + inventory.

    Returns a manifest of files written. `rule_ids=None` means every
    active rule in the spec.
    """
    if not run_dir.exists():
        raise FileNotFoundError(f"Run dir not found: {run_dir}")

    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes()) if manifest_path.exists() else {}

    # Pull alerts + decisions (same shape as effectiveness.py).
    alerts_by_rule: dict[str, list[dict[str, Any]]] = {}
    alerts_dir = run_dir / "alerts"
    if alerts_dir.exists():
        for jsonl in sorted(alerts_dir.glob("*.jsonl")):
            rule_id = jsonl.stem
            rows: list[dict[str, Any]] = []
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
            alerts_by_rule[rule_id] = rows

    decisions: list[dict[str, Any]] = []
    decisions_path = run_dir / "decisions.jsonl"
    if decisions_path.exists():
        for line in decisions_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                decisions.append(json.loads(line))

    if as_of is None and manifest.get("as_of"):
        try:
            as_of = datetime.fromisoformat(manifest["as_of"])
        except ValueError:
            as_of = None

    targets = [r for r in spec.rules if r.id in rule_ids] if rule_ids else list(spec.rules)

    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[dict[str, str]] = []
    for rule in targets:
        dossier = build_dossier(
            rule,
            decisions=decisions,
            alerts_by_rule=alerts_by_rule,
            manifest=manifest,
            as_of=as_of,
        )
        json_path = out_dir / f"{rule.id}.json"
        md_path = out_dir / f"{rule.id}.md"
        json_path.write_bytes(
            json.dumps(dossier.to_dict(), indent=2, sort_keys=True, default=str).encode("utf-8")
        )
        md_path.write_text(render_dossier_markdown(dossier), encoding="utf-8")
        written.append({"rule_id": rule.id, "json": str(json_path), "markdown": str(md_path)})

    # Always write the spec-wide inventory.
    inventory = build_inventory(spec)
    inv_path = out_dir / "inventory.json"
    inv_path.write_bytes(
        json.dumps(inventory, indent=2, sort_keys=True, default=str).encode("utf-8")
    )

    return {
        "guidance": GUIDANCE_VERSION,
        "out_dir": str(out_dir),
        "rules_written": written,
        "inventory_path": str(inv_path),
        "summary": inventory["summary"],
    }


def _today() -> date:
    """Indirection for tests that want to pin 'today'."""
    return datetime.now(tz=timezone.utc).date()
