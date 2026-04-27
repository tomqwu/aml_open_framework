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
from aml_framework.engine import run_spec
from aml_framework.paths import PROJECT_ROOT as _PROJECT_ROOT
from aml_framework.spec import load_spec

_DEFAULT_SPEC = _PROJECT_ROOT / "examples" / "community_bank" / "aml.yaml"


def _parse_cli_args() -> tuple[Path, int]:
    """Extract spec_path and seed from Streamlit's ``--`` pass-through args."""
    args = sys.argv[1:]
    # Streamlit injects its own args; ours come after ``--``.
    if "--" in args:
        args = args[args.index("--") + 1 :]
    spec_path = Path(args[0]) if len(args) >= 1 else _DEFAULT_SPEC
    seed = int(args[1]) if len(args) >= 2 else 42
    return spec_path, seed


def initialize_session() -> None:
    """Run the AML engine once, cache all results in ``st.session_state``."""
    if "initialized" in st.session_state:
        return

    spec_path, seed = _parse_cli_args()
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
        from aml_framework.data.sources import load_csv_source

        data = load_csv_source(data_input_dir, spec, as_of)
    else:
        data = generate_dataset(as_of=as_of, seed=seed)

    artifacts = Path(tempfile.mkdtemp(prefix="aml_dashboard_"))
    result = run_spec(
        spec=spec,
        spec_path=spec_path,
        data=data,
        as_of=as_of,
        artifacts_root=artifacts,
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

    # Store everything.
    st.session_state.update(
        initialized=True,
        spec=spec,
        spec_path=spec_path,
        data=data,
        result=result,
        run_dir=run_dir,
        as_of=as_of,
        seed=seed,
        df_alerts=df_alerts,
        df_customers=df_customers,
        df_txns=df_txns,
        df_metrics=df_metrics,
        df_cases=df_cases,
        df_decisions=df_decisions,
    )
