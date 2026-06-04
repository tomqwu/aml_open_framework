"""Champion-challenger outcome analysis for the N1 prioritization scorer.

Scores historical LABELLED alerts with a champion and a challenger config,
computes precision@k + recall per config, and emits a deterministic
`priority_outcome.json` (SR 26-2 outcome analysis). Pure + reproducible.

Temporal-leakage guard: `score_alert` reads only the as-of feature keys in
`LEAKAGE_SAFE_FEATURES` off each alert dict — never a global/time lookup — so
a champion-challenger replay cannot bias scores with post-as_of data. The
allowlist + `test_score_is_invariant_to_a_future_dated_field` enforce it.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from aml_framework.engine.prioritization import score_alert

# The ONLY per-alert keys the scorer may read. A tripwire: adding a feature
# means consciously updating this set (and re-proving the leakage test).
LEAKAGE_SAFE_FEATURES = frozenset({"sum_amount", "amount", "count", "matched_row_ids"})

_DEFAULT_KS = (5, 10, 20)
_TRUE = {"true", "1", "yes", "y", "t"}


class ConfigOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    precision_at_k: dict[str, float]
    recall: float
    mean_score: float
    weights: dict[str, float]


class PriorityOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    n_alerts: int
    n_labelled_positives: int
    k_values: list[int]
    champion: ConfigOutcome
    challenger: ConfigOutcome
    winner: str


def precision_at_k(ranked_ids: list[str], labels: dict[str, bool], k: int) -> float:
    """Textbook precision@k: labelled positives in the top-k divided by `k`.
    The denominator is `k` (not the slice length) so a short ranking is not
    flattered — precision@20 over 3 alerts can be at most 3/20."""
    if k <= 0:
        return 0.0
    hits = sum(1 for cid in ranked_ids[:k] if labels.get(cid) is True)
    return round(hits / k, 6)


def recall_at_labels(ranked_ids: list[str], labels: dict[str, bool]) -> float:
    """Fraction of all labelled positives that appear anywhere in the ranking."""
    positives = {cid for cid, v in labels.items() if v is True}
    if not positives:
        return 0.0
    surfaced = positives & set(ranked_ids)
    return round(len(surfaced) / len(positives), 6)


def load_labels_csv(path: Path) -> dict[str, bool]:
    """Parse a `customer_id,is_true_positive` CSV into {customer_id: bool}.
    Mirrors the `aml backtest --labels` convention."""
    labels: dict[str, bool] = {}
    with Path(path).open(newline="") as fh:
        for row in csv.DictReader(fh):
            cid = (row.get("customer_id") or "").strip()
            if not cid:
                continue
            labels[cid] = (row.get("is_true_positive") or "").strip().lower() in _TRUE
    return labels


def _score_rows(
    alerts_by_rule: dict[str, list[dict[str, Any]]],
    rules: dict[str, Any],
    config: Any,
) -> list[tuple[float, str, str]]:
    """(score, rule_id, customer_id) for every alert under `config`."""
    rows: list[tuple[float, str, str]] = []
    for rule_id, alerts in alerts_by_rule.items():
        rule = rules.get(rule_id)
        if rule is None:
            continue
        for a in alerts:
            # ENFORCE the leakage guard: the scorer only ever sees the as-of
            # feature keys — never a post-as_of field that happens to ride on
            # the alert dict. customer_id is carried separately for ranking.
            safe = {k: a[k] for k in LEAKAGE_SAFE_FEATURES if k in a}
            score = score_alert(safe, rule, config).score
            rows.append((score, str(rule_id), str(a.get("customer_id"))))
    return rows


def _config_outcome(
    alerts_by_rule: dict[str, list[dict[str, Any]]],
    rules: dict[str, Any],
    labels: dict[str, bool],
    config: Any,
    ks: tuple[int, ...],
) -> ConfigOutcome:
    rows = _score_rows(alerts_by_rule, rules, config)
    # Rank by score desc, deterministic tiebreak on (rule_id, customer_id).
    rows.sort(key=lambda t: (-t[0], t[1], t[2]))
    ranked_ids = [cid for _, _, cid in rows]
    w = config.weights
    return ConfigOutcome(
        precision_at_k={str(k): precision_at_k(ranked_ids, labels, k) for k in ks},
        recall=recall_at_labels(ranked_ids, labels),
        mean_score=round(sum(s for s, _, _ in rows) / len(rows), 6) if rows else 0.0,
        weights={
            "severity": w.severity,
            "risk_tier": w.risk_tier,
            "amount": w.amount,
            "volume": w.volume,
        },
    )


def build_priority_outcome(
    alerts_by_rule: dict[str, list[dict[str, Any]]],
    rules: dict[str, Any],
    labels: dict[str, bool],
    *,
    champion: Any,
    challenger: Any,
    ks: tuple[int, ...] = _DEFAULT_KS,
) -> PriorityOutcome:
    """Deterministic champion-vs-challenger outcome on labelled alerts."""
    champ = _config_outcome(alerts_by_rule, rules, labels, champion, ks)
    chall = _config_outcome(alerts_by_rule, rules, labels, challenger, ks)
    max_k = str(max(ks))
    # Winner by recall, then precision@max-k. Deterministic, explainable.
    champ_key = (champ.recall, champ.precision_at_k[max_k])
    chall_key = (chall.recall, chall.precision_at_k[max_k])
    if champ_key > chall_key:
        winner = "champion"
    elif chall_key > champ_key:
        winner = "challenger"
    else:
        winner = "tie"
    n_alerts = sum(len(v) for v in alerts_by_rule.values())
    n_pos = sum(1 for v in labels.values() if v is True)
    return PriorityOutcome(
        enabled=True,
        n_alerts=n_alerts,
        n_labelled_positives=n_pos,
        k_values=list(ks),
        champion=champ,
        challenger=chall,
        winner=winner,
    )
