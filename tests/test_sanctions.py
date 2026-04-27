"""Sanctions feed adapter tests — parsers, cache delta-diff, signature verify.

No network calls: every test passes payload bytes directly. The fixture
XML/JSON snippets are minimal but exercise the same XPath/attribute paths
production payloads use.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from aml_framework.sanctions import (
    ComplyAdvantageWebhookSource,
    EUConsolidatedSource,
    OFACAdvancedXMLSource,
    SanctionEntry,
    SanctionsCache,
    sync_source,
)


# ---------------------------------------------------------------------------
# OFAC parser
# ---------------------------------------------------------------------------


_OFAC_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<sdnList>
  <DistinctParty FixedRef="1001">
    <PartySubType>
      <Value>Individual</Value>
    </PartySubType>
    <NamePartValue>ALEXEI</NamePartValue>
    <NamePartValue>VOLKOV</NamePartValue>
    <Country>RU</Country>
  </DistinctParty>
  <DistinctParty FixedRef="2002">
    <PartySubType>
      <Value>Entity</Value>
    </PartySubType>
    <NamePartValue>ROSOBORONEXPORT</NamePartValue>
    <Country>RU</Country>
  </DistinctParty>
  <DistinctParty FixedRef="3003">
    <PartySubType>
      <Value>Vessel</Value>
    </PartySubType>
    <NamePartValue>STAR DRAGON</NamePartValue>
  </DistinctParty>
</sdnList>
"""


class TestOFACParser:
    def test_parses_three_distinct_parties(self):
        entries = OFACAdvancedXMLSource().parse(_OFAC_FIXTURE)
        assert len(entries) == 3

    def test_individual_name_concatenated(self):
        entries = OFACAdvancedXMLSource().parse(_OFAC_FIXTURE)
        names = {e.name for e in entries}
        assert "ALEXEI VOLKOV" in names
        assert "ROSOBORONEXPORT" in names
        assert "STAR DRAGON" in names

    def test_party_type_mapping(self):
        entries = {e.name: e for e in OFACAdvancedXMLSource().parse(_OFAC_FIXTURE)}
        assert entries["ALEXEI VOLKOV"].type == "individual"
        assert entries["ROSOBORONEXPORT"].type == "entity"
        assert entries["STAR DRAGON"].type == "vessel"

    def test_country_extracted(self):
        entries = {e.name: e for e in OFACAdvancedXMLSource().parse(_OFAC_FIXTURE)}
        assert entries["ALEXEI VOLKOV"].country == "RU"
        assert entries["ROSOBORONEXPORT"].country == "RU"
        # Vessel had no country in fixture; should be empty string, not crash.
        assert entries["STAR DRAGON"].country == ""

    def test_list_id_preserved(self):
        entries = {e.list_id: e for e in OFACAdvancedXMLSource().parse(_OFAC_FIXTURE)}
        assert "1001" in entries
        assert entries["1001"].list_source == "OFAC_SDN"

    def test_empty_payload_returns_empty(self):
        out = OFACAdvancedXMLSource().parse(b"<?xml version='1.0'?><sdnList/>")
        assert out == []


# ---------------------------------------------------------------------------
# EU parser
# ---------------------------------------------------------------------------


_EU_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<export>
  <sanctionEntity logicalId="EU-1" euReferenceNumber="EU.1.111" regulation="269/2014">
    <subjectType code="P">person</subjectType>
    <nameAlias wholeName="MIKHAIL FRADKOV"/>
    <nameAlias wholeName="MICHAEL FRADKOV"/>
    <citizenship countryIso2Code="RU"/>
  </sanctionEntity>
  <sanctionEntity logicalId="EU-2" euReferenceNumber="EU.2.222" regulation="269/2014">
    <subjectType code="E">enterprise</subjectType>
    <nameAlias wholeName="GAZPROMBANK"/>
    <address countryIso2Code="RU"/>
  </sanctionEntity>
