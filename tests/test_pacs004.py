"""pacs.004 (Payment Return) parser + return-reason library tests.

Round-5 PR #5 — composes with PR #56 ingestion (same parser module) and
PR #58 spec library (sibling YAML, same load pattern). pacs.004 rows
go to a separate `txn_return` data contract — these tests verify the
parser splits cleanly from the credit-transfer flow and the rule
snippets are valid Pydantic Rule objects.

Five layers:
  - Bundled sample yields the right rows (4 returns from ROAMR LTD).
  - Field extraction: reason codes, original UETR/EndToEndId, original
    parties under <OrgnlTxRef>.
  - Auto-detect dispatch routes pacs.004 to Pacs004Parser, not pacs.008.
  - load_iso20022_dir filters out pacs.004; load_iso20022_returns_dir
    returns only pacs.004 (no schema mixing).
  - Library YAML: every snippet validates as a Rule; CSV reference data
    classifies every code cited in snippets.
"""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import yaml

from aml_framework.data.iso20022 import (
    Pacs004Parser,
    load_iso20022_dir,
    load_iso20022_returns_dir,
    parse_iso20022_xml,
)
from aml_framework.spec.library import LIBRARY_ROOT
from aml_framework.spec.models import Rule

SAMPLE_PACS004 = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "aml_framework"
    / "data"
    / "iso20022"
    / "sample_pacs004.xml"
)
SAMPLE_PACS008 = SAMPLE_PACS004.parent / "sample_pacs008.xml"
SAMPLE_PAIN001 = SAMPLE_PACS004.parent / "sample_pain001.xml"

LIBRARY_FILE = LIBRARY_ROOT / "iso20022_return_reasons.yaml"
RETURN_REASON_CSV = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "aml_framework"
    / "data"
    / "lists"
    / "iso20022_return_reason_codes.csv"
)


# ---------------------------------------------------------------------------
# Bundled-sample extraction
# ---------------------------------------------------------------------------


class TestPacs004Parser:
    def test_bundled_sample_yields_four_returns(self):
        rows = Pacs004Parser().load(SAMPLE_PACS004)
        assert len(rows) == 4

    def test_msg_kind_pacs004_on_every_row(self):
        rows = Pacs004Parser().load(SAMPLE_PACS004)
        for r in rows:
            assert r["msg_kind"] == "pacs.004"

    def test_return_ids_extracted(self):
        rows = Pacs004Parser().load(SAMPLE_PACS004)
        ids = [r["return_id"] for r in rows]
        assert ids == ["RTR-001", "RTR-002", "RTR-003", "RTR-004"]

    def test_original_uetr_extracted(self):
        rows = Pacs004Parser().load(SAMPLE_PACS004)
        uetrs = [r["original_uetr"] for r in rows]
        # Each UETR is well-formed (RFC 4122 v4 shape).
        assert all(len(u) == 36 and u.count("-") == 4 for u in uetrs)
        assert "11111111-1111-4111-8111-111111111111" in uetrs

    def test_original_endtoendid_extracted(self):
        rows = Pacs004Parser().load(SAMPLE_PACS004)
        end_to_ends = {r["original_end_to_end_id"] for r in rows}
        assert "ROAMR-2026-04-20-A" in end_to_ends
        assert len(end_to_ends) == 4

    def test_returned_amount_and_currency(self):
        rows = Pacs004Parser().load(SAMPLE_PACS004)
        amounts = [r["amount"] for r in rows]
        assert amounts == [
            Decimal("12000.00"),
            Decimal("9500.00"),
            Decimal("7800.00"),
            Decimal("15500.00"),
        ]
        for r in rows:
            assert r["currency"] == "EUR"

    def test_returned_at_parsed(self):
        rows = Pacs004Parser().load(SAMPLE_PACS004)
        assert rows[0]["returned_at"] == datetime(2026, 4, 22)
        assert rows[3]["returned_at"] == datetime(2026, 4, 25)

    def test_reason_codes_extracted(self):
        rows = Pacs004Parser().load(SAMPLE_PACS004)
        codes = [r["reason_code"] for r in rows]
        assert codes == ["AC03", "AC04", "MD07", "AM05"]

    def test_reason_info_extracted(self):
        rows = Pacs004Parser().load(SAMPLE_PACS004)
        infos = [r["reason_info"] for r in rows]
        assert "Invalid creditor account number" in infos
        assert "End-customer deceased" in infos

    def test_originator_pulled_from_orgnl_tx_ref(self):
        rows = Pacs004Parser().load(SAMPLE_PACS004)
        for r in rows:
            assert r["originator_name"] == "ROAMR LTD"
            assert r["originator_country"] == "GB"

    def test_beneficiary_pulled_from_orgnl_tx_ref(self):
        rows = Pacs004Parser().load(SAMPLE_PACS004)
        beneficiaries = {r["beneficiary_name"] for r in rows}
        assert beneficiaries == {
            "SHELL VEHICLE 1",
            "SHELL VEHICLE 2",
            "MULE OPERATOR 3",
            "MULE OPERATOR 4",
        }
        for r in rows:
            assert r["beneficiary_country"] == "CH"

    def test_msg_id_propagated(self):
        rows = Pacs004Parser().load(SAMPLE_PACS004)
        for r in rows:
            assert r["msg_id"] == "RTR-2026-04-27-001"


