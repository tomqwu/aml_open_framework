from __future__ import annotations
from aml_framework.engine.typology_discovery import (  # noqa: F401 — public-surface import assertions
    CandidateTypology,
    DiscoveryReport,
    discover_candidates,
)

FEATS = ["txn_count", "sum_amount", "unique_counterparties", "cross_border_ratio"]


def _cust(cid, **vals):
    base = {
        "customer_id": cid,
        "txn_count": 5.0,
        "sum_amount": 5000.0,
        "unique_counterparties": 3.0,
        "cross_border_ratio": 0.1,
    }
    base.update(vals)
    return base


def test_empty_input():
    r = discover_candidates([], set())
    assert r.candidates == [] and r.n_unexplained == 0 and r.n_candidates == 0


def test_alerted_customers_excluded():
    # one strongly-anomalous customer, but it's already alerted -> excluded
    custs = [_cust("C1", txn_count=500.0)] + [_cust(f"N{i}") for i in range(10)]
    r = discover_candidates(custs, {"C1"}, min_cohort_size=1)
    assert r.n_unexplained == 10  # C1 excluded
    # the 10 baseline customers are identical -> stdev 0 -> no anomaly -> no candidates
    assert r.candidates == []


def test_cohort_of_shared_shape_becomes_one_candidate():
    # 4 customers with high txn_count (the anomalous shape), among 20 normal
    normals = [_cust(f"N{i}") for i in range(20)]
    hi = [_cust(f"H{i}", txn_count=200.0) for i in range(4)]
    r = discover_candidates(normals + hi, set(), anomaly_z=2.0, min_cohort_size=3)
    assert r.n_candidates == 1
    c = r.candidates[0]
    assert c.size == 4
    assert "txn_count" in c.anomalous_features
    assert sorted(c.customer_ids) == ["H0", "H1", "H2", "H3"]
    assert c.suggested_rule["status"] == "pending_promotion"
    assert "auto_discovered" in c.suggested_rule.get("tags", [])


def test_cohort_below_min_size_dropped():
    normals = [_cust(f"N{i}") for i in range(20)]
    hi = [_cust(f"H{i}", txn_count=200.0) for i in range(2)]  # only 2
    r = discover_candidates(normals + hi, set(), anomaly_z=2.0, min_cohort_size=3)
    assert r.candidates == []


def test_no_anomalous_feature_no_candidate():
    # all identical -> stdev 0 -> z=0 -> no anomalies
    r = discover_candidates([_cust(f"N{i}") for i in range(10)], set(), min_cohort_size=1)
    assert r.candidates == []


def test_deterministic():
    custs = [_cust(f"N{i}") for i in range(20)] + [
        _cust(f"H{i}", sum_amount=900000.0) for i in range(5)
    ]
    a = discover_candidates(custs, set(), anomaly_z=2.0, min_cohort_size=3)
    b = discover_candidates(custs, set(), anomaly_z=2.0, min_cohort_size=3)
    assert a.model_dump() == b.model_dump()


def test_having_uses_valid_metric_operator_clause():
    # high txn_count -> having must be {count: {gte: <cohort min>}}, the
    # valid aggregation_window shape, NOT a bare {txn_count: value}.
    normals = [_cust(f"N{i}") for i in range(20)]
    hi = [_cust(f"H{i}", txn_count=200.0 + i) for i in range(4)]  # cohort min 200.0
    r = discover_candidates(normals + hi, set(), anomaly_z=2.0, min_cohort_size=3)
    having = r.candidates[0].suggested_rule["logic"]["having"]
    assert having == {"count": {"gte": 200.0}}
    assert "txn_count" not in having


def test_unmapped_hi_feature_goes_to_business_intent_not_having():
    # cross_border_ratio has no aggregation metric -> must NOT be in having,
    # and must be noted in business_intent for the reviewer. having stays
    # non-empty (schema requires minProperties: 1) via a placeholder.
    normals = [_cust(f"N{i}") for i in range(20)]
    hi = [_cust(f"H{i}", cross_border_ratio=0.95) for i in range(4)]
    r = discover_candidates(normals + hi, set(), anomaly_z=2.0, min_cohort_size=3)
    rule = r.candidates[0].suggested_rule
    assert rule["logic"]["having"] == {"count": {"gte": 1}}  # placeholder, non-empty
    assert "cross_border_ratio" in rule["business_intent"]


def test_suggested_rule_is_schema_shaped():
    # The stub must carry every field the rule schema requires so an operator
    # can complete the TODO_ placeholders and run `aml validate`.
    normals = [_cust(f"N{i}") for i in range(20)]
    hi = [_cust(f"H{i}", txn_count=200.0) for i in range(4)]
    r = discover_candidates(normals + hi, set(), anomaly_z=2.0, min_cohort_size=3)
    rule = r.candidates[0].suggested_rule

    # Rule-level required fields.
    for field in ("id", "name", "severity", "regulation_refs", "logic", "escalate_to"):
        assert field in rule, field
    assert rule["escalate_to"] == "TODO_queue"
    assert isinstance(rule["regulation_refs"], list) and rule["regulation_refs"]
    assert {"citation", "description"} <= set(rule["regulation_refs"][0])

    # aggregation_window logic required fields.
    logic = rule["logic"]
    assert logic["type"] == "aggregation_window"
    for field in ("source", "group_by", "window", "having"):
        assert field in logic, field
    assert logic["source"] == "TODO_txn_contract_id"
    assert logic["group_by"] == ["customer_id"]
    assert logic["window"] == "30d"

    # having is a NON-EMPTY {metric: {operator: value}} clause.
    having = logic["having"]
    assert having, "having must be non-empty"
    metric, clause = next(iter(having.items()))
    assert isinstance(metric, str)
    assert isinstance(clause, dict) and clause
    op, val = next(iter(clause.items()))
    assert isinstance(op, str) and isinstance(val, (int, float))


def test_candidates_sorted_by_size_desc():
    custs = [_cust(f"N{i}") for i in range(40)]
    custs += [_cust(f"A{i}", txn_count=300.0) for i in range(3)]  # cohort size 3
    custs += [_cust(f"B{i}", cross_border_ratio=0.95) for i in range(6)]  # cohort size 6
    r = discover_candidates(custs, set(), anomaly_z=2.0, min_cohort_size=3)
    assert [c.size for c in r.candidates] == [6, 3]  # bigger first
