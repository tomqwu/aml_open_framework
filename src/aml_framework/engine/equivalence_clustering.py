"""Deterministic shape-signature clustering of equivalence divergences (#494).

Post-hoc analyzer over ``EquivalenceReport``. Groups the NEW_ONLY and
LEGACY_ONLY cells — the cells where the two systems *disagree* — by a
canonical "shape signature" so a data scientist triages parallel-run
defects by pattern (e.g. "47 NEW_ONLY on STRUCT_CASH, high severity,
31-day window") instead of scrolling thousands of flat rows.

Design rules (mirror ``engine/equivalence.py``):

* **Pure / deterministic.** No I/O, no clock reads, no random state.
  Same ``EquivalenceReport`` -> identical ``DivergenceClusterReport``.
  This is why clustering is a fixed shape signature, *not* k-means or
  any sklearn estimator: the framework's determinism contract
  (``test_run_is_reproducible``) and the ``.[dev]``-only unit CI (no
  sklearn/numpy) both forbid stochastic clustering here.
* **Stdlib + pydantic only.** No pandas, no sklearn, no new deps.
* **Explanation, not record.** The cluster report does not mutate the
  ``EquivalenceReport`` and is not hashed into the ledger. The four-way
  classification remains authoritative; clusters are a triage lens.

Signature = ``(classification, rule_id, severity, window_days)`` where
for NEW_ONLY the rule/severity come from the *new* side and for
LEGACY_ONLY from the *legacy* side. MATCH and DIFF cells are out of
scope (agreement / already-explained-by-diff_reason).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from aml_framework.engine.equivalence import (
    EquivalenceCell,
    EquivalenceClass,
    EquivalenceReport,
)

_UNMAPPED_RULE = "<unmapped>"
_UNSPECIFIED_SEVERITY = "unspecified"

# Only these two classes are "divergences" worth clustering.
_DIVERGENCE_CLASSES = (EquivalenceClass.NEW_ONLY, EquivalenceClass.LEGACY_ONLY)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DivergenceMember(_Base):
    """One divergent cell's identity inside a cluster (for drill-down)."""

    customer_id: str
    period_start: datetime
    period_end: datetime
    rule_id_new: str | None = None
    rule_id_legacy: str | None = None


class DivergenceCluster(_Base):
    """A group of divergent cells sharing one shape signature."""

    classification: EquivalenceClass
    rule_id: str
    severity: str
    window_days: int
    label: str
    size: int
    members: list[DivergenceMember]


class DivergenceClusterReport(_Base):
    """Shape-signature clustering of an ``EquivalenceReport``'s divergences."""

    clusters: list[DivergenceCluster]
    total_divergences: int
    generated_at: datetime


def _signature(cell: EquivalenceCell) -> tuple[EquivalenceClass, str, str, int]:
    if cell.classification is EquivalenceClass.NEW_ONLY:
        rule_id = cell.rule_id_new or _UNMAPPED_RULE
        severity = cell.new_severity or _UNSPECIFIED_SEVERITY
    else:  # LEGACY_ONLY
        rule_id = cell.rule_id_legacy or _UNMAPPED_RULE
        severity = cell.legacy_severity or _UNSPECIFIED_SEVERITY
    # ``.days`` truncates to whole days on purpose: window_days is a coarse
    # triage bucket, not an exact duration.
    window_days = (cell.period_end - cell.period_start).days
    return (cell.classification, rule_id, severity, window_days)


def _label(sig: tuple[EquivalenceClass, str, str, int], size: int) -> str:
    classification, rule_id, severity, window_days = sig
    return (
        f"{classification.value} · {rule_id} · {severity} severity · "
        f"{window_days}-day window ({size})"
    )


def cluster_divergences(report: EquivalenceReport) -> DivergenceClusterReport:
    """Cluster NEW_ONLY/LEGACY_ONLY cells by deterministic shape signature.

    Returns a ``DivergenceClusterReport`` whose clusters are sorted by
    ``size`` descending, then by the signature ascending (stable). Member
    cells within each cluster are sorted by ``(customer_id, period_start,
    period_end, rule_id_new, rule_id_legacy)`` so the output is independent
    of the order cells arrived in ``report.cells``.
    """
    grouped: dict[tuple[EquivalenceClass, str, str, int], list[DivergenceMember]] = {}
    for cell in report.cells:
        if cell.classification not in _DIVERGENCE_CLASSES:
            continue
        sig = _signature(cell)
        grouped.setdefault(sig, []).append(
            DivergenceMember(
                customer_id=cell.customer_id,
                period_start=cell.period_start,
                period_end=cell.period_end,
                rule_id_new=cell.rule_id_new,
                rule_id_legacy=cell.rule_id_legacy,
            )
        )

    for members in grouped.values():
        # Sort members by a stable key so cluster output never depends on the
        # order identical cells happened to arrive in ``report.cells``.
        members.sort(
            key=lambda m: (
                m.customer_id,
                m.period_start,
                m.period_end,
                m.rule_id_new or "",
                m.rule_id_legacy or "",
            )
        )

    clusters = [
        DivergenceCluster(
            classification=sig[0],
            rule_id=sig[1],
            severity=sig[2],
            window_days=sig[3],
            label=_label(sig, len(members)),
            size=len(members),
            members=members,
        )
        for sig, members in grouped.items()
    ]
    clusters.sort(
        key=lambda c: (-c.size, c.classification.value, c.rule_id, c.severity, c.window_days)
    )

    total = sum(c.size for c in clusters)
    return DivergenceClusterReport(
        clusters=clusters, total_divergences=total, generated_at=report.generated_at
    )
