"""Cross-page deep-link helpers built on Streamlit's query-param + session-state.

Phase A of the dashboard workflow plan. Every page-to-page drill-down
(e.g. Alert Queue → Customer 360 with `?customer_id=C0001`) flows
through this module so the wiring is consistent + testable.

Streamlit gotcha: `st.query_params` is a write-through to the URL, but
`st.page_link` doesn't currently pass query params on navigation. We
mirror the value into `st.session_state[f"selected_{name}"]` so the
destination page can read it whichever way it arrived (deep link or
in-app navigation).

Convention:
- Keys live under `selected_<name>` in session state
- Destination pages call `read_param("customer_id")` to pick up either
  the URL param OR the session-state mirror, with URL winning
- `consume_param()` reads + clears the session-state mirror so a
  subsequent page reload doesn't re-trigger the drill-down state
"""

from __future__ import annotations

from typing import TypeVar

import streamlit as st

T = TypeVar("T")


def _session_key(name: str) -> str:
    return f"selected_{name}"


def read_param(name: str, default: T | None = None) -> str | T | None:
    """Read a query param with session-state fallback.

    Resolution order:
        1. URL query param (`?customer_id=C0001`) — wins when present
        2. Session-state mirror (set by `link_to_page` or `set_param`)
        3. Provided `default`

    Returns the raw string value. Callers needing typed values should
    coerce themselves (e.g. `int(read_param("page", "1"))`).
    """
    try:
        if name in st.query_params:
            return st.query_params[name]
    except Exception:
        # st.query_params can raise on edge runtime states (e.g. older
        # Streamlit during script reruns); fall through to session state.
        pass
    return st.session_state.get(_session_key(name), default)


def set_param(name: str, value: str) -> None:
    """Write a query param + mirror it into session state.

    Used by pages that want to update the URL when a user drills down
    via an in-page widget (so a refresh preserves the drill-down state).
    """
    try:
        st.query_params[name] = value
    except Exception:
        # Same fallback as read_param — session-state mirror is always set
        # so destination pages have a consistent place to read from.
        pass
    st.session_state[_session_key(name)] = value


def consume_param(name: str) -> str | None:
    """Read a param and clear it from session state.

    Use when the drill-down state should be one-shot (e.g. "open the
    case for this alert" — once viewed, the page should not re-trigger
    on refresh). Does NOT clear the URL param itself; that requires
    `clear_param()`.
    """
    value = read_param(name)
    st.session_state.pop(_session_key(name), None)
    return value


def clear_param(name: str) -> None:
    """Remove the param from both URL and session state.

    Use when the drill-down has been resolved + persisted into the
    canonical state (e.g. user clicked "Open" on a case row → the case
    is now the active selection in the page's own selectbox state, so
    the deep-link param can be retired).
    """
    try:
        if name in st.query_params:
            del st.query_params[name]
    except Exception:
        pass
    st.session_state.pop(_session_key(name), None)


__all__ = [
    "clear_param",
    "consume_param",
    "read_param",
    "set_param",
]
