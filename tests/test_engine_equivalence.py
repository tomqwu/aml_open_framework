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


class TestSeverityFallbackFromSpec:
    """Codex PR-EQ-2 pass 1: when the alert payload doesn't carry
    `severity` (the engine runner puts it on cases, not alerts), the
    classifier must fall back to the spec's rule severity so a
    severity mismatch surfaces as DIFF instead of silently degrading
    to MATCH."""

    def test_severity_diff_from_rule_severities_map(self):
        # Real runner-shaped alert: no `severity` key on the dict.
        new = [
            {
                "rule_id": "rapid_pass_through",
                "customer_id": "C001",
                "window_start": PS,
                "window_end": PE,
            },
        ]
        legacy = [_legacy("MANTAS_RPT", "C001", severity="high")]
        report = classify_alerts(
            new,
            legacy,
            rule_map={"rapid_pass_through": "MANTAS_RPT"},
            rule_severities={"rapid_pass_through": "medium"},
        )
        assert report.counts[EquivalenceClass.DIFF] == 1, (
            f"expected DIFF when severities mismatch via rule map; got {report.counts}"
        )
        assert report.counts[EquivalenceClass.MATCH] == 0

    def test_severity_match_from_rule_severities_map(self):
        # Same shape but severities agree → MATCH.
        new = [
            {
                "rule_id": "rapid_pass_through",
                "customer_id": "C001",
                "window_start": PS,
                "window_end": PE,
            },
        ]
        legacy = [_legacy("MANTAS_RPT", "C001", severity="high")]
        report = classify_alerts(
            new,
            legacy,
            rule_map={"rapid_pass_through": "MANTAS_RPT"},
            rule_severities={"rapid_pass_through": "high"},
        )
        assert report.counts[EquivalenceClass.MATCH] == 1

    def test_payload_severity_wins_when_present(self):
        # If the caller already enriched the alert with severity,
        # don't ignore it. payload wins → DIFF expected here.
        new = [_new("rapid_pass_through", "C001", severity="medium")]
        legacy = [_legacy("MANTAS_RPT", "C001", severity="high")]
        report = classify_alerts(
            new,
            legacy,
            rule_map={"rapid_pass_through": "MANTAS_RPT"},
            rule_severities={"rapid_pass_through": "high"},  # would have matched, but
            # the payload's "medium" should win
        )
        assert report.counts[EquivalenceClass.DIFF] == 1


class TestManyNewRulesPerLegacy:
    """Codex PR-EQ-2 pass 1: when two new rule_ids map to the same
    legacy rule_id (operator-declared many-to-one) AND both fire on
    the same customer/window, neither alert should disappear from the
    report."""

    def test_two_new_rules_same_legacy_same_cell_no_legacy_alert(self):
        # Two new alerts share one legacy mapping for the same cell.
        # No legacy alert exists → both should surface as NEW_ONLY,
        # not collapse to a single bucket.
        new = [
            _new("rapid_pass_through_v1", "C001", severity="high"),
            _new("rapid_pass_through_v2", "C001", severity="medium"),
        ]
        report = classify_alerts(
            new,
            [],
            rule_map={
                "rapid_pass_through_v1": "MANTAS_RPT",
                "rapid_pass_through_v2": "MANTAS_RPT",
            },
        )
        assert report.counts[EquivalenceClass.NEW_ONLY] == 2, (
            f"both new alerts must surface as NEW_ONLY; got {report.counts}"
        )
        seen_rule_ids = {c.rule_id_new for c in report.cells}
        assert seen_rule_ids == {"rapid_pass_through_v1", "rapid_pass_through_v2"}

    def test_two_new_rules_same_legacy_with_legacy_alert(self):
        # Two new alerts share one legacy mapping; one legacy alert
        # at the same cell. The first new alert pairs to MATCH/DIFF
        # with legacy; the other surfaces as NEW_ONLY (instead of
        # being silently dropped by dict-clobber).
        new = [
            _new("rapid_pass_through_v1", "C001", severity="high"),
            _new("rapid_pass_through_v2", "C001", severity="high"),
        ]
        legacy = [_legacy("MANTAS_RPT", "C001", severity="high")]
        report = classify_alerts(
            new,
            legacy,
            rule_map={
                "rapid_pass_through_v1": "MANTAS_RPT",
                "rapid_pass_through_v2": "MANTAS_RPT",
            },
        )
        # Total cells = 2 (no NEW_ONLY collapse); 1 MATCH + 1 NEW_ONLY.
        assert report.counts[EquivalenceClass.MATCH] == 1
        assert report.counts[EquivalenceClass.NEW_ONLY] == 1
        assert report.counts[EquivalenceClass.LEGACY_ONLY] == 0
        assert report.counts[EquivalenceClass.DIFF] == 0


