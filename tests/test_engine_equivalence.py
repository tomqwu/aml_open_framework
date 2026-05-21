"""Tests for engine/equivalence.py (PR-EQ-2).

Covers the four classification classes (MATCH / NEW_ONLY / LEGACY_ONLY
/ DIFF), the CSV loader, deterministic ordering, edge cases, and the
spec-side rule_map round-trip + cross-reference validation that PR-EQ-2
step 1 added to ``LegacyReference``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from aml_framework.engine.equivalence import (
    EquivalenceCell,
    EquivalenceClass,
    EquivalenceReport,
    LegacyAlert,
    classify_alerts,
    load_legacy_alerts_csv,
)

PS = datetime(2026, 1, 1)
PE = datetime(2026, 2, 1)


def _new(
    rule_id: str,
    customer_id: str,
    *,
    severity: str = "high",
    window_start: datetime = PS,
    window_end: datetime = PE,
) -> dict:
    return {
        "rule_id": rule_id,
        "customer_id": customer_id,
        "window_start": window_start,
        "window_end": window_end,
        "severity": severity,
    }


def _legacy(
    rule_id_legacy: str,
    customer_id: str,
    *,
    severity: str | None = "high",
    period_start: datetime = PS,
    period_end: datetime = PE,
) -> LegacyAlert:
    return LegacyAlert(
        customer_id=customer_id,
        period_start=period_start,
        period_end=period_end,
        rule_id_legacy=rule_id_legacy,
        severity=severity,
    )


class TestClassifyAlerts:
    """All four classification classes plus rollups."""

    def test_all_four_classes_in_one_report(self):
        # C001 — both alerted with same severity → MATCH
        # C002 — only new alerted → NEW_ONLY
        # C003 — only legacy alerted → LEGACY_ONLY
        # C004 — both alerted but severities differ → DIFF
        new = [
            _new("rapid_pass_through", "C001", severity="high"),
            _new("rapid_pass_through", "C002", severity="high"),
            _new("rapid_pass_through", "C004", severity="medium"),
        ]
        legacy = [
            _legacy("MANTAS_RPT", "C001", severity="high"),
            _legacy("MANTAS_RPT", "C003", severity="medium"),
            _legacy("MANTAS_RPT", "C004", severity="high"),
        ]
        report = classify_alerts(new, legacy, rule_map={"rapid_pass_through": "MANTAS_RPT"})
        assert isinstance(report, EquivalenceReport)
        assert report.counts == {
            EquivalenceClass.MATCH: 1,
            EquivalenceClass.NEW_ONLY: 1,
            EquivalenceClass.LEGACY_ONLY: 1,
            EquivalenceClass.DIFF: 1,
        }
        by_cust = {c.customer_id: c for c in report.cells}
        assert by_cust["C001"].classification is EquivalenceClass.MATCH
        assert by_cust["C002"].classification is EquivalenceClass.NEW_ONLY
        assert by_cust["C003"].classification is EquivalenceClass.LEGACY_ONLY
        assert by_cust["C004"].classification is EquivalenceClass.DIFF

    def test_diff_reason_format_for_severity_mismatch(self):
        new = [_new("rapid_pass_through", "C001", severity="medium")]
        legacy = [_legacy("MANTAS_RPT", "C001", severity="high")]
        report = classify_alerts(new, legacy, rule_map={"rapid_pass_through": "MANTAS_RPT"})
        cell = report.cells[0]
        assert cell.classification is EquivalenceClass.DIFF
        assert cell.diff_reason == "severity mismatch: new=medium legacy=high"
        assert cell.new_severity == "medium"
        assert cell.legacy_severity == "high"

    def test_period_offset_makes_two_distinct_cells(self):
        # Same customer + same rule but disjoint periods → no match.
        # The new-side cell becomes NEW_ONLY; the legacy-side cell
        # becomes LEGACY_ONLY. The diff_reason field is reserved for
        # severity mismatches in this PR; period misalignment shows up
        # structurally as two separate cells.
        new = [_new("rapid_pass_through", "C001", window_start=PS, window_end=PE)]
        legacy = [
            _legacy(
                "MANTAS_RPT",
                "C001",
                period_start=datetime(2026, 3, 1),
                period_end=datetime(2026, 4, 1),
            )
        ]
        report = classify_alerts(new, legacy, rule_map={"rapid_pass_through": "MANTAS_RPT"})
        kinds = sorted(c.classification.value for c in report.cells)
        assert kinds == ["LEGACY_ONLY", "NEW_ONLY"]
        assert report.counts[EquivalenceClass.MATCH] == 0
        assert report.counts[EquivalenceClass.DIFF] == 0

    def test_by_rule_rollup_uses_new_id_when_mapped(self):
        new = [_new("rapid_pass_through", "C001", severity="high")]
        legacy = [_legacy("MANTAS_RPT", "C001", severity="high")]
        report = classify_alerts(new, legacy, rule_map={"rapid_pass_through": "MANTAS_RPT"})
        assert list(report.by_rule.keys()) == ["rapid_pass_through"]
        assert report.by_rule["rapid_pass_through"][EquivalenceClass.MATCH] == 1

    def test_by_rule_rollup_for_unmapped_legacy_uses_legacy_prefix(self):
        # Legacy rule has no entry in rule_map — the cell still
        # classifies (as LEGACY_ONLY) and the rollup keys it under
        # ``legacy:<id>`` so the operator can see which legacy rules
        # they have not yet mapped.
        legacy = [_legacy("MANTAS_UNKNOWN", "C001", severity="medium")]
        report = classify_alerts([], legacy, rule_map={})
        assert "legacy:MANTAS_UNKNOWN" in report.by_rule
        assert report.by_rule["legacy:MANTAS_UNKNOWN"][EquivalenceClass.LEGACY_ONLY] == 1

    def test_unmapped_new_rule_classifies_as_new_only(self):
        # If the operator forgot to map a new rule_id, every alert from
        # that rule lands in NEW_ONLY (never LEGACY_ONLY by accident).
        new = [_new("brand_new_typology", "C001", severity="high")]
        report = classify_alerts(new, [], rule_map={})
        assert report.counts[EquivalenceClass.NEW_ONLY] == 1
        assert report.cells[0].rule_id_legacy is None

    def test_match_when_both_sides_missing_severity(self):
        # Neither side has severity → MATCH (no mismatch to flag).
        new = [_new("rapid_pass_through", "C001", severity="")]
        legacy = [_legacy("MANTAS_RPT", "C001", severity=None)]
        report = classify_alerts(new, legacy, rule_map={"rapid_pass_through": "MANTAS_RPT"})
        assert report.cells[0].classification is EquivalenceClass.MATCH
        assert report.cells[0].new_severity is None
        assert report.cells[0].legacy_severity is None

    def test_cells_sorted_deterministically(self):
        new = [
            _new("rapid_pass_through", "C002"),
            _new("rapid_pass_through", "C001"),
        ]
        legacy = []
        report = classify_alerts(new, legacy, rule_map={"rapid_pass_through": "MANTAS_RPT"})
        assert [c.customer_id for c in report.cells] == ["C001", "C002"]

    def test_generated_at_is_caller_supplied_when_passed(self):
        report = classify_alerts([], [], rule_map={}, generated_at=datetime(2026, 5, 21, 12, 0))
        assert report.generated_at == datetime(2026, 5, 21, 12, 0)

    def test_repeated_calls_are_deterministic(self):
        new = [_new("rapid_pass_through", "C001", severity="high")]
        legacy = [_legacy("MANTAS_RPT", "C001", severity="high")]
        kwargs = dict(
            rule_map={"rapid_pass_through": "MANTAS_RPT"},
            generated_at=datetime(2026, 5, 21),
        )
        a = classify_alerts(new, legacy, **kwargs)
        b = classify_alerts(new, legacy, **kwargs)
        assert a.model_dump() == b.model_dump()


class TestEdgeCases:
    def test_empty_inputs(self):
        report = classify_alerts([], [], rule_map={})
        assert report.cells == []
        assert report.counts == {cls: 0 for cls in EquivalenceClass}
        assert report.by_rule == {}

    def test_empty_new_alerts(self):
        legacy = [_legacy("MANTAS_RPT", "C001", severity="high")]
        report = classify_alerts([], legacy, rule_map={"rapid_pass_through": "MANTAS_RPT"})
        assert report.counts[EquivalenceClass.LEGACY_ONLY] == 1
        assert report.counts[EquivalenceClass.MATCH] == 0
        assert report.counts[EquivalenceClass.NEW_ONLY] == 0
        assert report.counts[EquivalenceClass.DIFF] == 0

    def test_empty_legacy_alerts(self):
        new = [_new("rapid_pass_through", "C001", severity="high")]
        report = classify_alerts(new, [], rule_map={"rapid_pass_through": "MANTAS_RPT"})
        assert report.counts[EquivalenceClass.NEW_ONLY] == 1
        assert report.counts[EquivalenceClass.LEGACY_ONLY] == 0


class TestLoadLegacyAlertsCsv:
    """CSV → LegacyAlert round-trip."""

    def test_roundtrip_with_required_and_optional_columns(self, tmp_path: Path):
        csv_path = tmp_path / "legacy.csv"
        csv_path.write_text(
            "customer_id,period_start,period_end,rule_id_legacy,severity\n"
            "C001,2026-01-01T00:00:00,2026-02-01T00:00:00,MANTAS_RPT,high\n"
            "C002,2026-01-01T00:00:00,2026-02-01T00:00:00,MANTAS_OTHER,medium\n",
            encoding="utf-8",
        )
        rows = load_legacy_alerts_csv(csv_path)
        assert len(rows) == 2
        assert rows[0].customer_id == "C001"
        assert rows[0].period_start == datetime(2026, 1, 1)
        assert rows[0].rule_id_legacy == "MANTAS_RPT"
        assert rows[0].severity == "high"
        assert rows[1].severity == "medium"

    def test_unknown_columns_preserved_in_payload(self, tmp_path: Path):
        csv_path = tmp_path / "legacy.csv"
        csv_path.write_text(
            "customer_id,period_start,period_end,rule_id_legacy,"
            "severity,alert_id,score\n"
            "C001,2026-01-01,2026-02-01,MANTAS_RPT,high,A123,0.92\n",
            encoding="utf-8",
        )
        [row] = load_legacy_alerts_csv(csv_path)
        assert row.payload == {"alert_id": "A123", "score": "0.92"}

    def test_missing_required_column_raises(self, tmp_path: Path):
        csv_path = tmp_path / "bad.csv"
        # Drop `rule_id_legacy`.
        csv_path.write_text(
            "customer_id,period_start,period_end,severity\nC001,2026-01-01,2026-02-01,high\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="missing required column"):
            load_legacy_alerts_csv(csv_path)

    def test_empty_csv_returns_empty_list(self, tmp_path: Path):
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text(
            "customer_id,period_start,period_end,rule_id_legacy,severity\n",
            encoding="utf-8",
        )
        rows = load_legacy_alerts_csv(csv_path)
        assert rows == []

    def test_csv_then_classify_end_to_end(self, tmp_path: Path):
        csv_path = tmp_path / "legacy.csv"
        csv_path.write_text(
            "customer_id,period_start,period_end,rule_id_legacy,severity\n"
            "C001,2026-01-01T00:00:00,2026-02-01T00:00:00,MANTAS_RPT,high\n",
            encoding="utf-8",
        )
        legacy = load_legacy_alerts_csv(csv_path)
        new = [_new("rapid_pass_through", "C001", severity="high")]
        report = classify_alerts(new, legacy, rule_map={"rapid_pass_through": "MANTAS_RPT"})
        assert report.counts[EquivalenceClass.MATCH] == 1


class TestModelContracts:
    """Pydantic models enforce frozen + extra=forbid."""

    def test_legacy_alert_is_frozen(self):
        la = _legacy("MANTAS_RPT", "C001")
        with pytest.raises(ValidationError):
            la.customer_id = "C002"  # type: ignore[misc]

    def test_legacy_alert_forbids_extra(self):
        with pytest.raises(ValidationError):
            LegacyAlert(
                customer_id="C001",
                period_start=PS,
                period_end=PE,
                rule_id_legacy="MANTAS_RPT",
                unexpected="nope",  # type: ignore[call-arg]
            )

    def test_equivalence_cell_is_frozen(self):
        cell = EquivalenceCell(
            customer_id="C001",
            period_start=PS,
            period_end=PE,
            rule_id_new="rapid_pass_through",
            rule_id_legacy="MANTAS_RPT",
            classification=EquivalenceClass.MATCH,
        )
        with pytest.raises(ValidationError):
            cell.classification = EquivalenceClass.DIFF  # type: ignore[misc]


class TestSpecRuleMap:
    """PR-EQ-2 step 1 — rule_map on LegacyReference (model + schema)."""

    def test_rule_map_round_trips(self):
        from aml_framework.spec.models import LegacyReference

        ref = LegacyReference(
            path="/exports/legacy.csv",
            key_columns=["rule_id", "customer_id", "window_start"],
            rule_map={"rapid_pass_through": "MANTAS_RPT"},
        )
        assert ref.rule_map == {"rapid_pass_through": "MANTAS_RPT"}

    def test_rule_map_defaults_to_none(self):
        from aml_framework.spec.models import LegacyReference

        ref = LegacyReference(path="/exports/legacy.csv", key_columns=["alert_id"])
        assert ref.rule_map is None

    def test_rule_map_unknown_rule_id_rejected_at_spec_load(self, tmp_path: Path):
        # End-to-end: when a spec carries a rule_map entry pointing at a
        # rule_id that does not exist on the spec, AMLSpec validation
        # raises so the equivalence engine never silently misclassifies
        # the typo as LEGACY_ONLY.
        from aml_framework.spec.loader import load_spec

        # Start from the CA spec (which already carries a legacy_reference)
        # and inject a bogus rule_map entry pointing at a non-existent rule.
        src = Path("examples/canadian_schedule_i_bank/aml.yaml").read_text(encoding="utf-8")
        injected = src.replace(
            "key_columns: [rule_id, customer_id, window_start]",
            "key_columns: [rule_id, customer_id, window_start]\n"
            "    rule_map:\n"
            "      not_a_real_rule_id: MANTAS_X\n",
        )
        bad_spec = tmp_path / "aml.yaml"
        bad_spec.write_text(injected, encoding="utf-8")
        with pytest.raises(Exception, match="not_a_real_rule_id"):
            load_spec(bad_spec)

    def test_rule_map_with_real_rule_id_accepted(self, tmp_path: Path):
        from aml_framework.spec.loader import load_spec

        src = Path("examples/canadian_schedule_i_bank/aml.yaml").read_text(encoding="utf-8")
        # `rapid_pass_through` is one of the rules defined on this spec.
        injected = src.replace(
            "key_columns: [rule_id, customer_id, window_start]",
            "key_columns: [rule_id, customer_id, window_start]\n"
            "    rule_map:\n"
            "      rapid_pass_through: MANTAS_RPT_001\n",
        )
        good_spec = tmp_path / "aml.yaml"
        good_spec.write_text(injected, encoding="utf-8")
        spec = load_spec(good_spec)
        assert spec.program.legacy_reference is not None
        assert spec.program.legacy_reference.rule_map == {"rapid_pass_through": "MANTAS_RPT_001"}
