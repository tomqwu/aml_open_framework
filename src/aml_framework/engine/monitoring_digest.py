"""Post-run monitoring digest (Pillar 6 — issue #386 / PR-LF4).

The runner already emits the regulator-facing artifacts (alerts,
decisions, cases, manifest). The on-call AML analyst opening a fresh run
directory needs a *summary* — "did anything change since yesterday?
which rule fired the most? are DQ failures piling up?" — without
re-parsing the full evidence tree.

This module produces a single ``monitoring_digest.json`` artifact next
to ``manifest.json``. It is:

- deterministic (sorted keys, no wall-clock state) — same spec + data +
  as_of yields identical bytes, preserved by the manifest-hash pin;
- frozen post-finalize via ``_FROZEN_SNAPSHOT_TARGETS`` so a tampered
  digest is detectable via ``monitoring_digest_hash`` on the manifest;
- self-contained for the on-call surface — the only dependency on the
  persistence layer is the optional ``prior_run`` lookup, which fails
  gracefully when ``DATABASE_URL`` / Cosmos credentials are absent.

Engine-side ONLY for now — the dashboard surface follows in a separate
PR after the persistence-layer changes on #413 land.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from aml_framework.engine.dq import DQException
from aml_framework.spec.models import AMLSpec

logger = logging.getLogger("aml.engine.monitoring_digest")


class RuleAlertCount(BaseModel):
    """One (rule_id, count) tuple for the ``top_rules`` ranking."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str
    count: int


