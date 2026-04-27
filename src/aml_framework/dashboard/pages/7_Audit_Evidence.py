"""Audit & Evidence -- manifest viewer, hash verification, decision log."""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.components import kpi_card, page_header
from aml_framework.engine.audit import AuditLedger

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
st.markdown("### Integrity Verification")

# Always show current integrity status.
valid, msg = AuditLedger.verify_decisions(run_dir)
if valid:
    st.markdown(
        '<div style="background:linear-gradient(135deg, #05966918, #05966908); '
        "border-left:4px solid #059669; border-radius:8px; padding:1rem 1.5rem; "
        'margin-bottom:0.5rem;">'
        '<span style="font-size:1.1rem; font-weight:600; color:#059669;">'
        "&#x2705; Decision Log Integrity Verified</span><br>"
        f'<span style="font-size:0.85rem; color:#475569;">{msg}</span>'
        "</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<div style="background:linear-gradient(135deg, #dc262618, #dc262608); '
        "border-left:4px solid #dc2626; border-radius:8px; padding:1rem 1.5rem; "
        'margin-bottom:0.5rem;">'
        '<span style="font-size:1.1rem; font-weight:600; color:#dc2626;">'
        "&#x1F6A8; TAMPER DETECTED</span><br>"
        f'<span style="font-size:0.85rem; color:#475569;">{msg}</span>'
        "</div>",
        unsafe_allow_html=True,
    )

# Also verify rule output hashes against stored hashes.
rule_outputs = manifest.get("rule_outputs", {})
alerts_dir = run_dir / "alerts"
mismatches = []
if alerts_dir.exists():
    for rule_id, stored_hash in rule_outputs.items():
        hash_file = alerts_dir / f"{rule_id}.hash"
        if hash_file.exists():
            on_disk = hash_file.read_text(encoding="utf-8").strip()
            if on_disk != stored_hash:
                mismatches.append(rule_id)

if mismatches:
    st.error(f"Rule output hash mismatch for: {', '.join(mismatches)}")
elif rule_outputs:
    st.caption(f"All {len(rule_outputs)} rule output hashes match manifest.")

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


# ---------------------------------------------------------------------------
# Regulation Drift (compliance/regwatch.py — Round-7 PR #74)
# ---------------------------------------------------------------------------
# FinCEN BOI was silently narrowed in March 2025 — the canonical
# example of a regulator page changing without redirect, leaving
# downstream specs citing stale language. The watcher surfaces drift
# at the URL-content-hash level. This panel reads the baseline written
# by `aml regwatch <spec> --update` and shows current state.
spec = st.session_state.spec
st.markdown("---")
st.markdown("### Regulation Drift")
st.caption(
    "Hashes every cited regulation URL and compares against the saved "
    "baseline. Run `aml regwatch <spec> --update` to refresh after "
    "acknowledging drift. Closes the gap from FinCEN BOI Mar 2025 narrowing."
)

try:
    from pathlib import Path as _Path

    from aml_framework.compliance.regwatch import load_baseline, scan_spec

    citations = scan_spec(spec)
    # Default baseline path matches the CLI default.
    _baseline_path = _Path(".regwatch.json")
    _baseline = load_baseline(_baseline_path)
    _baseline_by_key = {(e.citation, e.url): e for e in _baseline}

    rows = []
    resolved_count = 0
    for citation, url in citations:
        if url is None:
            rows.append(
                {
                    "citation": citation,
                    "url": "(no URL — add `url:` to regulation_refs)",
                    "in_baseline": False,
                    "baseline_age": "",
                }
            )
            continue
        resolved_count += 1
        entry = _baseline_by_key.get((citation, url))
        rows.append(
            {
                "citation": citation,
                "url": url,
                "in_baseline": entry is not None,
                "baseline_age": entry.fetched_at[:10] if entry else "—",
            }
        )

    rc1, rc2, rc3, rc4 = st.columns(4)
    with rc1:
        kpi_card("Citations", len(citations), "#2563eb")
    with rc2:
        kpi_card("Resolvable URLs", resolved_count, "#059669")
    with rc3:
        kpi_card("In baseline", len(_baseline), "#7c3aed")
    with rc4:
        kpi_card(
            "Baseline at",
            str(_baseline_path) if _baseline else "(none)",
            "#d97706" if not _baseline else "#16a34a",
        )

    if not _baseline:
        st.info(
            "No baseline at `.regwatch.json`. Run "
            f"`aml regwatch {st.session_state.spec_path} --update` to capture "
            "current URL hashes; subsequent runs will detect drift."
        )
    else:
        import pandas as _pd

        st.dataframe(_pd.DataFrame(rows), use_container_width=True, hide_index=True)
except Exception as _e:  # noqa: BLE001 — drift panel must never crash the page
    st.caption(f"Regwatch unavailable: {_e}")
