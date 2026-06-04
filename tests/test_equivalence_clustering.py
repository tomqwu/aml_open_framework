from __future__ import annotations

from datetime import datetime

from aml_framework.engine.equivalence import (
    EquivalenceCell,
    EquivalenceClass,
    EquivalenceReport,
)
from aml_framework.engine.equivalence_clustering import (
    DivergenceCluster,
    DivergenceClusterReport,
    cluster_divergences,
)

PS = datetime(2026, 1, 1)
PE = datetime(2026, 2, 1)  # 31-day window
GEN = datetime(2026, 6, 4)


def _cell(cust, cls, *, rn=None, rl=None, ns=None, ls=None, ps=PS, pe=PE):
    return EquivalenceCell(
        customer_id=cust,
        period_start=ps,
        period_end=pe,
        rule_id_new=rn,
        rule_id_legacy=rl,
        classification=cls,
        new_severity=ns,
        legacy_severity=ls,
    )


def _report(cells):
    counts = {c: 0 for c in EquivalenceClass}
    for cell in cells:
        counts[cell.classification] += 1
    return EquivalenceReport(cells=cells, counts=counts, by_rule={}, generated_at=GEN)


def test_empty_report_yields_no_clusters():
    report = cluster_divergences(_report([]))
    assert isinstance(report, DivergenceClusterReport)
    assert report.clusters == []
    assert report.total_divergences == 0
    assert report.generated_at == GEN


def test_match_and_diff_cells_are_ignored():
    cells = [
        _cell("C1", EquivalenceClass.MATCH, rn="R1", rl="L1"),
        _cell("C2", EquivalenceClass.DIFF, rn="R1", rl="L1", ns="high", ls="medium"),
    ]
    report = cluster_divergences(_report(cells))
    assert report.clusters == []
    assert report.total_divergences == 0


def test_same_shape_new_only_cells_form_one_cluster():
    cells = [
        _cell("C1", EquivalenceClass.NEW_ONLY, rn="STRUCT_CASH", ns="high"),
        _cell("C2", EquivalenceClass.NEW_ONLY, rn="STRUCT_CASH", ns="high"),
        _cell("C3", EquivalenceClass.NEW_ONLY, rn="STRUCT_CASH", ns="high"),
    ]
    report = cluster_divergences(_report(cells))
    assert len(report.clusters) == 1
    cluster = report.clusters[0]
    assert isinstance(cluster, DivergenceCluster)
    assert cluster.classification == EquivalenceClass.NEW_ONLY
    assert cluster.rule_id == "STRUCT_CASH"
    assert cluster.severity == "high"
    assert cluster.window_days == 31
    assert cluster.size == 3
    assert [m.customer_id for m in cluster.members] == ["C1", "C2", "C3"]
    assert report.total_divergences == 3


def test_different_shapes_split_into_separate_clusters():
    cells = [
        _cell("C1", EquivalenceClass.NEW_ONLY, rn="STRUCT_CASH", ns="high"),
        _cell("C2", EquivalenceClass.NEW_ONLY, rn="WIRE_BURST", ns="medium"),
        _cell("C3", EquivalenceClass.LEGACY_ONLY, rl="STRUCT_CASH", ls="high"),
    ]
    report = cluster_divergences(_report(cells))
    assert len(report.clusters) == 3


def test_legacy_only_uses_legacy_rule_and_severity():
    cells = [_cell("C1", EquivalenceClass.LEGACY_ONLY, rl="DORMANT", ls="low")]
    cluster = cluster_divergences(_report(cells)).clusters[0]
    assert cluster.classification == EquivalenceClass.LEGACY_ONLY
    assert cluster.rule_id == "DORMANT"
    assert cluster.severity == "low"


def test_none_rule_and_severity_use_sentinels():
    cells = [_cell("C1", EquivalenceClass.NEW_ONLY, rn=None, ns=None)]
    cluster = cluster_divergences(_report(cells)).clusters[0]
    assert cluster.rule_id == "<unmapped>"
    assert cluster.severity == "unspecified"


def test_label_is_human_readable():
    cells = [_cell("C1", EquivalenceClass.NEW_ONLY, rn="STRUCT_CASH", ns="high")]
    cluster = cluster_divergences(_report(cells)).clusters[0]
    assert "NEW_ONLY" in cluster.label
    assert "STRUCT_CASH" in cluster.label
    assert "high" in cluster.label
    assert "31" in cluster.label


def test_clusters_sorted_by_size_desc_then_signature():
    cells = [
        _cell("C1", EquivalenceClass.NEW_ONLY, rn="A", ns="high"),
        _cell("C2", EquivalenceClass.NEW_ONLY, rn="B", ns="high"),
        _cell("C3", EquivalenceClass.NEW_ONLY, rn="B", ns="high"),
    ]
    clusters = cluster_divergences(_report(cells)).clusters
    assert clusters[0].rule_id == "B" and clusters[0].size == 2
    assert clusters[1].rule_id == "A" and clusters[1].size == 1


def test_deterministic_same_input_same_output():
    cells = [
        _cell("C2", EquivalenceClass.NEW_ONLY, rn="A", ns="high"),
        _cell("C1", EquivalenceClass.LEGACY_ONLY, rl="B", ls="low"),
    ]
    r1 = cluster_divergences(_report(cells))
    r2 = cluster_divergences(_report(cells))
    assert r1.model_dump() == r2.model_dump()


def test_equal_size_clusters_break_ties_by_signature_deterministically():
    cells = [
        _cell("C1", EquivalenceClass.NEW_ONLY, rn="B", ns="high"),
        _cell("C2", EquivalenceClass.NEW_ONLY, rn="B", ns="high"),
        _cell("C3", EquivalenceClass.NEW_ONLY, rn="A", ns="high"),
        _cell("C4", EquivalenceClass.NEW_ONLY, rn="A", ns="high"),
    ]
    clusters = cluster_divergences(_report(cells)).clusters
    assert [c.rule_id for c in clusters] == ["A", "B"]
    assert clusters[0].size == 2 and clusters[1].size == 2


def test_window_days_truncates_and_can_be_zero():
    cells = [_cell("C1", EquivalenceClass.NEW_ONLY, rn="A", ns="high", ps=PS, pe=PS)]
    cluster = cluster_divergences(_report(cells)).clusters[0]
    assert cluster.window_days == 0


def test_member_order_is_input_order_independent():
    cells = [
        _cell("C3", EquivalenceClass.NEW_ONLY, rn="A", ns="high"),
        _cell("C1", EquivalenceClass.NEW_ONLY, rn="A", ns="high"),
        _cell("C2", EquivalenceClass.NEW_ONLY, rn="A", ns="high"),
        _cell("C5", EquivalenceClass.LEGACY_ONLY, rl="B", ls="low"),
        _cell("C4", EquivalenceClass.LEGACY_ONLY, rl="B", ls="low"),
    ]
    r1 = cluster_divergences(_report(cells))
    r2 = cluster_divergences(_report(list(reversed(cells))))
    assert r1.model_dump() == r2.model_dump()
    # 3+ member cluster so member ordering actually matters.
    big = next(c for c in r1.clusters if c.size == 3)
    assert [m.customer_id for m in big.members] == ["C1", "C2", "C3"]
