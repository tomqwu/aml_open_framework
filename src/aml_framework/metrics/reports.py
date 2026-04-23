"""Render per-audience markdown reports from evaluated metrics.

A report picks metrics by id and arranges them into sections. Each audience
level (SVP → developer) gets a view tuned to the decisions it actually makes:
executives see outcomes and RAG; developers see operational health numbers.
"""

from __future__ import annotations

from aml_framework.metrics.engine import MetricResult
from aml_framework.spec.models import AMLSpec, Report

_RAG_ICON = {"green": "🟢", "amber": "🟡", "red": "🔴", "unset": "⚪"}


def _fmt_value(r: MetricResult) -> str:
    if r.unit == "%":
        return f"{r.value * 100:.1f}%"
    if r.unit in ("usd", "USD"):
        return f"${r.value:,.0f}"
    if isinstance(r.value, float) and not r.value.is_integer():
        return f"{r.value:.3f}"
    return f"{int(r.value)}" if float(r.value).is_integer() else f"{r.value}"


def _target_str(r: MetricResult) -> str:
    if r.target_met is None:
        return "—"
    return "on target" if r.target_met else "off target"


def render_report(
    spec: AMLSpec,
    report: Report,
    results: list[MetricResult],
) -> str:
    by_id = {r.id: r for r in results}
    title = report.title or f"{report.audience.upper()} {report.cadence} report"

    lines: list[str] = [
        f"# {title}",
        "",
        f"**Program:** {spec.program.name}  ",
        f"**Jurisdiction / Regulator:** {spec.program.jurisdiction} / {spec.program.regulator}  ",
        f"**Audience:** {report.audience}  ",
        f"**Cadence:** {report.cadence}  ",
        "",
    ]

    overall = _overall_rag([by_id[m] for s in report.sections for m in s.metrics if m in by_id])
    lines.append(f"## Overall status: {_RAG_ICON[overall]} {overall.upper()}")
    lines.append("")

    for section in report.sections:
        lines.append(f"## {section.title}")
        lines.append("")
        if section.commentary:
            lines.append(section.commentary)
            lines.append("")
        lines.append("| RAG | Metric | Value | Target | Owner |")
        lines.append("|---|---|---|---|---|")
        for m_id in section.metrics:
            r = by_id.get(m_id)
            if r is None:
                lines.append(f"| ⚪ | _{m_id} (missing)_ | — | — | — |")
                continue
            lines.append(
                f"| {_RAG_ICON[r.rag]} | **{r.name}** "
                f"| {_fmt_value(r)} "
                f"| {_target_str(r)} "
                f"| {r.owner or '—'} |"
            )
        lines.append("")
    return "\n".join(lines)


def _overall_rag(results: list[MetricResult]) -> str:
    if any(r.rag == "red" for r in results):
        return "red"
    if any(r.rag == "amber" for r in results):
        return "amber"
    if any(r.rag == "green" for r in results):
        return "green"
    return "unset"


def render_all_reports(spec: AMLSpec, results: list[MetricResult]) -> dict[str, str]:
    """Return {report_id: markdown} for every report in the spec."""
    return {report.id: render_report(spec, report, results) for report in spec.reports}
