"""Audit & Evidence -- manifest viewer, hash verification, decision log."""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.components import kpi_card, page_header

page_header(
    "Audit & Evidence",
    "Immutable audit trail with hash verification, decision log, and evidence bundle.",
)

result = st.session_state.result
run_dir = st.session_state.run_dir
df_decisions = st.session_state.df_decisions
manifest = result.manifest

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Audit & Evidence**\n\n"
        "Every rule execution records a content hash so the same spec + "
        "same data + same engine = same output. The decision log is "
        "append-only. This is the regulator and auditor view."
    )

# --- KPI row ---
rule_outputs = manifest.get("rule_outputs", {})
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Spec Hash", manifest.get("spec_content_hash", "")[:12] + "...", "#2563eb")
with c2:
    kpi_card("Rules Hashed", len(rule_outputs), "#059669")
with c3:
    kpi_card("Decisions", len(df_decisions), "#7c3aed")
with c4:
    kpi_card("Engine Version", manifest.get("engine_version", "N/A"), "#6b7280")

# --- Integrity verification ---
st.markdown("<br>", unsafe_allow_html=True)
if st.button("Verify Decision Log Integrity", type="primary"):
    from aml_framework.engine.audit import AuditLedger

    valid, msg = AuditLedger.verify_decisions(run_dir)
    if valid:
        st.success(f"Integrity verified: {msg}")
    else:
        st.error(f"INTEGRITY CHECK FAILED: {msg}")

st.markdown("<br>", unsafe_allow_html=True)

# --- Hash Verification ---
st.markdown("### Rule Output Hashes")
if rule_outputs:
    import pandas as pd

    hash_rows = []
    for rule_id, output_hash in rule_outputs.items():
        hash_rows.append(
            {
                "Rule": rule_id,
                "SHA-256": output_hash,
            }
        )
    st.dataframe(pd.DataFrame(hash_rows), use_container_width=True, hide_index=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- Decision Log with Search ---
st.markdown("### Decision Log")
if not df_decisions.empty:
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        event_filter = st.multiselect(
            "Event type",
            df_decisions["event"].unique().tolist() if "event" in df_decisions.columns else [],
            default=None,
        )
    with col_f2:
        search_text = st.text_input("Search", placeholder="case_id, rule_id...")
    with col_f3:
        csv_export = st.download_button(
            "Export Decisions CSV",
            df_decisions.to_csv(index=False),
            "decisions.csv",
            "text/csv",
            use_container_width=True,
        )

    filtered_decisions = df_decisions
    if event_filter:
        filtered_decisions = filtered_decisions[filtered_decisions["event"].isin(event_filter)]
    if search_text:
        mask = filtered_decisions.apply(
            lambda row: search_text.lower() in str(row.values).lower(), axis=1
        )
        filtered_decisions = filtered_decisions[mask]

    st.dataframe(
        filtered_decisions,
        use_container_width=True,
        hide_index=True,
        height=300,
    )
    st.caption(f"Showing {len(filtered_decisions)} of {len(df_decisions)} decisions.")
else:
    st.caption("No decisions recorded.")

st.markdown("<br>", unsafe_allow_html=True)

# --- Run Manifest ---
col_left, col_right = st.columns(2)

with col_left:
    st.markdown("### Run Manifest")
    st.json(manifest, expanded=False)

with col_right:
    st.markdown("### Evidence Bundle")
    if run_dir.exists():
        file_tree = []
        for p in sorted(run_dir.rglob("*")):
            if p.is_file():
                rel = p.relative_to(run_dir)
                size = p.stat().st_size
                file_tree.append(f"  {rel}  ({size:,} bytes)")
        st.code(f"{run_dir.name}/\n" + "\n".join(file_tree), language="text")

# --- Spec Snapshot ---
snapshot_path = run_dir / "spec_snapshot.yaml"
if snapshot_path.exists():
    with st.expander("View spec snapshot (aml.yaml at execution time)"):
        st.code(snapshot_path.read_text(encoding="utf-8"), language="yaml")
