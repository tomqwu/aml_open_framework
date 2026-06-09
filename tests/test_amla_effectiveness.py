"""AMLA RTS effectiveness telemetry pack (#528).

Covers the pure report builder (`metrics.amla_effectiveness`), the
`aml amla-effectiveness-report` CLI, the streamlit-free dashboard
alignment mapping, and the eu_bank spec's new AMLA RTS citations.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aml_framework.cli import app
from aml_framework.metrics.amla_effectiveness import (
    AMLA_RTS_ARTICLES,
    build_amla_effectiveness_report,
    build_rts_coverage,
    render_markdown,
)

EU_SPEC = Path("examples/eu_bank/aml.yaml")
AS_OF = datetime(2026, 6, 9, 18, 0, 0)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# --- A small, deterministic, hand-built run -------------------------------

_CASES = [
    {"case_id": "c1", "rule_id": "structuring_cash"},
    {"case_id": "c2", "rule_id": "structuring_cash"},
    {"case_id": "c3", "rule_id": "pep_screening"},
    {"case_id": "c4", "rule_id": "sanctions_screening"},
    {"case_id": "c5", "rule_id": "travel_rule_completeness"},
]
# c1, c3, c4 escalate to STR; c2 closed no action; c5 has no decisions (pending).
_DECISIONS = [
    {"case_id": "c1", "event": "escalated_to_str"},
    {"case_id": "c2", "event": "closed_no_action"},
    {"case_id": "c3", "event": "escalated_to_str"},
    {"case_id": "c4", "event": "escalated_to_str"},
]
_RULE_CITATIONS = {
    "structuring_cash": ["AMLD6 Art. 50", "AMLR Art. 28(1)"],
    "pep_screening": ["AMLD6 Art. 20-23", "AMLR Art. 19(9)"],
    "sanctions_screening": ["EU Regulation 269/2014", "AMLD6 Art. 53(10)"],
    "travel_rule_completeness": ["FATF R.16 (June 2025 revision)"],
}


def _build() -> object:
    return build_amla_effectiveness_report(
        cases=_CASES,
        decisions=_DECISIONS,
        rule_citations=_RULE_CITATIONS,
        spec_program="eu_bank_aml",
        generated_at=AS_OF,
    )


# --- Funnel correctness ----------------------------------------------------


def test_funnel_totals() -> None:
    r = _build()
    assert r.total_alerts == 5
    assert r.total_cases == 5
    assert r.total_str_filed == 3  # c1, c3, c4
    assert r.total_closed_no_action == 1  # c2
    assert r.alert_to_case_pct == 100.0
    assert r.case_to_str_pct == 60.0  # 3/5
    assert r.alert_to_str_pct == 60.0


def test_str_acceptance_not_tracked() -> None:
    r = _build()
    assert r.str_acceptance_status == "not_tracked"
    assert r.str_acceptance_rate_pct is None


def test_per_rule_funnel() -> None:
    r = _build()
    by_id = {rule.rule_id: rule for rule in r.rules}
    assert by_id["structuring_cash"].alerts == 2
    assert by_id["structuring_cash"].str_filed == 1
    assert by_id["structuring_cash"].closed_no_action == 1
    assert by_id["sanctions_screening"].str_filed == 1
    assert by_id["travel_rule_completeness"].pending == 1


def test_precision_with_labels() -> None:
    labels = {"c1": True, "c2": False}  # structuring_cash: 1 TP, 1 FP
    r = build_amla_effectiveness_report(
        cases=_CASES,
        decisions=_DECISIONS,
        rule_citations=_RULE_CITATIONS,
        spec_program="eu_bank_aml",
        generated_at=AS_OF,
        labels=labels,
    )
    by_id = {rule.rule_id: rule for rule in r.rules}
    assert by_id["structuring_cash"].precision == 0.5
    assert by_id["structuring_cash"].true_positives == 1
    assert by_id["structuring_cash"].false_positives == 1
    # Recall is never computable from the alert set alone — stays None.
    assert by_id["structuring_cash"].recall is None
    # Unlabelled rules keep precision None.
    assert by_id["pep_screening"].precision is None


# --- AMLA RTS citation coverage -------------------------------------------


def test_rts_coverage_maps_three_articles() -> None:
    r = _build()
    assert r.n_rts_articles == 3
    assert r.n_rts_covered == 3
    by_key = {c.key: c for c in r.rts_coverage}
    assert by_key["cdd"].covering_rule_ids == ["structuring_cash"]
    assert by_key["business_relationships"].covering_rule_ids == ["pep_screening"]
    assert by_key["pecuniary_sanctions"].covering_rule_ids == ["sanctions_screening"]
    assert all(c.status == "covered" for c in r.rts_coverage)


def test_rts_gap_when_no_citation() -> None:
    coverage, per_rule = build_rts_coverage({"r1": ["FATF R.16 (June 2025 revision)"]})
    assert all(c.status == "gap" for c in coverage)
    assert per_rule["r1"] == []


def test_per_rule_article_keys() -> None:
    r = _build()
    by_id = {rule.rule_id: rule for rule in r.rules}
    assert by_id["structuring_cash"].amla_rts_articles == ["cdd"]
    assert by_id["sanctions_screening"].amla_rts_articles == ["pecuniary_sanctions"]
    assert by_id["travel_rule_completeness"].amla_rts_articles == []


def test_article_constants() -> None:
    keys = [a.key for a in AMLA_RTS_ARTICLES]
    assert keys == ["cdd", "business_relationships", "pecuniary_sanctions"]


# --- Determinism -----------------------------------------------------------


def test_report_is_deterministic() -> None:
    a = _build().model_dump_json()
    b = _build().model_dump_json()
    assert a == b


def test_markdown_renders() -> None:
    md = render_markdown(_build())
    assert "AMLA RTS effectiveness pack" in md
    assert "AMLR Art. 28(1)" in md
    assert "not tracked in run" in md
    # Deterministic.
    assert md == render_markdown(_build())


# --- Dashboard alignment mapping (streamlit-free) -------------------------


def test_dashboard_alignment_mapping_eu_spec() -> None:
    from aml_framework.spec import load_spec
    from aml_framework.dashboard.frameworks import build_amla_rts_alignment, get_framework_tabs

    spec = load_spec(EU_SPEC)
    rows = build_amla_rts_alignment(spec)
    assert len(rows) == 3
    # eu_bank rules carry evidence trails, so every cited article is "mapped".
    statuses = {row["name"]: row["status"] for row in rows}
    assert statuses["AMLR Art. 28(1)"] == "mapped"
    assert statuses["AMLR Art. 19(9)"] == "mapped"
    assert statuses["AMLD6 Art. 53(10)"] == "mapped"
    # The AMLA tab is appended for EU specs only when spec is supplied.
    labels = [t["label"] for t in get_framework_tabs("EU", spec)]
    assert "AMLA RTS coverage" in labels
    assert "AMLA RTS coverage" not in [t["label"] for t in get_framework_tabs("EU")]
    assert "AMLA RTS coverage" not in [t["label"] for t in get_framework_tabs("US", spec)]


class _Ref:
    def __init__(self, citation: str) -> None:
        self.citation = citation


class _Rule:
    def __init__(self, rid: str, citations: list[str], evidence: list[str]) -> None:
        self.id = rid
        self.regulation_refs = [_Ref(c) for c in citations]
        self.evidence = evidence


class _Spec:
    def __init__(self, rules: list[_Rule]) -> None:
        self.rules = rules


def test_dashboard_alignment_gap_and_partial() -> None:
    from aml_framework.dashboard.frameworks import build_amla_rts_alignment

    # r_cdd cites the CDD RTS but carries NO evidence -> partial; the other
    # two RTS articles are uncited -> gap.
    spec = _Spec([_Rule("r_cdd", ["AMLR Art. 28(1)"], evidence=[])])
    rows = build_amla_rts_alignment(spec)
    statuses = {row["name"]: row["status"] for row in rows}
    assert statuses["AMLR Art. 28(1)"] == "partial"
    assert statuses["AMLR Art. 19(9)"] == "gap"
    assert statuses["AMLD6 Art. 53(10)"] == "gap"


# --- CLI -------------------------------------------------------------------


def _make_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run-test"
    (run_dir / "cases").mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"as_of": AS_OF.isoformat()}), encoding="utf-8"
    )
    for case in _CASES:
        (run_dir / "cases" / f"{case['case_id']}.json").write_text(
            json.dumps(case), encoding="utf-8"
        )
    (run_dir / "decisions.jsonl").write_text(
        "\n".join(json.dumps(d) for d in _DECISIONS) + "\n", encoding="utf-8"
    )
    return run_dir


def test_cli_writes_json_and_markdown(runner: CliRunner, tmp_path: Path) -> None:
    run_dir = _make_run_dir(tmp_path)
    md_path = tmp_path / "report.md"
    result = runner.invoke(
        app,
        ["amla-effectiveness-report", str(EU_SPEC), str(run_dir), "--markdown", str(md_path)],
    )
    assert result.exit_code == 0, result.output
    json_path = run_dir / "amla_effectiveness_report.json"
    assert json_path.exists()
    payload = json.loads(json_path.read_text())
    assert payload["spec_program"] == "eu_bank_aml"
    assert payload["generated_at"] == AS_OF.isoformat()
    assert payload["str_acceptance_status"] == "not_tracked"
    assert payload["n_rts_covered"] == 3
    assert md_path.exists()
    assert "AMLA RTS citation coverage" in md_path.read_text()


def test_cli_missing_manifest_exits(runner: CliRunner, tmp_path: Path) -> None:
    run_dir = tmp_path / "empty-run"
    run_dir.mkdir()
    result = runner.invoke(app, ["amla-effectiveness-report", str(EU_SPEC), str(run_dir)])
    assert result.exit_code == 1


# --- Spec validity ---------------------------------------------------------


def test_eu_bank_spec_validates_with_amla_citations() -> None:
    from aml_framework.spec import load_spec

    spec = load_spec(EU_SPEC)
    citations = {ref.citation for rule in spec.rules for ref in rule.regulation_refs}
    assert "AMLR Art. 28(1)" in citations
    assert "AMLR Art. 19(9)" in citations
    assert "AMLD6 Art. 53(10)" in citations


def test_eu_bank_amla_citations_resolvable() -> None:
    from aml_framework.compliance.regwatch import citation_url

    for c in ("AMLR Art. 28(1)", "AMLR Art. 19(9)", "AMLD6 Art. 53(10)"):
        assert citation_url(c) is not None
