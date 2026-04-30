"""Audit & Evidence -- manifest viewer, hash verification, decision log.

The huashu-design review picked this page as the candidate for the
"signature 120%" treatment — it's the page auditors and regulators
look at first, and the place where the framework's evidence-chain
claim has to feel **trustworthy** rather than just functional. PR 4
adds:

  - Mono-font terminal block for spec/run hashes (scannable hashes
    without 0/O ambiguity).
  - Explicit "Verify hash chain" button that re-runs verification and
    timestamps the proof, instead of only relying on the auto-load
    check.
  - Migrated KPI borders to RAG semantics (PR 2 helper).
  - Citations / baseline KPIs use rag=None for facts and a real RAG
    band on baseline freshness.
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from aml_framework.dashboard.components import (
    event_type_cell_style,
    glossary_legend,
    kpi_card_rag,
    page_header,
    terminal_block,
    tooltip_banner,
    tour_panel,
)
from aml_framework.engine.audit import AuditLedger

page_header(
    "Audit & Evidence",
    "What you'd hand a regulator if they walked in tomorrow.",
)

result = st.session_state.result
run_dir = st.session_state.run_dir
df_decisions = st.session_state.df_decisions
manifest = result.manifest


tour_panel("Audit & Evidence")
tooltip_banner(
    "Audit & Evidence",
    "Every rule execution records a content hash so the same spec + "
    "same data + same engine = same output. The decision log is "
    "append-only. This is the regulator and auditor view.",
)

# --- Run identity: terminal-style header ---
# Hashes go in mono-font dark block (cyan) — the rest of the dashboard
# uses rounded SaaS cards, this page leans terminal.
rule_outputs = manifest.get("rule_outputs", {})
spec_hash = manifest.get("spec_content_hash", "")
output_hash = manifest.get("output_hash", "")
engine_version = manifest.get("engine_version", "n/a")
ts = manifest.get("ts", "")[:19] if manifest.get("ts") else ""

terminal_block(
    [
        ("Spec Hash", spec_hash or "—", "hash"),
        ("Output Hash", output_hash or "—", "hash"),
        ("Engine", engine_version, ""),
        ("Run At", ts or "—", ""),
    ]
)

st.markdown("<br>", unsafe_allow_html=True)

# --- KPI row — counts only (facts, not assessments) ---
c1, c2, c3 = st.columns(3)
with c1:
    kpi_card_rag("Rules Hashed", len(rule_outputs))
with c2:
    kpi_card_rag("Decisions Logged", len(df_decisions))
with c3:
    kpi_card_rag("Cases", len(getattr(result, "case_ids", [])))

# --- Integrity verification ---
st.markdown("<br>", unsafe_allow_html=True)
ver_col1, ver_col2 = st.columns([3, 1])
with ver_col1:
    st.markdown("### Integrity Verification")
with ver_col2:
    # Re-verify on demand — gives auditors an explicit ritual ("I clicked
    # Verify, the chain held, here's the timestamp") rather than relying
    # on the implicit auto-load check.
    if st.button("🔒 Re-verify chain", use_container_width=True):
        st.session_state["audit_last_verified"] = datetime.now(tz=timezone.utc).isoformat()

# Always show current integrity status.
valid, msg = AuditLedger.verify_decisions(run_dir)
last_verified = st.session_state.get("audit_last_verified")
if valid:
    rows = [("Status", "✓ chain verified", "ok"), ("Detail", msg, "")]
    if last_verified:
        rows.append(("Verified at", last_verified, ""))
    terminal_block(rows)
else:
    rows = [("Status", "✗ TAMPER DETECTED", "bad"), ("Detail", msg, "")]
    if last_verified:
        rows.append(("Verified at", last_verified, ""))
    terminal_block(rows)

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

# --- Per-rule hash chain (mono terminal block) ---
st.markdown("### Rule Output Hashes")
if rule_outputs:
    # Each rule rendered as a row in a single terminal block — looks
    # like a verification log rather than a sortable spreadsheet.
    # The hash kind class makes the SHA-256 cyan / fixed-width.
    terminal_block([(rid, h, "hash") for rid, h in rule_outputs.items()])
    st.caption(f"{len(rule_outputs)} rule output hashes — copy from any row.")

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

    # Colour the event-type column so analysts scanning the decision log
    # can distinguish escalations (red) from closures (green) at a glance.
    styled_decisions = filtered_decisions.style
    if "event" in filtered_decisions.columns:
        styled_decisions = styled_decisions.map(event_type_cell_style, subset=["event"])
    st.dataframe(
        styled_decisions,
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

    # Citations + resolvable + in-baseline are facts — neutral border.
    # Baseline-status carries an actual assessment: missing baseline =
    # red (drift detection unavailable); present = green.
    baseline_rag = "green" if _baseline else "red"
    rc1, rc2, rc3, rc4 = st.columns(4)
    with rc1:
        kpi_card_rag("Citations", len(citations))
    with rc2:
        kpi_card_rag("Resolvable URLs", resolved_count)
    with rc3:
        kpi_card_rag("In baseline", len(_baseline))
    with rc4:
        kpi_card_rag(
            "Baseline",
            str(_baseline_path) if _baseline else "(none)",
            rag=baseline_rag,
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


# ---------------------------------------------------------------------------
# Pre-examination Audit Pack (generators/audit_pack.py — Round-7 PR #78)
# ---------------------------------------------------------------------------
# FINTRAC's January 2026 examination manual update made the pre-exam
# evidence demand explicit. Examiners now expect institutions to arrive
# with a pre-built bundle covering rule inventory + alert volumes +
# case dispositions + audit-trail integrity + sanctions evidence +
# section coverage. The CLI `aml audit-pack` does this; the dashboard
# button serves the same shape for analysts who never leave the UI.
spec_for_pack = st.session_state.spec
st.markdown("---")
st.markdown("### Pre-Examination Audit Pack")
st.caption(
    "Deterministic ZIP for regulator submission: rule inventory, alert "
    "volumes, case dispositions, audit-trail integrity proof, sanctions "
    "evidence + jurisdiction-specific section maps. CLI equivalent: "
    "`aml audit-pack <spec> --jurisdiction <regulator>`."
)

if spec_for_pack.program.jurisdiction == "CA":
    try:
        import json as _json2
        from pathlib import Path as _Path2

        from aml_framework.generators.audit_pack import build_audit_pack

        # Load cases + decisions same way the funnel block does.
        _ap_run_dir = _Path2(st.session_state.run_dir)
        _ap_cases: list[dict] = []
        _ap_cases_dir = _ap_run_dir / "cases"
        if _ap_cases_dir.exists():
            for _f in sorted(_ap_cases_dir.glob("*.json")):
                _ap_cases.append(_json2.loads(_f.read_text(encoding="utf-8")))
        _ap_decisions: list[dict] = []
        _ap_dec_path = _ap_run_dir / "decisions.jsonl"
        if _ap_dec_path.exists():
            for _line in _ap_dec_path.read_text(encoding="utf-8").splitlines():
                _line = _line.strip()
                if _line:
                    _ap_decisions.append(_json2.loads(_line))

        _audit_pack_bytes = build_audit_pack(
            spec_for_pack,
            _ap_cases,
            _ap_decisions,
            jurisdiction="CA-FINTRAC",
        )
        st.download_button(
            "📥 FINTRAC Audit Pack (ZIP)",
            data=_audit_pack_bytes,
            file_name=f"{spec_for_pack.program.name.replace(' ', '_')}_fintrac_audit_pack.zip",
            mime="application/zip",
            help="9 files: program.md + inventory.json + alerts_summary.json + "
            "cases_summary.json + audit_trail_verification.json + "
            "sanctions_evidence.json + pcmltfa_section_map.md + "
            "osfi_b8_pillars.md + manifest.json (file-by-file SHA-256).",
        )
    except Exception as _ape:  # noqa: BLE001
        st.caption(f"Audit pack unavailable: {_ape}")
else:
    st.info(
        f"Pre-exam audit pack only ships for `CA-FINTRAC` in v1. "
        f"This spec's jurisdiction is `{spec_for_pack.program.jurisdiction}`. "
        "Future rounds will add UK FCA / EU AMLA / US FinCEN templates "
        "using the same generator skeleton."
    )

st.markdown("---")
st.caption(
    "**See also** · "
    '[PAIN-1 in research — "We can\'t prove what we did"]'
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-aml-process-pain.md)"
    " · [TD 2024 case study — the framing case for evidence-defensibility]"
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/case-studies/td-2024.md)"
    " · [FINTECH-1 — sponsor-bank cure notices]"
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-fintech-aml-reality.md)"
)

# Acronyms used on this page — leader-friendly expansions so the
# regulator-facing terminology stays visible without losing readers.
st.markdown(
    glossary_legend(["STR", "SAR", "FINTRAC", "OSFI", "FCA", "AMLA", "FinCEN", "MRM"]),
    unsafe_allow_html=True,
)
