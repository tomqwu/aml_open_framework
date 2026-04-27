"""ISO 20022 ingestion tests — pacs.008 + pacs.009 parsers, source wiring.

Network is forbidden in CI. All tests work against bundled sample XML
or inline payload bytes.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from aml_framework.data.iso20022 import (
    Pacs008Parser,
    Pacs009Parser,
    parse_iso20022_xml,
)
from aml_framework.data.iso20022.parser import load_iso20022_dir

SAMPLE_PACS008 = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "aml_framework"
    / "data"
    / "iso20022"
    / "sample_pacs008.xml"
)


# ---------------------------------------------------------------------------
# pacs.008 parser
# ---------------------------------------------------------------------------


class TestPacs008Parser:
    def test_bundled_sample_yields_three_txns(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        assert len(rows) == 3

    def test_uetr_used_as_txn_id_when_present(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        # First two have UETRs.
        assert rows[0]["txn_id"] == "11111111-2222-3333-4444-555555555555"
        assert rows[1]["txn_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    def test_endtoend_falls_back_when_uetr_missing(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        # Third txn has no UETR — falls back to EndToEndId.
        assert rows[2]["txn_id"] == "E2E-INVS-2026-04-27-1003"

    def test_amount_and_currency_extracted(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        assert rows[0]["amount"] == Decimal("5000.00")
        assert rows[0]["currency"] == "EUR"
        assert rows[2]["amount"] == Decimal("10000.00")

    def test_settlement_date_parsed(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        assert rows[0]["booked_at"] == datetime(2026, 4, 27)

    def test_channel_and_direction_constants(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        for r in rows:
            assert r["channel"] == "wire"
            assert r["direction"] == "out"

    def test_msg_kind_set(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        for r in rows:
            assert r["msg_kind"] == "pacs.008"

    def test_debtor_becomes_customer_id(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        assert rows[0]["customer_id"] == "OLENA KOWALSKI"
        assert rows[2]["customer_id"] == "BORIS PETROV"

    def test_creditor_extracted_as_counterparty(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        assert rows[0]["counterparty_name"] == "ACME TRADING SARL"
        assert rows[0]["counterparty_country"] == "FR"
        assert rows[2]["counterparty_country"] == "CH"

    def test_iban_fields_preserved(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        assert rows[0]["debtor_iban"] == "DE89370400440532013000"
        assert rows[0]["counterparty_account"] == "FR1420041010050500013M02606"

    def test_bic_fields_preserved(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        assert rows[0]["debtor_bic"] == "DEUTDEFFXXX"
        assert rows[0]["creditor_bic"] == "BNPAFRPPXXX"
        assert rows[0]["instructing_agent"] == "DEUTDEFFXXX"

    def test_purpose_code_preserved(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        assert rows[0]["purpose_code"] == "GDDS"
        assert rows[1]["purpose_code"] == "CHAR"
        assert rows[2]["purpose_code"] == "INVS"

    def test_charge_bearer_preserved(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        assert rows[0]["charge_bearer"] == "SHAR"
        assert rows[1]["charge_bearer"] == "DEBT"
        assert rows[2]["charge_bearer"] == "CRED"

    def test_msg_id_propagates(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        for r in rows:
            assert r["msg_id"] == "SAMPLE-MSG-2026-04-27-001"

    def test_structured_remittance_extracted(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        rmt = rows[0]["structured_remittance"]
        assert rmt is not None
        assert rmt.get("AddtlRmtInf") == "Spring shipment 1 of 3"

    def test_missing_remittance_yields_none(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        assert rows[2]["structured_remittance"] is None

    def test_debtor_country_preserved(self):
        rows = Pacs008Parser().load(SAMPLE_PACS008)
        assert rows[0]["debtor_country"] == "DE"
        assert rows[2]["debtor_country"] == "RU"


# ---------------------------------------------------------------------------
# Edge cases — missing fields, malformed input
# ---------------------------------------------------------------------------


_MINIMAL_PACS008 = b"""<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.13">
  <FIToFICstmrCdtTrf>
    <GrpHdr><MsgId>MIN-1</MsgId></GrpHdr>
    <CdtTrfTxInf>
      <PmtId><EndToEndId>E2E-MIN-1</EndToEndId></PmtId>
      <IntrBkSttlmAmt Ccy="USD">100.00</IntrBkSttlmAmt>
      <Dbtr><Nm>MIN DEBTOR</Nm></Dbtr>
      <Cdtr><Nm>MIN CREDITOR</Nm></Cdtr>
    </CdtTrfTxInf>
  </FIToFICstmrCdtTrf>
