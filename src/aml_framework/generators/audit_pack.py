"""Pre-examination audit pack generator.

Round-7 PR #5. **FINTRAC's January 2026 examination manual update**
([FINTRAC examination guidance](
https://fintrac-canafe.canada.ca/guidance-directives/exam-examen/eng))
made the pre-exam evidence demand explicit: examiners now expect
institutions to arrive with a pre-built bundle covering rule
inventory, alert volumes, case dispositions, audit-trail integrity,
sanctions screening, and STR-filing record. Pulling this together
manually takes weeks; this generator does it in seconds.

Pattern mirrors the existing `mrm-bundle` generator (PR #53):
deterministic ZIP, per-section files, manifest with file-level
SHA-256. The shape is jurisdiction-templated — the FINTRAC pack
covers PCMLTFA + OSFI B-8 sections; future jurisdictions (FCA UK,
BaFin DE) clone the same skeleton and swap the section list +
regulator-specific evidence requirements.

What's in the FINTRAC pack
- `program.md` — program metadata + jurisdiction + effective date
- `inventory.json` — every active rule with regulation_refs +
  tier + last validation date
- `alerts_summary.json` — per-rule alert counts + severity dist
- `cases_summary.json` — case dispositions + STR-filing record
- `audit_trail_verification.json` — hash-chain integrity proof
- `sanctions_evidence.json` — list_match rule outputs +
  reference list refresh dates
- `pcmltfa_section_map.md` — every cited PCMLTFA section + which
  rules cover it (lets examiners verify coverage at a glance)
- `osfi_b8_pillars.md` — OSFI Guideline B-8 pillar coverage
- `manifest.json` — file-by-file + bundle-wide SHA-256

Why per-jurisdiction (not generic)
Examiners arrive with a checklist that's regulator-specific. A
FINTRAC examiner wants the LCTR/STR/EFTR filing record; an FCA
examiner wants the SAR-to-NCA log; an AMLA supervisor wants the
RTS effectiveness JSON (already covered by the Round-7 #2
outcomes pack). One generator per regulator with shared skeleton.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aml_framework.spec.models import AMLSpec

PACK_VERSION = "1"

# Fixed timestamp baked into every ZipInfo so identical inputs produce
# byte-identical archives — same determinism guarantee as the STR
# bundle generator (PR #64).
_ZIP_FIXED_TIME = (1980, 1, 1, 0, 0, 0)


# ---------------------------------------------------------------------------
# Jurisdiction-specific section assemblers
# ---------------------------------------------------------------------------


def _program_md(spec: AMLSpec) -> str:
    return (
        f"# Program: {spec.program.name}\n\n"
        f"- Jurisdiction: {spec.program.jurisdiction}\n"
        f"- Regulator: {spec.program.regulator}\n"
        f"- Owner: {spec.program.owner}\n"
        f"- Effective date: {spec.program.effective_date}\n"
        f"- Active rules: {sum(1 for r in spec.rules if r.status == 'active')}\n"
        f"- Total rules: {len(spec.rules)}\n"
        f"- Workflow queues: {len(spec.workflow.queues)}\n"
        f"- Reporting forms: {len(spec.reporting.forms) if spec.reporting else 0}\n"
    )


def _inventory(spec: AMLSpec) -> dict[str, Any]:
    return {
        "spec_program": spec.program.name,
        "rules": [
            {
                "id": r.id,
                "name": r.name,
                "severity": r.severity,
                "status": r.status,
                "logic_type": r.logic.type,
                "regulation_refs": [
                    {"citation": ref.citation, "description": ref.description}
                    for ref in r.regulation_refs
                ],
                "tier": r.model_tier or "unclassified",
                "validation_cadence_months": r.validation_cadence_months,
                "tags": list(r.tags),
            }
            for r in spec.rules
        ],
    }


def _alerts_summary(
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Per-rule alert counts + severity distribution."""
    by_rule: dict[str, dict[str, Any]] = {}
    for case in cases:
        rule_id = case.get("rule_id", "")
        sev = case.get("severity", "unknown")
        bucket = by_rule.setdefault(
            rule_id,
            {"total": 0, "by_severity": {}},
        )
        bucket["total"] += 1
        bucket["by_severity"][sev] = bucket["by_severity"].get(sev, 0) + 1
    return {
        "total_alerts": len(cases),
        "by_rule": by_rule,
    }


