from __future__ import annotations

import pytest

from aml_framework.assistant.models import AssistantContext
from aml_framework.dashboard.case_copilot import (
    CASE_COPILOT_ACTIONS,
    build_case_copilot_context,
    case_copilot_prompt,
)


def test_actions_present():
    assert CASE_COPILOT_ACTIONS == ("summarize", "typology", "draft_narrative", "network", "risk")


@pytest.mark.parametrize("action", ["summarize", "typology", "draft_narrative", "network", "risk"])
def test_prompt_non_empty_per_action(action):
    p = case_copilot_prompt(action)
    assert isinstance(p, str) and len(p.strip()) > 10


def test_prompt_unknown_action_raises():
    with pytest.raises(ValueError):
        case_copilot_prompt("bogus")


def _case():
    return {
        "case_id": "CASE-1",
        "severity": "high",
        "queue": "l2",
        "status": "open",
        "rule_id": "R1",
        "rule_name": "Structuring",
        "alert": {"customer_id": "C1"},
    }


def _customer():
    return {"customer_id": "C1", "full_name": "Jane Doe", "country": "CA", "risk_rating": "high"}


def test_build_context_basic():
    ctx = build_case_copilot_context(
        page="Case Investigation",
        action="summarize",
        case=_case(),
        customer=_customer(),
        txns=[{"amount": 9000}, {"amount": 8000}],
        spec_name="P",
        spec_jurisdiction="CA",
        spec_regulator="FINTRAC",
        run_id="run-1",
    )
    assert isinstance(ctx, AssistantContext)
    assert ctx.selected_case_id == "CASE-1"
    assert ctx.section_id == "case_copilot.summarize"
    assert ctx.page == "Case Investigation"
    # case + customer + txn detail rides in section_data
    assert ctx.section_data["case_id"] == "CASE-1"
    assert ctx.section_data["txn_count"] == 2
    assert ctx.section_data.get("customer_risk_rating") == "high"


def test_build_context_tolerates_missing_customer_and_txns():
    ctx = build_case_copilot_context(
        page="Case Investigation",
        action="typology",
        case=_case(),
        customer=None,
        txns=[],
        spec_name="P",
        spec_jurisdiction="CA",
        spec_regulator="FINTRAC",
        run_id="run-1",
    )
    assert ctx.section_id == "case_copilot.typology"
    assert ctx.section_data["txn_count"] == 0


def test_build_context_deterministic():
    kw = dict(
        page="Case Investigation",
        action="risk",
        case=_case(),
        customer=_customer(),
        txns=[{"amount": 100}],
        spec_name="P",
        spec_jurisdiction="CA",
        spec_regulator="FINTRAC",
        run_id="run-1",
    )
    a = build_case_copilot_context(**kw)
    b = build_case_copilot_context(**kw)
    assert a.model_dump() == b.model_dump()


def test_section_data_is_json_safe():
    import json

    ctx = build_case_copilot_context(
        page="Case Investigation",
        action="network",
        case=_case(),
        customer=_customer(),
        txns=[{"amount": 100, "channel": "wire"}],
        spec_name="P",
        spec_jurisdiction="CA",
        spec_regulator="FINTRAC",
        run_id="run-1",
    )
    json.dumps(ctx.section_data)  # must not raise (no Decimal/datetime/DataFrame leaks)
