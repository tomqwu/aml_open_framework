from __future__ import annotations

from aml_framework.engine.mule_ring import MuleRing, MuleRingReport, detect_mule_rings  # noqa: F401


def test_empty_edges():
    r = detect_mule_rings([])
    assert r.rings == [] and r.n_rings == 0 and r.n_entities == 0


def test_triangle_is_a_ring():
    # 3 mutually-linked customers -> one dense ring
    edges = [("C1", "C2"), ("C2", "C3"), ("C1", "C3")]
    r = detect_mule_rings(edges, min_ring_size=3, min_density=0.5)
    assert r.n_rings == 1
    ring = r.rings[0]
    assert ring.size == 3
    assert ring.members == ["C1", "C2", "C3"]
    assert ring.internal_edges == 3
    assert ring.density == 1.0
    assert ring.ring_id.startswith("MR-")
    assert r.n_entities == 3


def test_thin_chain_below_density_not_a_ring():
    # a 4-node chain C1-C2-C3-C4: 3 edges, max possible = 6 -> density 0.5
    edges = [("C1", "C2"), ("C2", "C3"), ("C3", "C4")]
    r = detect_mule_rings(edges, min_ring_size=3, min_density=0.6)
    assert r.rings == []  # 0.5 < 0.6


def test_chain_at_density_threshold_is_ring():
    edges = [("C1", "C2"), ("C2", "C3"), ("C3", "C4")]
    r = detect_mule_rings(edges, min_ring_size=3, min_density=0.5)
    assert r.n_rings == 1 and r.rings[0].size == 4


def test_below_min_size_dropped():
    edges = [("C1", "C2")]  # component size 2
    r = detect_mule_rings(edges, min_ring_size=3)
    assert r.rings == []


def test_two_components_independent():
    edges = [
        ("A1", "A2"),
        ("A2", "A3"),
        ("A1", "A3"),  # dense triangle
        ("B1", "B2"),
    ]  # size-2, dropped
    r = detect_mule_rings(edges, min_ring_size=3, min_density=0.5)
    assert r.n_rings == 1 and r.rings[0].members == ["A1", "A2", "A3"]


def test_undirected_dedupe_and_self_loops_ignored():
    edges = [("C1", "C2"), ("C2", "C1"), ("C1", "C1"), ("C2", "C3"), ("C1", "C3")]
    r = detect_mule_rings(edges, min_ring_size=3, min_density=0.5)
    assert r.n_rings == 1 and r.rings[0].internal_edges == 3  # C1-C2, C2-C3, C1-C3


def test_ring_id_stable_for_same_members():
    e1 = [("C1", "C2"), ("C2", "C3"), ("C1", "C3")]
    e2 = [("C3", "C1"), ("C2", "C1"), ("C3", "C2")]  # same graph, shuffled/reversed
    a = detect_mule_rings(e1, min_ring_size=3, min_density=0.5)
    b = detect_mule_rings(e2, min_ring_size=3, min_density=0.5)
    assert a.rings[0].ring_id == b.rings[0].ring_id


def test_deterministic_across_shuffled_input():
    edges = [("C2", "C3"), ("C1", "C3"), ("C1", "C2"), ("D1", "D2"), ("D2", "D3"), ("D1", "D3")]
    a = detect_mule_rings(edges, min_ring_size=3, min_density=0.5)
    import random  # noqa: F401  # NOT used for logic — only present to mirror the spec's order-independence note

    shuffled = list(edges)
    shuffled.reverse()
    b = detect_mule_rings(shuffled, min_ring_size=3, min_density=0.5)
    assert a.model_dump() == b.model_dump()


def test_rings_sorted_by_size_desc():
    edges = [
        ("A1", "A2"),
        ("A2", "A3"),
        ("A1", "A3"),  # size 3
        ("B1", "B2"),
        ("B2", "B3"),
        ("B3", "B4"),
        ("B1", "B3"),
        ("B1", "B4"),
        ("B2", "B4"),
        ("B1", "B2"),
    ]  # size 4 dense
    r = detect_mule_rings(edges, min_ring_size=3, min_density=0.5)
    assert [ring.size for ring in r.rings] == [4, 3]
