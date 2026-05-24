"""Pillar-2 defect log — issue #371 (artifact), #372 (11-category classifier),
and #373 (data / rule / mapping triage decision tree).

The north-star coverage page (Pillar 2 — "Evidence as a product") flagged
this as a gap: the engine emitted DQ exceptions, python_ref failures, and
contract violations as decision events, but there was no single
*ticket-shaped* defect artifact a 2LoD reviewer could rank by severity,
classify (data vs rule vs mapping), and track through a lifecycle.

This module derives one ``Defect`` per qualifying issue from the run's
existing audit substrate (DQ exceptions + python_ref failures). Pure
function — no I/O until ``write_defect_log`` is called, so the unit
tests don't need a run directory.

The artifact lives at ``defect_log.jsonl`` next to ``dq_exceptions.jsonl``;
its SHA-256 is pinned on the manifest (``defect_log_hash``) and the file
is frozen post-finalize via ``_FROZEN_SNAPSHOT_TARGETS``, matching the
same tamper-detection posture as every other regulator-facing artifact.

Scope of THIS PR (engine + spec only):
- 11 ``DefectCategory`` values (#372).
- 3 ``DefectClassification`` values (#373 triage decision tree).
- 5 ``DefectSeverity`` values.
- ``Defect`` Pydantic model — frozen, ``extra="forbid"``.
- ``build_defect_log()`` pure derivation from DQ exceptions +
  python_ref failures.
- ``write_defect_log()`` deterministic JSONL emit (sort_keys, byte-stable).
- ``classify_defect()`` decision-tree helper exposed for callers that
  want to attach a defect from a different source.

Dashboard surface (the operator-facing defect-triage page) is a
follow-up PR — keep this one scoped to the engine + spec layer.
"""

from __future__ import annotations

import enum
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from aml_framework.engine.dq import DQException


class DefectCategory(str, enum.Enum):
    """Issue #372 — the 11 categories a defect can fall under.

    Categories describe *what kind of thing* the defect is about. They
    are stable strings (not int codes) so the JSONL artifact remains
    human-readable and survives schema migrations cleanly.
    """

    DATA_QUALITY = "data_quality"
    RULE_LOGIC = "rule_logic"
    MAPPING = "mapping"
    THRESHOLD = "threshold"
    LINEAGE = "lineage"
    METRIC = "metric"
    SPEC_CONFIG = "spec_config"
    EXTERNAL = "external"
    RUNTIME = "runtime"
    SANCTIONS_REF = "sanctions_ref"
    TYPOLOGY_COVERAGE = "typology_coverage"


class DefectClassification(str, enum.Enum):
    """Issue #373 — the triage decision tree.

    Every defect must be one of: a DATA problem (the input feed is
    wrong / missing / stale), a RULE problem (the detection logic is
    wrong), or a MAPPING problem (the spec→warehouse glue is wrong).
    This is the first question a 2LoD reviewer asks when a defect
    lands; encoding it on the ticket avoids re-deriving it from prose.
    """

    DATA = "data"
    RULE = "rule"
    MAPPING = "mapping"


class DefectSeverity(str, enum.Enum):
    """Severity buckets — drives queue routing and SLA in a follow-up PR."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class DefectStatus(str, enum.Enum):
    """Lifecycle states a defect ticket moves through.

    OPEN: newly minted by the engine; nobody has triaged it yet.
    ACKNOWLEDGED: a reviewer has seen it and accepted ownership.
    RESOLVED: the underlying issue is fixed; awaiting verification.
    CLOSED: verified resolved; archived.
    WONT_FIX: a deliberate non-action (e.g. accepted residual risk).
    """

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    CLOSED = "closed"
    WONT_FIX = "wont_fix"


class Defect(BaseModel):
    """One defect ticket.

    Frozen + ``extra="forbid"`` so the JSONL shape is locked — adding a
    field is a deliberate schema bump, never an accidental dict-spread
    overflow. Same posture as ``DQException`` / ``MonitoringDigest``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    category: DefectCategory
    classification: DefectClassification
    severity: DefectSeverity
    summary: str
    detected_by: str  # subsystem that produced the defect (e.g. "dq.evaluator")
    source_run_id: str  # the run_dir basename — joins back to manifest.json
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    status: DefectStatus = DefectStatus.OPEN


