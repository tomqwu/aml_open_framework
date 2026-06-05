"""Deterministic shape-signature discovery of candidate typologies (#496).

Offline analyzer over per-customer feature rows. Clusters the
UNEXPLAINED customers — those not caught by any rule (not in
``alerted_ids``) — into candidate typologies by a canonical "shape
signature" of which numeric features are statistically anomalous, so a
data scientist can spot emergent patterns ("six customers all high
cross-border ratio") and promote a reviewed cohort into a real rule.

Design rules (mirror ``engine/equivalence_clustering.py``):

* **Pure / deterministic.** No I/O, no clock reads, no random state.
  Same inputs -> identical ``DiscoveryReport``. The signature is a fixed
  z-score threshold over population statistics, *not* k-means or any
  sklearn estimator: the framework's determinism contract and the
  ``.[dev]``-only unit CI (no sklearn/numpy/pandas) both forbid
  stochastic clustering here.
* **Stdlib + pydantic only.** ``statistics`` for mean/pstdev. No pandas,
  no sklearn, no numpy, no new deps.
* **OFFLINE — never in the engine run path.** This is a triage/proposal
  lens. It produces *suggested* rule stubs marked
  ``status="pending_promotion"``; nothing here mutates a spec, fires an
  alert, or is hashed into the audit ledger. Proposals only — a human
  reviews and promotes.
"""

from __future__ import annotations

import statistics
from typing import Any

from pydantic import BaseModel, ConfigDict

# The numeric features considered for shape signatures.
_FEATURES = ("txn_count", "sum_amount", "unique_counterparties", "cross_border_ratio")


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CandidateTypology(_Base):
    """A cohort of unexplained customers sharing one anomaly signature."""

    signature: str
    anomalous_features: list[str]
    size: int
    customer_ids: list[str]
    suggested_rule: dict[str, Any]
    label: str


class DiscoveryReport(_Base):
    """Shape-signature discovery over the unexplained customer population."""

    candidates: list[CandidateTypology]
    n_unexplained: int
    n_candidates: int


def _slug(signature: str) -> str:
    """Deterministic lowercase slug for a rule id (non-alnum -> '_')."""
    return "".join(ch if ch.isalnum() else "_" for ch in signature.lower())


def discover_candidates(
    customer_features: list[dict[str, Any]],
    alerted_ids: set[str],
    *,
    anomaly_z: float = 2.0,
    min_cohort_size: int = 3,
) -> DiscoveryReport:
    """Cluster unexplained customers into candidate typologies by shape.

    ``customer_features`` is a list of dicts each carrying ``customer_id``
    plus a subset of ``_FEATURES``. ``alerted_ids`` are customers already
    caught by some rule and are excluded from discovery. A customer is a
    cohort member only if at least one feature's absolute z-score (over the
    unexplained population, population stdev) is ``>= anomaly_z``. Cohorts
    smaller than ``min_cohort_size`` are dropped. Output is deterministic:
    candidates sorted by ``(-size, signature)``, member ids sorted.
    """
    unexplained = [c for c in customer_features if c["customer_id"] not in alerted_ids]

    # Population statistics per present feature.
    present = [f for f in _FEATURES if any(f in c for c in unexplained)]
    stats: dict[str, tuple[float, float]] = {}
    for feat in present:
        values = [float(c[feat]) for c in unexplained if feat in c]
        if not values:
            continue
        mean = statistics.fmean(values)
        # Population stdev: 0 when all values identical -> all z = 0.
        std = statistics.pstdev(values) if len(values) > 1 else 0.0
        stats[feat] = (mean, std)

    # Group customers by their (sorted) anomaly signature, preserving the
    # insertion order from ``unexplained`` for determinism.
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for cust in unexplained:
        sig_parts: list[str] = []
        for feat in present:
            if feat not in cust or feat not in stats:
                continue
            mean, std = stats[feat]
            if std == 0:
                continue
            z = (float(cust[feat]) - mean) / std
            if abs(z) >= anomaly_z:
                sig_parts.append(f"{feat}:{'hi' if z > 0 else 'lo'}")
        if not sig_parts:
            continue
        sig_key = tuple(sorted(sig_parts))
        grouped.setdefault(sig_key, []).append(cust)

    candidates: list[CandidateTypology] = []
    for sig_key, members in grouped.items():
        if len(members) < min_cohort_size:
            continue
        signature = "|".join(sig_key)
        anomalous_features = sorted({part.split(":")[0] for part in sig_key})
        customer_ids = sorted(m["customer_id"] for m in members)
        hi_features = [part.split(":")[0] for part in sig_key if part.endswith(":hi")]
        lo_features = [part.split(":")[0] for part in sig_key if part.endswith(":lo")]
        label = _label(len(members), sig_key)
        suggested_rule = _suggested_rule(signature, label, members, hi_features, lo_features)
        candidates.append(
            CandidateTypology(
                signature=signature,
                anomalous_features=anomalous_features,
                size=len(members),
                customer_ids=customer_ids,
                suggested_rule=suggested_rule,
                label=label,
            )
        )

    candidates.sort(key=lambda c: (-c.size, c.signature))
    return DiscoveryReport(
        candidates=candidates,
        n_unexplained=len(unexplained),
        n_candidates=len(candidates),
    )