</Document>
"""


class TestEdgeCases:
    def test_minimal_message_parses(self):
        rows = Pacs008Parser().parse(_MINIMAL_PACS008)
        assert len(rows) == 1
        assert rows[0]["txn_id"] == "E2E-MIN-1"
        assert rows[0]["amount"] == Decimal("100.00")

    def test_missing_optional_fields_default(self):
        rows = Pacs008Parser().parse(_MINIMAL_PACS008)
        r = rows[0]
        assert r["debtor_iban"] == ""
        assert r["debtor_bic"] == ""
        assert r["purpose_code"] == ""
        assert r["counterparty_country"] == ""
        assert r["booked_at"] is None
        assert r["structured_remittance"] is None

    def test_malformed_xml_returns_empty(self):
        out = Pacs008Parser().parse(b"<not><valid></not>")
        assert out == []

    def test_no_transactions_yields_empty(self):
        out = Pacs008Parser().parse(
            b"<Document xmlns='urn:iso:std:iso:20022:tech:xsd:pacs.008.001.13'>"
            b"<FIToFICstmrCdtTrf><GrpHdr><MsgId>EMPTY</MsgId></GrpHdr></FIToFICstmrCdtTrf>"
            b"</Document>"
        )
        assert out == []

    def test_unknown_amount_currency_safe(self):
        out = Pacs008Parser().parse(
            b"<Document xmlns='urn:iso:std:iso:20022:tech:xsd:pacs.008.001.13'>"
            b"<FIToFICstmrCdtTrf><GrpHdr><MsgId>X</MsgId></GrpHdr>"
            b"<CdtTrfTxInf><PmtId><EndToEndId>X1</EndToEndId></PmtId>"
            b"<Dbtr><Nm>D</Nm></Dbtr><Cdtr><Nm>C</Nm></Cdtr></CdtTrfTxInf>"
            b"</FIToFICstmrCdtTrf></Document>"
        )
        assert out[0]["amount"] == Decimal("0")
        assert out[0]["currency"] == ""

    def test_namespace_agnostic(self):
        # Same payload but with a bank-internal namespace.
        out = Pacs008Parser().parse(
            b"<Document xmlns='urn:bank-internal:isox'>"
            b"<FIToFICstmrCdtTrf><GrpHdr><MsgId>NS-1</MsgId></GrpHdr>"
            b"<CdtTrfTxInf><PmtId><EndToEndId>NS-E2E</EndToEndId></PmtId>"
            b"<IntrBkSttlmAmt Ccy='EUR'>1.00</IntrBkSttlmAmt>"
            b"<Dbtr><Nm>D</Nm></Dbtr><Cdtr><Nm>C</Nm></Cdtr>"
            b"</CdtTrfTxInf></FIToFICstmrCdtTrf></Document>"
        )
        assert len(out) == 1
        assert out[0]["txn_id"] == "NS-E2E"

    def test_fallback_txn_id_when_uetr_and_e2e_missing(self):
        out = Pacs008Parser().parse(
            b"<Document xmlns='urn:iso:std:iso:20022:tech:xsd:pacs.008.001.13'>"
            b"<FIToFICstmrCdtTrf><GrpHdr><MsgId>FALLBACK</MsgId></GrpHdr>"
            b"<CdtTrfTxInf><Dbtr><Nm>D</Nm></Dbtr><Cdtr><Nm>C</Nm></Cdtr>"
            b"</CdtTrfTxInf></FIToFICstmrCdtTrf></Document>"
        )
        assert out[0]["txn_id"] == "FALLBACK-1"


# ---------------------------------------------------------------------------
# pacs.009 parser
# ---------------------------------------------------------------------------


_PACS009 = b"""<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.009.001.10">
  <FICdtTrf>
    <GrpHdr><MsgId>FI-MSG-1</MsgId></GrpHdr>
    <CdtTrfTxInf>
      <PmtId>
        <EndToEndId>FI-E2E-1</EndToEndId>
        <UETR>aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa</UETR>
      </PmtId>
      <IntrBkSttlmAmt Ccy="USD">2500000.00</IntrBkSttlmAmt>
      <IntrBkSttlmDt>2026-04-27</IntrBkSttlmDt>
      <Dbtr><Nm>BANK A</Nm><PstlAdr><Ctry>US</Ctry></PstlAdr></Dbtr>
      <DbtrAgt><FinInstnId><BICFI>BANKAUS33</BICFI></FinInstnId></DbtrAgt>
      <CdtrAgt><FinInstnId><BICFI>BANKBGB22</BICFI></FinInstnId></CdtrAgt>
      <Cdtr><Nm>BANK B</Nm><PstlAdr><Ctry>GB</Ctry></PstlAdr></Cdtr>
    </CdtTrfTxInf>
  </FICdtTrf>
