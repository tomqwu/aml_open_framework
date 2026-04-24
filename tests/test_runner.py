from datetime import datetime
from pathlib import Path

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.spec import load_spec


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"


def test_end_to_end_detects_planted_structurer(tmp_path):
    spec = load_spec(EXAMPLE)
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)

    result = run_spec(
        spec=spec,
        spec_path=EXAMPLE,
        data=data,
        as_of=as_of,
        artifacts_root=tmp_path,
    )

    structuring_alerts = result.alerts["structuring_cash_deposits"]
    assert len(structuring_alerts) >= 1, "planted structurer must be alerted"

    # The planted structurer is customer C0001 (second id in the generator).
    assert any(a["customer_id"] == "C0001" for a in structuring_alerts)

    # Every alert must have a case file and an audit-ledger decision event.
    run_dir = Path(result.manifest["run_dir"])
    for alert in structuring_alerts:
        cases = list(
            (run_dir / "cases").glob(f"structuring_cash_deposits__{alert['customer_id']}*")
        )
        assert cases, f"missing case file for {alert['customer_id']}"

    decisions = (run_dir / "decisions.jsonl").read_bytes().splitlines()
    assert len(decisions) >= len(structuring_alerts)


def test_run_is_reproducible(tmp_path):
    spec = load_spec(EXAMPLE)
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)

    r1 = run_spec(
        spec=spec, spec_path=EXAMPLE, data=data, as_of=as_of, artifacts_root=tmp_path / "a"
    )
    r2 = run_spec(
        spec=spec, spec_path=EXAMPLE, data=data, as_of=as_of, artifacts_root=tmp_path / "b"
    )

    for rule_id, hash1 in r1.manifest["rule_outputs"].items():
        assert hash1 == r2.manifest["rule_outputs"][rule_id], (
            f"output hash drift on rule {rule_id} — non-deterministic engine"
        )
