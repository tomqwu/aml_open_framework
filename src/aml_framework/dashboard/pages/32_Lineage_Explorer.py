"""Lineage Explorer — end-to-end "source → query → alert → case" walk-back (PR-LIN-8).

Single-page deep-linkable view that stitches together every primitive
the Phase A backend PRs (PR-LIN-1..4) added:

  Source files  →  DuckDB tables  →  Rule (SQL or callable)
                                      ↓
                                   Alerts (with matched_row_ids)
                                      ↓
                                   Case  →  Investigation  →  STR

Inputs: case_id (paste box or URL param via deep-link from Alert Queue
/ Case Investigation / Audit & Evidence).

Output sections, top-to-bottom:
  1. Mermaid lineage graph
  2. Run anchors (run_dir, spec_hash, engine_version, as_of, rule_version,
     attestation status if present)
  3. Source provenance (per-contract: path + schema_hash + row_count +
     content_hash + earliest/latest ts)
  4. Rendered SQL (collapsible, syntax-highlighted)
  5. Matched source rows (AG Grid, sliced from DuckDB)
  6. Decision timeline (filterable view of all decisions tied to case_id)

The deeper-drill view that auditors actually open. The lighter "Why
this fired" panel on Case Investigation (PR-LIN-6) is the
in-workflow answer.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as _components

from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import (
    data_grid,
    empty_state,
    page_header,
    section_explainer,
)
from aml_framework.dashboard.query_params import consume_param
from aml_framework.dashboard.state import ensure_initialized
from aml_framework.engine.audit import walk_lineage

ensure_initialized()

section_explainer(
    page="Lineage Explorer",
    section_id="lineage_explorer.page",
    section_title="Lineage Explorer",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "rules": len(getattr(st.session_state.get("spec"), "rules", []) or []),
        "metrics": len(getattr(st.session_state.get("spec"), "metrics", []) or []),
        "case_count": (
            len(st.session_state.get("df_cases"))
            if st.session_state.get("df_cases") is not None
            else 0
        ),
    },
)

page_header(
    "Lineage Explorer",
    "Trace every alert from source row to STR · the regulator-defendable walk-back",
)
show_audience_context("Lineage Explorer")

run_dir = Path(st.session_state.run_dir)

# --- Input: case_id (deep-link or paste) -----------------------------------
deep_link = consume_param("case_id")
case_id_input = st.text_input(
    "case_id",
    value=deep_link or "",
    placeholder="Paste any case_id from this run, or arrive here via 'Why this fired' deep-link",
    key="lineage_explorer_case_input",
)

if not case_id_input.strip():
    empty_state(
        "No case_id selected.",
        icon="🧭",
        detail=(
            "Paste a case_id, or open the Lineage Explorer from a row-click on "
            "Alert Queue / Case Investigation / Audit & Evidence. Every case_id "
            "from the current run is supported."
        ),
        stop=True,
    )

chain = walk_lineage(run_dir, case_id_input.strip())

if chain.get("case") is None:
    empty_state(
        f"No case file found for `{case_id_input.strip()}` in this run.",
        icon="🚫",
        detail=(
            "The case_id may be from a previous run. Refresh the dashboard to "
            "load the current run, or paste a case_id from this run's Alert "
            "Queue."
        ),
        stop=True,
    )

# --- Section 1: Mermaid lineage graph --------------------------------------
st.markdown("### Lineage graph")
st.caption(
    "Source files feed contracts → DuckDB tables → the rule's SQL or callable → "
    "alerts → the case → its investigation → STR (when escalated). Every link "
    "is hash-stamped so a re-run with the same spec + data produces an "
    "identical chain."
)

_input_files = chain.get("input_files") or []
_rule_id = chain.get("rule_id") or "rule"
_case_id_short = chain["case_id"][:32]


def _mm_safe(text: str) -> str:
    """Escape characters Mermaid's flowchart parser can't handle inside
    a quoted node label. Quotes break the string; pipes are link
    syntax; brackets are node-shape syntax. Replace with safe forms."""
    return (
        str(text)
        .replace("\\", "/")
        .replace('"', "'")
        .replace("|", "/")
        .replace("[", "(")
        .replace("]", ")")
    )


_mermaid_lines = ["graph LR"]
for idx, inp in enumerate(_input_files):
    cid = _mm_safe(inp.get("contract_id") or f"contract_{idx}")
    src = _mm_safe(inp.get("source_path") or "-")
    rows = inp.get("row_count") or 0
    _mermaid_lines.append(f'    S{idx}["{src}<br>{rows:,} rows"]')
    _mermaid_lines.append(f'    C{idx}["{cid}<br>contract"]')
    _mermaid_lines.append(f'    T{idx}["{cid}<br>DuckDB table"]')
    _mermaid_lines.append(f"    S{idx} --> C{idx} --> T{idx} --> RuleN")
_mermaid_lines.append(f'    RuleN["{_mm_safe(_rule_id)}<br>rule"]')
_matched_count = len((chain.get("case") or {}).get("alert", {}).get("matched_row_ids") or [])
_mermaid_lines.append(f'    AlertN["alert<br>{_matched_count} matched rows"]')
_mermaid_lines.append(f'    CaseN["{_mm_safe(_case_id_short)}<br>case"]')
_mermaid_lines.append("    RuleN --> AlertN --> CaseN")
# Investigation + STR are conditional — only if any escalate event exists.
_decisions = chain.get("decisions") or []
_has_str = any(d.get("event") == "escalated_to_str" for d in _decisions)
if _has_str:
    _mermaid_lines.append('    InvN["investigation<br>per customer window"]')
    _mermaid_lines.append('    StrN["STR bundle<br>goAML XML + narrative"]')
    _mermaid_lines.append("    CaseN --> InvN --> StrN")
# classDef + class statements on separate lines. Class names use a
# `lin` prefix (not reserved by Mermaid's flowchart grammar). The
# v10 parser rejects `case` / `str` as class names — earlier versions
# silently accepted them.
_mermaid_lines.append("    classDef linSrc fill:#fef3c7,stroke:#b45309")
_mermaid_lines.append("    classDef linContract fill:#fed7aa,stroke:#9a3412")
_mermaid_lines.append("    classDef linTable fill:#fde68a,stroke:#92400e")
_mermaid_lines.append("    classDef linRule fill:#bfdbfe,stroke:#1d4ed8")
_mermaid_lines.append("    classDef linAlert fill:#fecaca,stroke:#b91c1c")
_mermaid_lines.append("    classDef linCase fill:#bbf7d0,stroke:#15803d")
_mermaid_lines.append("    classDef linInv fill:#ddd6fe,stroke:#6d28d9")
_mermaid_lines.append("    classDef linStr fill:#a7f3d0,stroke:#047857")
for idx in range(len(_input_files)):
    _mermaid_lines.append(f"    class S{idx} linSrc")
    _mermaid_lines.append(f"    class C{idx} linContract")
    _mermaid_lines.append(f"    class T{idx} linTable")
_mermaid_lines.append("    class RuleN linRule")
_mermaid_lines.append("    class AlertN linAlert")
_mermaid_lines.append("    class CaseN linCase")
if _has_str:
    _mermaid_lines.append("    class InvN linInv")
    _mermaid_lines.append("    class StrN linStr")
_mermaid = "\n".join(_mermaid_lines)
# Render via Streamlit's HTML component using mermaid.js loaded from CDN —
# matches the existing pattern in cases/str_bundle.py / Network Explorer.
_components.html(
    f"""
