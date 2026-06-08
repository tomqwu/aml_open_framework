"""Fraud↔AML cross-program case links — `case_links.jsonl` (#523).

Covers:
- the runner writes `case_links.jsonl` to the run dir;
- a customer with cases in BOTH the fraud and AML domains produces a
  cross-program link (`aml_priority: fraud` vs anything else);
- a customer in only one domain produces NO link;
- the artifact is always written (empty file) when nothing links;
- the manifest pins the artifact's SHA-256 hash;
- `case_links.jsonl` is in `_FROZEN_SNAPSHOT_TARGETS`;
- `_write_case_links` is byte-stable + masks customer_id when asked;
- the bundled `uk_app_fraud` example produces ≥1 cross-program link.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date as _date, datetime, timezone
from pathlib import Path

from aml_framework.cases.linkage import LinkedCustomer
from aml_framework.engine.audit import _FROZEN_SNAPSHOT_TARGETS
from aml_framework.engine.runner import _write_case_links, run_spec
from aml_framework.spec.loader import load_spec
from aml_framework.spec.models import (
    AggregationWindowLogic,
    AMLSpec,
    Column,
    DataContract,
    Program,
    Queue,
    RegulationRef,
    Rule,
    Workflow,
)

_AS_OF = datetime(2026, 5, 1, tzinfo=timezone.utc)


def _txn_contract() -> DataContract:
    return DataContract(
        id="txn",
        source="t",
        columns=[
            Column(name="txn_id", type="string", nullable=False),
            Column(name="customer_id", type="string", nullable=False, pii=True),
            Column(name="amount", type="decimal", nullable=False),
            Column(name="booked_at", type="timestamp", nullable=False),
        ],
    )


def _rule(rule_id: str, *, aml_priority: str | None) -> Rule:
    return Rule(
        id=rule_id,
        name=rule_id,
        severity="high",
        aml_priority=aml_priority,  # type: ignore[arg-type]
        regulation_refs=[RegulationRef(citation="x", description="x")],
        logic=AggregationWindowLogic(
            type="aggregation_window",
            source="txn",
            group_by=["customer_id"],
            window="365d",
            having={"count": {"gte": 1}, "sum_amount": {"gte": 1}},
        ),
        escalate_to="q1",
        evidence=[],
    )


def _make_spec(rules: list[Rule]) -> AMLSpec:
    return AMLSpec(
        version=1,
        program=Program(
            name="T",
            jurisdiction="US",
            regulator="FinCEN",
            owner="MLRO",
            effective_date=_date(2026, 1, 1),
        ),
        data_contracts=[_txn_contract()],
        rules=rules,
        workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
    )


def _run(tmp_path: Path, spec: AMLSpec, data: dict) -> Path:
    spec_path = tmp_path / "spec.yaml"
    spec_path.write_text("placeholder: 1\n", encoding="utf-8")
    run_spec(
        spec=spec,
        spec_path=spec_path,
        data=data,
        as_of=_AS_OF,
        artifacts_root=tmp_path,
    )
    return sorted(tmp_path.glob("run-*"))[-1]


def _txn(tid: str, cid: str) -> dict:
    return {"txn_id": tid, "customer_id": cid, "amount": 10.0, "booked_at": _AS_OF}


# ---------------------------------------------------------------------------
# Runner integration
# ---------------------------------------------------------------------------


def test_runner_emits_cross_program_link(tmp_path: Path):
    # One fraud-domain rule + one AML-domain rule, both firing on C1.
    spec = _make_spec(
        [
            _rule("fraud_rule", aml_priority="fraud"),
            _rule("aml_rule", aml_priority="corruption"),
        ]
    )
    run_dir = _run(tmp_path, spec, {"txn": [_txn("T1", "C1")]})
    path = run_dir / "case_links.jsonl"
    assert path.exists(), "case_links.jsonl must always be written"

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 1
    link = rows[0]
    assert link["customer_id"] == "C1"
    assert link["fraud_rule_ids"] == ["fraud_rule"]
    assert link["aml_rule_ids"] == ["aml_rule"]
    assert link["total_case_count"] == 2
    assert link["severity"] == "high"


def test_runner_masks_compound_case_ids_under_pii_masking(tmp_path: Path, monkeypatch):
    # Codex #536 P2-1: with AML_PII_MASKING on, neither the top-level
    # customer_id NOR the customer-id substring embedded in each compound
    # case_id may appear in plaintext in case_links.jsonl. The `txn`
    # contract here marks customer_id pii=true, so the ledger masks it.
    monkeypatch.setenv("AML_PII_MASKING", "1")
    spec = _make_spec(
        [
            _rule("fraud_rule", aml_priority="fraud"),
            _rule("aml_rule", aml_priority="corruption"),
        ]
    )
    run_dir = _run(tmp_path, spec, {"txn": [_txn("T1", "C1")]})
    text = (run_dir / "case_links.jsonl").read_text(encoding="utf-8")
    assert text.strip(), "expected one masked cross-program link"
    assert "C1" not in text, "raw customer_id leaked into case_links.jsonl"
    row = json.loads(text.splitlines()[0])
    assert row["customer_id"] != "C1"
    # Every compound case_id has its customer token replaced by the same
    # hash as the top-level customer_id (consistent with the pii_map).
    masked_cid = row["customer_id"]
    for cid in row["fraud_case_ids"] + row["aml_case_ids"]:
        assert masked_cid in cid.split("__")
        assert "C1" not in cid


def test_single_domain_customer_produces_no_link(tmp_path: Path):
    # Both rules are fraud-domain — no AML case, so no cross-program link.
    spec = _make_spec(
        [
            _rule("fraud_rule_a", aml_priority="fraud"),
            _rule("fraud_rule_b", aml_priority="fraud"),
        ]
    )
    run_dir = _run(tmp_path, spec, {"txn": [_txn("T1", "C1")]})
    path = run_dir / "case_links.jsonl"
    assert path.exists()
    assert path.read_bytes() == b"", "no link → empty (but present) artifact"


def test_artifact_always_written_with_no_rules(tmp_path: Path):
    run_dir = _run(tmp_path, _make_spec([]), {"txn": []})
    path = run_dir / "case_links.jsonl"
    assert path.exists()
    assert path.read_bytes() == b""


def test_manifest_pins_case_links_hash(tmp_path: Path):
    spec = _make_spec(
        [
            _rule("fraud_rule", aml_priority="fraud"),
            _rule("aml_rule", aml_priority="cybercrime"),
        ]
    )
    run_dir = _run(tmp_path, spec, {"txn": [_txn("T1", "C1")]})
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    expected = hashlib.sha256((run_dir / "case_links.jsonl").read_bytes()).hexdigest()
    assert manifest["case_links_hash"] == expected


def test_artifact_in_frozen_snapshot_targets():
    assert "case_links.jsonl" in _FROZEN_SNAPSHOT_TARGETS


# ---------------------------------------------------------------------------
# `_write_case_links` unit
# ---------------------------------------------------------------------------


def _linked(cid: str = "C1") -> LinkedCustomer:
    return LinkedCustomer(
        customer_id=cid,
        fraud_case_ids=["fraud_rule__C1__x"],
        aml_case_ids=["aml_rule__C1__x"],
        fraud_rule_ids=["fraud_rule"],
        aml_rule_ids=["aml_rule"],
        severity="high",
    )


def test_write_case_links_is_byte_stable(tmp_path: Path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _write_case_links(a, [_linked()])
    _write_case_links(b, [_linked()])
    assert (a / "case_links.jsonl").read_bytes() == (b / "case_links.jsonl").read_bytes()


def test_write_case_links_masks_customer_id_and_compound_case_ids(tmp_path: Path):
    # Codex #536 P2-1: the compound case_id embeds the plaintext customer
    # id (<rule>__<customer>__<ts>), so masking must token-mask that
    # substring too — exactly like audit_pack._mask_compound_string — or
    # the customer id leaks through the *_case_ids lists. Use an opaque
    # hash-like masker (as the real HMAC masker is) so the no-leak
    # assertion is meaningful.
    _write_case_links(tmp_path, [_linked("C1")], mask_customer_id=lambda v: "deadbeefdeadbeef")
    rows = [
        json.loads(line)
        for line in (tmp_path / "case_links.jsonl").read_text().splitlines()
        if line
    ]
    assert rows[0]["customer_id"] == "deadbeefdeadbeef"
    # The customer-id token inside each compound case_id is masked; the
    # rule_id and timestamp tokens are preserved.
    assert rows[0]["fraud_case_ids"] == ["fraud_rule__deadbeefdeadbeef__x"]
    assert rows[0]["aml_case_ids"] == ["aml_rule__deadbeefdeadbeef__x"]
    # rule_id lists carry no customer id and stay verbatim.
    assert rows[0]["fraud_rule_ids"] == ["fraud_rule"]
    # No plaintext customer id survives anywhere in the file.
    assert "C1" not in (tmp_path / "case_links.jsonl").read_text()


def test_write_case_links_preserves_case_ids_when_masking_off(tmp_path: Path):
    # With masking off (mask_customer_id=None) the raw compound ids are
    # written verbatim so they still reference the on-disk cases/*.json.
    _write_case_links(tmp_path, [_linked("C1")])
    rows = [
        json.loads(line)
        for line in (tmp_path / "case_links.jsonl").read_text().splitlines()
        if line
    ]
    assert rows[0]["customer_id"] == "C1"
    assert rows[0]["fraud_case_ids"] == ["fraud_rule__C1__x"]
    assert rows[0]["aml_case_ids"] == ["aml_rule__C1__x"]


def test_write_case_links_empty_is_empty_file(tmp_path: Path):
    _write_case_links(tmp_path, [])
    assert (tmp_path / "case_links.jsonl").read_bytes() == b""


# ---------------------------------------------------------------------------
# Bundled example
# ---------------------------------------------------------------------------


def test_uk_app_fraud_example_links_fraud_and_aml(tmp_path: Path):
    """The #523 demonstrator: the planted mule C0019 trips a fraud-domain
    rule and the AML-domain layering rule, so the run emits a link."""
    from aml_framework.data.synthetic import generate_dataset

    spec = load_spec("examples/uk_app_fraud/aml.yaml")
    data = generate_dataset(as_of=_AS_OF, seed=42)
    run_dir = _run(tmp_path, spec, data)
    rows = [
        json.loads(line) for line in (run_dir / "case_links.jsonl").read_text().splitlines() if line
    ]
    assert rows, "uk_app_fraud must produce ≥1 cross-program link"
    c0019 = [r for r in rows if r["customer_id"] == "C0019"]
    assert c0019, "C0019 (the planted mule) must be linked across fraud and AML"
    link = c0019[0]
    assert "rapid_pass_through_mule" in link["fraud_rule_ids"]
    assert "rapid_outbound_dispersal" in link["aml_rule_ids"]
