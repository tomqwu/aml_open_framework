"""Sanctions feed adapters — keep `data/lists/*.csv` fresh.

A regulated programme is only as current as its watchlists. This package
adapts upstream sources (OFAC SDN, EU Consolidated, ComplyAdvantage
webhook) to the framework's flat `name,list_source,country,type` CSV
format used by `list_match` rules.

Design
    Source.fetch(url) → bytes (HTTP; the only IO surface)
    Source.parse(payload: bytes) → list[SanctionEntry]
    SanctionsCache.write(name, entries) → SyncResult (delta-diff)

Tests pass payload bytes directly; no network calls in the unit suite.
"""

from aml_framework.sanctions.base import SanctionEntry, SanctionsSource
from aml_framework.sanctions.cache import SanctionsCache, SyncResult
from aml_framework.sanctions.complyadvantage import ComplyAdvantageWebhookSource
from aml_framework.sanctions.eu import EUConsolidatedSource
from aml_framework.sanctions.ofac import OFACAdvancedXMLSource
from aml_framework.sanctions.sync import sync_source

__all__ = [
    "SanctionEntry",
    "SanctionsSource",
    "SanctionsCache",
    "SyncResult",
    "OFACAdvancedXMLSource",
    "EUConsolidatedSource",
    "ComplyAdvantageWebhookSource",
    "sync_source",
]
