from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aml_framework.cli import _render_equivalence_markdown
from aml_framework.engine.equivalence import (
    EquivalenceCell,
    EquivalenceClass,
    EquivalenceReport,
)

GEN = datetime(2026, 6, 4)


def _report(cells):
    counts = {c: 0 for c in EquivalenceClass}
    for cell in cells:
        counts[cell.classification] += 1
    return EquivalenceReport(cells=cells, counts=counts, by_rule={}, generated_at=GEN)


def _new_only(cust, rule, sev):
    return EquivalenceCell(
        customer_id=cust,
        period_start=datetime(2026, 1, 1),
        period_end=datetime(2026, 2, 1),
        rule_id_new=rule,
        rule_id_legacy=None,
        classification=EquivalenceClass.NEW_ONLY,
        new_severity=sev,
    )


def test_markdown_has_divergence_clusters_section():
    report = _report(
        [_new_only("C1", "STRUCT_CASH", "high"), _new_only("C2", "STRUCT_CASH", "high")]
    )
    md = _render_equivalence_markdown(
        report, run_dir=Path("/tmp/run-x"), legacy_path=Path("/tmp/legacy.csv")
    )
    assert "## Divergence clusters" in md
    assert "STRUCT_CASH" in md
    assert "| 2 |" in md  # cluster size column


def test_markdown_clusters_section_empty_when_no_divergences():
    md = _render_equivalence_markdown(
        _report([]), run_dir=Path("/tmp/r"), legacy_path=Path("/tmp/l.csv")
    )
    assert "## Divergence clusters" in md
    assert "_No divergences to cluster._" in md


def test_markdown_clusters_section_precedes_per_class_tables():
    report = _report([_new_only("C1", "STRUCT_CASH", "high")])
    md = _render_equivalence_markdown(
        report, run_dir=Path("/tmp/r"), legacy_path=Path("/tmp/l.csv")
    )
    # the clusters section must appear before the per-class "first 20" tables
    assert md.index("## Divergence clusters") < md.index("## NEW_ONLY — first 20")
