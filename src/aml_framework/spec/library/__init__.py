"""Reusable spec snippet libraries.

Curated, copy-pasteable rule templates that compose with the framework's
existing data contracts. Operators drop the YAML snippets they want
into their own `aml.yaml` `rules:` block.

Why a snippet library (not an include mechanism):
    The framework's whole defensibility story is "every line of the
    spec was written by a human who can defend it in front of a
    regulator." An auto-include directive would let rules silently
    appear in the running spec on a library bump — which would erode
    that story. Copy-paste is the right ergonomic.

Files shipped:
- `iso20022_purpose_codes.yaml` — Round-5 #3 purpose-code typology
  rules (INVS pig-butchering, CHAR/GIFT shell-charity, DERI mandate
  mismatch, TRAD-to-high-risk TBML).
- `iso20022_return_reasons.yaml` — Round-5 #5 pacs.004 return-reason
  mining (mule-probing burst, corridor return-rate spike, MD07
  deceased-payee scraping). Reads from `txn_return` data contract.

Future rounds will add more (TBML in Round-7, RTP push fraud in
Round-8).
"""

from pathlib import Path

LIBRARY_ROOT = Path(__file__).parent

__all__ = ["LIBRARY_ROOT"]
