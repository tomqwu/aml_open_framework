"""VaspAttribution model + in-memory store + transaction enrichment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

VaspTier = Literal[
    "tier_1",  # major regulated exchange (e.g. Coinbase, Binance, Kraken)
    "tier_2",  # smaller regulated VASP
    "tier_3",  # unregulated / opaque exchange
    "mixer",  # privacy-preserving service
    "ransomware",  # cluster tied to ransomware payments
    "darknet",  # cluster tied to darknet markets
    "sanctioned",  # OFAC / EU / UN sanctioned cluster
    "unknown",
]


@dataclass(frozen=True)
class VaspAttribution:
    """Classification of one wallet / address cluster.

    `flags` carries free-form risk indicators (e.g. "iran_nexus",
    "russia_sanctions_evasion") so a rule can filter on a specific
    indicator without having to add it to the tier enum.
    """

    address: str
    cluster_name: str
    tier: VaspTier
    jurisdiction: str = ""  # ISO-2 of the operating entity, when known
    source: str = ""  # adapter that produced this attribution
    flags: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 1.0  # 0..1; commercial feeds may overwrite

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "cluster_name": self.cluster_name,
            "tier": self.tier,
            "jurisdiction": self.jurisdiction,
            "source": self.source,
            "flags": list(self.flags),
            "confidence": self.confidence,
        }


class VaspAttributionStore:
    """Address → VaspAttribution lookup with tier/flag indexes.

    Last-write-wins on duplicate addresses. The store is intentionally
    in-memory; a production deployment swaps it for a Redis or
    Postgres-backed implementation behind the same interface.
    """

    def __init__(self) -> None:
        self._by_address: dict[str, VaspAttribution] = {}
        self._by_cluster: dict[str, list[str]] = {}

    def __len__(self) -> int:
        return len(self._by_address)

    def add(self, attr: VaspAttribution) -> None:
        # Normalise: case-insensitive ETH/BTC mix; strip whitespace.
        addr = self._normalise(attr.address)
        if not addr:
            return
        normalised = VaspAttribution(
            address=addr,
            cluster_name=attr.cluster_name,
            tier=attr.tier,
            jurisdiction=attr.jurisdiction,
            source=attr.source,
            flags=tuple(attr.flags),
            confidence=attr.confidence,
        )
        self._by_address[addr] = normalised
        self._by_cluster.setdefault(attr.cluster_name, []).append(addr)

    def add_many(self, attrs: Iterable[VaspAttribution]) -> None:
        for a in attrs:
            self.add(a)

    def classify(self, address: str | None) -> VaspAttribution | None:
        if not address:
            return None
        return self._by_address.get(self._normalise(address))

    def addresses_in_cluster(self, cluster_name: str) -> list[str]:
        return list(self._by_cluster.get(cluster_name, []))

    def by_tier(self, tier: VaspTier) -> list[VaspAttribution]:
        return [a for a in self._by_address.values() if a.tier == tier]

    @staticmethod
    def _normalise(address: str) -> str:
        """Strip + uppercase. Crypto addresses are case-mixed in source data
        (Ethereum is checksummed; Bitcoin is mixed) but are uniquely identified
        by a case-insensitive comparison for our lookup purposes. Production
        code should keep checksummed forms for display and uppercase only for
        the index — this v1 keeps it simple."""
        return (address or "").strip().upper()


def enrich_transactions(
    txns: list[dict[str, Any]],
    store: VaspAttributionStore,
    *,
    address_field: str = "counterparty_address",
) -> list[dict[str, Any]]:
    """Return new transaction dicts with a `counterparty_vasp` block added.

    Source transactions are not mutated. When the counterparty address
    is missing or unattributed, the resulting txn carries
    `counterparty_vasp: None` so downstream filters can still treat
    "unknown" as a distinct case.
    """
    enriched: list[dict[str, Any]] = []
    for t in txns:
        addr = t.get(address_field)
        attr = store.classify(addr)
        out = dict(t)  # shallow copy
        out["counterparty_vasp"] = attr.to_dict() if attr is not None else None
        enriched.append(out)
    return enriched
