"""Tests for the counterparty-VASP attribution layer.

Network is forbidden in CI; both adapters are exercised via `parse()`
on payload bytes / `load()` on the bundled sample CSV.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aml_framework.vasp import (
    OFACCryptoAddressesSource,
    VaspAttribution,
    VaspAttributionStore,
    WalletLabelsSource,
    enrich_transactions,
)
from aml_framework.vasp.sources import load_into_store

SAMPLE_LABELS_CSV = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "aml_framework"
    / "data"
    / "lists"
    / "sample_walletlabels.csv"
)


# ---------------------------------------------------------------------------
# OFAC text-format parser
# ---------------------------------------------------------------------------


_OFAC_PAYLOAD = b"""# OFAC crypto addresses extract
XBT 1ZedcexBTCAddress0000000000000000000 (Zedcex / Zedxion)
ETH 0xZEDCEX00000000000000000000000000ZEDCEX00 (Zedcex / Zedxion)
USDT TLOWFEE000000000000000000000000000TLOWFEE
XMR 4HuioneMonero0000000000000000000000Huione (Huione Pay)

# blank lines and comments tolerated
ZEC zeczzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz (TornadoCash Lite)
"""


class TestOFACCryptoParser:
    def test_parses_each_supported_chain(self):
        out = OFACCryptoAddressesSource().parse(_OFAC_PAYLOAD)
        assert len(out) == 5

    def test_entity_in_parens_becomes_cluster_name(self):
        out = {a.address: a for a in OFACCryptoAddressesSource().parse(_OFAC_PAYLOAD)}
        eth = out["0xZEDCEX00000000000000000000000000ZEDCEX00"]
        assert eth.cluster_name == "Zedcex / Zedxion"
        assert eth.tier == "sanctioned"
        assert "ofac_sdn" in eth.flags

    def test_missing_entity_falls_back_to_default_cluster(self):
        out = {a.address: a for a in OFACCryptoAddressesSource().parse(_OFAC_PAYLOAD)}
        assert out["TLOWFEE000000000000000000000000000TLOWFEE"].cluster_name == "OFAC SDN"

    def test_blank_and_comment_lines_skipped(self):
        out = OFACCryptoAddressesSource().parse(b"# comment\n\n\nXBT 1foo (Foo)\n")
        assert len(out) == 1

    def test_unsupported_chain_skipped(self):
        out = OFACCryptoAddressesSource().parse(b"FOOBAR 1bar (Bar)\n")
        assert out == []

    def test_load_from_disk(self, tmp_path):
        f = tmp_path / "ofac.txt"
        f.write_bytes(_OFAC_PAYLOAD)
        out = OFACCryptoAddressesSource().load(f)
        assert len(out) == 5

    def test_fetch_requires_url(self):
        with pytest.raises(ValueError, match="explicit URL"):
            OFACCryptoAddressesSource().fetch()


# ---------------------------------------------------------------------------
# walletlabels.csv parser
# ---------------------------------------------------------------------------


class TestWalletLabelsParser:
    def test_parses_bundled_sample(self):
        attrs = WalletLabelsSource().load(SAMPLE_LABELS_CSV)
        assert len(attrs) == 6

    def test_category_to_tier_mapping(self):
        attrs = {a.address: a for a in WalletLabelsSource().load(SAMPLE_LABELS_CSV)}
        assert attrs["0xC0FFEEC0FFEEC0FFEEC0FFEEC0FFEEC0FFEEC0FF"].tier == "tier_1"
        assert attrs["0xDEADBEEFDEADBEEFDEADBEEFDEADBEEFDEADBEEF"].tier == "mixer"
        assert attrs["0xZEDCEX00000000000000000000000000ZEDCEX00"].tier == "sanctioned"
        assert attrs["TLOWFEE000000000000000000000000000TLOWFEE"].tier == "tier_3"
        assert attrs["0xRANSOMWARE000000000000000000000RANSOMWARE"].tier == "ransomware"

    def test_jurisdiction_uppercased_and_truncated(self):
        attrs = {a.address: a for a in WalletLabelsSource().load(SAMPLE_LABELS_CSV)}
        assert attrs["0xC0FFEEC0FFEEC0FFEEC0FFEEC0FFEEC0FFEEC0FF"].jurisdiction == "US"
        assert attrs["0xZEDCEX00000000000000000000000000ZEDCEX00"].jurisdiction == "GB"

    def test_flags_split_on_comma(self):
        attrs = {a.address: a for a in WalletLabelsSource().load(SAMPLE_LABELS_CSV)}
        zedcex = attrs["0xZEDCEX00000000000000000000000000ZEDCEX00"]
        assert "ofac_jan_2026" in zedcex.flags
        assert "iran_nexus" in zedcex.flags

    def test_unknown_category_falls_back_to_unknown_tier(self):
        out = WalletLabelsSource().parse(
            b"address,label,category,jurisdiction\n0xABC,Foo,bizarre_thing,US\n"
        )
        assert out[0].tier == "unknown"

    def test_empty_address_rows_skipped(self):
        out = WalletLabelsSource().parse(
            b"address,label,category,jurisdiction\n,Foo,exchange,US\n0xABC,Bar,mixer,XX\n"
        )
        assert len(out) == 1
        assert out[0].address == "0xABC"


# ---------------------------------------------------------------------------
# VaspAttributionStore
# ---------------------------------------------------------------------------


def _attr(address="0xABC", tier="tier_1", cluster="Coinbase", flags=()):
    return VaspAttribution(
        address=address, cluster_name=cluster, tier=tier, source="test", flags=tuple(flags)
    )


class TestVaspAttributionStore:
    def test_classify_returns_added_attribution(self):
        store = VaspAttributionStore()
        store.add(_attr())
        result = store.classify("0xABC")
        assert result is not None
        assert result.tier == "tier_1"

    def test_classify_normalises_case(self):
        store = VaspAttributionStore()
        store.add(_attr(address="0xabc"))
        assert store.classify("0xABC") is not None
        assert store.classify("0xabc") is not None

    def test_classify_returns_none_for_unknown(self):
        store = VaspAttributionStore()
        assert store.classify("0xDEAD") is None

    def test_classify_returns_none_for_empty(self):
        store = VaspAttributionStore()
        assert store.classify(None) is None
        assert store.classify("") is None

    def test_last_write_wins_on_duplicate(self):
        store = VaspAttributionStore()
        store.add(_attr(tier="tier_1", cluster="Coinbase"))
        store.add(_attr(tier="sanctioned", cluster="OFAC Override"))
        assert store.classify("0xABC").tier == "sanctioned"

    def test_by_tier_filters(self):
        store = VaspAttributionStore()
        store.add(_attr(address="0xA", tier="tier_1"))
        store.add(_attr(address="0xB", tier="mixer"))
        store.add(_attr(address="0xC", tier="tier_1"))
        assert {a.address for a in store.by_tier("tier_1")} == {"0XA", "0XC"}

    def test_addresses_in_cluster(self):
        store = VaspAttributionStore()
        store.add(_attr(address="0xA", cluster="Coinbase"))
        store.add(_attr(address="0xB", cluster="Coinbase"))
        assert sorted(store.addresses_in_cluster("Coinbase")) == ["0XA", "0XB"]

    def test_len(self):
        store = VaspAttributionStore()
        for i in range(3):
            store.add(_attr(address=f"0x{i:040x}"))
        assert len(store) == 3


# ---------------------------------------------------------------------------
# enrich_transactions
# ---------------------------------------------------------------------------


class TestEnrichTransactions:
    def test_attaches_classification_when_known(self):
        store = VaspAttributionStore()
        store.add(_attr(address="0xCEX", tier="tier_1", cluster="Coinbase"))
        txns = [{"txn_id": "T1", "amount": 100, "counterparty_address": "0xCEX"}]
        enriched = enrich_transactions(txns, store)
        assert enriched[0]["counterparty_vasp"]["tier"] == "tier_1"
        assert enriched[0]["counterparty_vasp"]["cluster_name"] == "Coinbase"

    def test_attaches_none_when_unknown(self):
        store = VaspAttributionStore()
        txns = [{"txn_id": "T1", "counterparty_address": "0xUNKNOWN"}]
        enriched = enrich_transactions(txns, store)
        assert enriched[0]["counterparty_vasp"] is None

    def test_does_not_mutate_source_txns(self):
        store = VaspAttributionStore()
        store.add(_attr(address="0xCEX"))
        original = {"txn_id": "T1", "counterparty_address": "0xCEX"}
        enriched = enrich_transactions([original], store)
        assert "counterparty_vasp" not in original
        assert "counterparty_vasp" in enriched[0]

    def test_address_field_override(self):
        store = VaspAttributionStore()
        store.add(_attr(address="0xCEX"))
        txns = [{"txn_id": "T1", "to_address": "0xCEX"}]
        enriched = enrich_transactions(txns, store, address_field="to_address")
        assert enriched[0]["counterparty_vasp"] is not None


# ---------------------------------------------------------------------------
# load_into_store helper
# ---------------------------------------------------------------------------


class TestLoadIntoStore:
    def test_combines_multiple_sources(self, tmp_path):
        ofac_file = tmp_path / "ofac.txt"
        ofac_file.write_bytes(_OFAC_PAYLOAD)

        store = VaspAttributionStore()
        load_into_store(
            store,
            [
                (OFACCryptoAddressesSource(), ofac_file),
                (WalletLabelsSource(), SAMPLE_LABELS_CSV),
            ],
        )
        assert 9 <= len(store) <= 11
        coinbase = store.classify("0xC0FFEEC0FFEEC0FFEEC0FFEEC0FFEEC0FFEEC0FF")
        assert coinbase is not None
        assert coinbase.tier == "tier_1"


# ---------------------------------------------------------------------------
# End-to-end with a list_match-style filter
# ---------------------------------------------------------------------------


class TestEndToEndComposition:
    def test_filter_to_sanctioned_counterparty_txns(self):
        """Demonstrates the use case: enrich txns, then filter to those
        whose counterparty is on a sanctioned cluster — the same shape
        a `list_match` rule would take after wiring this layer in."""
        store = VaspAttributionStore()
        store.add_many(WalletLabelsSource().load(SAMPLE_LABELS_CSV))

        txns = [
            {
                "txn_id": "T1",
                "amount": 100,
                "counterparty_address": "0xC0FFEEC0FFEEC0FFEEC0FFEEC0FFEEC0FFEEC0FF",
            },
            {
                "txn_id": "T2",
                "amount": 50000,
                "counterparty_address": "0xZEDCEX00000000000000000000000000ZEDCEX00",
            },
            {"txn_id": "T3", "amount": 200, "counterparty_address": "0xUNKNOWN"},
        ]
        enriched = enrich_transactions(txns, store)
        sanctioned = [
            t
            for t in enriched
            if t["counterparty_vasp"] and t["counterparty_vasp"]["tier"] == "sanctioned"
        ]
        assert [t["txn_id"] for t in sanctioned] == ["T2"]
