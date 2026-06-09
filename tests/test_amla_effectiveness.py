"""AMLA RTS effectiveness report — unit tests (issue #528)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

from aml_framework.metrics.amla_effectiveness import (
    AMLA_RTS_VERSION,
    AMLAEffectivenessReport,
    build_effectiveness_report,
    build_rts_coverage,
    format_effectiveness_json,
    format_effectiveness_markdown,
)
from aml_framework.metrics.outcomes import OutcomesReport, RuleOutcome


# ---------------------------------------------------------------------------
# Helpers — minimal spec doubles
# ---------------------------------------------------------------------------


@dataclass
class _RegRef:
    citation: str
    description: str = ""


@dataclass
class _Rule:
    id: str
    regulation_refs: list[_RegRef] = field(default_factory=list)


def _spec(rules: list[_Rule]) -> Any:
    prog = MagicMock()
    prog.name = "test_eu_program"
    s = MagicMock()
    s.program = prog
    s.rules = rules
    return s


def _empty_outcomes() -> OutcomesReport:
    return OutcomesReport(
        spec_program="test_eu_program",
        as_of="2026-06-09T00:00:00+00:00",
        total_alerts=0,
        total_cases=0,
        total_str_filed=0,
        total_closed_no_action=0,
        alert_to_case_pct=0.0,
        case_to_str_pct=0.0,
        alert_to_str_pct=0.0,
        sla_breach_rate_pct=0.0,
        rules=[],
    )


# ---------------------------------------------------------------------------
# build_rts_coverage
# ---------------------------------------------------------------------------


class TestBuildRtsCoverage:
    def test_empty_rules_all_gap(self):
        coverage = build_rts_coverage([])
        assert all(c.status == "gap" for c in coverage)
        assert all(c.rule_count == 0 for c in coverage)

    def test_single_rule_with_amlr_28_partial(self):
        rules = [_Rule("r1", [_RegRef("AMLR Art. 28(1)")])]
        coverage = build_rts_coverage(rules)
        amlr28 = next(c for c in coverage if c.article_id == "AMLR_28_1")
        assert amlr28.status == "partial"
        assert amlr28.rule_count == 1
        assert "r1" in amlr28.rule_ids

    def test_two_rules_with_amlr_28_covered(self):
        rules = [
            _Rule("r1", [_RegRef("AMLR Art. 28(1)")]),
            _Rule("r2", [_RegRef("AMLR Art. 28(1)")]),
        ]
        coverage = build_rts_coverage(rules)
        amlr28 = next(c for c in coverage if c.article_id == "AMLR_28_1")
        assert amlr28.status == "covered"
        assert amlr28.rule_count == 2

    def test_amlr_19_pattern_match(self):
        rules = [_Rule("pep", [_RegRef("AMLR Art. 19(9)")])]
        coverage = build_rts_coverage(rules)
        amlr19 = next(c for c in coverage if c.article_id == "AMLR_19_9")
        assert amlr19.status == "partial"
        assert "pep" in amlr19.rule_ids

    def test_amld6_53_pattern_match(self):
        rules = [_Rule("sanctions", [_RegRef("AMLD6 Art. 53(10)")])]
        coverage = build_rts_coverage(rules)
        amld6 = next(c for c in coverage if c.article_id == "AMLD6_53_10")
        assert amld6.status == "partial"
        assert "sanctions" in amld6.rule_ids

    def test_rule_with_no_amla_citations_has_no_effect(self):
        rules = [_Rule("r1", [_RegRef("AMLD6 Art. 50"), _RegRef("Directive 2015/849 Art. 11")])]
        coverage = build_rts_coverage(rules)
        assert all(c.status == "gap" for c in coverage)

    def test_rule_ids_are_sorted(self):
        rules = [
            _Rule("z_rule", [_RegRef("AMLR Art. 28(1)")]),
            _Rule("a_rule", [_RegRef("AMLR Art. 28(1)")]),
        ]
        coverage = build_rts_coverage(rules)
        amlr28 = next(c for c in coverage if c.article_id == "AMLR_28_1")
        assert list(amlr28.rule_ids) == ["a_rule", "z_rule"]

    def test_always_returns_three_articles(self):
        assert len(build_rts_coverage([])) == 3


# ---------------------------------------------------------------------------
# build_effectiveness_report
# ---------------------------------------------------------------------------


class TestBuildEffectivenessReport:
    def test_spec_program_propagated(self):
        spec = _spec([])
        report = build_effectiveness_report(spec, as_of="2026-06-09T00:00:00+00:00")
        assert report.spec_program == "test_eu_program"

    def test_rts_version_set(self):
        spec = _spec([])
        report = build_effectiveness_report(spec, as_of="2026-06-09T00:00:00+00:00")
        assert report.rts_version == AMLA_RTS_VERSION

    def test_funnel_none_when_not_provided(self):
        spec = _spec([])
        report = build_effectiveness_report(spec, as_of="2026-06-09T00:00:00+00:00")
        assert report.funnel is None

    def test_funnel_attached_when_provided(self):
        spec = _spec([])
        funnel = _empty_outcomes()
        report = build_effectiveness_report(spec, funnel=funnel, as_of="2026-06-09T00:00:00+00:00")
        assert report.funnel is funnel


# ---------------------------------------------------------------------------
# format_effectiveness_json
# ---------------------------------------------------------------------------


class TestFormatEffectivenessJson:
    def test_produces_valid_json(self):
        spec = _spec([])
        report = build_effectiveness_report(spec, as_of="2026-06-09T00:00:00+00:00")
        payload = format_effectiveness_json(report)
        parsed = json.loads(payload)
        assert "rts_coverage" in parsed
        assert "spec_program" in parsed

    def test_deterministic(self):
        spec = _spec([_Rule("r1", [_RegRef("AMLR Art. 28(1)")])])
        report = build_effectiveness_report(spec, as_of="2026-06-09T00:00:00+00:00")
        a = format_effectiveness_json(report)
        b = format_effectiveness_json(report)
        assert a == b

    def test_funnel_included_when_present(self):
        spec = _spec([])
        funnel = _empty_outcomes()
        report = build_effectiveness_report(spec, funnel=funnel, as_of="2026-06-09T00:00:00+00:00")
        parsed = json.loads(format_effectiveness_json(report))
        assert "funnel" in parsed

    def test_funnel_absent_when_none(self):
        spec = _spec([])
        report = build_effectiveness_report(spec, as_of="2026-06-09T00:00:00+00:00")
        parsed = json.loads(format_effectiveness_json(report))
        assert "funnel" not in parsed


# ---------------------------------------------------------------------------
# format_effectiveness_markdown
# ---------------------------------------------------------------------------


class TestFormatEffectivenessMarkdown:
    def _report(self, rules: list[_Rule] | None = None) -> AMLAEffectivenessReport:
        spec = _spec(rules or [])
        return build_effectiveness_report(spec, as_of="2026-06-09T00:00:00+00:00")

    def test_contains_rts_section(self):
        md = format_effectiveness_markdown(self._report())
        assert "RTS Article Coverage" in md

    def test_contains_program_name(self):
        md = format_effectiveness_markdown(self._report())
        assert "test_eu_program" in md

    def test_covered_rule_shows_tick(self):
        rules = [
            _Rule("r1", [_RegRef("AMLR Art. 28(1)")]),
            _Rule("r2", [_RegRef("AMLR Art. 28(1)")]),
        ]
        md = format_effectiveness_markdown(self._report(rules))
        assert "✓ covered" in md

    def test_gap_shows_cross(self):
        md = format_effectiveness_markdown(self._report())
        assert "✗ gap" in md

    def test_no_funnel_section_when_none(self):
        md = format_effectiveness_markdown(self._report())
        assert "Funnel" not in md

    def test_funnel_section_present_when_provided(self):
        spec = _spec([])
        funnel = _empty_outcomes()
        funnel.rules = [
            RuleOutcome(
                rule_id="structuring_cash",
                alerts=5,
                cases_opened=5,
                cases_escalated=0,
                str_filed=2,
                closed_no_action=2,
                pending=1,
                sla_breaches=0,
                sla_breach_rate_pct=0.0,
                precision=None,
                recall=None,
                true_positives=None,
                false_positives=None,
            )
        ]
        report = build_effectiveness_report(spec, funnel=funnel, as_of="2026-06-09T00:00:00+00:00")
        md = format_effectiveness_markdown(report)
        assert "Funnel" in md
        assert "structuring_cash" in md


# ---------------------------------------------------------------------------
# Integration: EU bank spec
# ---------------------------------------------------------------------------


class TestEuBankSpecCoverage:
    """Validate the live eu_bank spec carries the expected AMLA citations."""

    def test_eu_spec_loads_and_has_amla_citations(self):
        from pathlib import Path

        from aml_framework.spec import load_spec

        spec_path = Path(__file__).resolve().parents[1] / "examples" / "eu_bank" / "aml.yaml"
        spec = load_spec(spec_path)
        coverage = build_rts_coverage(spec.rules)
        amlr28 = next(c for c in coverage if c.article_id == "AMLR_28_1")
        assert amlr28.status == "covered", (
            f"Expected AMLR Art. 28(1) to be 'covered' but got {amlr28.status!r}; "
            f"rules: {amlr28.rule_ids}"
        )
        amlr19 = next(c for c in coverage if c.article_id == "AMLR_19_9")
        assert amlr19.status in ("covered", "partial"), (
            f"Expected AMLR Art. 19(9) to be 'covered' or 'partial' but got {amlr19.status!r}"
        )
        amld6 = next(c for c in coverage if c.article_id == "AMLD6_53_10")
        assert amld6.status in ("covered", "partial"), (
            f"Expected AMLD6 Art. 53(10) to be 'covered' or 'partial' but got {amld6.status!r}"
        )
