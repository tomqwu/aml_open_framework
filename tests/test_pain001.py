"""pain.001 (Customer Credit Transfer Initiation) parser tests.

Round-5 PR #4 — composes with PR #56 ingestion (same parser module) and
PR #57 travel-rule validator (output rows conform to the same `txn`
data contract). Tests cover bundled-sample extraction, multi-PmtInf
batches, debtor-shared-across-transfers semantics, and auto-detect
dispatch through `parse_iso20022_xml`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from aml_framework.data.iso20022 import (
    Pain001Parser,
    parse_iso20022_xml,
)
from aml_framework.data.iso20022.parser import load_iso20022_dir

SAMPLE_PAIN001 = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "aml_framework"
    / "data"
    / "iso20022"
    / "sample_pain001.xml"
)


# ---------------------------------------------------------------------------
# Bundled-sample extraction
# ---------------------------------------------------------------------------


class TestPain001Parser:
    def test_bundled_sample_yields_four_txns(self):
        # 3 in PmtInf #1 + 1 in PmtInf #2 = 4 total.
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        assert len(rows) == 4

    def test_msg_kind_pain001_on_every_row(self):
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        for r in rows:
            assert r["msg_kind"] == "pain.001"

    def test_debtor_shared_across_all_transfers_in_batch(self):
        # The corporate file has ONE debtor (ACME GMBH); every txn
        # carries that as customer_id + debtor_iban + debtor_country.
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        for r in rows:
            assert r["customer_id"] == "ACME GMBH"
            assert r["debtor_iban"] == "DE89370400440532013000"
            assert r["debtor_country"] == "DE"
            assert r["debtor_bic"] == "DEUTDEFFXXX"

    def test_endtoendid_used_as_txn_id(self):
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        ids = {r["txn_id"] for r in rows}
        assert "SUPPLIER-PAY-2026-04-1001" in ids
        assert "PAYROLL-MARCH-2026-1002" in ids
        assert "OFFSHORE-INVS-2026-04-1003" in ids
        assert "OFFSHORE-INVS-2026-04-2001" in ids

    def test_amounts_extracted_from_instdamt(self):
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        amts = {r["txn_id"]: r["amount"] for r in rows}
        assert amts["SUPPLIER-PAY-2026-04-1001"] == Decimal("15000.00")
        assert amts["PAYROLL-MARCH-2026-1002"] == Decimal("25000.00")
        assert amts["OFFSHORE-INVS-2026-04-1003"] == Decimal("22500.00")
        assert amts["OFFSHORE-INVS-2026-04-2001"] == Decimal("25000.00")

    def test_currencies_extracted(self):
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        for r in rows:
            assert r["currency"] == "EUR"

    def test_purpose_codes_preserved(self):
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        purposes = {r["txn_id"]: r["purpose_code"] for r in rows}
        assert purposes["SUPPLIER-PAY-2026-04-1001"] == "SUPP"
        assert purposes["PAYROLL-MARCH-2026-1002"] == "SALA"
        assert purposes["OFFSHORE-INVS-2026-04-1003"] == "INVS"
        assert purposes["OFFSHORE-INVS-2026-04-2001"] == "INVS"

    def test_creditor_extracted_per_transfer(self):
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        cps = {r["txn_id"]: r for r in rows}
        assert cps["SUPPLIER-PAY-2026-04-1001"]["counterparty_name"] == "FOURNISSEUR PARIS SARL"
        assert cps["SUPPLIER-PAY-2026-04-1001"]["counterparty_country"] == "FR"
        assert cps["OFFSHORE-INVS-2026-04-1003"]["counterparty_country"] == "CH"

    def test_creditor_bic_preserved(self):
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        cps = {r["txn_id"]: r for r in rows}
        assert cps["SUPPLIER-PAY-2026-04-1001"]["creditor_bic"] == "BNPAFRPPXXX"
        assert cps["OFFSHORE-INVS-2026-04-1003"]["creditor_bic"] == "UBSWCHZH80A"

    def test_creditor_account_iban_preserved(self):
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        cps = {r["txn_id"]: r for r in rows}
        assert (
            cps["SUPPLIER-PAY-2026-04-1001"]["counterparty_account"]
            == "FR1420041010050500013M02606"
        )
        assert cps["OFFSHORE-INVS-2026-04-1003"]["counterparty_account"] == "CH9300762011623852957"

    def test_execution_date_propagates_per_pmtinf(self):
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        by_id = {r["txn_id"]: r for r in rows}
        # PmtInf #1 has ReqdExctnDt 2026-04-28
        assert by_id["SUPPLIER-PAY-2026-04-1001"]["booked_at"] == datetime(2026, 4, 28)
        assert by_id["PAYROLL-MARCH-2026-1002"]["booked_at"] == datetime(2026, 4, 28)
        assert by_id["OFFSHORE-INVS-2026-04-1003"]["booked_at"] == datetime(2026, 4, 28)
        # PmtInf #2 has ReqdExctnDt 2026-04-29
        assert by_id["OFFSHORE-INVS-2026-04-2001"]["booked_at"] == datetime(2026, 4, 29)

    def test_payment_information_id_carried(self):
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        by_id = {r["txn_id"]: r for r in rows}
        assert (
            by_id["SUPPLIER-PAY-2026-04-1001"]["payment_information_id"]
            == "PMTINF-2026-04-27-DAILY"
        )
        assert (
            by_id["OFFSHORE-INVS-2026-04-2001"]["payment_information_id"]
            == "PMTINF-2026-04-29-WEEKLY"
        )

    def test_charge_bearer_inherited_from_pmtinf(self):
        # pain.001 sample has ChrgBr at PmtInf level; per-txn ChrgBr is missing.
        # The parser falls back to the PmtInf-level value.
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        for r in rows:
            assert r["charge_bearer"] == "SHAR"

    def test_uetr_empty_for_pain001(self):
        # pain.001 is customer-initiated; UETR is assigned by the FI later.
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        for r in rows:
            assert r["uetr"] == ""

    def test_msg_id_propagates(self):
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        for r in rows:
            assert r["msg_id"] == "CORP-PAIN001-2026-04-27-0001"

    def test_channel_and_direction_constants(self):
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        for r in rows:
            assert r["channel"] == "wire"
            assert r["direction"] == "out"

    def test_structured_remittance_extracted_when_present(self):
        rows = Pain001Parser().load(SAMPLE_PAIN001)
        by_id = {r["txn_id"]: r for r in rows}
        rmt = by_id["SUPPLIER-PAY-2026-04-1001"]["structured_remittance"]
        assert rmt is not None
        assert rmt.get("Nb") == "INV-2026-1001"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


_MINIMAL_PAIN001 = b"""<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.11">
  <CstmrCdtTrfInitn>
    <GrpHdr><MsgId>MIN-PAIN-1</MsgId></GrpHdr>
    <PmtInf>
      <PmtInfId>MIN-PMT-1</PmtInfId>
      <Dbtr><Nm>MIN CORP</Nm></Dbtr>
      <CdtTrfTxInf>
        <PmtId><EndToEndId>MIN-E2E-1</EndToEndId></PmtId>
        <Amt><InstdAmt Ccy="USD">100.00</InstdAmt></Amt>
        <Cdtr><Nm>MIN CREDITOR</Nm></Cdtr>
      </CdtTrfTxInf>
    </PmtInf>
  </CstmrCdtTrfInitn>
