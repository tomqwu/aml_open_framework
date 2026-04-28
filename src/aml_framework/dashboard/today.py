"""Per-persona "Today" landing card builder.

Pure-python helper — no streamlit import at module level so this file
runs on the unit-test CI image. The Today page (`pages/0_Today.py`)
calls `build_cards_for_audience()` passing live session state, then
renders the resulting cards via `kpi_card_rag` + `link_to_page`.

Design notes
------------

The "Today" page is the per-persona priorities surface flagged in the
huashu-design dashboard review (PR 3 of 5). The pre-PR-3 default
landing was Executive Dashboard for everyone — noisy and identical
across all 11 personas. This module gives each persona 3 cards built
from real run state (spec / RunResult / alerts dataframe), each one
linking to the destination page where the user can act on the signal.

The card count is fixed at 3 — fewer than that and "Today" feels
empty; more and it competes with the destination pages instead of
just routing into them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TodayCard:
    """One priority card on the Today landing.

    Attributes:
        label: KPI-card label (uppercase rendering handled by CSS).
        value: Headline value (string so the helper can pre-format
            "$1,234" / "78%" / "—" without the page guessing).
        hint: One-line context shown under the value, e.g.
            "across 7 rules" or "cases past deadline".
        rag: ``"green"`` / ``"amber"`` / ``"red"`` / ``"breached"`` /
            ``None``. Drives the kpi_card_rag border color. ``None``
            means "this is a fact, not an assessment".
        cta: Link text rendered below the card.
        target_page: Streamlit page path the cta links to (relative to
            the dashboard module — e.g. ``"pages/3_Alert_Queue.py"``).
    """

    label: str
    value: str
    hint: str
    rag: str | None
    cta: str
    target_page: str


def _count_high_severity_alerts(spec: Any, df_alerts: Any) -> int:
    """Count alerts whose rule severity is high/critical."""
    if df_alerts is None or len(df_alerts) == 0:
        return 0
    sev_map = {r.id: r.severity for r in spec.rules}
    return int(
        sum(
            1
            for _, row in df_alerts.iterrows()
            if sev_map.get(row["rule_id"]) in ("high", "critical")
        )
    )


def _typology_metric(result: Any) -> Any | None:
    return next((m for m in result.metrics if m.id == "typology_coverage"), None)


def _rag_count(result: Any, band: str) -> int:
    return sum(1 for m in result.metrics if m.rag == band)


def _open_findings_count(spec: Any) -> int:
    raw = getattr(spec, "open_findings", None)
    if raw is None:
        return 0
    return len(raw) if hasattr(raw, "__len__") else 0


def _sla_breach_count(df_cases: Any) -> int:
    if df_cases is None or len(df_cases) == 0:
        return 0
    if "sla_state" not in df_cases.columns:
        return 0
    return int((df_cases["sla_state"] == "breached").sum())


# ---------------------------------------------------------------------------
# Persona card builders
# ---------------------------------------------------------------------------


def _executive_cards(spec: Any, result: Any, df_alerts: Any) -> list[TodayCard]:
    """SVP / CTO / CCO / VP / Director / Business — strategic view."""
    red = _rag_count(result, "red")
    amber = _rag_count(result, "amber")
    green = _rag_count(result, "green")
    typ = _typology_metric(result)
    findings = _open_findings_count(spec)

    program_rag = "red" if red else "amber" if amber else "green" if green else None
    findings_rag = "red" if findings > 5 else "amber" if findings > 0 else "green"

    return [
        TodayCard(
            label="Program RAG",
            value=f"{green}G · {amber}A · {red}R",
            hint="metrics across all bands",
            rag=program_rag,
            cta="→ Executive Dashboard",
            target_page="pages/1_Executive_Dashboard.py",
        ),
        TodayCard(
            label="Typology Coverage",
            value=f"{typ.value * 100:.0f}%" if typ else "n/a",
            hint=(
                f"target {typ.target * 100:.0f}%"
                if typ and getattr(typ, "target", None)
                else "no target set"
            ),
            rag=typ.rag if typ else None,
            cta="→ Framework Alignment",
            target_page="pages/8_Framework_Alignment.py",
        ),
        TodayCard(
            label="Open findings",
            value=str(findings),
            hint="auditor remediation items",
            rag=findings_rag,
            cta="→ Audit & Evidence",
            target_page="pages/7_Audit_Evidence.py",
        ),
    ]


def _manager_cards(spec: Any, result: Any, df_alerts: Any, df_cases: Any) -> list[TodayCard]:
    """L1 supervisor — backlog, breaches, severity spikes."""
    queue_depth = len(result.case_ids)
    sla_breaches = _sla_breach_count(df_cases)
    high_sev = _count_high_severity_alerts(spec, df_alerts)

    queue_rag = "red" if queue_depth > 50 else "amber" if queue_depth > 20 else None
    breach_rag = "red" if sla_breaches > 0 else "green"
    high_rag = "red" if high_sev > 5 else "amber" if high_sev > 0 else None

    return [
        TodayCard(
            label="Queue backlog",
            value=str(queue_depth),
            hint="open cases across all queues",
            rag=queue_rag,
            cta="→ Investigations",
            target_page="pages/24_Investigations.py",
        ),
        TodayCard(
            label="SLA breaches",
            value=str(sla_breaches),
            hint="cases past their deadline",
            rag=breach_rag,
            cta="→ My Queue",
            target_page="pages/21_My_Queue.py",
        ),
        TodayCard(
            label="High / critical alerts",
            value=str(high_sev),
            hint="needing fast triage",
            rag=high_rag,
            cta="→ Alert Queue",
            target_page="pages/3_Alert_Queue.py",
        ),
    ]


def _analyst_cards(spec: Any, result: Any, df_alerts: Any, df_cases: Any) -> list[TodayCard]:
    """L1/L2 analyst — what's on my plate today."""
    open_cases = len(result.case_ids)
    sla_breaches = _sla_breach_count(df_cases)
    sanctions_alerts = 0
    if df_alerts is not None and len(df_alerts):
        sanctions_alerts = int((df_alerts["rule_id"] == "sanctions_screening").sum())

    return [
        TodayCard(
            label="Cases open",
            value=str(open_cases),
            hint="across analyst queues",
            rag=None,
            cta="→ My Queue",
            target_page="pages/21_My_Queue.py",
        ),
        TodayCard(
            label="SLA breaches",
            value=str(sla_breaches),
            hint="urgent — escalate or close",
            rag="red" if sla_breaches else "green",
            cta="→ Investigations",
            target_page="pages/24_Investigations.py",
        ),
        TodayCard(
            label="Sanctions matches",
            value=str(sanctions_alerts),
            hint="list-screening hits this run",
            rag="red" if sanctions_alerts else None,
            cta="→ Sanctions Screening",
            target_page="pages/12_Sanctions_Screening.py",
        ),
    ]