# ---------------------------------------------------------------------------
# Robustness — empty / malformed / missing-fields
# ---------------------------------------------------------------------------


class TestPacs004Robustness:
    def test_empty_payload_returns_empty(self):
        assert Pacs004Parser().parse(b"") == []

    def test_malformed_xml_returns_empty(self):
        assert Pacs004Parser().parse(b"<not-xml") == []

    def test_missing_reason_code_yields_empty_string(self):
        # No <RtrRsnInf> at all — code field falls back to empty string.
        payload = """<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.004.001.11">
  <PmtRtr>
    <GrpHdr><MsgId>X</MsgId></GrpHdr>
    <TxInf>
      <RtrId>R1</RtrId>
      <RtrdIntrBkSttlmAmt Ccy="EUR">100</RtrdIntrBkSttlmAmt>
      <IntrBkSttlmDt>2026-04-22</IntrBkSttlmDt>
      <OrgnlTxRef>
        <Dbtr><Nm>X CORP</Nm></Dbtr>
        <Cdtr><Nm>Y CORP</Nm></Cdtr>
      </OrgnlTxRef>
    </TxInf>
  </PmtRtr>
</Document>"""
        rows = Pacs004Parser().parse(payload)
        assert len(rows) == 1
        assert rows[0]["reason_code"] == ""
        assert rows[0]["reason_info"] == ""

    def test_falls_back_to_msg_id_when_no_rtrid(self):
        payload = """<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.004.001.11">
  <PmtRtr>
    <GrpHdr><MsgId>BATCH-X</MsgId></GrpHdr>
    <TxInf>
      <RtrdIntrBkSttlmAmt Ccy="EUR">50</RtrdIntrBkSttlmAmt>
      <IntrBkSttlmDt>2026-04-22</IntrBkSttlmDt>
    </TxInf>
  </PmtRtr>
</Document>"""
        rows = Pacs004Parser().parse(payload)
        assert rows[0]["return_id"] == "BATCH-X-1"

    def test_falls_back_to_intrbksttlmamt_when_no_rtrd_amount(self):
        # Some bank-internal variants emit the legacy IntrBkSttlmAmt tag.
        payload = """<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.004.001.11">
  <PmtRtr>
    <GrpHdr><MsgId>X</MsgId></GrpHdr>
    <TxInf>
      <RtrId>R1</RtrId>
      <IntrBkSttlmAmt Ccy="EUR">200</IntrBkSttlmAmt>
      <IntrBkSttlmDt>2026-04-22</IntrBkSttlmDt>
    </TxInf>
  </PmtRtr>
</Document>"""
        rows = Pacs004Parser().parse(payload)
        assert rows[0]["amount"] == Decimal("200")

    def test_namespace_agnostic_parsing(self):
        # Different XSD version still parses correctly.
        payload = """<?xml version="1.0"?>
<Document xmlns="urn:bank-internal:xsd:custom-pacs.004">
  <PmtRtr>
    <GrpHdr><MsgId>X</MsgId></GrpHdr>
    <TxInf>
      <RtrId>R1</RtrId>
      <RtrdIntrBkSttlmAmt Ccy="USD">99</RtrdIntrBkSttlmAmt>
      <IntrBkSttlmDt>2026-04-22</IntrBkSttlmDt>
      <RtrRsnInf><Rsn><Cd>AC04</Cd></Rsn></RtrRsnInf>
    </TxInf>
  </PmtRtr>
</Document>"""
        rows = Pacs004Parser().parse(payload)
        assert rows[0]["reason_code"] == "AC04"


