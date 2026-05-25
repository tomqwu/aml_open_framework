"""External-URL resolvers for cross-surface links.

Lightweight (stdlib only) so it can be imported from both the FastAPI
service (``api/main.py``) and the Streamlit dashboard (``dashboard/app.py``)
without pulling either's heavyweight deps into the other.

R32: extracted from inline code in ``api/main.py`` + ``dashboard/app.py``
after Codex (PR #446 review) flagged that two different env vars
(``AML_DOCS_URL`` set by ``app.py``, ``AML_KB_URL`` read by ``api/main.py``)
were a footgun in private-mirror deployments — an operator who sets one
but not the other would see split front doors. Single resolver here so
every surface honors the same override.
"""

from __future__ import annotations

import os

DEFAULT_DOCS_URL = "https://tomqwu.github.io/aml_open_framework_docs/"


def docs_url() -> str:
    """The docs / Knowledge / whitepapers site URL — always returns
    with a trailing slash so callers can ``urljoin`` sub-paths
    (e.g. ``how-to/``) without worrying about the operator's env
    formatting.

    Resolution order:
      1. ``AML_DOCS_URL`` env (canonical from R32 onward)
      2. ``AML_KB_URL`` env (legacy from PR-U4; honored for back-compat)
      3. ``DEFAULT_DOCS_URL`` (public GitHub Pages site)

    Single source of truth — both the FastAPI landing page CTA, the
    ``/knowledge`` redirect, and the dashboard sidebar links import
    this so they all honor the same operator override.
    """
    raw = os.environ.get("AML_DOCS_URL") or os.environ.get("AML_KB_URL") or DEFAULT_DOCS_URL
    return raw if raw.endswith("/") else raw + "/"