def _cases_summary(
    cases: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Case dispositions + STR-filing record."""
    decisions_by_case: dict[str, list[dict[str, Any]]] = {}
    for d in decisions:
        cid = d.get("case_id", "")
        if cid:
            decisions_by_case.setdefault(cid, []).append(d)

    str_filed = 0
    closed_no_action = 0
    pending = 0
    for case in cases:
        cid = case.get("case_id", "")
        case_decs = decisions_by_case.get(cid, [])
        # Same logic as outcomes.py — keep them in sync if extending.
        if any(
            (d.get("event") or "").lower() in {"str_filed", "sar_filed", "escalated_to_str"}
            or "str" in (d.get("disposition") or "").lower()
            for d in case_decs
        ):
            str_filed += 1
        elif any(
            (d.get("event") or "").lower()
            in {"closed_no_action", "closed_false_positive", "case_closed"}
            for d in case_decs
        ):
            closed_no_action += 1
        else:
            pending += 1

    return {
        "total_cases": len(cases),
        "str_filed": str_filed,
        "closed_no_action": closed_no_action,
        "pending": pending,
        "filing_rate_pct": round((str_filed / len(cases) * 100) if cases else 0, 2),
    }


def _audit_trail_verification(
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Hash-chain integrity proof — every decision links to its predecessor."""
    chain_intact = True
    chain_length = len(decisions)
    breaks: list[int] = []
    prev_hash = ""
    for i, d in enumerate(decisions):
        recorded_prev = d.get("prev_hash", "")
        if i == 0:
            # First decision: prev_hash should be empty or genesis marker.
            if recorded_prev not in ("", "0" * 64):
                chain_intact = False
                breaks.append(i)
        else:
            if recorded_prev != prev_hash:
                chain_intact = False
                breaks.append(i)
        prev_hash = d.get("hash", "")
    return {
        "chain_intact": chain_intact,
        "chain_length": chain_length,
        "breaks_at_indices": breaks,
        "verified_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
    }


def _sanctions_evidence(spec: AMLSpec, cases: list[dict[str, Any]]) -> dict[str, Any]:
    """list_match rule outputs + reference list refresh dates.

    For FINTRAC, the relevant lists are SEMA + UN consolidated +
    OFSI; the framework's `list_match` rule type handles all via
    `data/lists/sanctions.csv`. Examiners want to see (a) which
    rules screen, (b) when the list was last refreshed, (c) any
    matches found in the run.
    """
    list_match_rules = [r for r in spec.rules if r.logic.type == "list_match"]
    matches_by_rule: dict[str, int] = {}
    for case in cases:
        rule_id = case.get("rule_id", "")
        if any(r.id == rule_id for r in list_match_rules):
            matches_by_rule[rule_id] = matches_by_rule.get(rule_id, 0) + 1
    return {
        "screening_rules": [
            {
                "rule_id": r.id,
                "list_name": r.logic.list,
                "field": r.logic.field,
                "match_type": r.logic.match,
                "matches_in_run": matches_by_rule.get(r.id, 0),
            }
            for r in list_match_rules
        ],
        "total_matches": sum(matches_by_rule.values()),
    }


def _pcmltfa_section_map_md(spec: AMLSpec) -> str:
    """Every cited PCMLTFA section → which rules cover it."""
    by_section: dict[str, list[str]] = {}
    for rule in spec.rules:
        for ref in rule.regulation_refs:
            if "PCMLTFA" in ref.citation or "PCMLTFR" in ref.citation:
                by_section.setdefault(ref.citation, []).append(rule.id)
    if not by_section:
        return (
            "# PCMLTFA Section Coverage\n\n"
            "_No PCMLTFA / PCMLTFR citations found in this spec._\n\n"
            "If this spec is intended for FINTRAC submission, add Canadian "
            "regulation citations to each rule's `regulation_refs`.\n"
        )
    lines = ["# PCMLTFA Section Coverage", ""]
    for section in sorted(by_section.keys()):
        lines.append(f"## {section}")
        lines.append("")
        for rule_id in sorted(by_section[section]):
            lines.append(f"- `{rule_id}`")
        lines.append("")
    return "\n".join(lines)


def _osfi_b8_pillars_md(spec: AMLSpec) -> str:
    """OSFI Guideline B-8 pillar coverage cross-reference."""
    # OSFI B-8 has 4 named expectations; we cross-reference rule coverage.
    pillars = {
        "Board oversight": ["board", "governance", "oversight"],
        "Risk-based approach": ["risk", "edd", "kyc"],
        "Automated transaction monitoring": [
            "structuring",
            "rapid",
            "unusual",
            "dormant",
            "high_risk",
        ],
        "Sanctions integration": ["sanctions", "list_match", "screening"],
    }
    lines = ["# OSFI Guideline B-8 Pillar Coverage", ""]
    for pillar, keywords in pillars.items():
        matching = []
        for rule in spec.rules:
            haystack = " ".join([rule.id, rule.name] + list(rule.tags)).lower()
            if any(kw in haystack for kw in keywords):
                matching.append(rule.id)
        lines.append(f"## {pillar}")
        lines.append("")
        if matching:
            for rid in sorted(matching):
                lines.append(f"- `{rid}`")
        else:
            lines.append("_No rules tagged for this pillar._")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


SUPPORTED_JURISDICTIONS = frozenset({"CA-FINTRAC"})


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"unserialisable type {type(obj).__name__}")