</Document>
"""


class TestPacs009Parser:
    def test_parses_fi_credit_transfer(self):
        rows = Pacs009Parser().parse(_PACS009)
        assert len(rows) == 1
        assert rows[0]["txn_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        assert rows[0]["amount"] == Decimal("2500000.00")
        assert rows[0]["currency"] == "USD"

    def test_msg_kind_pacs009(self):
        rows = Pacs009Parser().parse(_PACS009)
        assert rows[0]["msg_kind"] == "pacs.009"

    def test_fi_parties_extracted(self):
        rows = Pacs009Parser().parse(_PACS009)
        assert rows[0]["customer_id"] == "BANK A"
        assert rows[0]["counterparty_name"] == "BANK B"
        assert rows[0]["counterparty_country"] == "GB"


# ---------------------------------------------------------------------------
# Auto-detect dispatch
# ---------------------------------------------------------------------------


class TestAutoDetect:
    def test_autodetect_pacs008(self):
        rows = parse_iso20022_xml(SAMPLE_PACS008.read_bytes())
        assert all(r["msg_kind"] == "pacs.008" for r in rows)

    def test_autodetect_pacs009(self):
        rows = parse_iso20022_xml(_PACS009)
        assert all(r["msg_kind"] == "pacs.009" for r in rows)


# ---------------------------------------------------------------------------
# Directory loader
# ---------------------------------------------------------------------------


class TestLoadDirectory:
    def test_loads_multiple_files(self, tmp_path):
        (tmp_path / "a.xml").write_bytes(SAMPLE_PACS008.read_bytes())
        (tmp_path / "b.xml").write_bytes(_PACS009)
        rows = load_iso20022_dir(tmp_path)
        # 3 from pacs.008 + 1 from pacs.009 = 4
        assert len(rows) == 4

    def test_skips_non_xml(self, tmp_path):
        (tmp_path / "doc.txt").write_text("not xml")
        rows = load_iso20022_dir(tmp_path)
        assert rows == []

    def test_recursive_walk(self, tmp_path):
        sub = tmp_path / "nested" / "deeper"
        sub.mkdir(parents=True)
        (sub / "file.xml").write_bytes(_PACS009)
        rows = load_iso20022_dir(tmp_path)
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# resolve_source('iso20022') integration
# ---------------------------------------------------------------------------


class TestResolveSource:
    def test_iso20022_source_returns_txn_dict(self, tmp_path):
        from datetime import datetime as _dt

        from aml_framework.data.sources import resolve_source
        from aml_framework.spec import load_spec

        spec = load_spec(
            Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"
        )
        (tmp_path / "msg.xml").write_bytes(SAMPLE_PACS008.read_bytes())

        data = resolve_source(
            source_type="iso20022",
            spec=spec,
            as_of=_dt(2026, 4, 27),
            data_dir=str(tmp_path),
        )
        assert "txn" in data
        assert len(data["txn"]) == 3
        # customer table is intentionally empty — operator pairs with a CSV.
        assert data["customer"] == []

    def test_iso20022_source_requires_data_dir(self):
        from datetime import datetime as _dt

        from aml_framework.data.sources import resolve_source
        from aml_framework.spec import load_spec

        spec = load_spec(
            Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"
        )
        with pytest.raises(ValueError, match="data-dir required"):
            resolve_source(source_type="iso20022", spec=spec, as_of=_dt(2026, 4, 27))