# Mapping from a DQException's `check_type` to its (category, classification).
# Kept as a module-level dict so the decision tree is one obvious place to
# read / extend — issue #373's whole point.
_DQ_CHECK_TYPE_DEFAULT: tuple[DefectCategory, DefectClassification] = (
    DefectCategory.DATA_QUALITY,
    DefectClassification.DATA,
)
_DQ_CHECK_TYPE_ROUTING: dict[str, tuple[DefectCategory, DefectClassification]] = {
    "not_null": (DefectCategory.DATA_QUALITY, DefectClassification.DATA),
    "unique": (DefectCategory.DATA_QUALITY, DefectClassification.DATA),
    "enum": (DefectCategory.DATA_QUALITY, DefectClassification.DATA),
    "regex": (DefectCategory.DATA_QUALITY, DefectClassification.DATA),
    "range": (DefectCategory.DATA_QUALITY, DefectClassification.DATA),
    # `malformed_check` is a spec defect, not a feed defect — the data
    # is fine, the quality_check declaration is wrong. Classification
    # flips to MAPPING (the spec→warehouse glue is broken) and the
    # category becomes SPEC_CONFIG so a reviewer skimming
    # defect_log.jsonl can spot it among the row-level data problems.
    "malformed_check": (DefectCategory.SPEC_CONFIG, DefectClassification.MAPPING),
}


# Severity routing for DQ check types. Almost all data-quality failures
# are MEDIUM by default; the exceptions are spec-defects (HIGH — a
# silently-disabled check is a compliance gap) and uniqueness violations
# (HIGH — a duplicated primary key risks double-counting in metrics).
_DQ_SEVERITY: dict[str, DefectSeverity] = {
    "not_null": DefectSeverity.MEDIUM,
    "unique": DefectSeverity.HIGH,
    "enum": DefectSeverity.MEDIUM,
    "regex": DefectSeverity.MEDIUM,
    "range": DefectSeverity.MEDIUM,
    "malformed_check": DefectSeverity.HIGH,
}


def classify_defect(exc: DQException) -> tuple[DefectCategory, DefectClassification]:
    """Decision-tree helper (issue #373) — DQException → (category, classification).

    Pure, deterministic, and exported so callers building defects from
    other sources (a future fraud-AML reconciliation break, an
    equivalence drift) can route through the same tree.

    Unknown check types fall through to ``DATA_QUALITY`` / ``DATA`` —
    the conservative classification. A future check_type added to
    ``engine/dq.py`` without a routing entry here still produces a
    defect; it just lands in the most generic bucket until someone
    extends the table.
    """
    return _DQ_CHECK_TYPE_ROUTING.get(exc.check_type, _DQ_CHECK_TYPE_DEFAULT)


def _defect_id_for_dq(run_id: str, exc: DQException, position: int) -> str:
    """Deterministic ID: ``defect:<run_id>:<position>:<check_id>``.

    ``position`` is the DQException's index in the run's exception
    stream — combined with ``check_id``, this guarantees a stable,
    collision-free ID across re-runs (same spec + same data + same
    as_of → same defect IDs). The ``check_id`` suffix keeps the ID
    human-readable when surfacing in dashboards.
    """
    return f"defect:{run_id}:{position:04d}:{exc.check_id}"


def _defect_id_for_python_ref(run_id: str, rule_id: str, position: int) -> str:
    """Deterministic ID for a python_ref failure defect."""
    return f"defect:{run_id}:pyref:{position:04d}:{rule_id}"