class TestDuplicateNewRowsDeduped:
    """Codex pass 6 P2: symmetrical to legacy dedupe — duplicate new-
    side rows for the same cell must not inflate NEW_ONLY counts."""

    def test_duplicate_new_rows_collapse_to_one_match(self):
        # Two new alerts for the same cell (e.g. custom_sql join
        # duplicate). One legacy alert. Expect one MATCH and no
        # spurious NEW_ONLY.
        new = [
            _new("rapid_pass_through", "C001", severity="high"),
            _new("rapid_pass_through", "C001", severity="high"),
        ]
        legacy = [_legacy("MANTAS_RPT", "C001", severity="high")]
        report = classify_alerts(
            new,
            legacy,
            rule_map={"rapid_pass_through": "MANTAS_RPT"},
        )
        assert report.counts[EquivalenceClass.MATCH] == 1
        assert report.counts[EquivalenceClass.NEW_ONLY] == 0
        assert report.counts[EquivalenceClass.LEGACY_ONLY] == 0


class TestMissingRuleIdFailsFast:
    """Codex pass 8 P2: a flat new alert without `rule_id` must raise
    rather than be silently dropped (otherwise a real MATCH/NEW_ONLY
    would silently degrade to a false LEGACY_ONLY)."""

    def test_flat_alert_without_customer_id_raises(self):
        # Codex pass 9: same rationale as missing rule_id — silent
        # acceptance would coerce to a blank cell key.
        new = [
            {
                "rule_id": "rapid_pass_through",
                # no customer_id
                "window_start": PS,
                "window_end": PE,
                "severity": "high",
            }
        ]
        with pytest.raises(ValueError, match="customer_id"):
            classify_alerts(new, [], rule_map={"rapid_pass_through": "MANTAS_RPT"})

    def test_flat_alert_without_rule_id_raises(self):
        new = [
            {
                # no rule_id
                "customer_id": "C001",
                "window_start": PS,
                "window_end": PE,
                "severity": "high",
            }
        ]
        with pytest.raises(ValueError, match="rule_id"):
            classify_alerts(new, [], rule_map={"rapid_pass_through": "MANTAS_RPT"})


class TestDictKeyAuthoritativeForRuleId:
    """Codex pass 6 P2: when flattening dict-of-lists, the outer dict
    key is the authoritative rule_id; any payload-level `rule_id`
    must be overridden to avoid lookup-against-wrong-rule_map bugs."""

    def test_dict_key_overrides_payload_rule_id(self):
        # Alert payload carries a stale/sub-rule rule_id; the dict
        # key is what the spec says the alert belongs to.
        new_dict = {
            "rapid_pass_through": [
                {
                    "rule_id": "internal_sub_rule_xyz",  # ignored
                    "customer_id": "C001",
                    "window_start": PS,
                    "window_end": PE,
                    "severity": "high",
                },
            ],
        }
        legacy = [_legacy("MANTAS_RPT", "C001", severity="high")]
        report = classify_alerts(
            new_dict,
            legacy,
            rule_map={"rapid_pass_through": "MANTAS_RPT"},
        )
        # Despite the payload-level "internal_sub_rule_xyz", the alert
        # should classify as MATCH via the dict-key rule_id.
        assert report.counts[EquivalenceClass.MATCH] == 1
        match_cell = next(c for c in report.cells if c.classification == EquivalenceClass.MATCH)
        assert match_cell.rule_id_new == "rapid_pass_through"


class TestDuplicateLegacyRowsDeduped:
    """Codex pass 5 P2: duplicate legacy rows for the same cell must
    not consume multiple new alerts and produce spurious LEGACY_ONLY
    tallies. The report is cell-level by contract."""

    def test_duplicate_legacy_rows_collapse_to_one_match(self):
        new = [_new("rapid_pass_through", "C001", severity="high")]
        # Two legacy rows for the same exact cell.
        legacy = [
            _legacy("MANTAS_RPT", "C001", severity="high"),
            _legacy("MANTAS_RPT", "C001", severity="high"),
        ]
        report = classify_alerts(
            new,
            legacy,
            rule_map={"rapid_pass_through": "MANTAS_RPT"},
        )
        # One MATCH, no spurious LEGACY_ONLY for the duplicate.
        assert report.counts[EquivalenceClass.MATCH] == 1
        assert report.counts[EquivalenceClass.LEGACY_ONLY] == 0
        assert report.counts[EquivalenceClass.NEW_ONLY] == 0


