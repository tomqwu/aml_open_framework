"""Generate auditor-facing control matrix from the spec."""

from __future__ import annotations

from aml_framework.spec.models import AMLSpec


def render_control_matrix(spec: AMLSpec) -> str:
    """One-page markdown table: rule → regulation → owner → severity."""
    lines: list[str] = [
        f"# Control Matrix — {spec.program.name}",
        "",
        f"- **Jurisdiction:** {spec.program.jurisdiction}",
        f"- **Regulator:** {spec.program.regulator}",
        f"- **Program owner:** {spec.program.owner}",
        f"- **Effective date:** {spec.program.effective_date.isoformat()}",
        "",
        "| Rule ID | Name | Severity | Status | Regulation(s) | Escalates to |",
        "|---|---|---|---|---|---|",
    ]
    for rule in spec.rules:
        refs = "; ".join(f"`{r.citation}`" for r in rule.regulation_refs)
        lines.append(
            f"| `{rule.id}` | {rule.name} | {rule.severity} | {rule.status} "
            f"| {refs} | `{rule.escalate_to}` |"
        )

    lines += ["", "## Reviewer queues", "", "| Queue | SLA | Next | Regulator form |",
              "|---|---|---|---|"]
    for q in spec.workflow.queues:
        nxt = ", ".join(f"`{n}`" for n in q.next) if q.next else "—"
        form = f"`{q.regulator_form}`" if q.regulator_form else "—"
        lines.append(f"| `{q.id}` | {q.sla} | {nxt} | {form} |")

    lines.append("")
    return "\n".join(lines)
