from __future__ import annotations

from pathlib import Path

from aml_framework.generators.board_pdf import _build_fallback_pdf, generate_board_pdf
from aml_framework.spec import load_spec


SPEC_PATH = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"


def test_board_pdf_falls_back_to_valid_minimal_pdf(monkeypatch):
    import aml_framework.generators.board_pdf as board_pdf

    spec = load_spec(SPEC_PATH)
    metrics = [{"id": "precision", "name": "Precision", "value": 0.91, "rag": "green"}]
    cases = [{"case_id": "CASE-1", "status": "open", "severity": "high"}]
    monkeypatch.setattr(
        board_pdf,
        "_build_reportlab_pdf",
        lambda *args, **kwargs: (_ for _ in ()).throw(ImportError("reportlab")),
    )

    pdf = generate_board_pdf(spec, metrics, cases)

    assert pdf.startswith(b"%PDF-1.4")
    assert b"AML Program Status Report" in pdf
    assert b"Precision" in pdf


def test_fallback_pdf_handles_empty_metrics_and_cases():
    spec = load_spec(SPEC_PATH)

    pdf = _build_fallback_pdf(spec, [], [])

    assert pdf.startswith(b"%PDF-1.4")
    assert b"Total Cases: 0" in pdf
    assert b"Metrics: 0" in pdf
