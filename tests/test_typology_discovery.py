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


def test_candidates_sorted_by_size_desc():
    custs = [_cust(f"N{i}") for i in range(40)]
    custs += [_cust(f"A{i}", txn_count=300.0) for i in range(3)]  # cohort size 3
    custs += [_cust(f"B{i}", cross_border_ratio=0.95) for i in range(6)]  # cohort size 6
    r = discover_candidates(custs, set(), anomaly_z=2.0, min_cohort_size=3)
    assert [c.size for c in r.candidates] == [6, 3]  # bigger first
