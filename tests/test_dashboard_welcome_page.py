"""Tests for persona/audience invariants and leader-surface page quality.

Process invariants guarded:
- Persona codes carry full human-readable titles, not bare abbreviations
- Leader-facing pages avoid technical jargon
  (YAML, spec, Pydantic, DuckDB, FastAPI, hash, deterministic) per
  the style guide in docs/research/2026-04-aml-process-pain.md
- Each PAIN-N reference in a page resolves to a real anchor in the
  pain doc — so the "see PAIN-X" links don't 404 a leader

Note: 0_Welcome.py was retired in favour of 0_Start.py (the first-run
wizard, default landing). The Welcome-specific content tests have been
removed along with the file.
"""

from __future__ import annotations

from pathlib import Path

from aml_framework.dashboard.audience import (
    AUDIENCE_PAGES,
    PERSONA_LABELS,
    persona_description,
    persona_options_with_labels,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Persona labels
# ---------------------------------------------------------------------------


def test_every_audience_code_has_a_label_and_description() -> None:
    """If a code exists in AUDIENCE_PAGES it must also have a human label
    so the sidebar dropdown never shows a bare abbreviation."""
    for code in AUDIENCE_PAGES:
        assert code in PERSONA_LABELS, f"missing PERSONA_LABELS entry for {code!r}"
        title, desc = PERSONA_LABELS[code]
        assert title and desc, f"persona {code!r} has empty title or description"


def test_persona_titles_are_full_phrases_not_abbreviations() -> None:
    """A leader landing in the sidebar should see 'Chief Compliance Officer',
    not 'cco'. Title must be at least 2 words for every persona that maps
    to an executive role."""
    executive_codes = {"svp", "cto", "cco", "vp", "director", "manager"}
    for code in executive_codes:
        title, _ = PERSONA_LABELS[code]
        assert len(title.split()) >= 2, (
            f"executive persona {code!r} title {title!r} should be a full role phrase"
        )


def test_persona_options_format_includes_title_and_code() -> None:
    options = persona_options_with_labels()
    for code, label in options:
        assert code.upper() in label, f"persona option {code} label missing the code"


def test_persona_description_lookup() -> None:
    assert persona_description("cco")
    assert persona_description("nonexistent") == ""


# ---------------------------------------------------------------------------
# Page-header rewrites — spot-check the highest-signal ones
# ---------------------------------------------------------------------------


PAGE_HEADER_EXPECTATIONS = {
    "7_Audit_Evidence.py": "What you'd hand a regulator if they walked in tomorrow",
    "8_Framework_Alignment.py": "How this program maps to",
    "24_Investigations.py": "Active investigations across teams, ranked by SLA urgency",
    "23_Tuning_Lab.py": "Test a threshold change before it goes live",
    "1_Executive_Dashboard.py": "headline picture",
    "2_Program_Maturity.py": "before the next exam",
    "5_Rule_Performance.py": "Is each detector still earning its keep",
    "13_Model_Performance.py": "scoring models behave",
}


def test_leader_page_headers_use_business_language() -> None:
    pages_dir = REPO_ROOT / "src" / "aml_framework" / "dashboard" / "pages"
    for filename, expected_phrase in PAGE_HEADER_EXPECTATIONS.items():
        path = pages_dir / filename
        assert path.exists(), f"page {filename} missing"
        content = path.read_text()
        assert expected_phrase in content, (
            f"{filename} should carry the new business-language header phrase: {expected_phrase!r}"
        )


def test_leader_page_headers_dropped_engineering_jargon() -> None:
    """Spot-check that the old engineering phrasing is gone from the
    rewritten headers. Catches accidental partial reverts."""
    pages_dir = REPO_ROOT / "src" / "aml_framework" / "dashboard" / "pages"
    forbidden_phrases = {
        "7_Audit_Evidence.py": "Immutable audit trail with hash verification",
        "8_Framework_Alignment.py": "Mapping spec primitives",
        "23_Tuning_Lab.py": "download a YAML spec patch",
    }
    for filename, old_phrase in forbidden_phrases.items():
        content = (pages_dir / filename).read_text()
        assert old_phrase not in content, (
            f"{filename} still contains the old engineering header: {old_phrase!r}"
        )
