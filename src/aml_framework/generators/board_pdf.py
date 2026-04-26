"""Board presentation PDF — executive summary for senior leadership."""

from __future__ import annotations

import io
from typing import Any

from aml_framework.spec.models import AMLSpec


def generate_board_pdf(
    spec: AMLSpec,
    metrics: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    maturity_scores: list[dict[str, Any]] | None = None,
) -> bytes:
    """Generate a board-ready PDF summarizing the AML program status.

    Returns raw PDF bytes suitable for download or attachment.
    Falls back to a text-based PDF if reportlab is not installed.
    """
    try:
        return _build_reportlab_pdf(spec, metrics, cases, maturity_scores)
    except ImportError:
        return _build_fallback_pdf(spec, metrics, cases)


def _build_reportlab_pdf(
    spec: AMLSpec,
    metrics: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    maturity_scores: list[dict[str, Any]] | None = None,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    elements: list = []

    # Custom styles.
    title_style = ParagraphStyle(
        "BoardTitle",
        parent=styles["Title"],
        fontSize=20,
        spaceAfter=6,
    )
    heading_style = ParagraphStyle(
        "BoardHeading",
        parent=styles["Heading2"],
        fontSize=14,
        spaceBefore=18,
        spaceAfter=8,
        textColor=colors.HexColor("#1e293b"),
    )
    body_style = ParagraphStyle(
        "BoardBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
    )
    small_style = ParagraphStyle(
        "BoardSmall",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#64748b"),
    )

    # --- Title ---
    elements.append(Paragraph(f"{spec.program.name}", title_style))
    elements.append(
        Paragraph(
            f"AML Program Status Report &mdash; {spec.program.jurisdiction} / {spec.program.regulator}",
            small_style,
        )
    )
    elements.append(Spacer(1, 20))

    # --- Program overview ---
    elements.append(Paragraph("Program Overview", heading_style))
    overview_data = [
        ["Program", spec.program.name],
        ["Jurisdiction", spec.program.jurisdiction],
        ["Regulator", spec.program.regulator],
        ["Program Owner", spec.program.owner.replace("_", " ").title()],
        ["Active Rules", str(len([r for r in spec.rules if r.status == "active"]))],
        ["Workflow Queues", str(len(spec.workflow.queues))],
        ["Data Contracts", str(len(spec.data_contracts))],
    ]
    t = Table(overview_data, colWidths=[2 * inch, 4.5 * inch])
    t.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ]
        )
    )
    elements.append(t)
    elements.append(Spacer(1, 16))

    # --- Key Metrics ---
    elements.append(Paragraph("Key Metrics", heading_style))
    if metrics:
        metric_header = ["Metric", "Value", "RAG", "Category"]
        metric_rows = [metric_header]
        for m in metrics:
            rag = m.get("rag", "unset").upper()
            metric_rows.append(
                [
                    m.get("name", m.get("id", "")),
                    str(m.get("value", "")),
                    rag,
                    m.get("category", ""),
                ]
            )

        t = Table(metric_rows, colWidths=[2.5 * inch, 1.2 * inch, 1 * inch, 1.8 * inch])
        rag_colors = {
            "GREEN": colors.HexColor("#dcfce7"),
            "AMBER": colors.HexColor("#fef3c7"),
            "RED": colors.HexColor("#fecaca"),
        }
        style_cmds = [
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("GRID", (0, 0), (-1, 0), 0.5, colors.HexColor("#cbd5e1")),
        ]
        # Color-code RAG cells.
        for i, row in enumerate(metric_rows[1:], start=1):
            bg = rag_colors.get(row[2])
            if bg:
                style_cmds.append(("BACKGROUND", (2, i), (2, i), bg))
        t.setStyle(TableStyle(style_cmds))
        elements.append(t)
    else:
        elements.append(Paragraph("No metrics available.", body_style))

    elements.append(Spacer(1, 16))

    # --- Case summary ---
    elements.append(Paragraph("Case Summary", heading_style))
    if cases:
        total = len(cases)
        open_count = sum(1 for c in cases if c.get("status") == "open")
        resolved = total - open_count
        high_sev = sum(1 for c in cases if c.get("severity") in ("high", "critical"))

        case_summary = [
            ["Total Cases", str(total)],
            ["Open", str(open_count)],
            ["Resolved", str(resolved)],
            ["High/Critical Severity", str(high_sev)],
        ]
        t = Table(case_summary, colWidths=[3 * inch, 3.5 * inch])
        t.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ]
            )
        )
        elements.append(t)
    else:
        elements.append(Paragraph("No cases in this run.", body_style))

    elements.append(Spacer(1, 16))

    # --- Maturity scores ---
    if maturity_scores:
        elements.append(Paragraph("Program Maturity Assessment", heading_style))
        mat_header = ["Dimension", "Current", "Target", "Gap"]
        mat_rows = [mat_header]
        for dim in maturity_scores:
            current = dim.get("current", 0)
            target = dim.get("target", 0)
            gap = target - current
            gap_str = f"-{gap}" if gap > 0 else "On target"
            mat_rows.append([dim["name"], str(current), str(target), gap_str])

        t = Table(mat_rows, colWidths=[2.5 * inch, 1 * inch, 1 * inch, 2 * inch])
        style_cmds = [
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ]
        # Highlight gaps.
        for i, row in enumerate(mat_rows[1:], start=1):
            if row[3] != "On target":
                style_cmds.append(("TEXTCOLOR", (3, i), (3, i), colors.HexColor("#dc2626")))
        t.setStyle(TableStyle(style_cmds))
        elements.append(t)

    # --- Footer ---
    elements.append(Spacer(1, 30))
    elements.append(
        Paragraph(
            "Generated by AML Open Framework &mdash; spec-driven compliance automation",
            small_style,
        )
    )

    doc.build(elements)
    return buf.getvalue()


def _build_fallback_pdf(
    spec: AMLSpec,
    metrics: list[dict[str, Any]],
    cases: list[dict[str, Any]],
) -> bytes:
    """Minimal text-based PDF when reportlab is not available."""
    lines = [
        f"AML Program Status Report — {spec.program.name}",
        f"Jurisdiction: {spec.program.jurisdiction} / {spec.program.regulator}",
        f"Owner: {spec.program.owner}",
        "",
        f"Active Rules: {len([r for r in spec.rules if r.status == 'active'])}",
        f"Total Cases: {len(cases)}",
        f"Metrics: {len(metrics)}",
        "",
    ]
    for m in metrics:
        lines.append(f"  {m.get('name', m.get('id'))}: {m.get('value')} [{m.get('rag', 'unset')}]")

    # Build a minimal valid PDF.
    text = "\n".join(lines)
    content = "1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    content += "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    content += "3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    stream = f"BT /F1 10 Tf 72 720 Td ({text[:500]}) Tj ET"
    content += f"4 0 obj<</Length {len(stream)}>>stream\n{stream}\nendstream\nendobj\n"
    content += "5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Courier>>endobj\n"
    xref_offset = len(content) + 15
    pdf = f"%PDF-1.4\n{content}xref\n0 6\ntrailer<</Size 6/Root 1 0 R>>\nstartxref\n{xref_offset}\n%%EOF"
    return pdf.encode("latin-1")
