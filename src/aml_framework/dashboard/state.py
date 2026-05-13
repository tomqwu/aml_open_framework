"""Session state initialization — run the engine once and cache results."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from aml_framework.data import generate_dataset
from aml_framework.dashboard.tenants import (
    TenantConfig,
    load_tenants,
    resolve_tenant,
)
from aml_framework.engine import run_spec
from aml_framework.paths import PROJECT_ROOT as _PROJECT_ROOT
from aml_framework.spec import load_spec

_DEFAULT_SPEC = _PROJECT_ROOT / "examples" / "community_bank" / "aml.yaml"


def _parse_cli_args() -> tuple[Path | None, int]:
    """Extract optional spec_path and seed from Streamlit's ``--`` pass-through.

    When a CLI spec path is given it overrides the tenant registry — useful
    for `aml dashboard <spec.yaml>` ergonomics. When omitted (the multi-tenant
    case), spec resolution falls back to the tenant registry.
    """
    args = sys.argv[1:]
    if "--" in args:
        args = args[args.index("--") + 1 :]
    spec_path = Path(args[0]) if len(args) >= 1 else None
    seed = int(args[1]) if len(args) >= 2 else 42
    return spec_path, seed


def _resolve_spec_for_session(cli_spec: Path | None) -> tuple[Path, TenantConfig | None]:
    """Pick the spec to load.

    Precedence:
        1. Explicit CLI spec (single-tenant ergonomics; tenant left as None
           and the dashboard does not show a tenant selector).
        2. Session-state-selected tenant (operator switched via the sidebar).
        3. First tenant in the registry (default startup state).
    """
    if cli_spec is not None:
        return cli_spec, None
    selected_id = st.session_state.get("selected_tenant_id")
    tenant = resolve_tenant(selected_id)
    return tenant.spec_path, tenant


def ensure_initialized() -> None:
    """Idempotent guard for direct-URL hits to sub-pages.

    Streamlit's multipage layout runs the entry script (``app.py``) once
    when the user lands at the root URL, but a direct hit to ``/Today``
    (or any other sub-page URL — bookmark, deep link, refresh after a
    Container App revision rollover) only executes the page script.
    Without this guard, every page that reads ``st.session_state.spec``
    raises ``AttributeError`` because the entry script never ran.

    Also re-applies the custom theme CSS. Streamlit's ``[theme]`` block
    in ``.streamlit/config.toml`` sets the base palette on every page
    automatically, but the *custom* CSS in
    ``components.apply_theme()`` (which carries ``color-scheme: light``
    + every dna-* class our pages render against) is injected by
    ``app.py`` only. A direct sub-page hit on a browser running
    ``prefers-color-scheme: dark`` falls back to the browser UA — body
    bg goes black, slate-blue section headers vanish into it. Pinned
    by `tests/test_dashboard_pages_init_guard.py` so we can't drop the
    helper from a page silently.

    Call this at the top of every sub-page (after the imports, before
    any ``st.session_state.<x>`` read). Cheap no-op when state is
    already populated — ``initialize_session`` short-circuits on its
    cache_key check, and ``apply_theme`` is idempotent (Streamlit
    de-dupes identical ``st.markdown`` injections per rerun).
    """
    if "spec" not in st.session_state:
        initialize_session()
    # Re-apply the custom CSS — required even when state is already
    # populated, because Streamlit doesn't carry CSS injections across
    # the script-rerun boundary on a page navigation.
    from aml_framework.dashboard.components import apply_theme

    apply_theme()


def initialize_session() -> None:
    """Run the AML engine once per (tenant, seed), cache in ``st.session_state``."""
    cli_spec, seed = _parse_cli_args()
    spec_path, tenant = _resolve_spec_for_session(cli_spec)
    # Cache key includes tenant id + seed so switching tenants triggers a re-run
    # without losing previously-computed results for other tenants this session.
    cache_key = f"{tenant.id if tenant else 'cli'}:{seed}"
    if st.session_state.get("active_cache_key") == cache_key:
        return

    as_of = datetime.now(tz=timezone.utc).replace(tzinfo=None)

    spec = load_spec(spec_path)

    # Check for CSV files in data/input/ — use them if present.
    data_input_dir = _PROJECT_ROOT / "data" / "input"
    csv_files_present = (
        data_input_dir.exists()
        and (data_input_dir / "txn.csv").exists()
        and (data_input_dir / "customer.csv").exists()
    )
    if csv_files_present:
        from aml_framework.data.sources import infer_source_paths, load_csv_source

        data = load_csv_source(data_input_dir, spec, as_of)
        data_source_mode = "csv"
        data_sources = infer_source_paths("csv", spec, data_dir=str(data_input_dir))
    else:
        from aml_framework.data.sources import infer_source_paths

        data = generate_dataset(as_of=as_of, seed=seed)
        data_source_mode = "synthetic"
        data_sources = infer_source_paths("synthetic", spec)

    artifacts = Path(tempfile.mkdtemp(prefix="aml_dashboard_"))
    result = run_spec(
        spec=spec,
        spec_path=spec_path,
        data=data,
        as_of=as_of,
        artifacts_root=artifacts,
        data_sources=data_sources,
    )

    # Flatten alerts into a single DataFrame.
    alert_rows = []
    for rule_id, alerts in result.alerts.items():
        for a in alerts:
            row = {"rule_id": rule_id, **a}
            alert_rows.append(row)
    df_alerts = pd.DataFrame(alert_rows) if alert_rows else pd.DataFrame()

    df_customers = pd.DataFrame(data["customer"])
    df_txns = pd.DataFrame(data["txn"])
    # Convert Decimal to float for Plotly compatibility.
    if "amount" in df_txns.columns:
        df_txns["amount"] = df_txns["amount"].astype(float)

    # Metrics DataFrame.
    df_metrics = pd.DataFrame([m.to_dict() for m in result.metrics])

    # Cases from disk.
    run_dir = Path(result.manifest["run_dir"])
    case_rows = []
    cases_dir = run_dir / "cases"
    if cases_dir.exists():
        for f in sorted(cases_dir.glob("*.json")):
            case_rows.append(json.loads(f.read_bytes()))
    df_cases = pd.DataFrame(case_rows) if case_rows else pd.DataFrame()

    # Decisions from disk.
    decision_rows = []
    decisions_path = run_dir / "decisions.jsonl"
    if decisions_path.exists():
        for line in decisions_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                decision_rows.append(json.loads(line))
    df_decisions = pd.DataFrame(decision_rows) if decision_rows else pd.DataFrame()

    # Store everything. `active_cache_key` lets initialize_session detect
    # tenant switches and re-run without losing prior session preferences
    # (audience selector, guided-demo toggle).
    st.session_state.update(
        initialized=True,
        active_cache_key=cache_key,
        active_tenant=tenant,
        all_tenants=load_tenants() if tenant is not None else [],
        spec=spec,
        spec_path=spec_path,
        data=data,
        result=result,
        run_dir=run_dir,
        as_of=as_of,
        seed=seed,
        data_source_mode=data_source_mode,
        df_alerts=df_alerts,
        df_customers=df_customers,
        df_txns=df_txns,
        df_metrics=df_metrics,
        df_cases=df_cases,
        df_decisions=df_decisions,
    )
