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
from datetime import datetime
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
                # PR-A2 follow-up: surface the rule author's stated
                # intent + explicit exclusions in the inventory so a
                # FINTRAC examiner reading the pack sees the scope
                # boundary alongside the citations. `business_intent`
                # stays None when undocumented; `out_of_scope` is always
                # a list (possibly empty).
                "business_intent": r.business_intent,
                "out_of_scope": list(r.out_of_scope),
            }
            for r in spec.rules
        ],
    }


def _program_intent_md(spec: AMLSpec) -> str:
    """PR-A2 follow-up: top-level rule-author scope-declarations digest.

    Surfaces every rule's `business_intent` + `out_of_scope` so an
    examiner answering "why didn't this fire on case X?" can scan the
    declared exclusions without opening the YAML. Skipped rules (those
    with neither field populated) get a one-line undocumented marker so
    the reviewer can see coverage gaps at a glance.
    """
    lines = [
        "# Program intent — rule-author scope declarations",
        "",
        f"Program: **{spec.program.name}** "
        f"(jurisdiction: {spec.program.jurisdiction}, "
        f"regulator: {spec.program.regulator})",
        "",
        (
            "Each rule's author may declare a `business_intent` (free-text "
            "rationale aimed at examiners / 2LoD) and `out_of_scope` "
            "(activities the rule deliberately does not catch). Both are "
            "optional — rules without either field are flagged below so "
            "reviewers can see documentation gaps."
        ),
        "",
    ]
    for rule in spec.rules:
        lines.append(f"## `{rule.id}` — {rule.name}")
        lines.append("")
        if rule.business_intent:
            lines.append(f"- **Intent:** {rule.business_intent.strip()}")
        if rule.out_of_scope:
            lines.append("- **Out-of-scope:**")
            for item in rule.out_of_scope:
                lines.append(f"  - {item}")
        if not rule.business_intent and not rule.out_of_scope:
            lines.append(
                "- _No `business_intent` or `out_of_scope` declared on this "
                "rule. Rule author should populate the spec to close this "
                "documentation gap._"
            )
        lines.append("")
    return "\n".join(lines)


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
    # NOTE: deliberately no wall-clock `verified_at` here. The audit pack is a
    # byte-deterministic artifact (see TestDeterminism) — embedding
    # datetime.now() made two builds straddling a one-second boundary differ,
    # an intermittent determinism-guarantee violation. The verification result
    # (chain_intact / breaks / length) is a pure function of the decisions and
    # can be re-derived at any time; the "when" is not evidence.
    return {
        "chain_intact": chain_intact,
        "chain_length": chain_length,
        "breaks_at_indices": breaks,
    }


