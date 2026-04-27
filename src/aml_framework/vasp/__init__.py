"""Counterparty-VASP attribution layer.

Closes the gap between "block this OFAC-listed wallet" (already covered
by `list_match` against `sanctioned_wallets.csv`) and "score the
*counterparty* of every crypto transfer based on its full attribution
profile" (the high-margin Chainalysis / TRM Labs / ComplyAdvantage paid
capability). Public attribution data is noisier than commercial feeds
but enough for typology-coverage and compliant detection of obvious
risk vectors: sanctioned-nexus exchanges, mixers, ransomware payment
clusters, jurisdiction-of-concern on/off ramps.

Why now (2026)
- **OFAC's January 2026 designation of UK-registered Zedcex/Zedxion**
  (tens of billions in IRGC-linked flows) made counterparty-VASP
  attribution the dominant risk vector for any institution serving
  crypto on/off ramps.
- **Tornado Cash delisting (March 2025)** moved the field from
  "block this address" to "score this counterparty's full attribution
  profile" — single-address blocklists are no longer sufficient.

Design
- Each `VaspAttribution` is a single classification of one wallet
  address: VASP cluster name + tier + jurisdiction + risk flags.
- Sources implement a simple `name + load(path) → list[VaspAttribution]`
  contract — same shape as `sanctions/` adapters from PR #44.
- Two adapters in v1: `OFACCryptoAddressesSource` (parses OFAC's text
  list) and `WalletLabelsSource` (parses the de-facto-standard
  `walletlabels.csv` schema used by several open data sets).
- `VaspAttributionStore` indexes attributions by address for O(1)
  lookup and exposes `classify(addr) → VaspAttribution | None`.
- `enrich_transactions(txns, store)` annotates each txn with a
  `counterparty_vasp` block (cluster, tier, jurisdiction, flags) so
  downstream `list_match` / `aggregation_window` rules can filter on
  attribution attributes.

This is **public-data-only** by design. Production VASP de-risking
should layer commercial enrichment (Chainalysis, TRM Labs, Elliptic)
on top via the same store + enrich shape — the engine doesn't care
which provider populated the attribution.
"""

from aml_framework.vasp.attribution import (
    VaspAttribution,
    VaspTier,
    VaspAttributionStore,
    enrich_transactions,
)
from aml_framework.vasp.sources import (
    OFACCryptoAddressesSource,
    WalletLabelsSource,
)

__all__ = [
    "VaspAttribution",
    "VaspTier",
    "VaspAttributionStore",
    "enrich_transactions",
    "OFACCryptoAddressesSource",
    "WalletLabelsSource",
]