</export>
"""


class TestEUParser:
    def test_parses_entities(self):
        entries = EUConsolidatedSource().parse(_EU_FIXTURE)
        assert len(entries) == 2

    def test_aliases_extracted_for_person(self):
        entries = {e.name: e for e in EUConsolidatedSource().parse(_EU_FIXTURE)}
        person = entries["MIKHAIL FRADKOV"]
        assert "MICHAEL FRADKOV" in person.aliases
        assert person.type == "individual"

    def test_country_from_citizenship_then_address(self):
        entries = {e.name: e for e in EUConsolidatedSource().parse(_EU_FIXTURE)}
        assert entries["MIKHAIL FRADKOV"].country == "RU"
        assert entries["GAZPROMBANK"].country == "RU"
        assert entries["GAZPROMBANK"].type == "entity"

    def test_program_carried_through(self):
        entries = EUConsolidatedSource().parse(_EU_FIXTURE)
        assert all(e.program == "269/2014" for e in entries)

    def test_list_source_label(self):
        entries = EUConsolidatedSource().parse(_EU_FIXTURE)
        assert all(e.list_source == "EU_CONSOL" for e in entries)


# ---------------------------------------------------------------------------
# ComplyAdvantage webhook adapter
# ---------------------------------------------------------------------------


_CA_PAYLOAD = json.dumps(
    {
        "event": "monitor_match",
        "data": {
            "matches": [
                {
                    "entity_id": "ca-1",
                    "name": "Boris Petrov",
                    "country_codes": ["RU", "BY"],
                    "entity_type": "person",
                    "sources": ["OFAC SDN List"],
                },
                {
                    "entity_id": "ca-2",
                    "name": "OOO Vostok",
                    "country_codes": ["RU"],
                    "entity_type": "company",
                    "sources": ["EU Consolidated List"],
                },
            ]
        },
    }
).encode("utf-8")


class TestComplyAdvantageParser:
    def test_parses_matches(self):
        entries = ComplyAdvantageWebhookSource().parse(_CA_PAYLOAD)
        assert len(entries) == 2

    def test_entity_type_mapping(self):
        entries = {e.name: e for e in ComplyAdvantageWebhookSource().parse(_CA_PAYLOAD)}
        assert entries["BORIS PETROV"].type == "individual"
        assert entries["OOO VOSTOK"].type == "entity"

    def test_first_country_used(self):
        entries = {e.name: e for e in ComplyAdvantageWebhookSource().parse(_CA_PAYLOAD)}
        assert entries["BORIS PETROV"].country == "RU"

    def test_source_label_includes_upstream_list(self):
        entries = {e.name: e for e in ComplyAdvantageWebhookSource().parse(_CA_PAYLOAD)}
        assert "OFAC SDN List" in entries["BORIS PETROV"].list_source

    def test_invalid_json_returns_empty(self):
        assert ComplyAdvantageWebhookSource().parse(b"not-json") == []

    def test_signature_verifier_accepts_correct_hmac(self):
        secret = "shhh"
        sig = hmac.new(secret.encode(), _CA_PAYLOAD, hashlib.sha256).hexdigest()
        assert ComplyAdvantageWebhookSource.verify_signature(_CA_PAYLOAD, f"sha256={sig}", secret)

    def test_signature_verifier_rejects_wrong_hmac(self):
        assert not ComplyAdvantageWebhookSource.verify_signature(
            _CA_PAYLOAD, "sha256=deadbeef", "shhh"
        )

    def test_signature_verifier_accepts_bare_hex(self):
        secret = "shhh"
        sig = hmac.new(secret.encode(), _CA_PAYLOAD, hashlib.sha256).hexdigest()
        assert ComplyAdvantageWebhookSource.verify_signature(_CA_PAYLOAD, sig, secret)

    def test_fetch_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            ComplyAdvantageWebhookSource().fetch()


# ---------------------------------------------------------------------------
# Cache + delta diff
# ---------------------------------------------------------------------------


class TestSanctionsCache:
    def _make_entries(self):
        return [
            SanctionEntry(name="ALICE", list_source="OFAC_SDN", country="RU", type="individual"),
            SanctionEntry(name="BOB", list_source="OFAC_SDN", country="IR", type="individual"),
        ]

    def test_first_write_creates_csv_and_meta(self, tmp_path):
        cache = SanctionsCache(lists_dir=tmp_path)
        result = cache.write("test", self._make_entries(), source_url="http://x")
        assert result.unchanged is False
        assert result.row_count == 2
        assert result.csv_path.exists()
        assert (tmp_path / ".cache" / "test.meta.json").exists()
        assert len(result.added) == 2
        assert result.removed == []

    def test_second_write_same_payload_unchanged(self, tmp_path):
        cache = SanctionsCache(lists_dir=tmp_path)
        cache.write("test", self._make_entries())
        result = cache.write("test", self._make_entries())
        assert result.unchanged is True
        assert result.added == []
        assert result.removed == []

    def test_diff_added_and_removed(self, tmp_path):
        cache = SanctionsCache(lists_dir=tmp_path)
        cache.write("test", self._make_entries())
        new_entries = [
            SanctionEntry(name="ALICE", list_source="OFAC_SDN", country="RU", type="individual"),
            SanctionEntry(name="CAROL", list_source="OFAC_SDN", country="KP", type="individual"),
        ]
        result = cache.write("test", new_entries)
        assert result.unchanged is False
        assert [e.name for e in result.added] == ["CAROL"]
        assert [e.name for e in result.removed] == ["BOB"]

    def test_canonical_csv_is_sorted(self, tmp_path):
        cache = SanctionsCache(lists_dir=tmp_path)
        unsorted = list(reversed(self._make_entries()))
        cache.write("test", unsorted)
        content = (tmp_path / "test.csv").read_text()
        # ALICE comes before BOB lexicographically.
        assert content.index("ALICE") < content.index("BOB")

    def test_meta_records_sha256_and_counts(self, tmp_path):
        cache = SanctionsCache(lists_dir=tmp_path)
        result = cache.write("test", self._make_entries(), source_url="http://x")
        meta = json.loads((tmp_path / ".cache" / "test.meta.json").read_bytes())
        assert meta["sha256"] == result.sha256
        assert meta["row_count"] == 2
        assert meta["added_count"] == 2
        assert meta["removed_count"] == 0
        assert meta["source_url"] == "http://x"

    def test_meta_persists_across_runs(self, tmp_path):
        cache = SanctionsCache(lists_dir=tmp_path)
        cache.write("test", self._make_entries())
        meta = cache.read_meta("test")
        assert meta is not None
        assert meta["row_count"] == 2

    def test_read_meta_missing_returns_none(self, tmp_path):
        cache = SanctionsCache(lists_dir=tmp_path)
        assert cache.read_meta("never_synced") is None


# ---------------------------------------------------------------------------
# sync_source orchestrator
# ---------------------------------------------------------------------------


class TestSyncOrchestrator:
    def test_sync_with_payload_bypasses_network(self, tmp_path):
        result = sync_source(
            OFACAdvancedXMLSource(),
            lists_dir=tmp_path,
            payload=_OFAC_FIXTURE,
        )
        assert result.row_count == 3
        assert (tmp_path / "ofac.csv").exists()

    def test_sync_uses_custom_list_name(self, tmp_path):
        result = sync_source(
            OFACAdvancedXMLSource(),
            lists_dir=tmp_path,
            list_name="sanctions",
            payload=_OFAC_FIXTURE,
        )
        assert (tmp_path / "sanctions.csv").exists()
        assert result.list_name == "sanctions"

    def test_sync_unchanged_on_repeat(self, tmp_path):
        sync_source(OFACAdvancedXMLSource(), lists_dir=tmp_path, payload=_OFAC_FIXTURE)
        second = sync_source(OFACAdvancedXMLSource(), lists_dir=tmp_path, payload=_OFAC_FIXTURE)
        assert second.unchanged is True


# ---------------------------------------------------------------------------
# CSV produced is consumable by list_match (smoke test against engine path)
# ---------------------------------------------------------------------------


class TestCSVCompatibleWithEngine:
    def test_csv_columns_match_engine_loader(self, tmp_path):
        sync_source(
            OFACAdvancedXMLSource(),
            lists_dir=tmp_path,
            list_name="sanctions",
            payload=_OFAC_FIXTURE,
        )
        # Mirror the engine's `_load_reference_list` minimal expectation:
        # csv DictReader[row]['name'] is non-empty.
        import csv as _csv

        rows = list(_csv.DictReader((tmp_path / "sanctions.csv").open()))
        assert all(r.get("name") for r in rows)
        assert all(r.get("list_source") for r in rows)
