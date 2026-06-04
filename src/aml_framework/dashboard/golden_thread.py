"""Pure builder for the first-run Golden Thread (Streamlit-free, stdlib-only).

Selects ONE real planted example from the cached run and shapes it into four
narrated beats — alert -> case -> audit -> doors — that `pages/0_Start.py`
renders full-canvas. No pandas/streamlit import, so it unit-tests under the
`.[dev]`-only CI. Deterministic: same records in -> same beats out.
"""

from __future__ import annotations

from typing import Any

PANEL_ALERT = "alert"
PANEL_CASE = "case"
PANEL_AUDIT = "audit"
PANEL_DOORS = "doors"
PANEL_EMPTY = "empty"

# The canonical first-impression example: planted structuring positive.
_HERO_CUSTOMER = "C0001"


def _score(alert: dict[str, Any]) -> float:
    s = alert.get("priority_score")
    try:
        return float(s)
    except (TypeError, ValueError):
        return -1.0


def pick_hero_alert(alerts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the example alert: prefer the planted C0001 structuring case, else
    the highest priority_score, else the first alert, else None."""
    if not alerts:
        return None
    planted = [a for a in alerts if str(a.get("customer_id")) == _HERO_CUSTOMER]
    if planted:
        return sorted(planted, key=lambda a: str(a.get("rule_id", "")))[0]
    scored = [a for a in alerts if _score(a) >= 0.0]
    if scored:
        return max(scored, key=_score)
    return alerts[0]


def _case_for(cases: list[dict[str, Any]], alert: dict[str, Any]) -> dict[str, Any]:
    cid = str(alert.get("customer_id"))
    rid = str(alert.get("rule_id"))
    exact = [c for c in cases if str(c.get("customer_id")) == cid and str(c.get("rule_id")) == rid]
    if exact:
        return exact[0]
    any_cid = [c for c in cases if str(c.get("customer_id")) == cid]
    return any_cid[0] if any_cid else {}


def build_beats(
    alerts: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    audit: dict[str, Any],
) -> list[dict[str, Any]]:
    """Shape the four-beat Golden Thread from real run records. Falls back to a
    single friendly beat when the run produced no alerts."""
    hero = pick_hero_alert(alerts)
    if hero is None:
        return [
            {
                "title": "A clean run",
                "narration": (
                    "This program produced no alerts on the current data — every "
                    "rule ran and nothing crossed a threshold. Load a spec with "
                    "planted activity to watch the full alert → case → audit story."
                ),
                "panel_kind": PANEL_EMPTY,
                "payload": {},
            }
        ]
    case = _case_for(cases, hero)
    is_structuring = (
        str(hero.get("customer_id")) == _HERO_CUSTOMER
        and "structuring" in str(hero.get("rule_id", "")).lower()
    )
    alert_narration = (
        "A rule flagged a suspicious pattern — here, repeated cash deposits "
        "just under the reporting threshold. Classic structuring."
        if is_structuring
        else "A rule flagged a suspicious pattern that crossed a detection threshold."
    )
    return [
        {
            "title": "The engine caught this.",
            "narration": alert_narration,
            "panel_kind": PANEL_ALERT,
            "payload": hero,
        },
        {
            "title": "Here's the case your team works.",
            "narration": "Everything an investigator needs is already assembled — no hunting across eight tabs.",
            "panel_kind": PANEL_CASE,
            "payload": case,
        },
        {
            "title": "Here's what you hand the regulator.",
            "narration": "Every decision is recorded and replayable byte-for-byte. No six-week reconstruction.",
            "panel_kind": PANEL_AUDIT,
            "payload": dict(audit),
        },
        {
            "title": "Now it's yours.",
            "narration": "Pick the view for your role, or browse the full toolkit.",
            "panel_kind": PANEL_DOORS,
            "payload": {},
        },
    ]