def _label(size: int, sig_key: tuple[str, ...]) -> str:
    """Short human description e.g. ``"4 customers · high txn_count"``."""
    plural = "customer" if size == 1 else "customers"
    descr = " · ".join(
        f"{'high' if part.endswith(':hi') else 'low'} {part.split(':')[0]}" for part in sig_key
    )
    return f"{size} {plural} · {descr}"


def _suggested_rule(
    signature: str,
    label: str,
    members: list[dict[str, Any]],
    hi_features: list[str],
    lo_features: list[str],
) -> dict[str, Any]:
    """A schema-shaped ``aggregation_window`` rule stub for the cohort.

    The stub carries every field the rule schema requires (``source``,
    ``group_by``, ``window``, a NON-EMPTY ``having``, plus rule-level
    ``regulation_refs`` and ``escalate_to``) so it is *structurally*
    complete, but the values an operator must own are explicit
    ``TODO_`` placeholders. Precedent: ``generators/legacy_import.py`` —
    stubs are shaped-but-incomplete proposals an operator completes
    before ``aml validate``.

    ``having`` is a valid spec clause: ``{metric: {operator: value}}`` (e.g.
    ``count: {gte: 3}``). Only "hi" features that map to a real
    aggregation_window metric become a threshold, using the cohort's MINIMUM
    value — a conservative floor the whole cohort clears:

    * ``txn_count``   -> ``count: {gte: <cohort min>}``
    * ``sum_amount``  -> ``sum_amount: {gte: <cohort min>}``

    Features with no clean aggregation metric (``unique_counterparties``,
    ``cross_border_ratio``) and any "lo" features are NOT placed in
    ``having`` (which would be an invalid clause); they are surfaced in
    ``business_intent`` so a reviewer refines them before promotion. When
    the cohort has NO aggregatable "hi" feature, ``having`` falls back to a
    placeholder ``{"count": {"gte": 1}}`` so the stub stays schema-shaped
    (non-empty) — the operator must set the real threshold.
    """
    # Map discovery feature names to aggregation_window having metrics.
    _METRIC_FOR_FEATURE = {"txn_count": "count", "sum_amount": "sum_amount"}

    having: dict[str, dict[str, float]] = {}
    unmapped_hi: list[str] = []
    for feat in hi_features:
        metric = _METRIC_FOR_FEATURE.get(feat)
        if metric is None:
            unmapped_hi.append(feat)
            continue
        vals = [float(m[feat]) for m in members if feat in m]
        if vals:
            having[metric] = {"gte": min(vals)}

    placeholder_having = not having
    if placeholder_having:
        # No aggregatable "hi" feature → keep the clause non-empty (schema
        # requires minProperties: 1) with a conservative placeholder the
        # operator must replace before promotion.
        having = {"count": {"gte": 1}}

    note = ""
    if unmapped_hi:
        note += (
            " Also anomalous on (no direct aggregation metric — refine before "
            "promotion): " + ", ".join(sorted(unmapped_hi)) + "."
        )
    if lo_features:
        note += " Low features (review): " + ", ".join(sorted(lo_features)) + "."
    if placeholder_having:
        note += " The placeholder having threshold (count >= 1) must be set."
    note += (
        " Complete the TODO_ placeholders (source, escalate_to, regulation "
        "citation) before `aml validate`."
    )
    return {
        "id": f"candidate_{_slug(signature)}",
        "name": label,
        "severity": "medium",
        "status": "pending_promotion",
        "logic": {
            "type": "aggregation_window",
            "source": "TODO_txn_contract_id",
            "group_by": ["customer_id"],
            "window": "30d",
            "having": having,
        },
        "escalate_to": "TODO_queue",
        "regulation_refs": [
            {
                "citation": "TODO_citation",
                "description": (
                    "Auto-discovered candidate — supply the regulation citation before promotion."
                ),
            }
        ],
        "tags": ["auto_discovered"],
        "business_intent": "Auto-discovered candidate — review before promotion." + note,
    }
