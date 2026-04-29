"""Fraud–AML case linkage — find customers reviewed by both teams.

The process problem this solves
-------------------------------
At most banks the fraud team and the financial-crime (AML) team operate
two separate case management systems. The same customer can be under
investigation in both at the same time, with neither analyst aware of
the other's evidence. Two teams write two narratives, the customer
gets two contradictory letters, and the regulator finds duplicate or
conflicting STRs.

The fix is **not** "merge the two teams" — that's a re-org. The fix is
to make it cheap to detect the overlap so each analyst sees the other
side's open cases on the customer they're working.

This module is pure-function over the case list `engine.runner` already
produces, plus the spec (so we know which rules are fraud-domain vs
AML-domain). It returns a per-customer record that the Investigations
dashboard surfaces as a "⚠️ Linked across domains" panel.

How a case's domain is decided
------------------------------
1. If the rule that produced the case carries `aml_priority == "fraud"`,
   the case is fraud-domain.
2. Otherwise, if the rule's id contains "fraud" or "app_fraud" or
   matches a heuristic, the case is fraud-domain (covers specs that
   haven't backfilled `aml_priority` yet).
3. Otherwise, the case is AML-domain.

A linkage record is only emitted when a single customer has at least
one case in **each** domain — that's the only condition that creates
the parallel-investigation problem.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from aml_framework.spec.models import AMLSpec, Rule

Domain = Literal["fraud", "aml"]

# Rule-id substrings that strongly suggest a fraud-domain rule even
# when `aml_priority` isn't set. Conservative on purpose — false
# positives here would over-flag links and erode signal value.
_FRAUD_RULE_HINTS = ("app_fraud", "scam", "push_fraud", "rtp_fraud", "card_fraud")


@dataclass(frozen=True)
class LinkedCustomer:
    """One customer with cases under both fraud and AML investigation."""

    customer_id: str
    fraud_case_ids: list[str] = field(default_factory=list)
    aml_case_ids: list[str] = field(default_factory=list)
    fraud_rule_ids: list[str] = field(default_factory=list)
    aml_rule_ids: list[str] = field(default_factory=list)
    severity: str = "low"  # max across all linked cases

    @property
    def total_case_count(self) -> int:
        return len(self.fraud_case_ids) + len(self.aml_case_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "fraud_case_ids": list(self.fraud_case_ids),
            "aml_case_ids": list(self.aml_case_ids),
            "fraud_rule_ids": list(self.fraud_rule_ids),
            "aml_rule_ids": list(self.aml_rule_ids),
            "severity": self.severity,
            "total_case_count": self.total_case_count,
        }


# ---------------------------------------------------------------------------
# Domain classification
# ---------------------------------------------------------------------------


def _rule_is_fraud(rule: Rule) -> bool:
    if getattr(rule, "aml_priority", None) == "fraud":
        return True
    rid = rule.id.lower()
    return any(hint in rid for hint in _FRAUD_RULE_HINTS)


def classify_rule_domain(rule: Rule) -> Domain:
    """Decide whether a rule's cases are fraud-domain or AML-domain.

    Public so dashboard pages can render a domain badge on individual
    rules without re-implementing the logic.
    """
    return "fraud" if _rule_is_fraud(rule) else "aml"


def build_rule_domain_map(spec: AMLSpec) -> dict[str, Domain]:
    return {rule.id: classify_rule_domain(rule) for rule in spec.rules}


# ---------------------------------------------------------------------------
# Severity helpers (mirror cases/aggregator's ordering)
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _max_severity(cases: Iterable[dict[str, Any]]) -> str:
    best_rank = -1
    best = "low"
    for c in cases:
        sev = (c.get("severity") or "low").lower()
        rank = _SEVERITY_ORDER.get(sev, 0)
        if rank > best_rank:
            best_rank = rank
            best = sev
    return best


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_linked_customers(
    cases: list[dict[str, Any]],
    spec: AMLSpec,
) -> list[LinkedCustomer]:
    """Return customers with cases in both fraud and AML domains.

    Customers with cases in only one domain are intentionally omitted —
    they are not the parallel-investigation problem. The output is
    sorted (highest severity first, then case count, then customer_id)
    so dashboard renderers don't have to.
    """
    domain_map = build_rule_domain_map(spec)

    fraud_by_cust: dict[str, list[dict[str, Any]]] = defaultdict(list)
    aml_by_cust: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for case in cases:
        cid = case.get("customer_id") or (case.get("alert") or {}).get("customer_id")
        if not cid:
            continue
        rule_id = case.get("rule_id") or (case.get("alert") or {}).get("rule_id")
        if not rule_id:
            continue
        domain = domain_map.get(rule_id, "aml")
        if domain == "fraud":
            fraud_by_cust[cid].append(case)
        else:
            aml_by_cust[cid].append(case)

    linked: list[LinkedCustomer] = []
    for cid in sorted(set(fraud_by_cust) & set(aml_by_cust)):
        fc = fraud_by_cust[cid]
        ac = aml_by_cust[cid]
        linked.append(
            LinkedCustomer(
                customer_id=cid,
                fraud_case_ids=sorted({c.get("case_id", "") for c in fc if c.get("case_id")}),
                aml_case_ids=sorted({c.get("case_id", "") for c in ac if c.get("case_id")}),
                fraud_rule_ids=sorted({c.get("rule_id", "") for c in fc if c.get("rule_id")}),
                aml_rule_ids=sorted({c.get("rule_id", "") for c in ac if c.get("rule_id")}),
                severity=_max_severity(fc + ac),
            )
        )

    linked.sort(
        key=lambda lc: (
            -_SEVERITY_ORDER.get(lc.severity, 0),
            -lc.total_case_count,
            lc.customer_id,
        )
    )
    return linked


def linkage_summary(linked: list[LinkedCustomer]) -> dict[str, Any]:
    """One-line summary suitable for a dashboard KPI panel."""
    return {
        "linked_customer_count": len(linked),
        "total_linked_cases": sum(lc.total_case_count for lc in linked),
        "highest_severity": linked[0].severity if linked else "none",
    }
