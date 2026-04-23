"""Audit & Evidence — manifest viewer, hash verification, decision log."""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.components import page_header

page_header(
    "Audit & Evidence",
    "Immutable audit trail with hash verification, decision log, and evidence bundle contents.",
)

result = st.session_state.result
run_dir = st.session_state.run_dir
df_decisions = st.session_state.df_decisions

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo — Audit & Evidence**\n\n"
        "This is what your auditor and regulator see. Every rule execution "
        "records a content hash so the same spec + same data + same engine = "
        "same output. The decision log is append-only. The evidence bundle "
        "is a signed, zipped artifact ready for regulatory examination."
    )

# --- Run Manifest ---
st.subheader("Run Manifest")
manifest = result.manifest
st.json(manifest)

st.divider()

# --- Hash Verification ---
st.subheader("Rule Output Hashes")
rule_outputs = manifest.get("rule_outputs", {})
if rule_outputs:
    import pandas as pd

    hash_rows = []
    for rule_id, output_hash in rule_outputs.items():
        hash_rows.append({
            "Rule ID": rule_id,
            "Output Hash (SHA-256)": output_hash,
            "Verified": "\u2705" if output_hash else "\u274c",
        })
    df_hashes = pd.DataFrame(hash_rows)
    st.dataframe(df_hashes, use_container_width=True, hide_index=True)
else:
    st.caption("No rule output hashes in manifest.")

st.divider()

# --- Decision Log ---
st.subheader("Decision Log (append-only)")
if not df_decisions.empty:
    st.dataframe(df_decisions, use_container_width=True, hide_index=True)
else:
    st.caption("No decisions recorded.")

st.divider()

# --- Evidence Bundle Structure ---
st.subheader("Evidence Bundle Contents")
if run_dir.exists():
    file_tree = []
    for p in sorted(run_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(run_dir)
            size = p.stat().st_size
            file_tree.append(f"  {rel}  ({size:,} bytes)")
    st.code(f"{run_dir.name}/\n" + "\n".join(file_tree), language="text")
else:
    st.caption("Run directory not found.")

st.divider()

# --- Spec Snapshot ---
st.subheader("Spec Snapshot")
snapshot_path = run_dir / "spec_snapshot.yaml"
if snapshot_path.exists():
    with st.expander("View spec snapshot (aml.yaml at execution time)"):
        st.code(snapshot_path.read_text(encoding="utf-8"), language="yaml")
else:
    st.caption("Spec snapshot not found.")

# --- Input Manifest ---
st.subheader("Input Data Manifest")
input_manifest = manifest.get("inputs", {})
if input_manifest:
    st.json(input_manifest)
else:
    st.caption("No input manifest data.")