# ---------------------------------------------------------------------------
# Auto-detect dispatch + dir loaders
# ---------------------------------------------------------------------------


class TestAutoDetectDispatch:
    def test_pacs004_routed_to_pacs004_parser(self):
        rows = parse_iso20022_xml(SAMPLE_PACS004.read_bytes())
        # Distinguishing field: msg_kind=pacs.004 + return_id present.
        assert len(rows) == 4
        for r in rows:
            assert r["msg_kind"] == "pacs.004"
            assert "return_id" in r

    def test_pacs008_still_routes_to_pacs008(self):
        rows = parse_iso20022_xml(SAMPLE_PACS008.read_bytes())
        for r in rows:
            assert r["msg_kind"] == "pacs.008"

    def test_pain001_still_routes_to_pain001(self):
        rows = parse_iso20022_xml(SAMPLE_PAIN001.read_bytes())
        for r in rows:
            assert r["msg_kind"] == "pain.001"


class TestDirLoaders:
    def test_load_iso20022_dir_filters_out_pacs004(self, tmp_path):
        # Drop both pacs.004 and pacs.008 into a dir; only pacs.008 rows
        # come back from the credit-transfer loader.
        (tmp_path / "ret.xml").write_bytes(SAMPLE_PACS004.read_bytes())
        (tmp_path / "txn.xml").write_bytes(SAMPLE_PACS008.read_bytes())
        rows = load_iso20022_dir(tmp_path)
        assert len(rows) > 0
        for r in rows:
            assert r["msg_kind"] != "pacs.004"
            assert r["msg_kind"] in ("pacs.008", "pacs.009", "pain.001")

    def test_load_iso20022_returns_dir_returns_only_pacs004(self, tmp_path):
        (tmp_path / "ret.xml").write_bytes(SAMPLE_PACS004.read_bytes())
        (tmp_path / "txn.xml").write_bytes(SAMPLE_PACS008.read_bytes())
        rows = load_iso20022_returns_dir(tmp_path)
        # 4 returns from the bundled sample, none from pacs.008.
        assert len(rows) == 4
        for r in rows:
            assert r["msg_kind"] == "pacs.004"

    def test_dir_loaders_are_disjoint(self, tmp_path):
        (tmp_path / "ret.xml").write_bytes(SAMPLE_PACS004.read_bytes())
        (tmp_path / "txn.xml").write_bytes(SAMPLE_PACS008.read_bytes())
        (tmp_path / "corp.xml").write_bytes(SAMPLE_PAIN001.read_bytes())
        txns = load_iso20022_dir(tmp_path)
        returns = load_iso20022_returns_dir(tmp_path)
        # No row appears in both — schemas don't overlap.
        txn_ids = {r.get("txn_id") for r in txns}
        return_ids = {r.get("return_id") for r in returns}
        assert txn_ids.isdisjoint(return_ids)


# ---------------------------------------------------------------------------
# Library YAML — every snippet must be a valid Rule
# ---------------------------------------------------------------------------


