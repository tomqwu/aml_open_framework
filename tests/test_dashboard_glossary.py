"""Tests for the dashboard glossary tooltip helper.

The leader-friendliness invariant this guards: domain acronyms (STR,
SAR, OSFI, FINTRAC, MRM …) stay visible because regulators speak that
way, but every one carries a one-sentence plain-English definition on
hover. Adding a new term must remain a one-line change.
"""

from __future__ import annotations

import re

# Import from the standalone glossary module (no pandas/streamlit
# dependency) so this test runs on the unit-tests CI image where
# `.[dashboard]` extras aren't installed.
from aml_framework.dashboard.glossary import (
    GLOSSARY,
    glossary_legend,
    glossary_term,
)


# ---------------------------------------------------------------------------
# GLOSSARY dictionary contents
# ---------------------------------------------------------------------------


def test_glossary_covers_the_load_bearing_acronyms() -> None:
    """If a term shows up frequently in our leader-facing copy, it
    must have a definition. Catches a contributor adding 'BOI' to a
    page header without first putting it in the glossary."""
    must_cover = {
        "STR",
        "SAR",
        "KYC",
        "EDD",
        "CDD",
        "BOI",
        "MRM",
        "MLRO",
        "OSFI",
        "FINTRAC",
        "FinCEN",
        "FCA",
        "BSA",
        "PCMLTFA",
        "AMLA",
        "FATF",
        "1LoD",
        "2LoD",
        "3LoD",
    }
    missing = must_cover - set(GLOSSARY.keys())
    assert not missing, f"Glossary missing must-cover terms: {missing}"


def test_glossary_definitions_are_plain_english_one_sentence() -> None:
    """Each definition should be short — one sentence, no nested
    technical term un-defined. We approximate "one sentence" as
    "ends with a period and contains at most one period before the end"."""
    for term, defn in GLOSSARY.items():
        assert defn.endswith("."), f"{term}: definition should end with a period"
        # Allow one or two sentences; reject paragraphs.
        sentence_count = defn.count(".") + defn.count("!") + defn.count("?")
        assert sentence_count <= 2, (
            f"{term}: definition is too long ({sentence_count} sentences) — "
            "keep to one short sentence"
        )


# ---------------------------------------------------------------------------
# glossary_term helper — output shape
# ---------------------------------------------------------------------------


def test_glossary_term_known_acronym_wraps_with_title() -> None:
    html = glossary_term("STR")
    assert "<span" in html
    assert "title=" in html
    assert ">STR</span>" in html
    assert GLOSSARY["STR"][:30] in html  # definition is in the title attr


def test_glossary_term_unknown_falls_back_to_bare_term() -> None:
    """Unknown terms return the raw text, no HTML — so a typo like
    'STAR' renders as plain 'STAR' rather than crashing or producing
    a broken empty-tooltip span."""
    html = glossary_term("STAR_THAT_DOES_NOT_EXIST")
    assert html == "STAR_THAT_DOES_NOT_EXIST"


def test_glossary_term_case_insensitive_lookup() -> None:
    upper = glossary_term("STR")
    lower = glossary_term("str")
    # Same definition regardless of case in the input
    assert "Suspicious Transaction" in upper
    assert "Suspicious Transaction" in lower


def test_glossary_term_custom_definition_overrides() -> None:
    html = glossary_term("STR", custom_definition="Custom override sentence.")
    assert "Custom override sentence." in html
    # Built-in definition should not also be in the output
    assert GLOSSARY["STR"] not in html


def test_glossary_term_escapes_quotes_in_definitions() -> None:
    """A definition containing a double-quote must not break the HTML
    title attribute. Use a custom definition with a quote to test."""
    html = glossary_term("STR", custom_definition='Says "hello" loudly.')
    assert 'title="Says &quot;hello&quot; loudly."' in html


# ---------------------------------------------------------------------------
# glossary_legend helper
# ---------------------------------------------------------------------------


def test_glossary_legend_renders_each_known_term() -> None:
    html = glossary_legend(["STR", "MRM", "OSFI"])
    assert "STR" in html
    assert "MRM" in html
    assert "OSFI" in html
    # Each definition should appear too
    assert "Suspicious Transaction" in html
    assert "Model Risk Management" in html
    assert "Office of the Superintendent" in html


def test_glossary_legend_returns_empty_for_no_terms() -> None:
    assert glossary_legend(None) == ""
    assert glossary_legend([]) == ""


def test_glossary_legend_skips_unknown_terms_silently() -> None:
    html = glossary_legend(["STR", "DOES_NOT_EXIST"])
    assert "STR" in html
    assert "DOES_NOT_EXIST" not in html


def test_glossary_legend_renders_only_unknowns_to_empty() -> None:
    """If every term is unknown, the legend is empty — a leader gets
    no broken-looking footer instead of a partial one."""
    assert glossary_legend(["NOT_A_TERM_1", "NOT_A_TERM_2"]) == ""


# ---------------------------------------------------------------------------
# Output safety
# ---------------------------------------------------------------------------


def test_glossary_term_output_is_unsafe_html_not_arbitrary_user_input() -> None:
    """The helper outputs HTML for `unsafe_allow_html=True` consumers.
    It must not be vulnerable to definition-based XSS — definitions
    in the dictionary are author-controlled, but the escape applies
    regardless."""
    html = glossary_term("STR", custom_definition="</span><script>alert(1)</script>")
    # Quotes are escaped; no double-quote breaks out of the title attr
    assert '"' not in html.split('title="', 1)[1].split('"', 1)[0]


def test_every_glossary_definition_renders_through_glossary_term() -> None:
    """Smoke check that no definition contains characters that produce
    invalid HTML output through `glossary_term`."""
    for term in GLOSSARY:
        html = glossary_term(term)
        # Output should be a single <span ...>TERM</span>, exactly one open + close
        assert html.count("<span") == 1
        assert html.count("</span>") == 1
        # The visible text in the span is exactly the term we passed in
        assert re.search(rf">{re.escape(term)}</span>$", html)
