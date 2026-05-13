"""Per-section GenAI explanations — inline, auto-loaded.

The sidebar `ai_panel()` in `components.py` answers freeform questions
about the *whole page*. This module gives every visual section
(KPI card, chart, table) its own AI explanation that fires
automatically on page render, scoped to *that specific section's data*.

Design:

- **Inline.** Renders directly into the page flow via `st.container()`
  + a `#####` markdown header. No expander, no click.
- **Auto-fire on first render.** Every `section_explainer()` call
  invokes the configured backend during page render. The
  `(section_id, data_hash, persona)` cache key short-circuits repeat
  visits in the same session — only the first paint per filter-state
  pays the LLM cost. Within an Ollama Cloud free-tier session, this
  is cheap; for paid backends, the operator can switch to
  `AML_AI_BACKEND=template` for zero-cost canned scaffolding.
- **Visible spinner.** Wrapped in `st.spinner(...)` so the operator
  sees the LLM call is in flight rather than a frozen page.
- **Audit-logged.** Every reply appended to the run's
  `ai_interactions.jsonl` with `event="ai_section_explanation"` so an
  auditor can trace exactly which sections were explained.
- **Failure-safe.** Outer try/except catches any error (backend down,
  no key, JSON parse failure) and renders a single
  `st.caption("Explanation unavailable")` instead of breaking the page.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

import streamlit as st

_CACHE_KEY = "section_explanations"


def _data_hash(data_summary: Mapping[str, Any]) -> str:
    """Stable 16-hex hash of a section's data summary.

    Sorted keys + `default=str` so any JSON-incompatible value (e.g.
    numpy scalars from pandas) falls back to repr. Keeps the hash
    deterministic across reruns while tolerating mixed types page
    authors throw in by mistake.
    """
    blob = json.dumps(dict(data_summary), sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _cache_get(page: str, section_id: str, persona: str | None, data_hash: str) -> Any:
    """Look up a cached reply in `st.session_state` for this triplet."""
    cache = st.session_state.get(_CACHE_KEY)
    if not isinstance(cache, dict):
        return None
    return cache.get((page, section_id, persona or "", data_hash))


def _cache_put(page: str, section_id: str, persona: str | None, data_hash: str, reply: Any) -> None:
    cache = st.session_state.get(_CACHE_KEY)
    if not isinstance(cache, dict):
        cache = {}
        st.session_state[_CACHE_KEY] = cache
    cache[(page, section_id, persona or "", data_hash)] = reply


def _build_context(
    *,
    page: str,
    section_id: str,
    section_title: str,
    section_data: Mapping[str, Any],
    persona: str | None,
) -> Any:
    """Build an `AssistantContext` for a section explanation. Mirrors
    the field set `_handle_ai_submission` builds for the sidebar panel
    so the backend sees identical run-level context plus the new
    section_* fields.
    """
    from aml_framework.assistant.models import AssistantContext

    spec = st.session_state.get("spec")
    result = st.session_state.get("result")
    df_alerts = st.session_state.get("df_alerts")
    df_cases = st.session_state.get("df_cases")
    df_decisions = st.session_state.get("df_decisions")

    return AssistantContext(
        page=page,
        persona=persona or st.session_state.get("selected_audience"),
        spec_name=getattr(getattr(spec, "program", None), "name", "") or "",
        spec_jurisdiction=getattr(getattr(spec, "program", None), "jurisdiction", "") or "",
        spec_regulator=getattr(getattr(spec, "program", None), "regulator", "") or "",
        rule_count=len(getattr(spec, "rules", [])) if spec else 0,
        metric_count=len(getattr(spec, "metrics", [])) if spec else 0,
        run_id=str(getattr(result, "run_id", "")) if result else "",
        alert_count=len(df_alerts) if df_alerts is not None else 0,
        case_count=len(df_cases) if df_cases is not None else 0,
        decision_count=len(df_decisions) if df_decisions is not None else 0,
        selected_customer_id=st.session_state.get("selected_customer_id"),
        selected_case_id=st.session_state.get("selected_case_id"),
        selected_rule_id=st.session_state.get("selected_rule_id"),
        selected_metric_id=st.session_state.get("selected_metric_id"),
        section_id=section_id,
        section_title=section_title,
        section_data=dict(section_data),
    )


def _log_to_audit(reply: Any, *, section_id: str, section_title: str) -> None:
    """Append the section-explanation reply to `ai_interactions.jsonl`
    under `event="ai_section_explanation"`. Best-effort: any failure
    (no run_dir, write error) is swallowed so the page never breaks.
    """
    try:
        from pathlib import Path

        from aml_framework.assistant.models import reply_to_audit_dict
        from aml_framework.engine.audit import AuditLedger

        run_dir = st.session_state.get("run_dir")
        if run_dir is None:
            return
        spec = st.session_state.get("spec")
        audit_mode = getattr(getattr(spec, "program", None), "ai_audit_log", "hash_only")
        row = reply_to_audit_dict(reply, full_text=(audit_mode == "full_text"))
        row["section_id"] = section_id
        row["section_title"] = section_title
        AuditLedger.append_to_run_dir(
            Path(run_dir),
            {"event": "ai_section_explanation", **row},
            jsonl_name="ai_interactions.jsonl",
        )
    except Exception:  # noqa: BLE001
        return


def _render_reply(reply: Any) -> None:
    """Render an AssistantReply inside the popover. Compact form —
    DRAFT banner + body + confidence pill. No citation chips
    (the section context already scopes the claim)."""
    confidence_color = {"high": "#16a34a", "medium": "#d97706", "low": "#94a3b8"}.get(
        getattr(reply, "confidence", "low"), "#94a3b8"
    )
    st.markdown(
        '<div style="font-family:JetBrains Mono,monospace; font-size:10px; '
        "letter-spacing:0.08em; text-transform:uppercase; color:#dc2626; "
        'margin-top:4px; margin-bottom:6px;">DRAFT · analyst review required</div>',
        unsafe_allow_html=True,
    )
    st.markdown(getattr(reply, "text", "(no reply text)"))
    st.markdown(
        f'<span style="font-family:JetBrains Mono,monospace; font-size:10px; '
        f"padding:2px 6px; border-radius:3px; background:{confidence_color}22; "
        f'color:{confidence_color}; font-weight:600;">'
        f"confidence · {getattr(reply, 'confidence', 'low')}</span>",
        unsafe_allow_html=True,
    )


def section_explainer(
    *,
    page: str,
    section_id: str,
    section_title: str,
    data_summary: Mapping[str, Any],
    persona: str | None = None,
) -> None:
    """Render an inline AI explanation for a dashboard section.

    Drop this immediately after a section's content (chart, table,
    KPI card). On first render, the LLM call fires automatically and
    the reply lands inline below the section. The
    `(section_id, data_hash, persona)` cache short-circuits repeat
    renders in the same session — only the first paint per
    filter-state pays the LLM cost.

    Args:
        page: Page title — matches the value passed to `page_header()`.
        section_id: Stable slug identifying this section across reruns
            (e.g. ``"exec.kpis.headline"``). Used as the cache key
            and audit-log identifier — keep it stable across UI
            tweaks so cached replies and audit trails persist.
        section_title: Human-readable label rendered in the popover
            header and sent to the backend as section_title.
        data_summary: JSON-serializable dict describing the section's
            data. This is the *entire* view the LLM has of the
            section — curate it (no raw DataFrames, no PII unless
            opt-in). Numbers, counts, top-N breakdowns, RAG bands.
        persona: Override `selected_audience` if the section is
            persona-pinned. Usually None; defaults to the operator's
            current sidebar selection.

    The function never raises — every failure (no key, backend down,
    JSON parse error, missing session state) collapses to a single
    `st.caption("Explanation unavailable")` line.
    """
    try:
        import os

        data_hash = _data_hash(data_summary)
        effective_persona = persona or st.session_state.get("selected_audience")
        cached_reply = _cache_get(page, section_id, effective_persona, data_hash)

        # Inline render — no expander, no click, no env flag. The
        # explanation is part of the page flow: after the section's
        # content, the explainer renders its own header + spinner +
        # reply. On first render the LLM call fires automatically;
        # subsequent reruns hit the (section_id, data_hash, persona)
        # cache and render in <1 ms. For cost-conscious deployments,
        # the operator sets `AML_AI_BACKEND=template` (the framework
        # default) — TemplateBackend returns canned scaffolding with
        # zero network calls.
        with st.container():
            st.markdown(f"##### ℹ {section_title} — AI Explanation")
            if effective_persona:
                st.caption(f"Tailored for persona: `{effective_persona}`")

            if cached_reply is not None:
                _render_reply(cached_reply)
                return

            # Build context + invoke backend. Wrapped in st.spinner so the
            # operator sees that the ~2-3 sec LLM call is in flight rather
            # than a frozen page.
            context = _build_context(
                page=page,
                section_id=section_id,
                section_title=section_title,
                section_data=data_summary,
                persona=effective_persona,
            )
            backend_name = os.environ.get("AML_AI_BACKEND", "template")
            with st.spinner(f"Generating explanation via `{backend_name}` — typically 2-3 sec…"):
                try:
                    from aml_framework.assistant.factory import get_assistant

                    assistant = get_assistant(backend_name)
                    question = (
                        f"Explain the '{section_title}' section to the operator. "
                        "Highlight what is normal, what is unusual, and what an "
                        "analyst should do next."
                    )
                    reply = assistant.reply(question, context)
                except Exception:  # noqa: BLE001
                    from aml_framework.assistant.template import TemplateBackend

                    question = f"Explain '{section_title}'."
                    reply = TemplateBackend().reply(question, context)

            _cache_put(page, section_id, effective_persona, data_hash, reply)
            _log_to_audit(reply, section_id=section_id, section_title=section_title)
            _render_reply(reply)
    except Exception:  # noqa: BLE001
        # Don't break the page. The host section has already rendered
        # — just skip the explainer chrome.
        try:
            st.caption("Explanation unavailable")
        except Exception:  # noqa: BLE001
            return