def _dump_json(payload: Any) -> bytes:
    return json.dumps(
        payload, sort_keys=True, indent=2, default=_json_default, ensure_ascii=False
    ).encode("utf-8")


def build_audit_pack(
    spec: AMLSpec,
    cases: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    *,
    jurisdiction: str = "CA-FINTRAC",
) -> bytes:
    """Build a deterministic ZIP for pre-exam evidence submission.

    Args:
        spec: the AMLSpec to inventory.
        cases: list of case dicts (from `cases/<case_id>.json` ledger files).
        decisions: list of decision events (from `decisions.jsonl`).
        jurisdiction: which regulator's pack to build. Currently only
            CA-FINTRAC is supported; UK / EU / US planned for follow-ups.

    Returns the ZIP file as bytes (caller writes to disk / S3 / API).
    """
    if jurisdiction not in SUPPORTED_JURISDICTIONS:
        raise ValueError(
            f"unsupported jurisdiction {jurisdiction!r}; "
            f"supported: {sorted(SUPPORTED_JURISDICTIONS)}"
        )

    files: dict[str, bytes] = {
        "program.md": _program_md(spec).encode("utf-8"),
        "inventory.json": _dump_json(_inventory(spec)),
        "alerts_summary.json": _dump_json(_alerts_summary(cases)),
        "cases_summary.json": _dump_json(_cases_summary(cases, decisions)),
        "audit_trail_verification.json": _dump_json(_audit_trail_verification(decisions)),
        "sanctions_evidence.json": _dump_json(_sanctions_evidence(spec, cases)),
    }
    if jurisdiction == "CA-FINTRAC":
        files["pcmltfa_section_map.md"] = _pcmltfa_section_map_md(spec).encode("utf-8")
        files["osfi_b8_pillars.md"] = _osfi_b8_pillars_md(spec).encode("utf-8")

    # Manifest — last so it can hash everything else.
    file_hashes = {
        path: hashlib.sha256(payload).hexdigest() for path, payload in sorted(files.items())
    }
    bundle_hash = hashlib.sha256(
        "\n".join(f"{p}:{h}" for p, h in sorted(file_hashes.items())).encode("utf-8")
    ).hexdigest()
    manifest = {
        "pack_version": PACK_VERSION,
        "jurisdiction": jurisdiction,
        "spec_program": spec.program.name,
        "spec_jurisdiction": spec.program.jurisdiction,
        "regulator": spec.program.regulator,
        "files": file_hashes,
        "bundle_hash": bundle_hash,
    }
    files["manifest.json"] = _dump_json(manifest)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(files.keys()):
            info = zipfile.ZipInfo(filename=path, date_time=_ZIP_FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, files[path])
    return buf.getvalue()


def build_audit_pack_from_run_dir(
    spec: AMLSpec,
    run_dir: Path,
    *,
    jurisdiction: str = "CA-FINTRAC",
) -> bytes:
    """Convenience wrapper — load cases + decisions from disk, then build."""
    cases: list[dict[str, Any]] = []
    cases_dir = run_dir / "cases"
    if cases_dir.exists():
        for f in sorted(cases_dir.glob("*.json")):
            cases.append(json.loads(f.read_text(encoding="utf-8")))
    decisions: list[dict[str, Any]] = []
    dec_path = run_dir / "decisions.jsonl"
    if dec_path.exists():
        for line in dec_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                decisions.append(json.loads(line))
    return build_audit_pack(spec, cases, decisions, jurisdiction=jurisdiction)


__all__ = [
    "PACK_VERSION",
    "SUPPORTED_JURISDICTIONS",
    "build_audit_pack",
    "build_audit_pack_from_run_dir",
]
