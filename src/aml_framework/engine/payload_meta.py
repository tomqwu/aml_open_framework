"""Uniform `threshold` + `reference_data_version` metadata on every alert.

PR-PAY-1 (Pillar 6 — Alert lifecycle & explainability). Memory quote:

    "an alert is a handoff into investigation; features must explain
    the trigger (window, threshold, segment, rule version,
    reference-data version, supporting txns)."

Before this module, alerts produced by `engine/runner.py` had inconsistent
shape across rule types:

  * `aggregation_window` — the threshold lived inside `rule.logic.having`
    (e.g. `{"count": {"gte": 3}}`) but was never echoed on the alert
    payload, so an investigator answering "why did this fire on
    2026-04-23?" had to re-open the spec.
  * `list_match` — recorded `list_name` but not the list file's content
    fingerprint / refresh date, so a stale sanctions snapshot could
    silently change behaviour.
  * `custom_sql` — emitted whatever the analyst put in the SELECT, with
    no first-class threshold echo.
  * `python_ref` — opaque by nature.
  * `network_pattern` — its `having` clause was implicit.

This module ships two stdlib-only helpers the runner calls once per rule:

  * `alert_threshold_snapshot(rule)` — returns a small, JSON-serialisable
    dict snapshot of the rule's active threshold (or `None` when the
    rule has no threshold concept). Same shape for every rule type so
    downstream `cases/<id>.json` and the dashboard "why did this fire?"
    panel can read one schema.
  * `reference_data_version(rule, *, as_of, lists_dir=None)` — returns a
    short `"<list>@<sha256-16>"` fingerprint of the reference list a
    `list_match` rule depends on, or `None` for rules that don't read a
    reference list (or when the file is missing). The fingerprint is
    derived from file *content* rather than mtime so re-running on a
    fresh checkout reproduces the same string — matters for the
    determinism contract (`test_run_is_reproducible`).

Pure functions; no I/O beyond reading the reference-list CSV. The
runner stamps the result onto each alert dict before `record_alerts`
runs, so the metadata flows through `alerts/<rule_id>.jsonl` AND lands
on the final `cases/<case_id>.json` via `_build_case(...).alert`.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from aml_framework.paths import REFERENCE_LISTS_DIR
from aml_framework.spec.models import Rule

__all__ = [
    "alert_threshold_snapshot",
    "reference_data_version",
]


def alert_threshold_snapshot(rule: Rule) -> dict[str, Any] | None:
    """Return a JSON-serialisable threshold snapshot for `rule`, or `None`.

    Shapes returned, by rule logic type:

      * `aggregation_window` — `{"having": {<metric>: {<op>: <value>}, ...}}`
        echoes the rule's `having` block verbatim. Always present (the
        spec schema requires `having` on this logic type).
      * `list_match` — `{"match": "exact"|"fuzzy", "threshold": <float>|None}`.
        For exact matches, `threshold` is `None` (no scoring); for fuzzy
        it's the configured score floor (default 0.8 in the runner).
      * `network_pattern` — `{"pattern": "...", "max_hops": N,
        "having": {...}}`. The same `having` semantics as
        aggregation_window plus the network-specific shape knobs.
      * `custom_sql` — `None`. The threshold (if any) is buried in
        bespoke SQL; there is no general way to extract it. Investigators
        read `rules/<id>.sql` from the audit ledger instead.
      * `python_ref` — `None`. The threshold lives inside the scorer
        callable; explainability is the scorer's responsibility (see
        `_inspect_context` opt-in in the runner).

    Returning `None` rather than an empty dict is deliberate — it
    communicates "this rule shape carries no first-class threshold"
    rather than "the threshold happens to be empty today".
    """
    logic = rule.logic
    logic_type = logic.type

    if logic_type == "aggregation_window":
        # `having` is required by the spec model — defensive fallback
        # for forward-compat (a future logic variant might relax it).
        having = getattr(logic, "having", None) or {}
        return {"having": dict(having)}

    if logic_type == "list_match":
        # Surface the fuzzy-match floor verbatim. For exact matches the
        # spec model leaves threshold = None — preserve that so callers
        # can distinguish "no scoring" from "scoring at 0.0".
        return {
            "match": logic.match,
            "threshold": logic.threshold,
        }

    if logic_type == "network_pattern":
        having = getattr(logic, "having", None) or {}
        return {
            "pattern": logic.pattern,
            "max_hops": logic.max_hops,
            "having": dict(having),
        }

    # custom_sql / python_ref have no general threshold contract.
    return None


def reference_data_version(
    rule: Rule,
    *,
    as_of: datetime,
    lists_dir: Path | None = None,
) -> str | None:
    """Return a fingerprint of the reference list this rule depends on.

    Format: ``"<list_name>@<content-sha256-16>"`` (e.g.
    ``"sanctions@a1b2c3d4e5f60718"``). Content-hash rather than mtime so
    re-running on a fresh checkout produces the same string — required
    by the deterministic-replay contract.

    Returns `None` when:
      * the rule logic type does not read a reference list
        (aggregation_window / custom_sql / python_ref / network_pattern);
      * the reference list file is missing on disk (the runner already
        degrades to "no alerts" for that case — surfacing `None` here
        keeps the alert payload contract uniform but honest).

    `as_of` is accepted for forward-compat (a future implementation may
    pin a snapshot directory by date), but is currently unused — the
    content hash already gives byte-stable identity.
    """
    if rule.logic.type != "list_match":
        return None

    list_name = rule.logic.list
    base = lists_dir or REFERENCE_LISTS_DIR
    list_path = Path(base) / f"{list_name}.csv"
    if not list_path.exists():
        return None

    digest = hashlib.sha256(list_path.read_bytes()).hexdigest()[:16]
    # `as_of` intentionally unused — content-hash carries identity.
    del as_of
    return f"{list_name}@{digest}"


def stamp_payload_meta(
    rule: Rule,
    alerts: list[dict[str, Any]],
    *,
    as_of: datetime,
    lists_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Mutate each alert in-place to carry `threshold` + `reference_data_version`.

    Returns the same list for caller convenience. Existing keys on the
    alert are **not** overwritten — if a rule executor already chose to
    surface a richer threshold (today none do, but a future
    rule-shape might), the executor's value wins. The audit ledger's
    `record_alerts` runs over the same list so the metadata lands on
    `alerts/<rule_id>.jsonl` AND on the final `cases/<case_id>.json`
    via `_build_case`.
    """
    snapshot = alert_threshold_snapshot(rule)
    ref_version = reference_data_version(rule, as_of=as_of, lists_dir=lists_dir)
    for alert in alerts:
        alert.setdefault("threshold", snapshot)
        alert.setdefault("reference_data_version", ref_version)
    return alerts