def _case_lineage_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-case lineage chain for the audit pack (PR-LIN-17).

    For each case the engine produced, surface the chain stamps Round
    12 added: rule_id + rule_version (PR-LIN-3), matched_row_ids
    (PR-LIN-4), and the input_files dict (source_path + schema_hash +
    content_hash + row_count, PR-LIN-2). Lets a FINTRAC examiner
    answer "which rule version produced this case, and which source
    file fed it?" from the bundle alone.
    """
    by_case: dict[str, Any] = {}
    for case in cases:
        cid = case.get("case_id", "")
        if not cid:
            continue
        alert_dict = case.get("alert") or {}
        by_case[cid] = {
            "rule_id": case.get("rule_id"),
            # PR-PAY-1: prefer the case-level `rule_version` stamped by
            # `_build_case`; fall back to the alert-level field for
            # back-compat with case files written by older engine
            # versions.
            "rule_version": case.get("rule_version") or alert_dict.get("rule_version"),
            "matched_row_ids": alert_dict.get("matched_row_ids") or [],
            "input_files": [
                {
                    "contract_id": contract_id,
                    "row_count": meta.get("row_count"),
                    "content_hash": meta.get("content_hash"),
                    "source_path": meta.get("source_path"),
                    "schema_hash": meta.get("schema_hash"),
                }
                for contract_id, meta in (case.get("input_hash") or {}).items()
            ],
        }
    return {
        "case_count": len(by_case),
        "lineage_fields": [
            "rule_id",
            "rule_version",
            "matched_row_ids",
            "input_files.source_path",
            "input_files.schema_hash",
            "input_files.content_hash",
        ],
        "by_case_id": by_case,
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
        # PR-LIN-17: per-case lineage chain. Lets a FINTRAC examiner
        # answer "which rule version produced this case, and which
        # source file fed it?" from the bundle alone — no need to
        # request the run dir.
        "case_lineage_summary.json": _dump_json(_case_lineage_summary(cases)),
        # PR-A2 follow-up: rule-author scope declarations digest
        # (`business_intent` + `out_of_scope` per rule). Answers
        # "why didn't this rule fire on case X" from the bundle alone.
        "program_intent.md": _program_intent_md(spec).encode("utf-8"),
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


# ---------------------------------------------------------------------------
# PR-D4: per-case / per-batch evidence packs (closes #377)
# ---------------------------------------------------------------------------
#
# The whole-run audit pack above is ~50 MB on a real bank's monthly run.
# Investigators / regulators frequently want only the subset that pertains
# to one case (or a handful of escalations). These two helpers carve out
# the minimum set of artefacts needed to defend one alert: the case file
# itself, the rule SQL that produced it, the alert payload, the per-case
# decision sub-chain, lineage stamps, and the spec snapshot. Determinism
# guarantees match the whole-run pack — same inputs → byte-identical ZIP
# — and an optional `signing_key` attaches an HMAC-SHA256 over the
# bundle hash to the manifest so the receiver can verify provenance.


CASE_PACK_VERSION = "1"


def _read_case_file(case_path: Path) -> dict[str, Any]:
    if not case_path.exists():
        raise FileNotFoundError(f"case file not found: {case_path}")
    return json.loads(case_path.read_text(encoding="utf-8"))


def _load_decisions(run_dir: Path) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    dec_path = run_dir / "decisions.jsonl"
    if dec_path.exists():
        for line in dec_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                decisions.append(json.loads(line))
    return decisions


class _PiiMap:
    """Field-aware PII mapping loaded from a run's ``pii_map.jsonl``.

    Carries two views of the same sidecar so the masker can reason
    about *context*:

    - ``by_field``: ``field_name → {plaintext → hash}``. Used to only
      mask a leaf when its parent dict key matches a recorded PII
      field (Codex P2 — prevents short numeric plaintexts like ``"1"``
      from rewriting unrelated leaves such as ``matched_row_ids: [1]``
      or ``row_count: 1``).
    - ``fields``: the set of all PII field names; cheap membership test.

    Compound substring masking (``case_id``, ``source_path``) is still
    done by iterating all known plaintexts, but with token-level guards
    that prevent partial replacement of timestamps / non-PII path
    components (see ``_mask_compound_string``).
    """

    __slots__ = ("by_field", "fields", "_all_plaintexts")

    def __init__(self, by_field: dict[str, dict[str, str]]) -> None:
        self.by_field: dict[str, dict[str, str]] = by_field
        self.fields: frozenset[str] = frozenset(by_field.keys())
        all_pt: dict[str, str] = {}
        for mapping in by_field.values():
            all_pt.update(mapping)
        self._all_plaintexts: dict[str, str] = all_pt

    def __bool__(self) -> bool:
        return bool(self._all_plaintexts)

    def lookup(self, field: str | None, value_str: str) -> str | None:
        """Hash for ``value_str`` if the field is a known PII column."""
        if field is None:
            return None
        col_map = self.by_field.get(field)
        if not col_map:
            return None
        return col_map.get(value_str)

    @property
    def all_plaintexts(self) -> dict[str, str]:
        return self._all_plaintexts


class PiiMapCorruptError(ValueError):
    """Raised when a run's ``pii_map.jsonl`` is malformed.

    Fail-closed for regulator-facing evidence exports (Codex P2): a
    corrupt masking sidecar must abort the pack build, not be silently
    skipped — otherwise the requested case's customer_id could remain
    unmasked in the ZIP while the manifest still advertises
    ``pii_masked: true``.
    """


def _load_pii_map(run_dir: Path) -> _PiiMap:
    """Load the run's ``pii_map.jsonl`` sidecar into a field-aware map.

    The engine writes one row per ``(field, hash, plaintext)`` tuple
    whenever PII masking is enabled (``AML_PII_MASKING=1`` + spec
    columns flagged ``pii: true``). Granular packs use the field tag to
    restrict masking to the right column so a numeric plaintext can't
    rewrite unrelated audit evidence (Codex P2).

    Raises ``PiiMapCorruptError`` when the sidecar exists but a row is
    malformed (Codex P2): silent skip would let a granular pack ship
    with plaintext PII for the corrupt row's case.
    """
    by_field: dict[str, dict[str, str]] = {}
    sidecar = run_dir / "pii_map.jsonl"
    if not sidecar.exists():
        return _PiiMap(by_field)
    for line_no, line in enumerate(sidecar.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PiiMapCorruptError(f"{sidecar}: malformed JSON on line {line_no}: {exc}") from exc
        plain = row.get("plaintext")
        hashed = row.get("hash")
        field = row.get("field")
        if plain is None or hashed is None or field is None:
            raise PiiMapCorruptError(
                f"{sidecar}: missing required key (field/plaintext/hash) on line {line_no}"
            )
        by_field.setdefault(str(field), {})[str(plain)] = str(hashed)
    return _PiiMap(by_field)


def _mask_compound_string(value: str, pii_map: _PiiMap, *, key: str = "case_id") -> str:
    """Token-level substring-mask of a compound engine identifier.

    The engine builds compound strings whose components are joined by a
    fixed delimiter — ``<rule>__<customer>__<window_end>`` for
    ``case_id`` and ``<dir>/<customer>/<file>`` for ``source_path``.
    Codex P2: a naive ``str.replace`` would rewrite *every* occurrence
    of a short / numeric plaintext, mangling the non-PII timestamp /
    rule_id components (e.g. ``rule__1__2026-01-15...`` → bad).

    Fix: split on the appropriate delimiter and only swap whole tokens
    that exactly equal a recorded plaintext. The hashes the engine
    emits are opaque 16-hex strings that can never collide with any
    rule_id, timestamp, or filename token, so token-level equality is
    sufficient and never causes partial corruption.
    """
    if not pii_map or not value:
        return value
    if key == "source_path":
        delimiter = "/"
    else:
        delimiter = "__"
    parts = value.split(delimiter)
    all_plaintexts = pii_map.all_plaintexts
    masked_parts = [all_plaintexts.get(p, p) for p in parts]
    return delimiter.join(masked_parts)


_COMPOUND_ID_KEYS = frozenset({"case_id", "source_path"})
"""Keys whose *values* are engine-built compound strings that may embed
plaintext PII (``case_id`` = ``<rule>__<customer>__<ts>``,
``source_path`` = ``data/<customer>/txn.csv``). Only these keys get
substring masking — generic leaf strings stay on exact-value masking
so a short PII value like ``1`` cannot accidentally rewrite timestamps,
hashes, or other strings (Codex P2 fix)."""


def _apply_pii_map(payload: Any, pii_map: _PiiMap, *, key: str | None = None) -> Any:
    """Recursively replace plaintext values with their hashes.

    Walks dicts/lists with **field awareness** (Codex P2): masking is
    keyed to the parent dict key, so a numeric plaintext like ``"1"``
    only rewrites values under the recorded PII field name (e.g.
    ``customer_id``) and never collateral leaves like ``row_count: 1``
    or ``matched_row_ids: [1]``.

    Leaf rules:

    - Leaf (string or scalar) under a recorded PII field whose
      ``str()`` matches that field's plaintext → swap for hash.
    - String leaf under ``_COMPOUND_ID_KEYS`` (``case_id`` /
      ``source_path``) → token-level masking that swaps whole
      delimited components matching a recorded plaintext.
    - Anything else → returned as-is.
    """
    if not pii_map:
        return payload
    if isinstance(payload, dict):
        return {k: _apply_pii_map(v, pii_map, key=k) for k, v in payload.items()}
    if isinstance(payload, list):
        return [_apply_pii_map(v, pii_map, key=key) for v in payload]
    if isinstance(payload, str):
        # Field-keyed exact-match swap (handles PII columns directly).
        hashed = pii_map.lookup(key, payload)
        if hashed is not None:
            return hashed
        if key in _COMPOUND_ID_KEYS:
            return _mask_compound_string(payload, pii_map, key=key)
        # Network-pattern cases nest customer ids inside subgraph
        # objects under generic keys like ``seed``, ``id``, ``source``,
        # ``target``. Those keys are not PII field names, so the
        # field-keyed lookup above misses them. Fall back to an
        # all-fields exact-string lookup — safe for opaque PII
        # identifiers and only applied to *string* leaves so a numeric
        # plaintext "1" still cannot rewrite int leaves like
        # ``row_count`` (Codex P1 follow-up).
        all_pt_hash = pii_map.all_plaintexts.get(payload)
        if all_pt_hash is not None:
            return all_pt_hash
        return payload
    # Non-string leaf — coerce to str() and look up under the same
    # field so a numeric/decimal/bool PII column gets hashed without
    # accidentally rewriting unrelated numeric audit evidence.
    coerced = str(payload)
    hashed = pii_map.lookup(key, coerced)
    if hashed is not None:
        return hashed
    return payload


def _alerts_for_case(case: dict[str, Any], pii_map: dict[str, str]) -> list[dict[str, Any]]:
    """Return the alert payload(s) attributable to *this* case.

    Codex P2 / P1 fix: rather than mining ``alerts/<rule>.jsonl`` and
    trying to identify which row produced this case (a join that's
    ambiguous for network rules and for rules with multiple alerts per
    customer with shared ``matched_row_ids``), we take the canonical
    alert the engine stamped onto ``case["alert"]`` as the
    single-source-of-truth. The case file is opened by the engine 1:1
    with its triggering alert, so this is exactly the right row and no
    sibling-case rows can ever leak in. PII masking is reapplied through
    ``pii_map`` so the pack honours the run's masking contract.
    """
    alert = case.get("alert") or {}
    if not alert:
        return []
    return [_apply_pii_map(alert, pii_map)]


def _filter_decisions_for_cases(
    decisions: list[dict[str, Any]], case_ids: set[str]
) -> list[dict[str, Any]]:
    return [d for d in decisions if d.get("case_id", "") in case_ids]


def _read_optional(run_dir: Path, relative: str) -> bytes | None:
    p = run_dir / relative
    if p.exists() and p.is_file():
        return p.read_bytes()
    return None


def _attach_signature(manifest: dict[str, Any], signing_key: str | None) -> None:
    """Sign the manifest in-place when a key is supplied.

    Uses HMAC-SHA256 over the canonical ``bundle_hash`` — same primitive
    the engine uses to hash PII (`engine/audit.py`). Receivers verify by
    re-running HMAC over the bundle_hash with the shared key.
    """
    if not signing_key:
        return
    import hmac

    sig = hmac.new(
        signing_key.encode("utf-8"),
        manifest["bundle_hash"].encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    manifest["signature"] = {"algorithm": "HMAC-SHA256", "value": sig}


def _assemble_pack(
    files: dict[str, bytes],
    manifest_base: dict[str, Any],
    *,
    signing_key: str | None,
) -> bytes:
    """Common tail: per-file hashes, bundle hash, manifest, deterministic ZIP."""
    file_hashes = {
        path: hashlib.sha256(payload).hexdigest() for path, payload in sorted(files.items())
    }
    bundle_hash = hashlib.sha256(
        "\n".join(f"{p}:{h}" for p, h in sorted(file_hashes.items())).encode("utf-8")
    ).hexdigest()
    manifest = {**manifest_base, "files": file_hashes, "bundle_hash": bundle_hash}
    _attach_signature(manifest, signing_key)
    files["manifest.json"] = _dump_json(manifest)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(files.keys()):
            info = zipfile.ZipInfo(filename=path, date_time=_ZIP_FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, files[path])
    return buf.getvalue()


def _case_pack_files(
    spec: AMLSpec,
    case: dict[str, Any],
    run_dir: Path,
    all_decisions: list[dict[str, Any]],
    pii_map: dict[str, str],
) -> dict[str, bytes]:
    """Per-case file payloads — shared by single-case + batch packs.

    ``pii_map`` (plaintext → hash from the run's ``pii_map.jsonl``) is
    applied to the case dict, decision sub-chain, alert payload AND the
    case_id-derived ZIP entry names + lineage identifiers before they
    are written. PII embedded inside compound identifiers (e.g.
    ``case_id`` = ``<rule>__<customer>__<ts>``) is substring-replaced.
    Empty mapping (unmasked run) is a no-op.
    """
    raw_case_id = case.get("case_id", "")
    masked_case_id = _mask_compound_string(raw_case_id, pii_map)
    rule_id = case.get("rule_id", "")
    # decisions are looked up by the engine-emitted raw case_id; mask
    # them only on the way out.
    decisions = _filter_decisions_for_cases(all_decisions, {raw_case_id})
    alerts = _alerts_for_case(case, pii_map)
    rule_sql = _read_optional(run_dir, f"rules/{rule_id}.sql")
    # Codex P2: the engine stamps `rule_version` on the `case_opened`
    # decision event, not on the alert payload, so prefer the alert
    # but fall back to the decision sub-chain so packs built from real
    # `aml run` output never record rule_version as null.
    alert_dict = case.get("alert") or {}
    rule_version = alert_dict.get("rule_version")
    if rule_version is None:
        for d in decisions:
            if d.get("rule_version"):
                rule_version = d["rule_version"]
                break

    # Codex P2 follow-up: source_path is now in _COMPOUND_ID_KEYS, so
    # the recursive _apply_pii_map walk masks it everywhere it appears
    # (lineage AND the embedded ``input_hash`` inside the case dict),
    # and no per-field special-casing is needed here.
    lineage_raw = {
        "case_id": masked_case_id,
        "rule_id": rule_id,
        "rule_version": rule_version,
        "matched_row_ids": alert_dict.get("matched_row_ids") or [],
        "input_files": [
            {
                "contract_id": contract_id,
                "row_count": meta.get("row_count"),
                "content_hash": meta.get("content_hash"),
                "source_path": meta.get("source_path"),
                "schema_hash": meta.get("schema_hash"),
            }
            for contract_id, meta in sorted((case.get("input_hash") or {}).items())
        ],
    }
    lineage = _apply_pii_map(lineage_raw, pii_map)
    masked_case = _apply_pii_map(case, pii_map)
    masked_decisions = [_apply_pii_map(d, pii_map) for d in decisions]
    files: dict[str, bytes] = {
        f"cases/{masked_case_id}.json": _dump_json(masked_case),
        f"decisions/{masked_case_id}.jsonl": (
            "\n".join(json.dumps(d, sort_keys=True) for d in masked_decisions)
            + ("\n" if masked_decisions else "")
        ).encode("utf-8"),
        f"alerts/{masked_case_id}.jsonl": (
            "\n".join(json.dumps(a, sort_keys=True) for a in alerts) + ("\n" if alerts else "")
        ).encode("utf-8"),
        f"lineage/{masked_case_id}.json": _dump_json(lineage),
    }
    if rule_sql is not None:
        files[f"rules/{rule_id}.sql"] = rule_sql
    return files


def build_case_pack(
    spec: AMLSpec,
    case_path: Path,
    run_dir: Path,
    *,
    signing_key: str | None = None,
) -> bytes:
    """Per-case evidence pack — the minimum subset to defend one alert.

    Contents:
    - ``program.md`` — program metadata (same shape as full audit pack)
    - ``spec_snapshot.yaml`` — copied verbatim from the run when present
    - ``cases/<case_id>.json`` — the case file itself
    - ``decisions/<case_id>.jsonl`` — decision sub-chain for this case
    - ``alerts/<case_id>.jsonl`` — alert payload restricted to this case
    - ``rules/<rule_id>.sql`` — the SQL that produced the alert (if recorded)
    - ``lineage/<case_id>.json`` — rule_version + matched_row_ids + inputs
    - ``manifest.json`` — file-by-file SHA-256 + bundle hash (+ HMAC signature
      if ``signing_key`` supplied)

    Raises ``FileNotFoundError`` when ``case_path`` is missing.
    """
    case = _read_case_file(case_path)
    all_decisions = _load_decisions(run_dir)
    pii_map = _load_pii_map(run_dir)
    files: dict[str, bytes] = {
        "program.md": _program_md(spec).encode("utf-8"),
    }
    spec_snapshot = _read_optional(run_dir, "spec_snapshot.yaml")
    if spec_snapshot is not None:
        files["spec_snapshot.yaml"] = spec_snapshot
    files.update(_case_pack_files(spec, case, run_dir, all_decisions, pii_map))
    manifest_base = {
        "pack_version": CASE_PACK_VERSION,
        "pack_kind": "case",
        "pii_masked": bool(pii_map),
        "spec_program": spec.program.name,
        "spec_jurisdiction": spec.program.jurisdiction,
        "regulator": spec.program.regulator,
        # Mask any PII embedded in the compound case_id (Codex P1).
        "case_id": _mask_compound_string(case.get("case_id", ""), pii_map),
        "rule_id": case.get("rule_id", ""),
    }
    return _assemble_pack(files, manifest_base, signing_key=signing_key)


def build_batch_pack(
    spec: AMLSpec,
    run_dir: Path,
    case_ids: list[str],
    *,
    signing_key: str | None = None,
) -> bytes:
    """Multi-case evidence pack — hand-selected batch for a regulator request.

    ``case_ids`` is the list of ``case_id`` values to include. Each id is
    matched against ``cases/<case_id>.json`` under ``run_dir``. Missing
    cases raise ``FileNotFoundError`` — silent skips would let investigators
    accidentally hand over an incomplete pack. Empty ``case_ids`` raises
    ``ValueError`` (the caller almost certainly meant to use the full-run
    audit pack instead).
    """
    if not case_ids:
        raise ValueError("case_ids must not be empty; use build_audit_pack for full runs")
    # Deduplicate while preserving caller order for the manifest summary.
    seen: set[str] = set()
    ordered_ids: list[str] = []
    for cid in case_ids:
        if cid not in seen:
            seen.add(cid)
            ordered_ids.append(cid)

    cases_dir = run_dir / "cases"
    cases: list[dict[str, Any]] = []
    for cid in ordered_ids:
        path = cases_dir / f"{cid}.json"
        cases.append(_read_case_file(path))

    all_decisions = _load_decisions(run_dir)
    pii_map = _load_pii_map(run_dir)

    files: dict[str, bytes] = {
        "program.md": _program_md(spec).encode("utf-8"),
    }
    spec_snapshot = _read_optional(run_dir, "spec_snapshot.yaml")
    if spec_snapshot is not None:
        files["spec_snapshot.yaml"] = spec_snapshot
    for case in cases:
        files.update(_case_pack_files(spec, case, run_dir, all_decisions, pii_map))

    # Mask any PII embedded in compound case_ids (Codex P1) before
    # surfacing them in the batch_summary / manifest.
    masked_ids = sorted({_mask_compound_string(cid, pii_map) for cid in ordered_ids})
    files["batch_summary.json"] = _dump_json(
        {
            "case_count": len(cases),
            "case_ids": masked_ids,
            "rules": sorted({c.get("rule_id", "") for c in cases if c.get("rule_id")}),
        }
    )

    manifest_base = {
        "pack_version": CASE_PACK_VERSION,
        "pack_kind": "batch",
        "pii_masked": bool(pii_map),
        "spec_program": spec.program.name,
        "spec_jurisdiction": spec.program.jurisdiction,
        "regulator": spec.program.regulator,
        "case_count": len(cases),
        "case_ids": masked_ids,
    }
    return _assemble_pack(files, manifest_base, signing_key=signing_key)


__all__ = [
    "CASE_PACK_VERSION",
    "PACK_VERSION",
    "SUPPORTED_JURISDICTIONS",
    "build_audit_pack",
    "build_audit_pack_from_run_dir",
    "build_batch_pack",
    "build_case_pack",
]