class TestLibraryYAML:
    def test_library_file_exists(self):
        assert LIBRARY_FILE.exists(), f"library file missing at {LIBRARY_FILE}"

    def test_library_loads_as_yaml_list(self):
        data = yaml.safe_load(LIBRARY_FILE.read_text())
        assert isinstance(data, list)
        assert len(data) >= 3  # v1 ships at least 3 snippets

    def test_every_snippet_is_a_valid_rule(self):
        snippets = yaml.safe_load(LIBRARY_FILE.read_text())
        for snippet in snippets:
            rule = Rule.model_validate(snippet)
            assert rule.id
            assert rule.regulation_refs  # every snippet must cite something
            assert rule.tags

    def test_every_snippet_targets_pacs004_tag(self):
        snippets = yaml.safe_load(LIBRARY_FILE.read_text())
        for snippet in snippets:
            assert "pacs004" in snippet["tags"], (
                f"snippet {snippet['id']!r} must carry the pacs004 tag"
            )

    def test_known_snippets_present(self):
        snippets = yaml.safe_load(LIBRARY_FILE.read_text())
        ids = {s["id"] for s in snippets}
        assert "high_risk_return_burst_mule_probing" in ids
        assert "corridor_return_rate_spike" in ids
        assert "deceased_payee_returns_md07" in ids


# ---------------------------------------------------------------------------
# Reference CSV — every cited reason code must be classified
# ---------------------------------------------------------------------------


def _all_codes_in_csv() -> set[str]:
    with RETURN_REASON_CSV.open() as f:
        return {row["code"] for row in csv.DictReader(f)}


def _mule_signal_codes() -> set[str]:
    with RETURN_REASON_CSV.open() as f:
        return {row["code"] for row in csv.DictReader(f) if row["mule_signal"].lower() == "true"}


class TestReturnReasonCSV:
    def test_csv_exists(self):
        assert RETURN_REASON_CSV.exists()

    def test_csv_has_required_columns(self):
        with RETURN_REASON_CSV.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                for col in ("code", "description", "risk_band", "mule_signal"):
                    assert col in row, f"missing column {col!r} on row {row}"
                break

    def test_codes_cited_by_snippets_are_classified(self):
        codes_in_csv = _all_codes_in_csv()
        # Snippet 1 cites these — they MUST be in the CSV.
        for cited in (
            "AC03",
            "AC04",
            "AC06",
            "AG01",
            "AM05",
            "BE05",
            "BE06",
            "FRAD",
            "MD07",
            "RR04",
        ):
            assert cited in codes_in_csv, (
                f"snippet cites {cited!r} but it isn't in the return-reason CSV"
            )

    def test_risk_band_values_are_valid(self):
        valid_bands = {"low", "medium", "high"}
        with RETURN_REASON_CSV.open() as f:
            for row in csv.DictReader(f):
                assert row["risk_band"] in valid_bands, (
                    f"row {row['code']!r} has invalid risk_band {row['risk_band']!r}"
                )

    def test_mule_signal_values_are_boolean_strings(self):
        with RETURN_REASON_CSV.open() as f:
            for row in csv.DictReader(f):
                assert row["mule_signal"].lower() in ("true", "false"), (
                    f"row {row['code']!r} has non-boolean mule_signal {row['mule_signal']!r}"
                )

    def test_mule_signal_codes_align_with_snippet_1(self):
        # Snippet 1's code list should be a subset of mule_signal=true rows
        # — that's the contract.
        cited_in_snippet = {
            "AC03",
            "AC04",
            "AC06",
            "AG01",
            "AM05",
            "BE05",
            "BE06",
            "FRAD",
            "MD07",
            "RR04",
        }
        mule_codes = _mule_signal_codes()
        missing = cited_in_snippet - mule_codes
        assert not missing, (
            f"codes cited in mule-probing snippet but not flagged "
            f"mule_signal=true in CSV: {sorted(missing)}"
        )

    def test_no_duplicate_codes(self):
        with RETURN_REASON_CSV.open() as f:
            codes = [row["code"] for row in csv.DictReader(f)]
        assert len(codes) == len(set(codes)), "duplicate code in return-reason CSV"