def _run_id_from_dir(run_dir: Path | str | None) -> str:
    """Derive a stable ``source_run_id`` from a run-directory path.

    Returns the directory basename when available, ``"unknown"``
    otherwise. The runner always passes a real path; the fallback only
    exists so unit tests that build defects in isolation don't need a
    real directory.
    """
    if run_dir is None:
        return "unknown"
    return Path(run_dir).name or "unknown"


def build_defect_log(
    *,
    run_id: str,
    dq_exceptions: list[DQException],
    python_ref_failures: dict[str, str] | None = None,
    created_at: datetime | None = None,
) -> list[Defect]:
    """Derive defect tickets from existing audit substrate.

    Pure function — no I/O. Same inputs always produce the same output
    (including ``created_at`` when callers pin it; defaults to ``now()``
    only when omitted). The runner pins ``created_at`` to ``as_of`` so
    the defect_log.jsonl artifact stays byte-stable across re-runs.

    Sources covered in this PR:
      - DQ exceptions (one defect per exception, classified via the
        ``classify_defect`` decision tree).
      - python_ref failures (one defect per rule that failed to score;
        always RULE_LOGIC / RULE classification, HIGH severity — a
        scorer crash means the rule produced zero alerts under strict
        mode and would have produced silent zeros under permissive
        mode).

    Future sources (reconciliation breaks, equivalence drift, etc.)
    will plug in by appending to the returned list — keeping the same
    deterministic-order discipline.
    """
    ts = created_at if created_at is not None else datetime.now(tz=timezone.utc)
    defects: list[Defect] = []

    # DQ-derived defects, in the order ``evaluate_contract_checks``
    # produces them. The position index is what makes the defect IDs
    # collision-free even when two exceptions share a check_id.
    for idx, exc in enumerate(dq_exceptions):
        category, classification = classify_defect(exc)
        severity = _DQ_SEVERITY.get(exc.check_type, DefectSeverity.MEDIUM)
        defects.append(
            Defect(
                id=_defect_id_for_dq(run_id, exc, idx),
                category=category,
                classification=classification,
                severity=severity,
                summary=exc.reason,
                detected_by="dq.evaluator",
                source_run_id=run_id,
                created_at=ts,
                status=DefectStatus.OPEN,
            )
        )

    # python_ref scorer failures, deterministic by sorted rule_id so the
    # artifact diff stays stable across Python dict ordering changes.
    if python_ref_failures:
        for idx, rule_id in enumerate(sorted(python_ref_failures.keys())):
            error_msg = python_ref_failures[rule_id]
            defects.append(
                Defect(
                    id=_defect_id_for_python_ref(run_id, rule_id, idx),
                    category=DefectCategory.RULE_LOGIC,
                    classification=DefectClassification.RULE,
                    severity=DefectSeverity.HIGH,
                    summary=f"python_ref scorer failed for rule '{rule_id}': {error_msg}",
                    detected_by="engine.runner.python_ref",
                    source_run_id=run_id,
                    created_at=ts,
                    status=DefectStatus.OPEN,
                )
            )

    return defects


def write_defect_log(run_dir: Path, defects: list[Defect]) -> Path:
    """Persist defects as ``defect_log.jsonl`` under the run dir.

    Always writes the file — empty (``b""``) when there are no defects
    — so downstream consumers (manifest hash, exporters, the follow-up
    dashboard page) can rely on its presence rather than guarding on
    ``exists()``. Same artifact-always-present posture as
    ``dq_exceptions.jsonl`` and ``field_lineage.jsonl``.

    ``sort_keys=True`` so the JSONL diff is byte-stable across re-runs
    — required for the run reproducibility contract and the
    manifest-hash pin in ``audit.finalize()``.
    """
    path = run_dir / "defect_log.jsonl"
    if not defects:
        path.write_bytes(b"")
        return path
    lines = [
        json.dumps(d.model_dump(mode="json"), sort_keys=True, default=str).encode("utf-8")
        for d in defects
    ]
    path.write_bytes(b"\n".join(lines) + b"\n")
    return path
