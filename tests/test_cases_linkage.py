"""Tests for `cases/linkage.py` — fraud↔AML case linkage.

Guards the parallel-investigation prevention story: a customer with
cases in both fraud and AML domains must be surfaced so neither
analyst writes their narrative blind to the other.
"""

from __future__ import annotations

from pathlib import Path


from aml_framework.cases.linkage import (
    LinkedCustomer,
    build_rule_domain_map,
    classify_rule_domain,
    find_linked_customers,
    linkage_summary,
)
from aml_framework.spec import load_spec

REPO_ROOT = Path(__file__).resolve().parent.parent


def _spec_with(rule_ids_to_priority: dict[str, str | None]) -> object:
    """Load a real spec and patch a couple of rules' aml_priority for tests.

    We can't construct a fake AMLSpec cheaply because of the frozen
    Pydantic models + cross-reference validation, so we mutate copies
    via `model_copy`.
    """
    spec = load_spec(REPO_ROOT / "examples" / "canadian_schedule_i_bank" / "aml.yaml")
    new_rules = []
    for r in spec.rules:
        if r.id in rule_ids_to_priority:
            new_rules.append(r.model_copy(update={"aml_priority": rule_ids_to_priority[r.id]}))
        else:
            new_rules.append(r)
    return spec.model_copy(update={"rules": new_rules})


# ---------------------------------------------------------------------------
# Domain classification
# ---------------------------------------------------------------------------


def test_classify_rule_with_fraud_priority_is_fraud_domain() -> None:
    spec = _spec_with({"structuring_cash_deposits": "fraud"})
    rule = next(r for r in spec.rules if r.id == "structuring_cash_deposits")
    assert classify_rule_domain(rule) == "fraud"


def test_classify_rule_with_no_priority_falls_back_to_id_heuristic() -> None:
    """Rules whose id contains a fraud hint count as fraud-domain even
    without aml_priority set. We exercise this with a real rule renamed
    in-memory to carry a hint substring, avoiding reliance on whatever
    naming convention any one example spec happens to use."""
    spec = _spec_with({})
    rule = next(r for r in spec.rules if r.id == "structuring_cash_deposits")
    renamed = rule.model_copy(update={"id": "rtp_fraud_structuring"})
    assert classify_rule_domain(renamed) == "fraud"


def test_classify_default_aml_when_no_signal() -> None:
    spec = _spec_with({})
    # Pick a rule that has neither aml_priority nor a fraud-hint id.
    rule = next(r for r in spec.rules if r.id == "high_risk_jurisdiction")
    assert classify_rule_domain(rule) == "aml"


def test_build_rule_domain_map_covers_every_rule() -> None:
    spec = _spec_with({})
    m = build_rule_domain_map(spec)
    assert set(m.keys()) == {r.id for r in spec.rules}
    assert all(v in ("fraud", "aml") for v in m.values())


# ---------------------------------------------------------------------------
# Linkage detection
# ---------------------------------------------------------------------------


def _case(customer_id: str, rule_id: str, case_id: str, severity: str = "medium") -> dict:
    return {
        "case_id": case_id,
        "customer_id": customer_id,
        "rule_id": rule_id,
        "severity": severity,
        "alert": {"customer_id": customer_id, "rule_id": rule_id},
    }


def test_customer_with_only_aml_cases_not_linked() -> None:
    spec = _spec_with({})
    cases = [
        _case("C0001", "high_risk_jurisdiction", "c1"),
        _case("C0001", "structuring_cash_deposits", "c2"),
    ]
    assert find_linked_customers(cases, spec) == []


def test_customer_with_only_fraud_cases_not_linked() -> None:
    spec = _spec_with({"structuring_cash_deposits": "fraud", "rapid_pass_through": "fraud"})
    cases = [
        _case("C0001", "structuring_cash_deposits", "c1"),
        _case("C0001", "rapid_pass_through", "c2"),
    ]
    assert find_linked_customers(cases, spec) == []


def test_customer_with_cases_in_both_domains_is_linked() -> None:
    spec = _spec_with({"structuring_cash_deposits": "fraud"})
    cases = [
        _case("C0001", "structuring_cash_deposits", "c1", severity="high"),  # fraud
        _case("C0001", "high_risk_jurisdiction", "c2", severity="medium"),  # aml
    ]
    linked = find_linked_customers(cases, spec)
    assert len(linked) == 1
    lc = linked[0]
    assert isinstance(lc, LinkedCustomer)
    assert lc.customer_id == "C0001"
    assert lc.fraud_case_ids == ["c1"]
    assert lc.aml_case_ids == ["c2"]
    assert lc.severity == "high"  # max across both
    assert lc.total_case_count == 2


def test_linked_output_sorted_by_severity_then_count() -> None:
    spec = _spec_with({"structuring_cash_deposits": "fraud"})
    cases = [
        _case("C0001", "structuring_cash_deposits", "f1", severity="medium"),
        _case("C0001", "high_risk_jurisdiction", "a1", severity="medium"),
        _case("C0002", "structuring_cash_deposits", "f2", severity="critical"),
        _case("C0002", "high_risk_jurisdiction", "a2", severity="low"),
    ]
    linked = find_linked_customers(cases, spec)
    # C0002 has critical severity → ranks first.
    assert [lc.customer_id for lc in linked] == ["C0002", "C0001"]


def test_cases_without_customer_id_are_skipped() -> None:
    spec = _spec_with({"structuring_cash_deposits": "fraud"})
    cases = [
        {"case_id": "c1", "rule_id": "structuring_cash_deposits", "alert": {}},
        _case("C0001", "high_risk_jurisdiction", "c2"),
    ]
    assert find_linked_customers(cases, spec) == []


def test_cases_without_rule_id_are_skipped() -> None:
    spec = _spec_with({"structuring_cash_deposits": "fraud"})
    cases = [
        {"case_id": "c1", "customer_id": "C0001", "severity": "high", "alert": {}},
        _case("C0001", "high_risk_jurisdiction", "c2"),
    ]
    assert find_linked_customers(cases, spec) == []


def test_linkage_is_deterministic() -> None:
    """Same case set + same spec → same linked output. Audit-friendly."""
    spec = _spec_with({"structuring_cash_deposits": "fraud"})
    cases = [
        _case("C0001", "structuring_cash_deposits", "c1"),
        _case("C0001", "high_risk_jurisdiction", "c2"),
    ]
    a = find_linked_customers(cases, spec)
    b = find_linked_customers(cases, spec)
    assert [lc.customer_id for lc in a] == [lc.customer_id for lc in b]
    assert [lc.fraud_case_ids for lc in a] == [lc.fraud_case_ids for lc in b]


def test_summary_for_empty_linked_list() -> None:
    s = linkage_summary([])
    assert s["linked_customer_count"] == 0
    assert s["total_linked_cases"] == 0
    assert s["highest_severity"] == "none"


def test_summary_aggregates_correctly() -> None:
    spec = _spec_with({"structuring_cash_deposits": "fraud"})
    cases = [
        _case("C0001", "structuring_cash_deposits", "f1", severity="high"),
        _case("C0001", "high_risk_jurisdiction", "a1", severity="medium"),
        _case("C0002", "structuring_cash_deposits", "f2", severity="critical"),
        _case("C0002", "high_risk_jurisdiction", "a2", severity="low"),
    ]
    linked = find_linked_customers(cases, spec)
    s = linkage_summary(linked)
    assert s["linked_customer_count"] == 2
    assert s["total_linked_cases"] == 4
    assert s["highest_severity"] == "critical"