class TestAcceptsRunnerOutputShape:
    """Codex pass 4 P2: `RunResult.alerts` is
    ``dict[rule_id, list[alert]]`` not a flat list — `classify_alerts`
    must accept both shapes at the boundary."""

    def test_dict_of_lists_classified_correctly(self):
        new_dict = {
            "rapid_pass_through": [
                {
                    "customer_id": "C001",
                    "window_start": PS,
                    "window_end": PE,
                    "severity": "high",
                },
                {
                    "customer_id": "C002",
                    "window_start": PS,
                    "window_end": PE,
                    "severity": "high",
                },
            ],
        }
        legacy = [_legacy("MANTAS_RPT", "C001", severity="high")]
        report = classify_alerts(
            new_dict,
            legacy,
            rule_map={"rapid_pass_through": "MANTAS_RPT"},
        )
        assert report.counts[EquivalenceClass.MATCH] == 1
        assert report.counts[EquivalenceClass.NEW_ONLY] == 1


class TestDeterministicManyToOnePairing:
    """Codex pass 4 P2: when two new alerts at the same cell have the
    same severity, pairing must be order-independent so the audit
    report can't blame different rules across re-runs."""

    def test_same_severity_pairing_is_order_independent(self):
        # Two new alerts, same severity, same cell. Pairing must
        # consistently pick the alphabetically-earlier rule_id
        # regardless of input order.
        new_a = [
            _new("rule_alpha", "C001", severity="high"),
            _new("rule_zebra", "C001", severity="high"),
        ]
        new_b = list(reversed(new_a))
        legacy = [_legacy("LEG", "C001", severity="high")]
        rmap = {"rule_alpha": "LEG", "rule_zebra": "LEG"}
        report_a = classify_alerts(new_a, legacy, rule_map=rmap)
        report_b = classify_alerts(new_b, legacy, rule_map=rmap)
        # Same audit-relevant attribution either way.
        match_a = next(c for c in report_a.cells if c.classification == EquivalenceClass.MATCH)
        match_b = next(c for c in report_b.cells if c.classification == EquivalenceClass.MATCH)
        assert match_a.rule_id_new == match_b.rule_id_new == "rule_alpha"


class TestTimezoneNormalization:
    """Codex pass 3 P2: identical instants in different timezone
    spellings (UTC-aware vs naive) must key as the same cell."""

    def test_naive_new_alert_matches_utc_aware_legacy(self):
        from datetime import timezone as _tz

        # Runner-shaped alert: naive UTC datetime.
        new = [
            {
                "rule_id": "rapid_pass_through",
                "customer_id": "C001",
                "window_start": datetime(2026, 1, 1, 0, 0, 0),  # naive
                "window_end": datetime(2026, 2, 1, 0, 0, 0),  # naive
                "severity": "high",
            }
        ]
        # Legacy export: same instants but UTC-aware (trailing Z form).
        legacy = [
            LegacyAlert(
                customer_id="C001",
                period_start=datetime(2026, 1, 1, 0, 0, 0, tzinfo=_tz.utc),
                period_end=datetime(2026, 2, 1, 0, 0, 0, tzinfo=_tz.utc),
                rule_id_legacy="MANTAS_RPT",
                severity="high",
            )
        ]
        report = classify_alerts(
            new,
            legacy,
            rule_map={"rapid_pass_through": "MANTAS_RPT"},
        )
        assert report.counts[EquivalenceClass.MATCH] == 1, (
            f"naive + aware spellings of the same instant must MATCH; got {report.counts}"
        )
        assert report.counts[EquivalenceClass.NEW_ONLY] == 0
        assert report.counts[EquivalenceClass.LEGACY_ONLY] == 0


class TestManyToOnePairingPrefersSeverityMatch:
    """Codex pass 3 P2: with many-to-one mappings and multiple new
    alerts at the same cell, pair deterministically with the legacy
    alert by preferring a severity match."""

    def test_severity_match_wins_over_input_order(self):
        # Two new alerts at the same cell, both mapping to MANTAS_RPT.
        # The first has severity "medium" (would DIFF); the second
        # has "high" (would MATCH). Pairing must prefer the second
        # so the legacy cell classifies as MATCH, not DIFF.
        new = [
            _new("rapid_pass_through_v1", "C001", severity="medium"),
            _new("rapid_pass_through_v2", "C001", severity="high"),
        ]
        legacy = [_legacy("MANTAS_RPT", "C001", severity="high")]
        report = classify_alerts(
            new,
            legacy,
            rule_map={
                "rapid_pass_through_v1": "MANTAS_RPT",
                "rapid_pass_through_v2": "MANTAS_RPT",
            },
        )
        # Expect 1 MATCH (the high-severity new alert) + 1 NEW_ONLY
        # (the medium one, unpaired).
        assert report.counts[EquivalenceClass.MATCH] == 1
        assert report.counts[EquivalenceClass.NEW_ONLY] == 1
        assert report.counts[EquivalenceClass.DIFF] == 0
        # And the MATCH cell is from the high-severity new rule.
        match_cell = next(c for c in report.cells if c.classification == EquivalenceClass.MATCH)
        assert match_cell.rule_id_new == "rapid_pass_through_v2"


