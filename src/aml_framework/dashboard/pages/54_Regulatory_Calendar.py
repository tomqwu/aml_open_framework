"""Regulatory Calendar — forward regulatory deadlines + framework readiness (#511).

Read-only synthesis surface — no engine call, no spec write. Loads the packaged
forward calendar (`regulatory_calendar.yaml`) via the pure
`regulatory_calendar` module, computes live days-remaining against
`date.today()`, and for each upcoming deadline shows:

  • the urgency band (error/warning/info per `urgency_band`),
  • the framework features that evidence readiness (dashboard pages +
    example specs from `framework_alignment`), and
  • a per-deadline readiness indicator — which referenced `spec_fields`
    (dotted paths like `program.prioritization`) are populated in the
    LOADED spec.

The pure functions are deterministic given an explicit `as_of`; only this UI
uses the live `date.today()` as the countdown anchor — mirrors the Today
banner (#510).

Universally routed (every persona sees it) via `CALENDAR_PAGES` — mirrors the
North-Star / Triage idiom in `app.py`. NOT in `AUDIENCE_PAGES` so the
per-persona MAX_PAGES_PER_PERSONA cap is preserved.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import (
    page_footer,
    page_header,
    section_explainer,
)
from aml_framework.dashboard.regulatory_calendar import (
    active_deadlines,
    days_remaining,
    load_calendar,
    urgency_band,
)
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

page_header(
    "Regulatory Calendar",
    "Forward regulatory deadlines with the framework features that evidence readiness.",
)
show_audience_context("Regulatory Calendar")

as_of = date.today()
active = active_deadlines(load_calendar(), as_of=as_of)

section_explainer(
    page="Regulatory Calendar",
    section_id="regulatory_calendar.page",
    collapsed=True,
    section_title="Regulatory Calendar",
    data_summary={
        "n_active": len(active),
        "nearest_days": (days_remaining(active[0], as_of=as_of) if active else None),
        "as_of": as_of.isoformat(),
    },
)

st.subheader(f"Active regulatory deadlines — as of {as_of.isoformat()}")

if not active:
    st.info("No upcoming regulatory deadlines on the calendar.")
    page_footer()
    st.stop()


def _resolve_field(spec_obj: object, dotted: str) -> bool:
    """True when the dotted spec path resolves to a present, non-None value.

    Walks ``spec.program.prioritization``-style paths via getattr. Wrapped per
    field by the caller so a missing attribute → ✗, never a crash.
    """
    cur = spec_obj
    for part in dotted.split("."):
        cur = getattr(cur, part)
        if cur is None:
            return False
    return cur is not None


spec = st.session_state.get("spec")

for d in active:
    days = days_remaining(d, as_of=as_of)
    band = urgency_band(days)
    when = "due today" if days == 0 else f"← {days} days"
    headline = f"**{d.description}** — {when}  ·  due {d.deadline.isoformat()}"
    if band == "error":
        st.error(headline)
    elif band == "warning":
        st.warning(headline)
    else:
        st.info(headline)

    st.markdown(f"[Source]({d.source_url})")

    alignment = d.framework_alignment or {}

    # Evidence response / framework alignment.
    pages = alignment.get("pages") or []
    if pages:
        st.markdown("**Dashboard pages that address this:** " + ", ".join(str(p) for p in pages))

    example_specs = alignment.get("example_specs") or []
    if example_specs:
        st.markdown("**Example specs:** " + ", ".join(f"`{s}`" for s in example_specs))

    # Readiness indicator — which referenced spec_fields are populated in the
    # LOADED spec. Per-field try/except so a missing attribute → ✗, never a
    # crash.
    spec_fields = alignment.get("spec_fields") or []
    if spec_fields:
        populated = 0
        lines: list[str] = []
        for field in spec_fields:
            try:
                ok = spec is not None and _resolve_field(spec, str(field))
            except Exception:  # noqa: BLE001 — any resolution failure → not ready
                ok = False
            if ok:
                populated += 1
            lines.append(f"- `{field}`: {'✓' if ok else '✗'}")
        st.markdown("**Readiness:**\n" + "\n".join(lines))
        st.caption(f"Readiness: {populated}/{len(spec_fields)} spec fields populated")

    st.divider()

page_footer()
