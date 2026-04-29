"""Domain-acronym glossary — pure-Python, no dashboard dependencies.

Lives outside `components.py` so unit-tests CI can import it without
pulling in pandas + streamlit (`components.py` requires both at module
top-level). The leader-friendliness invariant — "we keep STR/SAR/MRM
visible because regulators speak that way, and define each on hover" —
is enforceable in CI now that the helpers live in their own module.

Public surface:
- `GLOSSARY` — dict of {acronym: one-sentence plain-English definition}
- `glossary_term(term, custom_definition=None)` — HTML span with title-
  attribute tooltip; safe to splice into markdown rendered with
  `unsafe_allow_html=True`
- `glossary_legend(terms)` — inline footer band of expanded definitions

`components.py` re-exports these so existing pages (`from
aml_framework.dashboard.components import glossary_legend`) keep
working without churn.
"""

from __future__ import annotations

GLOSSARY: dict[str, str] = {
    "STR": "Suspicious Transaction Report — the form a bank files with FINTRAC when a transaction looks suspicious.",
    "SAR": "Suspicious Activity Report — the US (FinCEN) equivalent of a STR.",
    "KYC": "Know Your Customer — verifying who a customer actually is at onboarding.",
    "CDD": "Customer Due Diligence — the standard checks done on every customer.",
    "EDD": "Enhanced Due Diligence — deeper checks for higher-risk customers.",
    "UBO": "Ultimate Beneficial Owner — the human who really owns or controls an entity customer.",
    "BOI": "Beneficial Ownership Information — the FinCEN return identifying UBOs of reporting companies.",
    "MRM": "Model Risk Management — proving your detection rules and scoring models still work.",
    "MLRO": "Money Laundering Reporting Officer — the named officer who signs the STRs (UK / Canada term).",
    "FCC": "Financial Crime Compliance — the function that runs AML, fraud, sanctions, and bribery controls.",
    "OSFI": "Office of the Superintendent of Financial Institutions — Canada's prudential regulator.",
    "FINTRAC": "Financial Transactions and Reports Analysis Centre of Canada — Canada's FIU and AML supervisor.",
    "FinCEN": "Financial Crimes Enforcement Network — US AML supervisor and FIU.",
    "FCA": "Financial Conduct Authority — UK conduct + financial-crime regulator.",
    "BSA": "Bank Secrecy Act (1970) — the foundational US AML statute.",
    "PCMLTFA": "Proceeds of Crime (Money Laundering) and Terrorist Financing Act — Canada's AML statute.",
    "AMLA": "Anti-Money Laundering Authority — the EU's new central AML supervisor (operational H2 2026).",
    "FATF": "Financial Action Task Force — sets the global AML/CFT standards.",
    "1LoD": "First Line of Defence — the business owns the risk (front office, FCC operations).",
    "2LoD": "Second Line of Defence — independent challenge (compliance, MLRO, MRM).",
    "3LoD": "Third Line of Defence — independent assurance (internal audit).",
    "RAG": "Red / Amber / Green — the colour-coded status banks use on dashboards and board reports.",
    "SLA": "Service Level Agreement — the time-to-decision target for an alert or case.",
    "LCTR": "Large Cash Transaction Report — Canadian threshold-based cash report (CAD 10,000+).",
    "CTR": "Currency Transaction Report — the US threshold-based cash report (USD 10,000+).",
}


def glossary_term(term: str, *, custom_definition: str | None = None) -> str:
    """Return an HTML span that renders `term` with a hover-tooltip definition.

    Use inline in markdown blocks::

        st.markdown(
            f"File the {glossary_term('STR')} within 30 days.",
            unsafe_allow_html=True,
        )

    The hover-tooltip uses the standard HTML `title` attribute, which
    Streamlit passes through unchanged. No JS, no extra CSS, no third-
    party widget — works in every Streamlit version and in print/PDF
    exports.

    Args:
        term: The acronym or term to wrap. Looked up case-insensitively
            in GLOSSARY; falls back to the raw term with no tooltip if
            unknown (and `custom_definition` not supplied).
        custom_definition: Override the built-in definition for one
            site. Useful for context-specific phrasing without polluting
            the shared dictionary.
    """
    definition = custom_definition or GLOSSARY.get(term.upper()) or GLOSSARY.get(term)
    if not definition:
        return term
    # Escape double-quotes inside the title so HTML doesn't break.
    safe = definition.replace('"', "&quot;")
    return (
        f'<span title="{safe}" '
        'style="border-bottom: 1px dotted currentColor; cursor: help;">'
        f"{term}</span>"
    )


def glossary_legend(terms: list[str] | None = None) -> str:
    """Render a small inline legend listing the acronyms used on a page.

    Useful at the bottom of a dashboard page that uses 4-5 acronyms a
    leader might not all know. Returns HTML the caller renders with
    `st.markdown(..., unsafe_allow_html=True)`.

    When `terms` is None or all entries are unknown, returns an empty
    string — leader sees no broken-looking partial footer.
    """
    if not terms:
        return ""
    pieces: list[str] = []
    for t in terms:
        defn = GLOSSARY.get(t.upper()) or GLOSSARY.get(t)
        if not defn:
            continue
        pieces.append(f"**{t}** = {defn}")
    if not pieces:
        return ""
    return (
        '<div style="font-size: 0.78rem; color: #94a3b8; '
        "border-top: 1px dashed rgba(148,163,184,0.2); padding-top: 0.5rem; "
        'margin-top: 1rem;">' + "  ·  ".join(pieces) + "</div>"
    )