class TestManyToOneLegacyAttribution:
    """Codex pass 2 P2: many-to-one mappings must not arbitrarily
    attribute a LEGACY_ONLY cell to one of multiple candidate new
    rules. Leave `rule_id_new=None` so the rollup buckets under
    `legacy:<id>` rather than blaming the wrong rule."""

    def test_legacy_only_with_multiple_new_candidates_is_unattributed(self):
        # Two new rules map to MANTAS_RPT. Legacy alerts but no new
        # alert. The LEGACY_ONLY cell must have `rule_id_new=None`
        # because picking either candidate would be order-dependent.
        legacy = [_legacy("MANTAS_RPT", "C001", severity="high")]
        report = classify_alerts(
            [],
            legacy,
            rule_map={
                "rapid_pass_through_v1": "MANTAS_RPT",
                "rapid_pass_through_v2": "MANTAS_RPT",
            },
        )
        assert report.counts[EquivalenceClass.LEGACY_ONLY] == 1
        cell = next(c for c in report.cells if c.classification == EquivalenceClass.LEGACY_ONLY)
        assert cell.rule_id_new is None, (
            "many-to-one mapping must not pick one candidate arbitrarily"
        )
        # And the rollup buckets under the synthetic legacy: prefix.
        assert "legacy:MANTAS_RPT" in report.by_rule

    def test_legacy_only_with_single_new_candidate_attributed(self):
        # 1:1 mapping → attribution is unambiguous, keep current behavior.
        legacy = [_legacy("MANTAS_RPT", "C001", severity="high")]
        report = classify_alerts(
            [],
            legacy,
            rule_map={"rapid_pass_through": "MANTAS_RPT"},
        )
        cell = next(c for c in report.cells if c.classification == EquivalenceClass.LEGACY_ONLY)
        assert cell.rule_id_new == "rapid_pass_through"


class TestUnmappedSeverityFallback:
    """Codex pass 2 P3: unmapped-new branch must also use the
    rule_severities map so unmapped-rule drilldown is consistent
    with mapped branches."""

    def test_unmapped_new_uses_rule_severities(self):
        # Alert has no `severity` key on the dict; rule_id isn't in
        # rule_map; rule_severities supplies the value.
        new = [
            {
                "rule_id": "wired_only_scorer",  # not in rule_map
                "customer_id": "C001",
                "window_start": PS,
                "window_end": PE,
            }
        ]
        report = classify_alerts(
            new,
            [],
            rule_map={},
            rule_severities={"wired_only_scorer": "medium"},
        )
        assert report.counts[EquivalenceClass.NEW_ONLY] == 1
        cell = report.cells[0]
        assert cell.new_severity == "medium", (
            f"unmapped-new branch must honor rule_severities; got {cell.new_severity!r}"
        )


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

    def test_headerless_csv_raises(self, tmp_path: Path):
        # Codex pass 7: a zero-byte or otherwise headerless export must
        # raise the same shape of error as a missing-column path,
        # rather than silently returning [] (which would inflate
        # NEW_ONLY counts on a mis-pointed export).
        csv_path = tmp_path / "headerless.csv"
        csv_path.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="no header row"):
            load_legacy_alerts_csv(csv_path)

    def test_column_mapping_supports_spec_native_legacy_columns(self, tmp_path: Path):
        # The CA example spec declares `key_columns` as
        # `["rule_id", "customer_id", "window_start"]`. The loader
        # must respect that without forcing the operator to rename
        # the legacy export. Codex pass 2 — closes spec/loader gap.
        csv_path = tmp_path / "legacy.csv"
        csv_path.write_text(
            "customer_id,window_start,window_end,rule_id,severity\n"
            "C001,2026-01-01T00:00:00,2026-02-01T00:00:00,MANTAS_RPT,high\n",
            encoding="utf-8",
        )
        legacy = load_legacy_alerts_csv(
            csv_path,
            column_mapping={
                "period_start": "window_start",
                "period_end": "window_end",
                "rule_id_legacy": "rule_id",
            },
        )
        assert len(legacy) == 1
        assert legacy[0].customer_id == "C001"
        assert legacy[0].rule_id_legacy == "MANTAS_RPT"
        assert legacy[0].severity == "high"


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