class MonitoringDigest(BaseModel):
    """Compact on-call summary of a single run.

    Frozen + ``extra="forbid"`` so the artifact shape is locked — a new
    field is a deliberate schema bump, never an accidental dict-spread
    overflow. Same posture as ``DQException`` / ``FieldLineageEntry``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Run identity.
    spec_name: str
    spec_path: str
    spec_content_hash: str
    as_of: datetime
    engine_version: str
    run_dir: str

    # Alert rollups.
    total_alerts: int
    alerts_per_rule: dict[str, int]
    alerts_per_queue: dict[str, int]
    alerts_per_severity: dict[str, int]
    top_rules: list[RuleAlertCount]

    # DQ rollups.
    dq_total: int
    dq_per_check_type: dict[str, int]
    dq_per_contract: dict[str, int]

    # "What changed since last run" — per-rule signed delta in alert
    # count. Empty dict when no prior run exists for this spec, or when
    # the persistence layer is unavailable.
    prior_run_id: str | None
    changed_since_last_run: dict[str, int]


def _rule_severity_map(spec: AMLSpec) -> dict[str, str]:
    return {rule.id: rule.severity for rule in spec.rules}


def _rule_queue_map(spec: AMLSpec) -> dict[str, str]:
    return {rule.id: rule.escalate_to for rule in spec.rules}


def _top_rules(
    alerts_per_rule: dict[str, int],
    *,
    n: int = 3,
) -> list[RuleAlertCount]:
    """Return the top-N rules by alert count, breaking ties on rule_id.

    Deterministic ordering: highest count first, then alphabetical
    rule_id. Rules with zero alerts are excluded — they're noise on a
    "what fired" digest. Returns fewer than ``n`` entries when fewer
    than ``n`` rules fired.
    """
    nonzero = [(rid, c) for rid, c in alerts_per_rule.items() if c > 0]
    nonzero.sort(key=lambda x: (-x[1], x[0]))
    return [RuleAlertCount(rule_id=rid, count=c) for rid, c in nonzero[:n]]


def _diff_against_prior(
    current: dict[str, int],
    prior_manifest: dict[str, Any] | None,
) -> tuple[str | None, dict[str, int]]:
    """Return (prior_run_id, per-rule delta dict).

    Delta is ``current[rule_id] - prior[rule_id]`` for every rule_id
    present in either snapshot. Missing rules count as zero on their
    side. When ``prior_manifest`` is None (no prior run / DB lookup
    failed) returns ``(None, {})``.
    """
    if not prior_manifest:
        return None, {}

    prior_outputs = prior_manifest.get("rule_outputs") or {}
    # The manifest stores SHA-256 strings under ``rule_outputs``, not
    # counts. The runner also writes ``alert_counts`` to the manifest in
    # this PR (see ``build_monitoring_digest``); fall back to the
    # ``monitoring_digest`` block on the prior manifest if present.
    prior_counts: dict[str, int] = {}
    digest_block = prior_manifest.get("monitoring_digest")
    if isinstance(digest_block, dict):
        block_counts = digest_block.get("alerts_per_rule")
        if isinstance(block_counts, dict):
            prior_counts = {str(k): int(v) for k, v in block_counts.items()}
    if not prior_counts and isinstance(prior_outputs, dict):
        # Older runs predating PR-LF4 don't carry a digest block.
        # Treat them as zero-count baselines so the diff still produces
        # a useful "everything is new" signal rather than crashing.
        prior_counts = {str(k): 0 for k in prior_outputs.keys()}

    prior_run_id = prior_manifest.get("run_id") or prior_manifest.get("run_dir")
    if isinstance(prior_run_id, str) and prior_run_id:
        prior_run_id_out: str | None = prior_run_id
    else:
        prior_run_id_out = None

    all_rule_ids = set(current.keys()) | set(prior_counts.keys())
    delta = {rid: int(current.get(rid, 0)) - int(prior_counts.get(rid, 0)) for rid in all_rule_ids}
    return prior_run_id_out, delta


def lookup_prior_run(
    spec_path: str, *, current_run_dir: str | None = None
) -> dict[str, Any] | None:
    """Best-effort lookup of the most-recent prior run for the same spec.

    Returns the prior run's manifest dict, or ``None`` when:

    - persistence isn't configured (``DATABASE_URL`` / ``COSMOS_ENDPOINT``
      both unset and SQLite has no rows);
    - the lookup raises any exception (DB unreachable, schema mismatch);
    - no prior runs exist for this spec.

    The lookup is intentionally permissive — a monitoring digest is a
    convenience artifact, not load-bearing evidence. Failing the
    lookup must NEVER abort the run. Mirrors the "always write
    artifact, possibly empty" posture of ``dq_exceptions.jsonl``.
    """
    try:
        from aml_framework.api import db
    except Exception:  # noqa: BLE001 — persistence layer is optional.
        logger.debug("monitoring_digest: api.db import failed; skipping prior-run lookup")
        return None

    try:
        # list_runs returns most-recent-first. Pull a small window —
        # we only need the most-recent run for the same spec_path.
        runs = db.list_runs(limit=20)
    except Exception:  # noqa: BLE001
        logger.debug("monitoring_digest: list_runs() raised; skipping prior-run lookup")
        return None

    for run in runs or []:
        if not isinstance(run, dict):
            continue
        if run.get("spec_path") != spec_path:
            continue
        run_id = run.get("run_id")
        if not run_id:
            continue
        # Skip the current run if it happens to already be persisted
        # (the runner writes the digest BEFORE persistence in normal
        # flow, but tests may seed runs ahead of time).
        if current_run_dir and run_id == current_run_dir:
            continue
        try:
            manifest = db.get_run(run_id)
        except Exception:  # noqa: BLE001
            logger.debug("monitoring_digest: get_run(%s) raised; skipping prior-run lookup", run_id)
            return None
        if isinstance(manifest, dict):
            # Stamp run_id onto the manifest so the diff helper can
            # surface it without re-querying the DB.
            manifest = dict(manifest)
            manifest.setdefault("run_id", run_id)
            return manifest
    return None


def build_monitoring_digest(
    spec: AMLSpec,
    *,
    run_dir: Path,
    spec_path: Path,
    spec_content_hash: str,
    engine_version: str,
    as_of: datetime,
    alerts_by_rule: dict[str, list[dict[str, Any]]],
    dq_exceptions: list[DQException],
    prior_run: dict[str, Any] | None,
) -> MonitoringDigest:
    """Aggregate alert + DQ rollups into a single digest.

    Pure function: no I/O, no clock reads. Caller is responsible for
    sourcing the inputs from the runner state and persisting the result
    via :func:`write_monitoring_digest`.
    """
    severity_by_rule = _rule_severity_map(spec)
    queue_by_rule = _rule_queue_map(spec)

    alerts_per_rule: dict[str, int] = {}
    alerts_per_queue: dict[str, int] = {}
    alerts_per_severity: dict[str, int] = {}
    total_alerts = 0
    for rule_id, alerts in alerts_by_rule.items():
        count = len(alerts)
        alerts_per_rule[rule_id] = count
        total_alerts += count
        queue = queue_by_rule.get(rule_id, "unknown")
        alerts_per_queue[queue] = alerts_per_queue.get(queue, 0) + count
        severity = severity_by_rule.get(rule_id, "unknown")
        alerts_per_severity[severity] = alerts_per_severity.get(severity, 0) + count

    # Sort for byte-stable output. dict ordering is preserved in JSON
    # serialization when ``sort_keys=False``; we still pass
    # ``sort_keys=True`` at write time as belt-and-suspenders.
    alerts_per_rule = dict(sorted(alerts_per_rule.items()))
    alerts_per_queue = dict(sorted(alerts_per_queue.items()))
    alerts_per_severity = dict(sorted(alerts_per_severity.items()))

    dq_per_check_type: dict[str, int] = {}
    dq_per_contract: dict[str, int] = {}
    for exc in dq_exceptions:
        dq_per_check_type[exc.check_type] = dq_per_check_type.get(exc.check_type, 0) + 1
        dq_per_contract[exc.contract_id] = dq_per_contract.get(exc.contract_id, 0) + 1
    dq_per_check_type = dict(sorted(dq_per_check_type.items()))
    dq_per_contract = dict(sorted(dq_per_contract.items()))

    prior_run_id, changed = _diff_against_prior(alerts_per_rule, prior_run)
    # Sort the diff dict too.
    changed = dict(sorted(changed.items()))

    return MonitoringDigest(
        spec_name=spec.program.name,
        spec_path=str(spec_path),
        spec_content_hash=spec_content_hash,
        as_of=as_of,
        engine_version=engine_version,
        run_dir=str(run_dir),
        total_alerts=total_alerts,
        alerts_per_rule=alerts_per_rule,
        alerts_per_queue=alerts_per_queue,
        alerts_per_severity=alerts_per_severity,
        top_rules=_top_rules(alerts_per_rule),
        dq_total=len(dq_exceptions),
        dq_per_check_type=dq_per_check_type,
        dq_per_contract=dq_per_contract,
        prior_run_id=prior_run_id,
        changed_since_last_run=changed,
    )


def write_monitoring_digest(run_dir: Path, digest: MonitoringDigest) -> Path:
    """Persist the digest as ``monitoring_digest.json`` under ``run_dir``.

    ``sort_keys=True`` so the file is byte-stable across re-runs — the
    manifest-hash pin in ``audit.finalize()`` would otherwise drift on
    every run. Returns the written path so callers can hash it without
    re-deriving the location.
    """
    path = run_dir / "monitoring_digest.json"
    payload = digest.model_dump(mode="json")
    path.write_bytes(json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8"))
    return path
