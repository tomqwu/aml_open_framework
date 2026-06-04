from __future__ import annotations

from aml_framework.dashboard.golden_thread import (
    PANEL_ALERT,
    PANEL_AUDIT,
    PANEL_CASE,
    PANEL_DOORS,
    PANEL_EMPTY,
    build_beats,
    pick_hero_alert,
)

_AUDIT = {"decisions_hash": "abc123", "reproducible": True}


def _alert(cid, rule_id="structuring_cash", sev="high", amount=95000, count=12, score=0.8):
    return {
        "customer_id": cid,
        "rule_id": rule_id,
        "severity": sev,
        "sum_amount": amount,
        "count": count,
        "priority_score": score,
    }


def _case(cid, rule_id="structuring_cash"):
    return {
        "case_id": f"{rule_id}__{cid}",
        "customer_id": cid,
        "rule_id": rule_id,
        "status": "open",
    }


def test_prefers_planted_c0001():
    alerts = [_alert("C0040", score=0.99), _alert("C0001", score=0.3)]
    hero = pick_hero_alert(alerts)
    assert hero["customer_id"] == "C0001"


def test_falls_back_to_highest_priority_when_no_c0001():
    alerts = [_alert("C0040", score=0.4), _alert("C0050", score=0.9)]
    hero = pick_hero_alert(alerts)
    assert hero["customer_id"] == "C0050"


def test_falls_back_to_first_alert_when_no_scores():
    alerts = [_alert("C0040", score=None), _alert("C0050", score=None)]
    hero = pick_hero_alert(alerts)
    assert hero["customer_id"] == "C0040"


def test_pick_hero_none_when_no_alerts():
    assert pick_hero_alert([]) is None


def test_build_beats_four_beats_with_real_payloads():
    alerts = [_alert("C0001")]
    cases = [_case("C0001")]
    beats = build_beats(alerts, cases, _AUDIT)
    kinds = [b["panel_kind"] for b in beats]
    assert kinds == [PANEL_ALERT, PANEL_CASE, PANEL_AUDIT, PANEL_DOORS]
    assert beats[0]["payload"]["customer_id"] == "C0001"
    assert beats[1]["payload"]["case_id"] == "structuring_cash__C0001"
    assert beats[2]["payload"]["decisions_hash"] == "abc123"
    assert all(b["title"] and b["narration"] for b in beats)


def test_build_beats_case_beat_tolerates_missing_case():
    beats = build_beats([_alert("C0001")], [], _AUDIT)
    assert beats[1]["panel_kind"] == PANEL_CASE
    assert beats[1]["payload"] == {}
    assert beats[1]["narration"]


def test_build_beats_empty_run_yields_friendly_single_beat():
    beats = build_beats([], [], _AUDIT)
    assert len(beats) == 1
    assert beats[0]["panel_kind"] == PANEL_EMPTY
    assert "no alerts" in beats[0]["narration"].lower()


def test_build_beats_is_deterministic():
    a = build_beats([_alert("C0001"), _alert("C0001", rule_id="other")], [_case("C0001")], _AUDIT)
    b = build_beats([_alert("C0001"), _alert("C0001", rule_id="other")], [_case("C0001")], _AUDIT)
    assert a == b


def test_case_beat_uses_any_matching_customer_when_rule_differs():
    beats = build_beats(
        [_alert("C0001", rule_id="layering")], [_case("C0001", rule_id="other_rule")], _AUDIT
    )
    assert beats[1]["payload"]["customer_id"] == "C0001"
    assert beats[1]["payload"]["rule_id"] == "other_rule"


def test_non_planted_hero_gets_generic_narration():
    beats = build_beats([_alert("C0050", rule_id="layering")], [], _AUDIT)
    assert "structuring" not in beats[0]["narration"].lower()


def test_c0001_with_non_structuring_rule_gets_generic_narration():
    beats = build_beats([_alert("C0001", rule_id="wire_to_high_risk")], [], _AUDIT)
    assert "structuring" not in beats[0]["narration"].lower()