</Document>
"""


class TestEdgeCases:
    def test_minimal_pain001_parses(self):
        rows = Pain001Parser().parse(_MINIMAL_PAIN001)
        assert len(rows) == 1
        assert rows[0]["txn_id"] == "MIN-E2E-1"
        assert rows[0]["amount"] == Decimal("100.00")

    def test_missing_optional_fields_default(self):
        rows = Pain001Parser().parse(_MINIMAL_PAIN001)
        r = rows[0]
        assert r["debtor_iban"] == ""
        assert r["debtor_bic"] == ""
        assert r["purpose_code"] == ""
        assert r["counterparty_country"] == ""
        assert r["booked_at"] is None
        assert r["structured_remittance"] is None
        assert r["uetr"] == ""

    def test_malformed_xml_returns_empty(self):
        assert Pain001Parser().parse(b"<not><valid></not>") == []

    def test_no_pmtinf_yields_empty(self):
        out = Pain001Parser().parse(
            b"<Document xmlns='urn:iso:std:iso:20022:tech:xsd:pain.001.001.11'>"
            b"<CstmrCdtTrfInitn><GrpHdr><MsgId>EMPTY</MsgId></GrpHdr></CstmrCdtTrfInitn>"
            b"</Document>"
        )
        assert out == []

    def test_pmtinf_without_transfers_yields_empty(self):
        out = Pain001Parser().parse(
            b"<Document xmlns='urn:iso:std:iso:20022:tech:xsd:pain.001.001.11'>"
            b"<CstmrCdtTrfInitn><GrpHdr><MsgId>X</MsgId></GrpHdr>"
            b"<PmtInf><PmtInfId>P1</PmtInfId><Dbtr><Nm>D</Nm></Dbtr></PmtInf>"
            b"</CstmrCdtTrfInitn></Document>"
        )
        assert out == []

    def test_multiple_pmtinf_with_different_debtors(self):
        # Real corporate batches *can* have multiple PmtInf groups with
        # different debtor accounts (e.g. multi-currency disbursements).
        # Each group's debtor must propagate to its own transfers.
        out = Pain001Parser().parse(
            b"<Document xmlns='urn:iso:std:iso:20022:tech:xsd:pain.001.001.11'>"
            b"<CstmrCdtTrfInitn><GrpHdr><MsgId>MULTI</MsgId></GrpHdr>"
            b"<PmtInf><PmtInfId>P-EUR</PmtInfId>"
            b"<Dbtr><Nm>DEBTOR-A</Nm><PstlAdr><Ctry>DE</Ctry></PstlAdr></Dbtr>"
            b"<CdtTrfTxInf><PmtId><EndToEndId>A-1</EndToEndId></PmtId>"
            b"<Amt><InstdAmt Ccy='EUR'>1.00</InstdAmt></Amt>"
            b"<Cdtr><Nm>C-A</Nm></Cdtr></CdtTrfTxInf>"
            b"</PmtInf>"
            b"<PmtInf><PmtInfId>P-USD</PmtInfId>"
            b"<Dbtr><Nm>DEBTOR-B</Nm><PstlAdr><Ctry>US</Ctry></PstlAdr></Dbtr>"
            b"<CdtTrfTxInf><PmtId><EndToEndId>B-1</EndToEndId></PmtId>"
            b"<Amt><InstdAmt Ccy='USD'>1.00</InstdAmt></Amt>"
            b"<Cdtr><Nm>C-B</Nm></Cdtr></CdtTrfTxInf>"
            b"</PmtInf>"
            b"</CstmrCdtTrfInitn></Document>"
        )
        by_id = {r["txn_id"]: r for r in out}
        assert by_id["A-1"]["customer_id"] == "DEBTOR-A"
        assert by_id["A-1"]["currency"] == "EUR"
        assert by_id["B-1"]["customer_id"] == "DEBTOR-B"
        assert by_id["B-1"]["currency"] == "USD"

    def test_namespace_agnostic(self):
        out = Pain001Parser().parse(
            b"<Document xmlns='urn:bank-internal:painx'>"
            b"<CstmrCdtTrfInitn><GrpHdr><MsgId>NS-1</MsgId></GrpHdr>"
            b"<PmtInf><PmtInfId>NS-P</PmtInfId>"
            b"<Dbtr><Nm>D</Nm></Dbtr>"
            b"<CdtTrfTxInf><PmtId><EndToEndId>NS-E2E</EndToEndId></PmtId>"
            b"<Amt><InstdAmt Ccy='EUR'>1.00</InstdAmt></Amt>"
            b"<Cdtr><Nm>C</Nm></Cdtr>"
            b"</CdtTrfTxInf></PmtInf>"
            b"</CstmrCdtTrfInitn></Document>"
        )
        assert len(out) == 1
        assert out[0]["txn_id"] == "NS-E2E"

    def test_fallback_txn_id_when_e2e_missing(self):
        out = Pain001Parser().parse(
            b"<Document xmlns='urn:iso:std:iso:20022:tech:xsd:pain.001.001.11'>"
            b"<CstmrCdtTrfInitn><GrpHdr><MsgId>FB</MsgId></GrpHdr>"
            b"<PmtInf><PmtInfId>FBP</PmtInfId>"
            b"<Dbtr><Nm>D</Nm></Dbtr>"
            b"<CdtTrfTxInf>"
            b"<Amt><InstdAmt Ccy='EUR'>1.00</InstdAmt></Amt>"
            b"<Cdtr><Nm>C</Nm></Cdtr>"
            b"</CdtTrfTxInf></PmtInf>"
            b"</CstmrCdtTrfInitn></Document>"
        )
        # Falls back to MsgId-PmtInfId-seq.
        assert out[0]["txn_id"] == "FB-FBP-1"


# ---------------------------------------------------------------------------
# Auto-detect dispatch
# ---------------------------------------------------------------------------


class TestAutoDetect:
    def test_autodetect_pain001(self):
        rows = parse_iso20022_xml(SAMPLE_PAIN001.read_bytes())
        assert len(rows) == 4
        assert all(r["msg_kind"] == "pain.001" for r in rows)


# ---------------------------------------------------------------------------
# Directory loader picks up pain.001 + pacs.008 in the same dir
# ---------------------------------------------------------------------------


class TestMixedIngestionDir:
    def test_loads_pain001_alongside_pacs008(self, tmp_path):
        sample_pacs008 = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "aml_framework"
            / "data"
            / "iso20022"
            / "sample_pacs008.xml"
        )
        (tmp_path / "corp.xml").write_bytes(SAMPLE_PAIN001.read_bytes())
        (tmp_path / "wire.xml").write_bytes(sample_pacs008.read_bytes())
        rows = load_iso20022_dir(tmp_path)
        # 4 from pain.001 + 3 from pacs.008 = 7
        assert len(rows) == 7
        kinds = {r["msg_kind"] for r in rows}
        assert kinds == {"pain.001", "pacs.008"}


# ---------------------------------------------------------------------------
# Composes with the FATF R.16 travel-rule validator (PR #57)
# ---------------------------------------------------------------------------


class TestComposesWithTravelRule:
    def test_pain001_rows_feed_travel_rule(self):
        """The pain.001 OFFSHORE-INVS rows go DE → CH (cross-border) at
        EUR 22.5k / 25k — comfortably above the EUR 1000 threshold —
        but they DO have full originator + beneficiary fields, so
        the travel-rule validator should NOT alert. This proves the
        composition works end-to-end."""
        import duckdb

        from aml_framework.models.travel_rule import validate_travel_rule

        rows = Pain001Parser().load(SAMPLE_PAIN001)
        con = duckdb.connect(":memory:")
        # Build a minimal txn table holding just what the validator reads.
        con.execute(
            "CREATE TABLE txn ("
            "txn_id VARCHAR, customer_id VARCHAR, amount DECIMAL(20,2), "
            "currency VARCHAR, channel VARCHAR, direction VARCHAR, "
            "booked_at TIMESTAMP, debtor_iban VARCHAR, debtor_country VARCHAR, "
            "debtor_bic VARCHAR, counterparty_name VARCHAR, "
            "counterparty_country VARCHAR, counterparty_account VARCHAR, "
            "uetr VARCHAR, purpose_code VARCHAR)"
        )
        cols = (
            "txn_id customer_id amount currency channel direction booked_at "
            "debtor_iban debtor_country debtor_bic counterparty_name "
            "counterparty_country counterparty_account uetr purpose_code"
        ).split()
        for r in rows:
            con.execute(
                "INSERT INTO txn VALUES (" + ",".join(["?"] * len(cols)) + ")",
                [r.get(c) for c in cols],
            )
        # All 4 rows are R.16-compliant (full debtor + creditor fields).
        # Validator should produce zero alerts.
        alerts = validate_travel_rule(con, datetime(2026, 4, 27))
        assert alerts == [], (
            f"expected 0 R.16 alerts on the bundled pain.001 sample "
            f"(every row has full fields); got: {alerts}"
        )

    def test_pain001_with_missing_creditor_fires_travel_rule(self):
        """If we strip the beneficiary IBAN from one pain.001 row,
        the travel-rule validator should fire."""
        import duckdb

        from aml_framework.models.travel_rule import validate_travel_rule

        rows = Pain001Parser().load(SAMPLE_PAIN001)
        # Strip the counterparty_account from one row.
        rows[2]["counterparty_account"] = ""
        con = duckdb.connect(":memory:")
        con.execute(
            "CREATE TABLE txn ("
            "txn_id VARCHAR, customer_id VARCHAR, amount DECIMAL(20,2), "
            "currency VARCHAR, channel VARCHAR, direction VARCHAR, "
            "booked_at TIMESTAMP, debtor_iban VARCHAR, debtor_country VARCHAR, "
            "debtor_bic VARCHAR, counterparty_name VARCHAR, "
            "counterparty_country VARCHAR, counterparty_account VARCHAR, "
            "uetr VARCHAR, purpose_code VARCHAR)"
        )
        cols = (
            "txn_id customer_id amount currency channel direction booked_at "
            "debtor_iban debtor_country debtor_bic counterparty_name "
            "counterparty_country counterparty_account uetr purpose_code"
        ).split()
        for r in rows:
            con.execute(
                "INSERT INTO txn VALUES (" + ",".join(["?"] * len(cols)) + ")",
                [r.get(c) for c in cols],
            )
        alerts = validate_travel_rule(con, datetime(2026, 4, 27))
        assert len(alerts) == 1
        assert alerts[0]["txn_id"] == rows[2]["txn_id"]
        assert "beneficiary_account" in alerts[0]["missing_fields"]


@pytest.fixture(autouse=True)
def _isolate():
    yield