def _auditor_cards(spec: Any, result: Any) -> list[TodayCard]:
    """Internal/external auditor — evidence + chain integrity."""
    findings = _open_findings_count(spec)
    rules_hashed = (
        len(getattr(result, "rule_outputs", {}))
        if hasattr(result, "rule_outputs")
        else len(spec.rules)
    )

    return [
        TodayCard(
            label="Open findings",
            value=str(findings),
            hint="remediation items in spec",
            rag="red" if findings > 5 else "amber" if findings > 0 else "green",
            cta="→ Framework Alignment",
            target_page="pages/8_Framework_Alignment.py",
        ),
        TodayCard(
            label="Rules hashed",
            value=str(rules_hashed),
            hint="this run's audit ledger",
            rag=None,
            cta="→ Audit & Evidence",
            target_page="pages/7_Audit_Evidence.py",
        ),
        TodayCard(
            label="Cases with decisions",
            value=str(len(result.case_ids)),
            hint="reviewable evidence trail",
            rag=None,
            cta="→ Investigations",
            target_page="pages/24_Investigations.py",
        ),
    ]


def _developer_cards(spec: Any, result: Any) -> list[TodayCard]:
    """Spec author — what fired, what's silent, where to tune."""
    rules_active = sum(1 for r in spec.rules if r.status == "active")
    rules_fired = len({a for a in result.rule_alerts}) if hasattr(result, "rule_alerts") else 0
    rules_silent = max(rules_active - rules_fired, 0)

    return [
        TodayCard(
            label="Active rules",
            value=str(rules_active),
            hint=f"{rules_fired} fired this run",
            rag=None,
            cta="→ Rule Performance",
            target_page="pages/5_Rule_Performance.py",
        ),
        TodayCard(
            label="Silent rules",
            value=str(rules_silent),
            hint="active but produced no alerts",
            rag="amber" if rules_silent > 0 else "green",
            cta="→ Tuning Lab",
            target_page="pages/23_Tuning_Lab.py",
        ),
        TodayCard(
            label="Last run hash",
            value=getattr(result, "spec_hash", "—")[:8] if hasattr(result, "spec_hash") else "—",
            hint="reproducibility checkpoint",
            rag=None,
            cta="→ Audit & Evidence",
            target_page="pages/7_Audit_Evidence.py",
        ),
    ]


