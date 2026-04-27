"""Public-data attribution adapters.

Two adapters in v1, designed to mirror the `sanctions/` adapter shape
from PR #44 (fetch + parse split, lazy stdlib HTTP, no extra deps).

OFACCryptoAddressesSource
    Parses OFAC's bundled crypto-addresses text dump. Format is one
    address per line preceded by a wallet-type prefix (`XBT`, `ETH`,
    `XMR`, `USDT`) and followed by the SDN entity name in
    parentheses. Real OFAC data lives in the SDN advanced XML
    (handled by PR #44's `OFACAdvancedXMLSource`); this adapter is
    targeted at the simpler text-format crypto address bundle.

WalletLabelsSource
    De-facto standard `walletlabels.csv` schema used by several open
    data sets (e.g. Etherscan address labels, walletexplorer.com
    cluster export). Columns: `address,label,category,jurisdiction`.

Real production deployments will plug in commercial feeds
(Chainalysis Reactor, TRM Labs, Elliptic) behind the same
`name + load(path) → list[VaspAttribution]` shape.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Iterable

from aml_framework.vasp.attribution import VaspAttribution, VaspTier


# ---------------------------------------------------------------------------
# OFAC crypto-addresses adapter (text format)
# ---------------------------------------------------------------------------


_OFAC_LINE = re.compile(
    r"""^\s*
        (?P<chain>XBT|ETH|XMR|USDT|TRX|BSC|LTC|ZEC|ARB|DASH)
        \s+
        (?P<address>[\w\-]+)
        (?:\s*\((?P<entity>[^)]+)\))?
        \s*$
    """,
    re.VERBOSE,
)


class OFACCryptoAddressesSource:
    """Parser for OFAC's crypto addresses text bundle."""

    name = "ofac_crypto_addresses"
    list_source = "OFAC_CRYPTO"

    def fetch(self, url: str | None = None, *, timeout: float = 30.0) -> bytes:
        from urllib.request import Request, urlopen

        if url is None:
            raise ValueError(
                "OFACCryptoAddressesSource.fetch needs an explicit URL — "
                "OFAC publishes the crypto bundle inside SDN.xml; "
                "operators typically pull a curated extract."
            )
        req = Request(url, headers={"User-Agent": "aml-open-framework/1.0"})
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - explicit URL
            return resp.read()

    def parse(self, payload: bytes | str) -> list[VaspAttribution]:
        text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
        out: list[VaspAttribution] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            m = _OFAC_LINE.match(line)
            if not m:
                continue
            entity = (m.group("entity") or "OFAC SDN").strip()
            out.append(
                VaspAttribution(
                    address=m.group("address"),
                    cluster_name=entity,
                    tier="sanctioned",
                    source=self.list_source,
                    flags=("ofac_sdn",),
                )
            )
        return out

    def load(self, path: str | Path) -> list[VaspAttribution]:
        return self.parse(Path(path).read_bytes())


# ---------------------------------------------------------------------------
# walletlabels.csv adapter
# ---------------------------------------------------------------------------


# Map common label categories → our VaspTier enum.
_CATEGORY_TIER_MAP: dict[str, VaspTier] = {
    "exchange": "tier_1",
    "regulated_exchange": "tier_1",
    "tier_1_exchange": "tier_1",
    "tier_2_exchange": "tier_2",
    "vasp": "tier_2",
    "unregulated_exchange": "tier_3",
    "p2p_exchange": "tier_3",
    "mixer": "mixer",
    "tumbler": "mixer",
    "privacy": "mixer",
    "ransomware": "ransomware",
    "darknet_market": "darknet",
    "darknet": "darknet",
    "sanctioned": "sanctioned",
    "ofac_sdn": "sanctioned",
}


class WalletLabelsSource:
    """Parser for the `walletlabels.csv` schema.

    Required columns: `address`, `label` (cluster name), `category`,
    `jurisdiction`. Extra columns are tolerated and ignored.
    """

    name = "walletlabels"
    list_source = "WALLETLABELS"

    def fetch(self, url: str | None = None, *, timeout: float = 30.0) -> bytes:
        from urllib.request import Request, urlopen

        if url is None:
            raise ValueError(
                "WalletLabelsSource.fetch needs an explicit URL or local path; "
                "use `load(path)` for local files."
            )
        req = Request(url, headers={"User-Agent": "aml-open-framework/1.0"})
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - explicit URL
            return resp.read()

    def parse(self, payload: bytes | str) -> list[VaspAttribution]:
        text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
        out: list[VaspAttribution] = []
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            address = (row.get("address") or "").strip()
            if not address:
                continue
            category = (row.get("category") or "").strip().lower()
            tier = _CATEGORY_TIER_MAP.get(category, "unknown")
            label = (row.get("label") or row.get("cluster_name") or category or "unknown").strip()
            jurisdiction = (row.get("jurisdiction") or "").strip().upper()[:2]
            flags: tuple[str, ...] = ()
            extra = (row.get("flags") or "").strip()
            if extra:
                flags = tuple(f.strip() for f in extra.split(",") if f.strip())
            out.append(
                VaspAttribution(
                    address=address,
                    cluster_name=label,
                    tier=tier,
                    jurisdiction=jurisdiction,
                    source=self.list_source,
                    flags=flags,
                )
            )
        return out

    def load(self, path: str | Path) -> list[VaspAttribution]:
        return self.parse(Path(path).read_bytes())


# ---------------------------------------------------------------------------
# Convenience: bulk-load multiple sources into a single store
# ---------------------------------------------------------------------------


def load_into_store(store, sources: Iterable[tuple[object, str | Path]]) -> None:
    """Convenience helper: each (source, path) pair gets `load`-ed and added."""
    for source, path in sources:
        attrs = source.load(path)
        store.add_many(attrs)
