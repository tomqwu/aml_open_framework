"""AI Assistant — transcript + backend status (PR-K MVP).

Companion page to the sidebar `ai_panel()` that lives on every other
page. This is where senior personas (CCO, MLRO, Auditor) come to:

- See WHICH backend is configured and whether it works
- Browse THIS session's full transcript across pages
- Tail `ai_interactions.jsonl` for forensic review

The sidebar panel is for asking; this page is for accountability.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from aml_framework.dashboard.components import (
    empty_state,
    page_header,
    research_link,
    see_also_footer,
    terminal_block,
)

PAGE_TITLE = "AI Assistant"

page_header(
    PAGE_TITLE,
    "Where the dashboard's GenAI co-pilot lives. Backend status, this "
    "session's transcript, and the run's AI audit trail — one place, "
    "auditable, with the same DRAFT-tagged citation discipline the "
    "narrative drafter uses.",
)

# ---------------------------------------------------------------------------
# Section 1 — Backend status
# ---------------------------------------------------------------------------

backend_name = os.environ.get("AML_AI_BACKEND", "template").lower()
backend_status: list[tuple[str, str, str]] = [
    ("Backend", backend_name, "ok" if backend_name in {"template", "ollama", "openai"} else "warn"),
]

if backend_name == "openai":
    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    backend_status.append(
        ("OPENAI_API_KEY", "set" if has_key else "MISSING", "ok" if has_key else "bad"),
    )
    backend_status.append(("Model", os.environ.get("AML_OPENAI_MODEL", "gpt-4o-mini"), ""))
    backend_status.append(
        ("Privacy", "PII may transit to OpenAI", "warn"),
    )
elif backend_name == "ollama":
    backend_status.append(
        ("URL", os.environ.get("AML_OLLAMA_URL", "http://localhost:11434/api/generate"), ""),
    )
    backend_status.append(("Model", os.environ.get("AML_OLLAMA_MODEL", "llama3.1"), ""))
    backend_status.append(("Privacy", "PII stays on host", "ok"))
else:
    backend_status.append(("Mode", "canned scaffolding (no LLM)", "warn"))
    backend_status.append(
        (
            "Enable",
            "set AML_AI_BACKEND=ollama or openai",
            "",
        ),
    )

spec = st.session_state.get("spec")
audit_mode = getattr(getattr(spec, "program", None), "ai_audit_log", "hash_only")
backend_status.append(
    (
        "Audit log",
        "FULL TEXT" if audit_mode == "full_text" else "hash-only (default)",
        "warn" if audit_mode == "full_text" else "ok",
    ),
)

terminal_block(backend_status)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 2 — This session's transcript
# ---------------------------------------------------------------------------

st.markdown("### This session's transcript")
transcript: dict = st.session_state.get("ai_transcript", {})
if not transcript:
    empty_state(
        "No questions asked yet in this session.",
        icon="💬",
        detail=(
            "Ask the assistant from the sidebar on any page — replies "
            "show up here, page-tagged, in chronological order."
        ),
    )
else:
    pages_sorted = sorted(transcript.keys())
    for page in pages_sorted:
        reply = transcript[page]
        with st.expander(f"**{page}** · {reply.confidence} confidence · {reply.backend}"):
            st.markdown(reply.text)
            if reply.citations:
                st.markdown("**Citations:**")
                for c in reply.citations:
                    st.markdown(f"- `{c.rule_id}` · {c.citation} — {c.claim}")
            if reply.referenced_metric_ids:
                st.markdown(
                    "**Metrics referenced:** "
                    + ", ".join(f"`{m}`" for m in reply.referenced_metric_ids)
                )
            if reply.referenced_case_ids:
                st.markdown(
                    "**Cases referenced:** "
                    + ", ".join(f"`{c}`" for c in reply.referenced_case_ids)
                )

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 3 — Run-level audit trail
# ---------------------------------------------------------------------------

st.markdown("### Run-level audit trail")
st.caption(
    "Every interaction with the assistant is appended to "
    "`ai_interactions.jsonl` in the run directory. The spec's "
    "`program.ai_audit_log` flag determines whether the full reply "
    "text or a SHA-256 hash is logged — flip to `full_text` only "
    "after clearing it against your privacy posture."
)

run_dir = st.session_state.get("run_dir")
log_rows = []
if run_dir is not None:
    log_path = Path(run_dir) / "ai_interactions.jsonl"
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            try:
                log_rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

if log_rows:
    df_log = pd.DataFrame(log_rows)
    show_cols = [
        c
        for c in ("ts", "page", "persona", "backend", "confidence", "question")
        if c in df_log.columns
    ]
    st.dataframe(df_log[show_cols], use_container_width=True, hide_index=True, height=280)
    st.caption(f"{len(log_rows)} interaction(s) logged.")
else:
    empty_state(
        "No interactions logged yet for this run.",
        icon="🗒",
        detail=(
            "The audit trail is created lazily — the first time you ask "
            "the assistant, the file appears at `<run_dir>/ai_interactions.jsonl`."
        ),
    )

# ---------------------------------------------------------------------------
# See also
# ---------------------------------------------------------------------------

see_also_footer(
    [
        "[Audit & Evidence — hash chain + decision log](./7_Audit_Evidence)",
        "[Case Investigation — narrative drafter (sister GenAI surface)](./4_Case_Investigation)",
        research_link(
            "Effectiveness research — what defensible AI in AML needs to look like",
            "2026-04-aml-process-pain.md",
        ),
    ]
)