<div class="mermaid" style="background:#f8fafc;padding:1rem;border-radius:8px;">
{_mermaid}
</div>
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
  mermaid.initialize({{startOnLoad: true, theme: 'neutral'}});
</script>
""",
    height=380,
)

st.markdown("<br>", unsafe_allow_html=True)

# --- Section 2: Run anchors -------------------------------------------------
st.markdown("### Run anchors")
_anchors_left, _anchors_right = st.columns(2)
with _anchors_left:
    st.markdown("**Case**")
    st.markdown(f"- case_id: `{chain['case_id']}`")
    st.markdown(f"- rule_id: `{chain.get('rule_id') or '—'}`")
    st.markdown(f"- rule_version: `{chain.get('rule_version') or '—'}`")
    st.markdown(f"- queue: `{chain.get('queue') or '—'}`")
with _anchors_right:
    st.markdown("**Run**")
    st.markdown(f"- run_dir: `{run_dir.name}`")
    st.markdown(f"- spec_content_hash: `{(chain.get('spec_content_hash') or '—')[:16]}…`")
    st.markdown(f"- engine_version: `{chain.get('engine_version') or '—'}`")
    st.markdown(f"- as_of: `{chain.get('as_of') or '—'}`")

st.markdown("<br>", unsafe_allow_html=True)

# --- Section 3: Source provenance -------------------------------------------
st.markdown("### Source provenance")
if _input_files:
    import pandas as _pd

    _df_src = _pd.DataFrame(_input_files)
    if "schema_columns" in _df_src.columns:
        _df_src["schema_columns"] = _df_src["schema_columns"].apply(
            lambda v: ", ".join(v) if isinstance(v, list) else "—"
        )
    data_grid(
        _df_src.rename(
            columns={
                "contract_id": "Contract",
                "source_path": "Source",
                "row_count": "Rows",
                "schema_hash": "Schema hash",
                "schema_columns": "Columns",
                "content_hash": "Content hash",
            }
        ),
        key="lineage_explorer_input_files",
        height=200,
    )
else:
    st.caption("No input manifest recorded for this run.")

st.markdown("<br>", unsafe_allow_html=True)

# --- Section 4: Rendered SQL ------------------------------------------------
st.markdown("### Rule SQL")
if chain.get("rule_sql"):
    with st.expander("Rule SQL (post-substitution, executed verbatim)", expanded=True):
        st.code(chain["rule_sql"], language="sql")
else:
    st.caption("No rule SQL captured for this rule (python_ref or non-SQL logic).")

st.markdown("<br>", unsafe_allow_html=True)

# --- Section 5: Matched source rows -----------------------------------------
st.markdown("### Matched source rows")
_alert = (chain.get("case") or {}).get("alert") or {}
_matched_ids = _alert.get("matched_row_ids") or []
_df_txns = st.session_state.get("df_txns")
if _matched_ids and _df_txns is not None and len(_df_txns):
    _valid = [i for i in _matched_ids if 0 <= i < len(_df_txns)]
    if _valid:
        st.caption(f"{len(_valid)} rows from the source `txn` table fired this rule.")
        data_grid(
            _df_txns.iloc[_valid].reset_index(drop=True),
            key="lineage_explorer_matched_rows",
            height=300,
        )
    else:
        st.caption("matched_row_ids resolved to no rows in this run's txn table.")
elif not _matched_ids:
    st.caption(
        "This alert did not stamp matched_row_ids (python_ref rules and pre-PR-LIN-4 "
        "runs return None)."
    )
else:
    st.caption("Source dataframe not available in session state.")

st.markdown("<br>", unsafe_allow_html=True)

# --- Section 6: Decision timeline -------------------------------------------
st.markdown(f"### Decision timeline ({len(_decisions)})")
if _decisions:
    import pandas as _pd

    data_grid(
        _pd.DataFrame(_decisions),
        key="lineage_explorer_decisions",
        height=300,
    )
else:
    st.caption("No decisions tied to this case yet.")

st.markdown("<br>", unsafe_allow_html=True)

# --- Section 7: Export lineage as JSON --------------------------------------
# A "single source of truth" download an auditor can stash without
# screenshotting. PDF generation is a follow-up — JSON ships now since
# it's deterministic and round-trippable.
st.markdown("### Export")
st.caption(
    "Download the full lineage chain as JSON. Same shape as `walk_lineage()` returns "
    "— round-trippable for offline review or attaching to a SAR."
)
_payload = json.dumps(chain, indent=2, sort_keys=True, default=str)
st.download_button(
    "Download lineage.json",
    data=_payload.encode("utf-8"),
    file_name=f"lineage_{chain['case_id']}.json",
    mime="application/json",
    key="lineage_explorer_download",
)
