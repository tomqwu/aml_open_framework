"""Tests for engine/explain.py + network_pattern subgraph capture in runner.

The runner enrichment is exercised end-to-end by spinning up DuckDB and
running a network_pattern rule against a tiny seeded link graph. The
pure helpers in explain.py are tested with hand-built alert payloads —
no DuckDB needed.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

import pytest

from aml_framework.engine.explain import (
    ExplainEdge,
    ExplainNode,
    ExplainPayload,
    NotANetworkAlert,
    explain_network_alert,
    to_mermaid,
)


# ---------------------------------------------------------------------------
# Pure helpers in explain.py
# ---------------------------------------------------------------------------


def _alert(seed="C0001", with_subgraph=True):
    a = {
        "rule_id": "nested_wallet_ring",
        "customer_id": seed,
        "component_size": 3,
        "counterparty_count": 2,
        "max_hops": 2,
        "pattern": "component_size",
        "window_start": "2026-04-27",
        "window_end": "2026-04-27",
    }
    if with_subgraph:
        a["subgraph"] = {
            "seed": seed,
            "max_hops": 2,
            "topology_hash": "deadbeef" * 8,
            "nodes": [
                {"id": seed, "hops": 0},
                {"id": "C0002", "hops": 1},
                {"id": "C0003", "hops": 1},
            ],
            "edges": [
                {"source": seed, "target": "C0002", "attribute": "phone", "weight": 1.0},
                {"source": seed, "target": "C0003", "attribute": "device_id", "weight": 1.0},
            ],
        }
    return a


class TestExplainNetworkAlert:
    def test_happy_path(self):
        explain = explain_network_alert(_alert())
        assert explain.seed == "C0001"
        assert explain.pattern == "component_size"
        assert len(explain.nodes) == 3
        assert len(explain.edges) == 2
        assert explain.topology_hash == "deadbeef" * 8

    def test_missing_subgraph_raises(self):
        with pytest.raises(NotANetworkAlert):
            explain_network_alert(_alert(with_subgraph=False))

    def test_non_network_alert_raises(self):
        with pytest.raises(NotANetworkAlert):
            explain_network_alert({"rule_id": "structuring", "customer_id": "C1"})

    def test_summary_includes_attribute_breakdown(self):
        explain = explain_network_alert(_alert())
        assert "phone" in explain.summary
        assert "device_id" in explain.summary
        assert "component_size" in explain.summary

    def test_seed_falls_back_to_customer_id(self):
        a = _alert()
        del a["subgraph"]["seed"]
        assert explain_network_alert(a).seed == "C0001"

    def test_to_dict_round_trip(self):
        explain = explain_network_alert(_alert())
        d = explain.to_dict()
        assert d["seed"] == "C0001"
        assert d["topology_hash"] == "deadbeef" * 8
        assert len(d["nodes"]) == 3
        # JSON-serialisable.
        json.dumps(d)


class TestToMermaid:
    def test_renders_graph_td_header(self):
        out = to_mermaid(explain_network_alert(_alert()))
        assert out.startswith("graph TD")

    def test_seed_node_has_seed_class(self):
        out = to_mermaid(explain_network_alert(_alert()))
        assert ":::seed" in out

    def test_attribute_appears_on_edge(self):
        out = to_mermaid(explain_network_alert(_alert()))
        assert "|phone|" in out
        assert "|device_id|" in out

    def test_node_ids_are_safe(self):
        a = _alert()
        a["subgraph"]["nodes"].append({"id": "with-dash:and@punct", "hops": 2})
        out = to_mermaid(explain_network_alert(a))
        assert "with_dash_and_punct" in out

    def test_empty_subgraph_renders_placeholder(self):
        empty = ExplainPayload(seed="X", pattern="component_size", max_hops=2)
        out = to_mermaid(empty)
        assert "(no subgraph)" in out

    def test_render_cap_truncates(self):
        nodes = [{"id": f"C{i:04}", "hops": 1} for i in range(60)]
        a = _alert()
        a["subgraph"]["nodes"] = nodes
        a["subgraph"]["edges"] = []
        out = to_mermaid(explain_network_alert(a), max_render_nodes=20)
        assert "more node(s)" in out


class TestExplainPayloadModel:
    def test_immutable(self):
        p = ExplainPayload(seed="X", pattern="component_size", max_hops=2)
        with pytest.raises(Exception):
            p.seed = "Y"  # type: ignore[misc]

    def test_node_immutable(self):
        n = ExplainNode(id="C1", hops=0)
        with pytest.raises(Exception):
            n.id = "C2"  # type: ignore[misc]

    def test_edge_immutable(self):
        e = ExplainEdge(source="A", target="B")
        with pytest.raises(Exception):
            e.source = "C"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Runner integration: subgraph capture during a real network_pattern fire
# ---------------------------------------------------------------------------


class TestRunnerSubgraphCapture:
    def _run_network_pattern(self, customers, links, *, having):
        """Helper: construct a minimal spec with one network_pattern rule
        and run it on a fake customer + link table."""
        import duckdb

        from aml_framework.engine.runner import _execute_network_pattern
        from aml_framework.spec.models import (
            NetworkPatternLogic,
            RegulationRef,
            Rule,
        )

        con = duckdb.connect()
        con.execute("CREATE TABLE customer (customer_id VARCHAR)")
        for c in customers:
            con.execute("INSERT INTO customer VALUES (?)", [c])
        con.execute(
            "CREATE TABLE resolved_entity_link ("
            "  left_customer_id VARCHAR,"
            "  right_customer_id VARCHAR,"
            "  attribute VARCHAR,"
            "  weight DOUBLE)"
        )
        for left, right, attr in links:
            con.execute(
                "INSERT INTO resolved_entity_link VALUES (?, ?, ?, ?)",
                [left, right, attr, 1.0],
            )

        rule = Rule(
            id="test_ring",
            name="Test ring",
            severity="high",
            regulation_refs=[RegulationRef(citation="X", description="X")],
            escalate_to="ignored",
            logic=NetworkPatternLogic(
                type="network_pattern",
                source="customer",
                pattern="component_size",
                max_hops=2,
                having=having,
            ),
        )
        return _execute_network_pattern(rule, con, datetime(2026, 4, 27))

    def test_alert_carries_subgraph(self):
        # Triangle: C1—C2 (phone), C2—C3 (email)
        alerts = self._run_network_pattern(
            customers=["C1", "C2", "C3"],
            links=[("C1", "C2", "phone"), ("C2", "C3", "email")],
            having={"component_size": {"gte": 3}},
        )
        assert len(alerts) >= 1
        # Pick the alert seeded on C2 (sees full component).
        c2_alert = next((a for a in alerts if a["customer_id"] == "C2"), None)
        assert c2_alert is not None
        sub = c2_alert["subgraph"]
        assert sub["seed"] == "C2"
        assert sub["max_hops"] == 2
        node_ids = {n["id"] for n in sub["nodes"]}
        assert {"C1", "C2", "C3"} <= node_ids
        edge_keys = {(e["source"], e["target"], e["attribute"]) for e in sub["edges"]}
        # Either direction is fine — assert one of each canonical edge present.
        assert any({"C1", "C2"} == {s, t} for s, t, _ in edge_keys)
        assert any({"C2", "C3"} == {s, t} for s, t, _ in edge_keys)
        assert "topology_hash" in sub
        assert len(sub["topology_hash"]) == 64  # SHA-256 hex

    def test_topology_hash_stable_across_seeds_in_same_component(self):
        # Triangle with two seeds; both should see the same topology_hash.
        alerts = self._run_network_pattern(
            customers=["C1", "C2", "C3"],
            links=[("C1", "C2", "phone"), ("C2", "C3", "email")],
            having={"component_size": {"gte": 3}},
        )
        hashes = {a["subgraph"]["topology_hash"] for a in alerts}
        assert len(hashes) == 1, f"expected one topology hash for the same component, got {hashes}"

    def test_isolated_customer_no_alert(self):
        alerts = self._run_network_pattern(
            customers=["C1"],
            links=[],
            having={"component_size": {"gte": 3}},
        )
        assert alerts == []

    def test_explainability_round_trip_from_runner_alert(self):
        alerts = self._run_network_pattern(
            customers=["C1", "C2", "C3"],
            links=[("C1", "C2", "phone"), ("C2", "C3", "email")],
            having={"component_size": {"gte": 3}},
        )
        explain = explain_network_alert(alerts[0])
        # The runner stamps Decimal counts; the explain helper coerces to int.
        assert isinstance(explain.summary, str)
        assert explain.topology_hash != ""
        # Numeric coercion (DuckDB returns Decimal).
        for n in explain.nodes:
            assert isinstance(n.hops, int)


# ---------------------------------------------------------------------------
# Decimal-coercion edge case (DuckDB-specific)
# ---------------------------------------------------------------------------


class TestDecimalHandling:
    def test_explain_handles_decimal_hops(self):
        a = _alert()
        a["subgraph"]["nodes"][0]["hops"] = Decimal(0)
        explain = explain_network_alert(a)
        # int() coerces Decimal cleanly.
        assert explain.nodes[0].hops == 0