def _pm_cards(spec: Any, result: Any) -> list[TodayCard]:
    """Programme manager — roadmap + maturity gap."""
    findings = _open_findings_count(spec)
    typ = _typology_metric(result)
    return [
        TodayCard(
            label="Typology Coverage",
            value=f"{typ.value * 100:.0f}%" if typ else "n/a",
            hint=(
                f"target {typ.target * 100:.0f}%"
                if typ and getattr(typ, "target", None)
                else "no target set"
            ),
            rag=typ.rag if typ else None,
            cta="→ Program Maturity",
            target_page="pages/2_Program_Maturity.py",
        ),
        TodayCard(
            label="Open findings",
            value=str(findings),
            hint="remediation backlog",
            rag="red" if findings > 5 else "amber" if findings > 0 else "green",
            cta="→ Transformation Roadmap",
            target_page="pages/9_Transformation_Roadmap.py",
        ),
        TodayCard(
            label="Active rules",
            value=str(sum(1 for r in spec.rules if r.status == "active")),
            hint="of total spec rules",
            rag=None,
            cta="→ Rule Performance",
            target_page="pages/5_Rule_Performance.py",
        ),
    ]


def _generic_cards(spec: Any, result: Any, df_alerts: Any) -> list[TodayCard]:
    """Fallback for "all" or unknown audience."""
    red = _rag_count(result, "red")
    amber = _rag_count(result, "amber")
    queue_depth = len(result.case_ids)

    return [
        TodayCard(
            label="Open alerts",
            value=str(result.total_alerts),
            hint=f"across {df_alerts['rule_id'].nunique() if df_alerts is not None and len(df_alerts) else 0} rules",
            rag=None,
            cta="→ Triage queue",
            target_page="pages/3_Alert_Queue.py",
        ),
        TodayCard(
            label="RAG amber/red",
            value=str(amber + red),
            hint=f"{red} red · {amber} amber",
            rag="red" if red else "amber" if amber else "green",
            cta="→ See RAG grid",
            target_page="pages/1_Executive_Dashboard.py",
        ),
        TodayCard(
            label="Open cases",
            value=str(queue_depth),
            hint="awaiting reviewer",
            rag=None,
            cta="→ Investigations",
            target_page="pages/24_Investigations.py",
        ),
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_cards_for_audience(
    audience: str | None,
    spec: Any,
    result: Any,
    df_alerts: Any = None,
    df_cases: Any = None,
) -> list[TodayCard]:
    """Return 3 priority cards for the given audience.

    Args:
        audience: One of the keys in AUDIENCE_PAGES, or ``None`` /
            ``"all"`` for the generic fallback.
        spec: Loaded :class:`Spec`.
        result: :class:`RunResult` from the engine.
        df_alerts: Pandas DataFrame of alerts (may be empty).
        df_cases: Pandas DataFrame of cases (may be ``None`` if the
            page hasn't loaded the case state yet).

    Returns:
        Always 3 cards, ordered by priority. Audiences with no
        operational queue (e.g. SVP) get strategic cards; analyst /
        manager get operational ones.
    """
    if audience in ("svp", "cco", "vp", "director", "cto", "business"):
        return _executive_cards(spec, result, df_alerts)
    if audience == "manager":
        return _manager_cards(spec, result, df_alerts, df_cases)
    if audience == "analyst":
        return _analyst_cards(spec, result, df_alerts, df_cases)
    if audience == "auditor":
        return _auditor_cards(spec, result)
    if audience == "developer":
        return _developer_cards(spec, result)
    if audience == "pm":
        return _pm_cards(spec, result)
    return _generic_cards(spec, result, df_alerts)
