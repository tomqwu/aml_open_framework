"""Data Integration -- the data layer answer to "what data is flowing?"

This page is the operator-facing answer to the whitepaper's premise
(`docs/research/2026-05-aml-data-problem.md`): AML's biggest practical
problem is data integration, not detection. Five sections, each
mapping to one or more DATA-N pains the whitepaper enumerates.

  1. KPI strip — sources wired / contracts validated / freshness OK /
     checks passing. The 30-second answer to "is the data layer
     healthy on this run?"
  2. Source catalogue — the 9 connectors `data/sources.py` ships
     (synthetic + csv + parquet + duckdb + snowflake + bigquery +
     s3 + gcs + iso20022) with per-connector status (wired this run /
     configured / available). Closes DATA-7 (connect-once-validate-
     forever) and DATA-5 (in-bank, not SaaS — the source list IS the
     deployment topology).
  3. Contract roll-up — the same per-contract loop the Data Quality
     page runs, BUT relabelled in whitepaper vocabulary:
     completeness / accuracy / staleness / reconciliation. The
     whitepaper style guide (`:154`) explicitly tells us to avoid the
     bare phrase "data quality" with leaders. Closes DATA-1.
  4. ISO 20022 message types — counts of pacs.008 / pacs.009 /
     pacs.004 / pain.001 parsed this run. Empty-state when no
     iso20022 source. Closes DATA-8 (payment-rail data is its own
     integration, not a generic ETL pipeline).
  5. DATA-N → artifact map — the 11 whitepaper pains, each linked
     to its concrete framework artifact (page / CLI / module). Makes
     the whitepaper's claims falsifiable from inside the dashboard.

Persona: this page is the entry point for the Data Engineer / Head
of Data persona (`docs/personas.md:25-42`). `audience.py` routes them
here first; `show_audience_context` confirms it.

The page is read-only by design — operators inspect, they don't
configure. Configuration lives in `aml.yaml` (data_contracts) and
in the CLI flags (`aml run --data-source <type> --data-dir <path>`).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import (
    bar_chart,
    citation_link,
    data_grid,
    empty_state,
    kpi_card_rag,
    page_header,
    research_link,
    see_also_footer,
)

# ---------------------------------------------------------------------------
# Palettes — local to this page. FRESHNESS_PALETTE mirrors the one in
# pages/14_Data_Quality.py (same vocabulary). SOURCE_STATUS_PALETTE
# is local — three states unique to this page.
# ---------------------------------------------------------------------------
FRESHNESS_PALETTE = {"breach": "#dc2626", "ok": "#16a34a", "n/a": "#6b7280"}

SOURCE_STATUS_PALETTE = {
    "wired this run": "#16a34a",
    "configured": "#d97706",
    "available": "#6b7280",
}

# The 9 source types `data/sources.py::resolve_source` dispatches on,
# in the order they appear in `docs/getting-started.md` "Bring Your
# Own Data". Description is what shows in the catalogue's "What it
# does" column — short enough to read at a glance.
SOURCE_CATALOGUE: list[tuple[str, str]] = [
    ("synthetic", "Deterministic test data — `aml.data.synthetic` (default for demos)."),
    ("csv", "Per-contract CSV files in a directory — `--data-source csv --data-dir <dir>`."),
    ("parquet", "Per-contract Parquet files — `--data-source parquet --data-dir <dir>`."),
    ("duckdb", "Local DuckDB file with one table per contract — `--db-path <path>`."),
    ("snowflake", "DuckDB `snowflake` extension — connection string via `--data-dir`."),
    ("bigquery", "DuckDB `bigquery` extension — connection string via `--data-dir`."),
    ("s3", "S3 bucket of CSV/Parquet via DuckDB `httpfs` — `--data-dir s3://...`."),
    ("gcs", "GCS bucket of CSV/Parquet via DuckDB `httpfs` — `--data-dir gs://...`."),
    ("iso20022", "Directory of pacs.008 / pacs.009 / pacs.004 / pain.001 XML messages."),
]

# DATA-N → framework artifact map. Mirrors the table that ships in
# `docs/research/2026-05-aml-data-problem.md` (PR-DATAVIZ-2 will add
# the docs side). Keeping a single source of truth here means the
# page render IS the proof — when a row says "see Customer 360 →
# staleness column," the analyst can navigate there in one click.
DATA_N_MAP: list[dict[str, str]] = [
    {
        "DATA-N": "DATA-1 · Fail-closed contract validation",
        "See in framework": "Contract roll-up below · `pages/14_Data_Quality.py`",
        "CLI": "`aml validate-data <spec> <data-dir>`",
    },
    {
        "DATA-N": "DATA-2 · Per-attribute freshness pinning",
        "See in framework": "Customer 360 → staleness column · contract roll-up below",
        "CLI": "`aml run --strict` (refuses stale attributes)",
    },
    {
        "DATA-N": "DATA-3 · Cross-system reconciliation",
        "See in framework": "Stub — surfaced via `audit_evidence` page; richer view planned",
        "CLI": "`aml run` emits `reconciliation.jsonl` per contract",
    },
    {
        "DATA-N": "DATA-4 · Lineage walk-back from KPI",
        "See in framework": "Audit & Evidence → decision log · `walk_lineage()`",
        "CLI": "`aml export --include-lineage`",
    },
    {
        "DATA-N": "DATA-5 · In-bank, not SaaS (data sovereignty)",
        "See in framework": "Source catalogue below — deployment topology is the source list",
        "CLI": "Docker / Helm — see `deployment.md`",
    },
    {
        "DATA-N": "DATA-6 · AI presumes data (fail-closed gate)",
        "See in framework": "Closes transitively via DATA-1 · `engine/runner.py:_validate_contracts`",
        "CLI": "`aml run --strict` halts on contract violation",
    },
    {
        "DATA-N": "DATA-7 · Engineering vs Compliance ownership boundary",
        "See in framework": "Spec is the boundary · Spec Editor + this page",
        "CLI": "`aml validate <spec>` (engineering) + `aml attest` (compliance)",
    },
    {
        "DATA-N": "DATA-8 · Payment-rail data (ISO 20022 native)",
        "See in framework": "ISO 20022 message-type chart below",
        "CLI": "`aml run --data-source iso20022 --data-dir <xml-dir>`",
    },
    {
        "DATA-N": "DATA-9 · STR/SAR filing-latency wall-clock",
        "See in framework": "Audit & Evidence · `cases/<id>__filing.json` sidecars",
        "CLI": "`aml export` rolls filing latency into the bundle",
    },
    {
        "DATA-N": "DATA-10 · Cross-bank information sharing",
        "See in framework": "Information Sharing page · share-pattern artifacts",
        "CLI": "`aml share-pattern` / `aml verify-pattern`",
    },
    {
        "DATA-N": "DATA-11 · Spec as data contract (versioned, hashable)",
        "See in framework": "Audit & Evidence → spec hash on every run",
        "CLI": "`aml validate <spec>` (JSON Schema + Pydantic)",
    },
]


# ---------------------------------------------------------------------------
# Page render
# ---------------------------------------------------------------------------
page_header(
    "Data Integration",
    "What data is flowing through this AML program — sources, contracts, "
    "ISO 20022 messages, lineage. The 30-second answer to the whitepaper's "
    "11 data pains.",
)
show_audience_context("Data Integration")

spec = st.session_state.spec
data = st.session_state.data
as_of = st.session_state.as_of

# Source-type detection: the CLI / app harness writes `data_source` into
# session_state when --data-source is passed. Fall back to "synthetic"
# (the default) when missing. This is the only signal the dashboard has
# for "what's wired this run" without re-reading CLI args.
wired_source: str = (st.session_state.get("data_source") or "synthetic").lower()


# --- Empty-state guard: no contracts means nothing to assess ---
if not spec.data_contracts:
    empty_state(
        "No data contracts defined in this spec.",
        icon="📋",
        detail=(
            "Add `data_contracts` to your `aml.yaml` to surface freshness SLAs, "
            "column types, and quality checks here. See `docs/spec-reference.md` "
            "for the schema."
        ),
        stop=True,
    )

# ---------------------------------------------------------------------------
# Section 1 — KPI strip
# ---------------------------------------------------------------------------
# Compute four numbers: sources wired (always 1 — only one source per
# run), contracts validated (= len(data_contracts)), freshness OK count,
# checks passing count. The freshness + check counts come from the same
# loop as Section 3, so we share the work.
contract_results: list[dict] = []
total_checks = 0
total_passed = 0
total_freshness_ok = 0

for contract in spec.data_contracts:
    rows = data.get(contract.id, [])
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    n_rows = len(df)

    # Freshness check — same logic as Data Quality page.
    freshness_ok = True
    freshness_note = "n/a"
    if contract.freshness_sla and not df.empty:
        ts_cols = [c.name for c in contract.columns if c.type == "timestamp"]
        for ts_col in ts_cols:
            if ts_col in df.columns:
                latest = pd.to_datetime(df[ts_col]).max()
                if latest is not pd.NaT:
                    age_hours = (
                        as_of - latest.to_pydatetime().replace(tzinfo=None)
                    ).total_seconds() / 3600
                    freshness_note = f"{age_hours:.1f}h (SLA: {contract.freshness_sla})"
                    sla_val = int(contract.freshness_sla[:-1])
                    sla_unit = contract.freshness_sla[-1]
                    sla_hours = sla_val * {"s": 1 / 3600, "m": 1 / 60, "h": 1, "d": 24}[sla_unit]
                    if age_hours > sla_hours:
                        freshness_ok = False
                    break
    if freshness_ok:
        total_freshness_ok += 1

    # Quality-check pass count (per-check, not per-field).
    contract_passed = 0
    contract_total = 0
    for qc in contract.quality_checks:
        for check_type, fields in qc.items():
            for field in fields:
                if field not in df.columns:
                    continue
                contract_total += 1
                if check_type == "not_null" and int(df[field].isna().sum()) == 0:
                    contract_passed += 1
                elif check_type == "unique" and int(df[field].duplicated().sum()) == 0:
                    contract_passed += 1
    total_checks += contract_total
    total_passed += contract_passed

    # Completeness = 1 - (null_count / total_cells) across declared columns.
    declared = [c.name for c in contract.columns if c.name in df.columns]
    if declared and not df.empty:
        cells = len(df) * len(declared)
        nulls = int(sum(int(df[c].isna().sum()) for c in declared))
        completeness_pct = 100.0 * (1.0 - nulls / cells) if cells else 0.0
    else:
        completeness_pct = 0.0

    contract_results.append(
        {
            "contract_id": contract.id,
            "source": contract.source,
            "rows": n_rows,
            "freshness_status": "ok" if freshness_ok else "breach",
            "freshness_detail": freshness_note,
            "completeness_pct": round(completeness_pct, 1),
            "checks_passing": f"{contract_passed} / {contract_total}",
        }
    )

c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card_rag(
        "Source wired",
        wired_source,
        rag="green",
    )
with c2:
    kpi_card_rag("Contracts validated", len(spec.data_contracts))
with c3:
    rag = "green" if total_freshness_ok == len(spec.data_contracts) else "amber"
    kpi_card_rag(
        "Freshness OK",
        f"{total_freshness_ok} / {len(spec.data_contracts)}",
        rag=rag,
    )
with c4:
    rag = "green" if total_passed == total_checks else "red"
    kpi_card_rag(
        "Checks passing",
        f"{total_passed} / {total_checks}" if total_checks else "n/a",
        rag=rag if total_checks else None,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 2 — Source catalogue
# ---------------------------------------------------------------------------
st.markdown("### Source catalogue")
st.caption(
    "9 connectors ship in the framework. The status column shows which is "
    "wired this run; the rest are configured-but-idle (no data this run) "
    "or available-but-not-yet-touched."
)
catalogue_rows = []
for src_type, desc in SOURCE_CATALOGUE:
    if src_type == wired_source:
        status = "wired this run"
    elif src_type == "synthetic":
        # synthetic is configured-by-default — it's the demo source.
        status = "configured" if wired_source != "synthetic" else "wired this run"
    else:
        status = "available"
    catalogue_rows.append(
        {
            "Source": src_type,
            "Status": status,
            "What it does": desc,
        }
    )

data_grid(
    pd.DataFrame(catalogue_rows),
    key="data_integration_source_catalogue",
    palette_cols={"Status": SOURCE_STATUS_PALETTE},
    pinned_left=["Source"],
    height=min(35 * len(catalogue_rows) + 60, 400),
)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 3 — Contract roll-up (whitepaper vocabulary)
# ---------------------------------------------------------------------------
# Whitepaper style guide (docs/research/2026-05-aml-data-problem.md:154):
#   "data quality alone — too vague. Use completeness / accuracy /
#    staleness / reconciliation / lineage."
# So this section's columns avoid the bare phrase "Quality":
#   - Completeness  — % of declared cells non-null
#   - Staleness     — freshness state (ok / breach) + age vs SLA
#   - Checks        — passing-over-total per contract
# Reconciliation + lineage cells are stubs (DATA-3 / DATA-4) until the
# engine emits richer signals.
st.markdown("### Contract roll-up")
st.caption(
    "Per-contract scorecard in whitepaper vocabulary — completeness, "
    "staleness, checks. Reconciliation + lineage roll-up are stubs "
    "until the engine emits richer signals (DATA-3 / DATA-4)."
)
overview = pd.DataFrame(
    [
        {
            "Contract": r["contract_id"],
            "Source": r["source"],
            "Rows": r["rows"],
            "Completeness %": r["completeness_pct"],
            "Staleness": r["freshness_status"],
            "Staleness detail": r["freshness_detail"],
            "Checks": r["checks_passing"],
        }
        for r in contract_results
    ]
)
data_grid(
    overview,
    key="data_integration_contract_rollup",
    palette_cols={"Staleness": FRESHNESS_PALETTE},
    gradient_cols=["Completeness %"],
    gradient_low=80.0,
    gradient_high=99.0,
    pinned_left=["Contract"],
    height=min(35 * len(overview) + 60, 320),
)

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 4 — ISO 20022 message types
# ---------------------------------------------------------------------------
st.markdown("### ISO 20022 message types")
# Look for an `msg_kind` column anywhere in the loaded data — the
# parser stamps it on every row it materialises (`data/iso20022/parser.py`).
# Group + count to surface which message types this run consumed.
msg_counts: dict[str, int] = {}
for contract_id, rows in data.items():
    for row in rows:
        if isinstance(row, dict) and "msg_kind" in row:
            kind = str(row.get("msg_kind", "")).strip()
            if kind:
                msg_counts[kind] = msg_counts.get(kind, 0) + 1

if msg_counts:
    iso_df = pd.DataFrame([{"Message type": k, "Count": v} for k, v in sorted(msg_counts.items())])
    bar_chart(
        iso_df,
        x="Message type",
        y="Count",
        title="Parsed ISO 20022 messages this run",
        height=280,
        key="data_integration_iso_messages",
    )
else:
    empty_state(
        "No ISO 20022 messages parsed in this run.",
        icon="📨",
        detail=(
            "ISO 20022 parsing fires when `--data-source iso20022` is passed and "
            "the data directory contains pacs.008 / pacs.009 / pacs.004 / pain.001 "
            "XML files. Default demos use the synthetic source (no XML). "
            "Try `aml run examples/canadian_schedule_i_bank/aml.yaml "
            "--data-source iso20022 --data-dir src/aml_framework/data/iso20022/`."
        ),
    )

st.markdown("<br>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Section 5 — DATA-N → artifact map
# ---------------------------------------------------------------------------
st.markdown("### Whitepaper data pains → framework artifacts")
st.caption(
    "Every claim in the *Data is the AML problem* whitepaper, mapped to "
    "the concrete framework artifact that closes it. Click through to "
    "verify."
)
data_grid(
    pd.DataFrame(DATA_N_MAP),
    key="data_integration_data_n_map",
    pinned_left=["DATA-N"],
    height=min(35 * len(DATA_N_MAP) + 60, 460),
)

# ---------------------------------------------------------------------------
# See also (research + cross-page nav)
# ---------------------------------------------------------------------------
see_also_footer(
    [
        research_link(
            "Data is the AML problem — 11 faces, primary-source only",
            "2026-05-aml-data-problem.md",
        ),
        "[Data Quality — per-contract check detail](./Data_Quality)",
        "[Customer 360 — per-attribute view + staleness](./Customer_360)",
        "[Information Sharing — DATA-10 partner exchange](./Information_Sharing)",
        "[Audit & Evidence — DATA-4 lineage walk-back](./Audit_Evidence)",
        # Compliance manifest link — citation_link with a stub URL keeps
        # the helper exercised even when the spec doesn't carry a URL.
        citation_link("docs/spec-reference.md", "../../docs/spec-reference.md"),
    ]
)
