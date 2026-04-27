"""FATF R.16 Travel Rule validator tests.

Round-5 PR #2 — composes with PR #56 ISO 20022 ingestion. The
validator runs as a python_ref scorer against the `txn` table; tests
spin up an in-memory DuckDB with a synthetic txn schema and exercise:
  - threshold logic (per-currency, env-overridable)
  - cross-border detection
  - field-completeness checks (originator + beneficiary)
  - severity scaling
  - schema-tolerant column discovery (older specs without the
    iso20022 columns must still run, just flag everything as missing)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import duckdb
import pytest

from aml_framework.models.travel_rule import (
    DEFAULT_THRESHOLDS,
    _crosses_threshold,
    _is_cross_border,
    _missing_fields,
    _resolve_thresholds,
    validate_travel_rule,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_FULL_TXN_COLS = (
    "txn_id VARCHAR",
    "customer_id VARCHAR",
    "amount DECIMAL(20, 2)",
    "currency VARCHAR",
    "channel VARCHAR",
    "direction VARCHAR",
    "booked_at TIMESTAMP",
    "debtor_iban VARCHAR",
    "debtor_country VARCHAR",
    "debtor_bic VARCHAR",
    "counterparty_name VARCHAR",
    "counterparty_country VARCHAR",
    "counterparty_account VARCHAR",
    "uetr VARCHAR",
    "purpose_code VARCHAR",
)


def _con(rows: list[dict], cols: tuple[str, ...] = _FULL_TXN_COLS) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute(f"CREATE TABLE txn ({', '.join(cols)})")
    if not rows:
        return con
    col_names = [c.split()[0] for c in cols]
    placeholders = ", ".join(["?"] * len(col_names))
    for r in rows:
        values = [r.get(name) for name in col_names]
        con.execute(f"INSERT INTO txn VALUES ({placeholders})", values)
    return con


def _full_row(**overrides) -> dict:
    """A complete, R.16-compliant cross-border wire."""
    base = {
        "txn_id": "T001",
        "customer_id": "OLENA KOWALSKI",
        "amount": Decimal("5000.00"),
        "currency": "EUR",
        "channel": "wire",
        "direction": "out",
        "booked_at": datetime(2026, 4, 27),
        "debtor_iban": "DE89370400440532013000",
        "debtor_country": "DE",
        "debtor_bic": "DEUTDEFFXXX",
        "counterparty_name": "ACME TRADING SARL",
        "counterparty_country": "FR",
        "counterparty_account": "FR1420041010050500013M02606",
        "uetr": "11111111-2222-3333-4444-555555555555",
        "purpose_code": "GDDS",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Threshold + cross-border helpers
# ---------------------------------------------------------------------------


class TestThresholdHelpers:
    def test_default_thresholds_cover_majors(self):
        for ccy in ("USD", "EUR", "GBP", "CAD", "CHF", "JPY", "AUD", "CNY"):
            assert ccy in DEFAULT_THRESHOLDS

    def test_resolve_thresholds_returns_defaults(self, monkeypatch):
        monkeypatch.delenv("AML_TRAVEL_RULE_THRESHOLDS", raising=False)
        assert _resolve_thresholds() == DEFAULT_THRESHOLDS

    def test_env_override_replaces_per_currency(self, monkeypatch):
        monkeypatch.setenv("AML_TRAVEL_RULE_THRESHOLDS", "USD=500,GBP=900")
        out = _resolve_thresholds()
        assert out["USD"] == Decimal("500")
        assert out["GBP"] == Decimal("900")
        # Untouched currency keeps its default.
        assert out["EUR"] == Decimal("1000")

    def test_env_invalid_token_skipped(self, monkeypatch):
        monkeypatch.setenv("AML_TRAVEL_RULE_THRESHOLDS", "USD=NaN,EUR=750")
        out = _resolve_thresholds()
        assert out["USD"] == Decimal("1000")  # invalid → fallback
        assert out["EUR"] == Decimal("750")

    def test_crosses_threshold_eur(self):
        thresholds = {"EUR": Decimal("1000")}
        assert _crosses_threshold({"amount": Decimal("1000"), "currency": "EUR"}, thresholds)
        assert (
            _crosses_threshold({"amount": Decimal("999.99"), "currency": "EUR"}, thresholds)
            is False
        )

    def test_unknown_currency_uses_1000_default(self):
        thresholds = {"EUR": Decimal("1000")}
        assert _crosses_threshold({"amount": Decimal("1500"), "currency": "ZAR"}, thresholds)


class TestCrossBorder:
    def test_different_countries_is_cross_border(self):
        assert _is_cross_border({"debtor_country": "DE", "counterparty_country": "FR"})

    def test_same_country_is_domestic(self):
        assert _is_cross_border({"debtor_country": "DE", "counterparty_country": "DE"}) is False

    def test_missing_country_treated_as_cross_border(self):
        # Conservative AML default: unknown country = treat as cross-border.
        assert _is_cross_border({"debtor_country": "DE", "counterparty_country": ""})
        assert _is_cross_border({"debtor_country": "", "counterparty_country": "FR"})


# ---------------------------------------------------------------------------
# Field completeness
# ---------------------------------------------------------------------------


class TestMissingFields:
    def test_complete_row_has_no_missing_fields(self):
        assert _missing_fields(_full_row()) == []

    def test_missing_originator_account_flagged(self):
        row = _full_row(debtor_iban="")
        assert "originator_account" in _missing_fields(row)

    def test_missing_originator_address_flagged(self):
        row = _full_row(debtor_country="")
        assert "originator_address_or_id" in _missing_fields(row)

    def test_originator_address_satisfied_by_alternate_column(self):
        # National_id satisfies the OR-logic.
        row = _full_row(debtor_country="")
        row["debtor_national_id"] = "DE-XXX"
        assert "originator_address_or_id" not in _missing_fields(row)

    def test_missing_beneficiary_account_flagged(self):
        row = _full_row(counterparty_account="")
        assert "beneficiary_account" in _missing_fields(row)

    def test_missing_beneficiary_name_flagged(self):
        row = _full_row(counterparty_name="")
        assert "beneficiary_name" in _missing_fields(row)

    def test_whitespace_value_treated_as_missing(self):
        row = _full_row(counterparty_name="   ")
        assert "beneficiary_name" in _missing_fields(row)


# ---------------------------------------------------------------------------
# End-to-end scorer
# ---------------------------------------------------------------------------


class TestValidateTravelRule:
    def test_complete_xborder_wire_no_alert(self):
        con = _con([_full_row()])
        assert validate_travel_rule(con, datetime(2026, 4, 27)) == []

    def test_missing_field_xborder_fires(self):
        con = _con([_full_row(counterparty_account="")])
        alerts = validate_travel_rule(con, datetime(2026, 4, 27))
        assert len(alerts) == 1
        a = alerts[0]
        assert "beneficiary_account" in a["missing_fields"]
        assert a["is_cross_border"] is True
        assert a["rule_kind"] == "travel_rule_completeness"
        assert "FATF R.16" in a["explanation"]

    def test_below_threshold_no_alert(self):
        # EUR 500 is below the EUR 1000 threshold even though field is missing.
        con = _con([_full_row(amount=Decimal("500.00"), counterparty_account="")])
        assert validate_travel_rule(con, datetime(2026, 4, 27)) == []

    def test_domestic_wire_no_alert(self):
        # Same-country wire — R.16 doesn't require full-fields domestically.
        con = _con([_full_row(counterparty_country="DE", counterparty_account="")])
        assert validate_travel_rule(con, datetime(2026, 4, 27)) == []

    def test_non_wire_channel_skipped(self):
        # Cash deposit, even cross-border + missing fields, isn't a wire.
        con = _con([_full_row(channel="cash", counterparty_account="")])
        assert validate_travel_rule(con, datetime(2026, 4, 27)) == []

    def test_severity_hint_critical_at_10x_threshold(self):
        con = _con([_full_row(amount=Decimal("10000.00"), counterparty_account="")])
        alerts = validate_travel_rule(con, datetime(2026, 4, 27))
        assert alerts[0]["severity_hint"] == "critical"

    def test_severity_hint_high_below_10x(self):
        con = _con([_full_row(amount=Decimal("5000.00"), counterparty_account="")])
        alerts = validate_travel_rule(con, datetime(2026, 4, 27))
        assert alerts[0]["severity_hint"] == "high"

    def test_uetr_and_purpose_code_propagate_to_alert(self):
        con = _con(
            [
                _full_row(
                    counterparty_account="",
                    uetr="abcd-1234",
                    purpose_code="INVS",
                )
            ]
        )
        a = validate_travel_rule(con, datetime(2026, 4, 27))[0]
        assert a["uetr"] == "abcd-1234"
        assert a["purpose_code"] == "INVS"

    def test_multiple_missing_fields_all_listed(self):
        row = _full_row(counterparty_name="", counterparty_account="")
        alerts = validate_travel_rule(_con([row]), datetime(2026, 4, 27))
        assert "beneficiary_name" in alerts[0]["missing_fields"]
        assert "beneficiary_account" in alerts[0]["missing_fields"]

    def test_one_alert_per_offending_row(self):
        rows = [
            _full_row(txn_id="T1", counterparty_account=""),  # alert
            _full_row(txn_id="T2"),  # no alert
            _full_row(txn_id="T3", counterparty_name=""),  # alert
        ]
        alerts = validate_travel_rule(_con(rows), datetime(2026, 4, 27))
        assert {a["txn_id"] for a in alerts} == {"T1", "T3"}


# ---------------------------------------------------------------------------
# Schema tolerance — old txn schema without iso20022 columns
# ---------------------------------------------------------------------------


class TestSchemaTolerance:
    def test_runs_against_minimal_schema(self):
        # Older synthetic txn schema: 7 columns, none of the iso20022 extras.
        cols = (
            "txn_id VARCHAR",
            "customer_id VARCHAR",
            "amount DECIMAL(20, 2)",
            "currency VARCHAR",
            "channel VARCHAR",
            "direction VARCHAR",
            "booked_at TIMESTAMP",
        )
        rows = [
            {
                "txn_id": "T001",
                "customer_id": "C0001",
                "amount": Decimal("5000.00"),
                "currency": "EUR",
                "channel": "wire",
                "direction": "out",
                "booked_at": datetime(2026, 4, 27),
            }
        ]
        con = _con(rows, cols=cols)
        # Missing IBAN + missing counterparty_name + counterparty_account →
        # all originator/beneficiary fields should be flagged.
        alerts = validate_travel_rule(con, datetime(2026, 4, 27))
        assert len(alerts) == 1
        flagged = set(alerts[0]["missing_fields"])
        # Originator address satisfied via debtor_country=NULL? No — should be missing.
        assert "originator_account" in flagged
        assert "beneficiary_name" in flagged
        assert "beneficiary_account" in flagged

    def test_missing_txn_table_returns_empty(self):
        con = duckdb.connect(":memory:")
        # No txn table at all.
        assert validate_travel_rule(con, datetime(2026, 4, 27)) == []


# ---------------------------------------------------------------------------
# End-to-end via the engine python_ref pathway
# ---------------------------------------------------------------------------


class TestPythonRefIntegration:
    def test_runner_invokes_validator(self, tmp_path):
        """Wire the validator into a minimal spec and run through `run_spec`."""
        from datetime import datetime as _dt
        from decimal import Decimal as _Dec

        from aml_framework.engine import run_spec
        from aml_framework.spec.models import (
            AggregationWindowLogic,  # noqa: F401 — used in inline spec build
            AMLSpec,
            Column,
            DataContract,
            Program,
            PythonRefLogic,
            Queue,
            RegulationRef,
            Rule,
            Workflow,
        )

        spec = AMLSpec(
            version=1,
            program=Program(
                name="Test",
                jurisdiction="EU",
                regulator="EBA",
                owner="x",
                effective_date="2026-01-01",
            ),
            data_contracts=[
                DataContract(
                    id="txn",
                    source="synthetic://travel-rule-test",
                    columns=[
                        Column(name="txn_id", type="string"),
                        Column(name="customer_id", type="string"),
                        Column(name="amount", type="decimal"),
                        Column(name="currency", type="string"),
                        Column(name="channel", type="string"),
                        Column(name="direction", type="string"),
                        Column(name="booked_at", type="timestamp"),
                        Column(name="debtor_country", type="string"),
                        Column(name="debtor_iban", type="string"),
                        Column(name="counterparty_name", type="string"),
                        Column(name="counterparty_country", type="string"),
                        Column(name="counterparty_account", type="string"),
                    ],
                )
            ],
            rules=[
                Rule(
                    id="travel_rule_completeness",
                    name="FATF R.16",
                    severity="high",
                    regulation_refs=[
                        RegulationRef(
                            citation="FATF R.16",
                            description="Originator/beneficiary completeness on cross-border wires.",
                        )
                    ],
                    escalate_to="l2",
                    logic=PythonRefLogic(
                        type="python_ref",
                        callable="aml_framework.models.travel_rule:validate_travel_rule",
                        model_id="travel_rule_completeness",
                        model_version="fatf_r16_2025-06",
                    ),
                )
            ],
            workflow=Workflow(queues=[Queue(id="l2", sla="72h")]),
        )

        # Provide a spec_path that the runner can hash. A throwaway file works.
        spec_path = tmp_path / "aml.yaml"
        spec_path.write_text("# test spec\n")

        # Two rows: one full-fields (no alert), one missing beneficiary (alert).
        data = {
            "txn": [
                {
                    "txn_id": "T-OK",
                    "customer_id": "OLENA",
                    "amount": _Dec("5000"),
                    "currency": "EUR",
                    "channel": "wire",
                    "direction": "out",
                    "booked_at": _dt(2026, 4, 27),
                    "debtor_country": "DE",
                    "debtor_iban": "DE89",
                    "counterparty_name": "ACME",
                    "counterparty_country": "FR",
                    "counterparty_account": "FR14",
                },
                {
                    "txn_id": "T-MISSING",
                    "customer_id": "BORIS",
                    "amount": _Dec("5000"),
                    "currency": "EUR",
                    "channel": "wire",
                    "direction": "out",
                    "booked_at": _dt(2026, 4, 27),
                    "debtor_country": "RU",
                    "debtor_iban": "RU01",
                    "counterparty_name": "",  # ← R.16 violation
                    "counterparty_country": "CH",
                    "counterparty_account": "",  # ← R.16 violation
                },
            ],
            "customer": [],
        }

        result = run_spec(
            spec=spec,
            spec_path=spec_path,
            data=data,
            as_of=_dt(2026, 4, 27),
            artifacts_root=tmp_path,
        )
        alerts = result.alerts.get("travel_rule_completeness", [])
        assert len(alerts) == 1
        assert alerts[0]["txn_id"] == "T-MISSING"
        assert "beneficiary_name" in alerts[0]["missing_fields"]
        assert "beneficiary_account" in alerts[0]["missing_fields"]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Make sure threshold env doesn't leak across tests."""
    monkeypatch.delenv("AML_TRAVEL_RULE_THRESHOLDS", raising=False)
    yield
