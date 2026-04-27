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

In v1 the library ships just one file (`iso20022_purpose_codes.yaml`,
Round-5 PR #3). Future rounds will add more (TBML in Round-7, RTP
push fraud in Round-8).
"""

from pathlib import Path

LIBRARY_ROOT = Path(__file__).parent

__all__ = ["LIBRARY_ROOT"]
