"""Client-side `prefers-color-scheme` bridge.

The dashboard's dark theme follows the OS via a CSS
``@media (prefers-color-scheme: dark)`` query (see components.py).
Server-side code that bakes colours into a payload — the ECharts
theme in ``charts.py`` — can't read a media query, and
``st.context.theme`` tracks Streamlit's *own* theme system, a
DIFFERENT signal that can desync from the CSS (Codex flagged this on
PR-2). This bridges the *exact same* signal the CSS uses into Python.

Mechanism (no new deps, no custom component build):

* A tiny injected ``<script>`` reads
  ``window.matchMedia('(prefers-color-scheme: dark)')`` and, **only
  when** the value disagrees with the ``?_cs=`` query param already in
  the URL, sets the param and reloads once. So:
  - first visit: no param → one reload → ``?_cs=dark|light`` present;
  - steady state: param matches matchMedia → no reload, no loop;
  - OS theme flip mid-session: a ``change`` listener re-bridges with a
    single reload.
* The param is intentionally NOT stripped — stripping would make the
  script immediately re-add it and reload forever. Carrying
  ``?_cs=`` is a cosmetic-only addition (deep-links still resolve).
* The one first-visit reload recomputes the engine deterministically
  via ``ensure_initialized`` (same spec+seed → identical output), so
  it costs a few seconds once, not data loss.

Resolved value is cached in ``st.session_state`` so every chart on
the page reads it without re-injecting the bridge.
"""

from __future__ import annotations

import streamlit as st

_SS_KEY = "_color_scheme"
_QP = "_cs"


def ensure_color_scheme_detected() -> None:
    """Resolve the OS colour scheme into ``session_state`` and mount
    the (idempotent) client bridge. Call once per page render
    (``page_header``). Crash-safety is the caller's contract (wrapped
    in try/except there) — a theme-detection hiccup must never break a
    page."""
    reported = st.query_params.get(_QP)
    if reported in ("dark", "light"):
        st.session_state[_SS_KEY] = reported

    import streamlit.components.v1 as components

    # The script reloads ONLY when matchMedia disagrees with the param
    # already in the URL, so it converges in one step and never loops.
    components.html(
        f"""
        <script>
        (function() {{
          try {{
            var mq = window.matchMedia('(prefers-color-scheme: dark)');
            function bridge() {{
              var want = mq.matches ? 'dark' : 'light';
              var url = new URL(window.parent.location);
              if (url.searchParams.get('{_QP}') !== want) {{
                url.searchParams.set('{_QP}', want);
                window.parent.location.replace(url.toString());
              }}
            }}
            bridge();
            mq.addEventListener('change', bridge);
          }} catch (e) {{ /* never break the host page */ }}
        }})();
        </script>
        """,
        height=0,
    )


def current_color_scheme() -> str:
    """``'dark'`` | ``'light'`` — the OS ``prefers-color-scheme`` as
    reported by the client bridge. Defaults to ``'light'`` before the
    first report (matches the CSS default; self-corrects within the
    single first-visit reload)."""
    return st.session_state.get(_SS_KEY, "light")
