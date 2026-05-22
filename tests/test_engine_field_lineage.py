"""Field-level lineage artifact (A3 — #364).

Covers:
- pure derivation (`derive_field_lineage`) for every Rule.logic type;
- empty spec degrades to an empty list;
- determinism: same spec → identical entries;
- the runner writes `field_lineage.jsonl` to the run dir;
- the manifest pins the artifact's SHA-256 hash;
- the artifact is always written (possibly empty) — same posture as
  `dq_exceptions.jsonl` from PR-B4;
- the artifact is in `_FROZEN_SNAPSHOT_TARGETS` so it gets chmodded
  0o444 by `_freeze_snapshot_files()` post-finalize.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date as _date, datetime, timezone
from pathlib import Path

from aml_framework.engine.audit import _FROZEN_SNAPSHOT_TARGETS
from aml_framework.engine.lineage import FieldLineageEntry, derive_field_lineage
from aml_framework.engine.runner import run_spec
from aml_framework.spec.models import (
    AggregationWindowLogic,
    AMLSpec,
    Column,
    CustomSQLLogic,
    DataContract,
    ListMatchLogic,
    NetworkPatternLogic,
    Program,
    PythonRefLogic,
    Queue,
    RegulationRef,
    Rule,
    Workflow,
)


_AS_OF = datetime(2026, 5, 1, tzinfo=timezone.utc)


def _txn_contract() -> DataContract:
    return DataContract(
        id="txn",
        source="t",
        columns=[
            Column(name="txn_id", type="string", nullable=False),
            Column(name="customer_id", type="string", nullable=False),
            Column(name="amount", type="decimal", nullable=False),
            Column(name="booked_at", type="timestamp", nullable=False),
        ],
    )


def _customer_contract() -> DataContract:
    return DataContract(
        id="customer",
        source="c",
        columns=[
            Column(name="customer_id", type="string", nullable=False),
            Column(name="legal_name", type="string", nullable=False),
            Column(name="onboarded_at", type="timestamp", nullable=False),
        ],
    )


def _make_spec(*, rules: list[Rule], contracts: list[DataContract] | None = None) -> AMLSpec:
    return AMLSpec(
        version=1,
        program=Program(
            name="T",
            jurisdiction="US",
            regulator="FinCEN",
            owner="MLRO",
            effective_date=_date(2026, 1, 1),
        ),
        data_contracts=contracts if contracts is not None else [_txn_contract()],
        rules=rules,
        workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
    )


# ---------------------------------------------------------------------------
# Pure derivation tests
# ---------------------------------------------------------------------------


class TestDeriveFieldLineagePure:
    def test_aggregation_window_traces_group_by_and_aggregations(self):
        rule = Rule(
            id="rapid_pass_through",
            name="Rapid pass-through",
            severity="high",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=AggregationWindowLogic(
                type="aggregation_window",
                source="txn",
                group_by=["customer_id"],
                window="7d",
                having={"count": {"gte": 5}, "sum_amount": {"gte": 10000}},
            ),
            escalate_to="q1",
            evidence=[],
        )
        spec = _make_spec(rules=[rule])

        entries = derive_field_lineage(spec, _AS_OF)

        # 1 group_by + 2 having metrics + 2 window fields = 5 entries.
        assert len(entries) == 5
        assert {e.alert_field for e in entries} == {
            "customer_id",
            "count",
            "sum_amount",
            "window_start",
            "window_end",
        }
        for e in entries:
            assert e.rule_id == "rapid_pass_through"
            assert e.source_contract_id == "txn"
            assert e.at == _AS_OF

        by_field = {e.alert_field: e for e in entries}
        assert by_field["customer_id"].source_column == "customer_id"
        assert by_field["customer_id"].transform == "GROUP_BY"
        assert by_field["count"].source_column == "*"
        assert by_field["count"].transform == "COUNT"
        assert by_field["sum_amount"].source_column == "amount"
        assert by_field["sum_amount"].transform == "SUM"
        # `compile_rule_sql` always emits window_start = MIN(booked_at)
        # and window_end = MAX(booked_at) on every aggregation alert.
        assert by_field["window_start"].source_column == "booked_at"
        assert by_field["window_start"].transform == "MIN"
        assert by_field["window_end"].source_column == "booked_at"
        assert by_field["window_end"].transform == "MAX"

    def test_aggregation_window_max_min_avg_traces_amount(self):
        rule = Rule(
            id="r_minmaxavg",
            name="R",
            severity="low",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=AggregationWindowLogic(
                type="aggregation_window",
                source="txn",
                group_by=["customer_id"],
                window="30d",
                having={
                    "max_amount": {"gte": 1},
                    "min_amount": {"gte": 0},
                    "avg_amount": {"gte": 100},
                },
            ),
            escalate_to="q1",
            evidence=[],
        )
        spec = _make_spec(rules=[rule])
        entries = derive_field_lineage(spec, _AS_OF)

        by_field = {e.alert_field: e for e in entries if e.alert_field != "customer_id"}
        assert by_field["max_amount"].transform == "MAX"
        assert by_field["min_amount"].transform == "MIN"
        assert by_field["avg_amount"].transform == "AVG"
        for fld in ("max_amount", "min_amount", "avg_amount"):
            assert by_field[fld].source_column == "amount"

    def test_custom_sql_emits_best_effort_row(self):
        rule = Rule(
            id="r_custom",
            name="R",
            severity="low",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=CustomSQLLogic(
                type="custom_sql",
                sql="SELECT customer_id FROM txn WHERE amount > 9000",
            ),
            escalate_to="q1",
            evidence=[],
        )
        spec = _make_spec(rules=[rule])
        entries = derive_field_lineage(spec, _AS_OF)

        assert len(entries) == 1
        e = entries[0]
        assert e.rule_id == "r_custom"
        assert e.alert_field == "*"
        assert e.source_contract_id == "*"
        assert e.source_column == "*"
        assert e.transform == "custom_sql"

    def test_python_ref_emits_best_effort_row(self):
        rule = Rule(
            id="r_py",
            name="R",
            severity="low",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=PythonRefLogic(
                type="python_ref",
                callable="aml_framework.models.iso_forest:score",
                model_id="iso_forest",
                model_version="1.0.0",
            ),
            escalate_to="q1",
            evidence=[],
        )
        spec = _make_spec(rules=[rule])
        entries = derive_field_lineage(spec, _AS_OF)

        assert len(entries) == 1
        e = entries[0]
        assert e.rule_id == "r_py"
        assert e.alert_field == "*"
        assert e.source_column == "*"
        assert e.transform == "python_ref:aml_framework.models.iso_forest:score"

    def test_list_match_exact_traces_matched_name_customer_id_and_score(self):
        # `_execute_list_match` writes `matched_name`, `customer_id`,
        # and `match_score` (=1.0 for exact) on every alert. The
        # lineage map must include all three so a regulator can resolve
        # "where did this alert come from?" without re-reading the
        # runner source. Codex P2 findings on PR-A3 (matched_name → field,
        # then match_score coverage).
        rule = Rule(
            id="r_listmatch",
            name="R",
            severity="critical",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=ListMatchLogic(
                type="list_match",
                source="customer",
                field="legal_name",
                list="ofac_sdn",
                match="exact",
            ),
            escalate_to="q1",
            evidence=[],
        )
        spec = _make_spec(rules=[rule], contracts=[_txn_contract(), _customer_contract()])
        entries = derive_field_lineage(spec, _AS_OF)

        assert len(entries) == 3
        by_field = {e.alert_field: e for e in entries}
        assert set(by_field) == {"matched_name", "customer_id", "match_score"}
        assert by_field["matched_name"].source_contract_id == "customer"
        assert by_field["matched_name"].source_column == "legal_name"
        assert by_field["matched_name"].transform == "list_match"
        assert by_field["customer_id"].source_contract_id == "customer"
        assert by_field["customer_id"].source_column == "customer_id"
        assert by_field["customer_id"].transform == "GROUP_BY"
        # match_score's source is the reference list, not a contract
        # column — source_column captures the list name, source_contract_id
        # is wildcard. `list_entry` is NOT emitted for exact matches.
        assert by_field["match_score"].source_contract_id == "*"
        assert by_field["match_score"].source_column == "ofac_sdn"
        assert by_field["match_score"].transform == "list_match:exact"
        for e in entries:
            assert e.rule_id == "r_listmatch"

    def test_list_match_fuzzy_also_traces_list_entry(self):
        # Fuzzy alerts additionally emit `list_entry` (the matched
        # reference-list value); lineage must include it. Codex P2.
        rule = Rule(
            id="r_listmatch_fuzzy",
            name="R",
            severity="critical",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=ListMatchLogic(
                type="list_match",
                source="customer",
                field="legal_name",
                list="ofac_sdn",
                match="fuzzy",
                threshold=0.85,
            ),
            escalate_to="q1",
            evidence=[],
        )
        spec = _make_spec(rules=[rule], contracts=[_txn_contract(), _customer_contract()])
        entries = derive_field_lineage(spec, _AS_OF)
        by_field = {e.alert_field: e for e in entries}
        assert set(by_field) == {"matched_name", "customer_id", "match_score", "list_entry"}
        assert by_field["match_score"].transform == "list_match:fuzzy"
        assert by_field["list_entry"].source_contract_id == "*"
        assert by_field["list_entry"].source_column == "ofac_sdn"
        assert by_field["list_entry"].transform == "list_match:fuzzy"

    def test_non_active_rules_are_skipped(self):
        # `run_spec` skips experimental + deprecated rules — see
        # `if rule.status != "active": continue` in runner.py. The
        # lineage artifact must match, or it claims lineage for rules
        # whose alerts/SQL never landed. Codex P2 on PR-A3.
        active = Rule(
            id="r_active",
            name="A",
            severity="low",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=AggregationWindowLogic(
                type="aggregation_window",
                source="txn",
                group_by=["customer_id"],
                window="7d",
                having={"count": {"gte": 1}},
            ),
            escalate_to="q1",
            evidence=[],
        )
        experimental = Rule(
            id="r_experimental",
            name="X",
            severity="low",
            status="experimental",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=AggregationWindowLogic(
                type="aggregation_window",
                source="txn",
                group_by=["customer_id"],
                window="7d",
                having={"count": {"gte": 1}},
            ),
            escalate_to="q1",
            evidence=[],
        )
        deprecated = Rule(
            id="r_deprecated",
            name="D",
            severity="low",
            status="deprecated",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=AggregationWindowLogic(
                type="aggregation_window",
                source="txn",
                group_by=["customer_id"],
                window="7d",
                having={"count": {"gte": 1}},
            ),
            escalate_to="q1",
            evidence=[],
        )
        spec = _make_spec(rules=[active, experimental, deprecated])
        entries = derive_field_lineage(spec, _AS_OF)
        rule_ids = {e.rule_id for e in entries}
        assert rule_ids == {"r_active"}, (
            f"only active rules should contribute lineage; got {rule_ids}"
        )

    def test_network_pattern_emits_both_metrics_and_customer_seed(self):
        # `_execute_network_pattern` always populates BOTH
        # `component_size` and `counterparty_count` on every alert
        # (regardless of which is thresholded in `having`), and seeds
        # from the hard-coded `customer` table (ignoring `logic.source`).
        # The lineage artifact must match the executor's actual output
        # contract. Codex P2 on PR-A3.
        rule = Rule(
            id="r_net",
            name="Net",
            severity="high",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=NetworkPatternLogic(
                type="network_pattern",
                pattern="component_size",
                max_hops=2,
                # `having` thresholds only component_size — but the alert
                # still carries counterparty_count, so lineage must too.
                having={"component_size": {"gte": 3}},
            ),
            escalate_to="q1",
            evidence=[],
        )
        spec = _make_spec(rules=[rule], contracts=[_txn_contract(), _customer_contract()])
        entries = derive_field_lineage(spec, _AS_OF)

        by_field = {e.alert_field: e for e in entries}
        assert set(by_field) == {"customer_id", "component_size", "counterparty_count"}
        # Seed customer_id traces to the hardcoded customer table, NOT to
        # `logic.source` (which defaults to "customer" anyway but could
        # be overridden — the executor ignores the override).
        assert by_field["customer_id"].source_contract_id == "customer"
        assert by_field["customer_id"].source_column == "customer_id"
        # Both metrics emit even though only one is thresholded. They
        # trace back to `customer` (the underlying declared contract);
        # `resolved_entity_link` is a derived in-memory table and is
        # NOT a valid lineage target — codex P2 caught the original
        # pointer.
        for metric in ("component_size", "counterparty_count"):
            assert by_field[metric].source_contract_id == "customer"
            assert by_field[metric].source_column == "*"
            assert by_field[metric].transform == "network_pattern:component_size"

    def test_empty_spec_returns_empty_list(self):
        # An AMLSpec with no rules — Pydantic permits it (the JSON schema's
        # `minItems: 1` only fires through the loader). The derivation
        # must degrade to an empty list rather than crash, so the
        # always-write contract still produces a 0-byte artifact.
        spec = _make_spec(rules=[])
        assert derive_field_lineage(spec, _AS_OF) == []

    def test_determinism_two_calls_match(self):
        # Two rules whose iteration order would otherwise sort
        # ambiguously without the explicit sort key inside
        # `derive_field_lineage`.
        rule_a = Rule(
            id="r_a",
            name="A",
            severity="low",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=AggregationWindowLogic(
                type="aggregation_window",
                source="txn",
                group_by=["customer_id"],
                window="7d",
                having={"count": {"gte": 1}, "sum_amount": {"gte": 1}},
            ),
            escalate_to="q1",
            evidence=[],
        )
        rule_b = Rule(
            id="r_b",
            name="B",
            severity="low",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=AggregationWindowLogic(
                type="aggregation_window",
                source="txn",
                group_by=["customer_id"],
                window="7d",
                having={"max_amount": {"gte": 1}},
            ),
            escalate_to="q1",
            evidence=[],
        )
        spec = _make_spec(rules=[rule_a, rule_b])
        a = derive_field_lineage(spec, _AS_OF)
        b = derive_field_lineage(spec, _AS_OF)
        assert [e.model_dump() for e in a] == [e.model_dump() for e in b]


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------


def _spec_for_run() -> AMLSpec:
    return _make_spec(
        rules=[
            Rule(
                id="r_agg",
                name="Aggregation",
                severity="low",
                regulation_refs=[RegulationRef(citation="x", description="x")],
                logic=AggregationWindowLogic(
                    type="aggregation_window",
                    source="txn",
                    group_by=["customer_id"],
                    window="365d",
                    having={"count": {"gte": 1}, "sum_amount": {"gte": 1}},
                ),
                escalate_to="q1",
                evidence=[],
            )
        ]
    )


def _txn_data() -> dict:
    return {
        "txn": [
            {"txn_id": "T1", "customer_id": "C1", "amount": 10.0, "booked_at": _AS_OF},
            {"txn_id": "T2", "customer_id": "C1", "amount": 20.0, "booked_at": _AS_OF},
        ],
    }


class TestRunSpecEmitsFieldLineage:
    def test_field_lineage_jsonl_written_with_expected_rows(self, tmp_path: Path):
        spec = _spec_for_run()
        data = _txn_data()
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")

        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )

        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        lineage_path = run_dir / "field_lineage.jsonl"
        assert lineage_path.exists(), "field_lineage.jsonl must always be written"

        lines = [ln for ln in lineage_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        # 1 group_by + 2 having + 2 window fields = 5 entries.
        assert len(lines) == 5, f"expected 5 entries, got {lines}"

        rows = [json.loads(ln) for ln in lines]
        by_field = {r["alert_field"]: r for r in rows}
        assert by_field["customer_id"]["source_column"] == "customer_id"
        assert by_field["customer_id"]["transform"] == "GROUP_BY"
        assert by_field["count"]["transform"] == "COUNT"
        assert by_field["count"]["source_column"] == "*"
        assert by_field["sum_amount"]["transform"] == "SUM"
        assert by_field["sum_amount"]["source_column"] == "amount"
        assert by_field["window_start"]["source_column"] == "booked_at"
        assert by_field["window_start"]["transform"] == "MIN"
        assert by_field["window_end"]["source_column"] == "booked_at"
        assert by_field["window_end"]["transform"] == "MAX"
        for r in rows:
            assert r["rule_id"] == "r_agg"
            assert r["source_contract_id"] == "txn"

    def test_manifest_pins_field_lineage_hash(self, tmp_path: Path):
        """Mirror of `dq_exceptions_hash` pinning from PR-B4: the manifest
        must carry a SHA-256 of `field_lineage.jsonl` so post-finalization
        edits to the artifact are detectable.
        """
        spec = _spec_for_run()
        data = _txn_data()
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")

        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )

        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        lineage_bytes = (run_dir / "field_lineage.jsonl").read_bytes()
        expected = hashlib.sha256(lineage_bytes).hexdigest()
        assert manifest["field_lineage_hash"] == expected, (
            "manifest must pin SHA-256 of field_lineage.jsonl for tamper detection"
        )

    def test_artifact_always_written_even_when_empty(self, tmp_path: Path):
        """Empty `rules` list → artifact is still written, just 0 bytes.
        Parallel to `dq_exceptions.jsonl`'s always-present contract.
        """
        spec = _make_spec(rules=[])
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")

        run_spec(
            spec=spec,
            spec_path=spec_path,
            data={"txn": []},
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )

        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        lineage_path = run_dir / "field_lineage.jsonl"
        assert lineage_path.exists()
        assert lineage_path.read_bytes() == b""

    def test_artifact_is_in_frozen_snapshot_targets(self):
        """The freeze list must include `field_lineage.jsonl` so
        `_freeze_snapshot_files()` chmods it 0o444 post-finalize —
        same audit-integrity posture as `dq_exceptions.jsonl`.
        """
        assert "field_lineage.jsonl" in _FROZEN_SNAPSHOT_TARGETS


# ---------------------------------------------------------------------------
# FieldLineageEntry model invariants
# ---------------------------------------------------------------------------


def test_field_lineage_entry_is_frozen_extra_forbid():
    entry = FieldLineageEntry(
        rule_id="r",
        alert_field="customer_id",
        source_contract_id="txn",
        source_column="customer_id",
        transform="GROUP_BY",
        at=_AS_OF,
    )
    import pytest

    with pytest.raises(Exception):
        entry.rule_id = "other"  # type: ignore[misc]
    with pytest.raises(Exception):
        FieldLineageEntry(
            rule_id="r",
            alert_field="x",
            source_contract_id="t",
            source_column="x",
            transform="GROUP_BY",
            at=_AS_OF,
            unknown_field="boom",  # type: ignore[call-arg]
        )
