"""Per-attribute freshness pinning + engine integration (PR-DATA-2).

Backs the "Data is the AML problem" whitepaper's DATA-2 claim that the
spec can pin a freshness requirement per attribute (`max_staleness_days`
+ `last_refreshed_at_column` on a `Column`) and the engine surfaces
stale-row violations as `pkyc_trigger` events in the audit ledger.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aml_framework.engine.freshness import (
    FreshnessViolation,
    scan_contract_freshness,
)
from aml_framework.engine.runner import run_spec
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


def _customer_contract_with_pinning() -> DataContract:
    """Contract pinning `risk_rating` to refresh every 365 days via the
    `last_kyc_review` timestamp."""
    return DataContract(
        id="customer",
        source="t_customer",
        columns=[
            Column(name="customer_id", type="string", nullable=False, pii=True),
            Column(name="full_name", type="string", nullable=False, pii=True),
            Column(
                name="risk_rating",
                type="string",
                nullable=False,
                max_staleness_days=365,
                last_refreshed_at_column="last_kyc_review",
            ),
            Column(name="last_kyc_review", type="timestamp", nullable=False),
        ],
    )


# ---------------------------------------------------------------------------
# Spec validation: freshness-pinning cross-references
# ---------------------------------------------------------------------------


def _build_spec_with_customer_columns(cols: list[Column]) -> AMLSpec:
    """Construct a minimal valid AMLSpec whose customer contract has the
    given columns. Used by the cross-reference validation tests below.
    """
    from datetime import date as _date

    return AMLSpec(
        version=1,
        program=Program(
            name="T",
            jurisdiction="US",
            regulator="FinCEN",
            owner="MLRO",
            effective_date=_date(2026, 1, 1),
        ),
        data_contracts=[
            DataContract(id="customer", source="s_customer", columns=cols),
        ],
        rules=[
            Rule(
                id="r",
                name="R",
                severity="low",
                regulation_refs=[RegulationRef(citation="x", description="x")],
                logic=AggregationWindowLogic(
                    type="aggregation_window",
                    source="customer",
                    group_by=["customer_id"],
                    window="7d",
                    having={"count": {"gte": 1}},
                ),
                escalate_to="q1",
                evidence=[],
            )
        ],
        workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
    )


_BASE_COLS = [
    Column(name="customer_id", type="string", nullable=False, pii=True),
    Column(name="full_name", type="string", nullable=False, pii=True),
]


class TestFreshnessPinningCrossReferences:
    def test_max_staleness_without_ref_column_fails(self):
        with pytest.raises(ValueError, match="must be set together"):
            _build_spec_with_customer_columns(
                _BASE_COLS
                + [
                    Column(
                        name="risk_rating",
                        type="string",
                        max_staleness_days=365,
                        # missing last_refreshed_at_column
                    ),
                ]
            )

    def test_ref_column_without_max_staleness_fails(self):
        with pytest.raises(ValueError, match="must be set together"):
            _build_spec_with_customer_columns(
                _BASE_COLS
                + [
                    Column(
                        name="risk_rating",
                        type="string",
                        last_refreshed_at_column="last_kyc_review",
                        # missing max_staleness_days
                    ),
                    Column(name="last_kyc_review", type="timestamp"),
                ]
            )

    def test_unknown_ref_column_fails(self):
        with pytest.raises(ValueError, match="unknown `last_refreshed_at_column`"):
            _build_spec_with_customer_columns(
                _BASE_COLS
                + [
                    Column(
                        name="risk_rating",
                        type="string",
                        max_staleness_days=365,
                        last_refreshed_at_column="nonexistent_column",
                    ),
                ]
            )

    def test_ref_column_wrong_type_fails(self):
        with pytest.raises(ValueError, match="not `timestamp` or `date`"):
            _build_spec_with_customer_columns(
                _BASE_COLS
                + [
                    Column(
                        name="risk_rating",
                        type="string",
                        max_staleness_days=365,
                        last_refreshed_at_column="full_name",  # string, not timestamp
                    ),
                ]
            )

    def test_valid_pinning_passes(self):
        # All cross-references valid — should construct cleanly.
        _build_spec_with_customer_columns(
            _BASE_COLS
            + [
                Column(
                    name="risk_rating",
                    type="string",
                    max_staleness_days=365,
                    last_refreshed_at_column="last_kyc_review",
                ),
                Column(name="last_kyc_review", type="timestamp"),
            ]
        )


# ---------------------------------------------------------------------------
# scan_contract_freshness: pure scanning logic
# ---------------------------------------------------------------------------


class TestFreshnessScanner:
    def test_no_pinned_columns_returns_empty(self):
        contract = DataContract(
            id="customer",
            source="t",
            columns=[Column(name="customer_id", type="string", nullable=False)],
        )
        rows = [{"customer_id": "C0001"}]
        assert scan_contract_freshness(contract, rows, _AS_OF) == []

    def test_no_rows_returns_empty(self):
        contract = _customer_contract_with_pinning()
        assert scan_contract_freshness(contract, [], _AS_OF) == []

    def test_fresh_row_no_violation(self):
        contract = _customer_contract_with_pinning()
        rows = [
            {
                "customer_id": "C0001",
                "full_name": "Alice",
                "risk_rating": "low",
                "last_kyc_review": _AS_OF - timedelta(days=30),  # well within 365d
            }
        ]
        assert scan_contract_freshness(contract, rows, _AS_OF) == []

    def test_stale_row_flagged(self):
        contract = _customer_contract_with_pinning()
        rows = [
            {
                "customer_id": "C0042",
                "full_name": "Bob",
                "risk_rating": "high",
                "last_kyc_review": _AS_OF - timedelta(days=400),  # over 365d
            }
        ]
        violations = scan_contract_freshness(contract, rows, _AS_OF)
        assert len(violations) == 1
        v = violations[0]
        assert v.contract_id == "customer"
        assert v.column_name == "risk_rating"
        assert v.row_id == "C0042"
        assert v.age_days == 400
        assert v.max_staleness_days == 365

    def test_iso_string_timestamps_parsed(self):
        contract = _customer_contract_with_pinning()
        rows = [
            {
                "customer_id": "C0001",
                "full_name": "Alice",
                "risk_rating": "low",
                "last_kyc_review": (_AS_OF - timedelta(days=500)).isoformat(),
            }
        ]
        violations = scan_contract_freshness(contract, rows, _AS_OF)
        assert len(violations) == 1
        assert violations[0].age_days == 500

    def test_null_timestamp_skipped(self):
        # Missing timestamps surface elsewhere as data-quality warnings;
        # the freshness scanner skips them rather than double-flagging.
        contract = _customer_contract_with_pinning()
        rows = [
            {
                "customer_id": "C0001",
                "full_name": "Alice",
                "risk_rating": "low",
                "last_kyc_review": None,
            }
        ]
        assert scan_contract_freshness(contract, rows, _AS_OF) == []

    def test_to_event_shape(self):
        v = FreshnessViolation(
            contract_id="customer",
            column_name="risk_rating",
            refreshed_at_column="last_kyc_review",
            row_id="C0042",
            refreshed_at=_AS_OF - timedelta(days=400),
            age_days=400,
            max_staleness_days=365,
        )
        event = v.to_event()
        assert event["event"] == "pkyc_trigger"
        assert event["kind"] == "stale_field"
        assert event["contract_id"] == "customer"
        assert event["column"] == "risk_rating"
        assert event["row_id"] == "C0042"
        assert event["age_days"] == 400


# ---------------------------------------------------------------------------
# Engine integration: run_spec emits pkyc_trigger events to the ledger
# ---------------------------------------------------------------------------


class TestEngineEmitsFreshnessEvents:
    def test_run_spec_emits_pkyc_trigger_for_stale_data(self, tmp_path: Path):
        # Use community_bank as the base spec, but feed it data where the
        # customer contract's `onboarded_at` (typed `timestamp`) is too
        # old. We'll need to extend community_bank's customer contract
        # in-memory with a max_staleness_days pin on `risk_rating` —
        # community_bank ships without freshness pinning.
        src = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"
        spec = load_spec(src)

        # Patch the customer contract's risk_rating column to pin
        # freshness against `onboarded_at` (already on the contract).
        # The Pydantic model is frozen, so we rebuild the spec with the
        # patched column rather than mutate.
        from aml_framework.spec.models import Column as _Column

        new_data_contracts = []
        for contract in spec.data_contracts:
            if contract.id != "customer":
                new_data_contracts.append(contract)
                continue
            new_cols = []
            for col in contract.columns:
                if col.name == "risk_rating":
                    new_cols.append(
                        _Column(
                            name="risk_rating",
                            type=col.type,
                            nullable=col.nullable,
                            pii=col.pii,
                            enum=col.enum,
                            max_staleness_days=180,
                            last_refreshed_at_column="onboarded_at",
                        )
                    )
                else:
                    new_cols.append(col)
            new_data_contracts.append(
                DataContract(
                    id=contract.id,
                    source=contract.source,
                    freshness_sla=contract.freshness_sla,
                    columns=new_cols,
                    quality_checks=contract.quality_checks,
                )
            )
        spec = spec.model_copy(update={"data_contracts": new_data_contracts})

        # Build data with one stale customer (onboarded 1 year ago, pin is
        # 180d) and one fresh customer (onboarded 30d ago).
        old_ts = _AS_OF - timedelta(days=365)
        new_ts = _AS_OF - timedelta(days=30)
        # One minimal txn row is enough to give the engine a typed warehouse;
        # without it `CREATE TABLE txn AS SELECT NULL WHERE 1=0` produces a
        # column-less table and rule SQL fails to bind. The freshness
        # scanner runs against the customer contract regardless.
        data = {
            "customer": [
                {
                    "customer_id": "C-STALE",
                    "full_name": "Stale Sam",
                    "country": "US",
                    "risk_rating": "high",
                    "onboarded_at": old_ts,
                },
                {
                    "customer_id": "C-FRESH",
                    "full_name": "Fresh Felicity",
                    "country": "US",
                    "risk_rating": "low",
                    "onboarded_at": new_ts,
                },
            ],
            "txn": [
                {
                    "txn_id": "T0001",
                    "customer_id": "C-FRESH",
                    "amount": 100.0,
                    "currency": "USD",
                    "channel": "wire",
                    "direction": "out",
                    "booked_at": _AS_OF,
                }
            ],
        }

        result = run_spec(
            spec=spec,
            spec_path=src,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        assert result.manifest is not None

        run_dirs = sorted(tmp_path.glob("run-*"))
        decisions_text = (run_dirs[-1] / "decisions.jsonl").read_text(encoding="utf-8")
        # Stale customer should appear; fresh one should not.
        assert "pkyc_trigger" in decisions_text
        assert "stale_field" in decisions_text
        assert "C-STALE" in decisions_text
        assert "C-FRESH" not in decisions_text

    def test_run_spec_with_no_pinned_columns_emits_no_pkyc_events(self, tmp_path: Path):
        from aml_framework.data.synthetic import generate_dataset

        src = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"
        spec = load_spec(src)
        data = generate_dataset(as_of=_AS_OF, seed=42)
        run_spec(
            spec=spec,
            spec_path=src,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dirs = sorted(tmp_path.glob("run-*"))
        decisions_text = (run_dirs[-1] / "decisions.jsonl").read_text(encoding="utf-8")
        # community_bank ships without freshness pinning; no pkyc events.
        assert "pkyc_trigger" not in decisions_text
