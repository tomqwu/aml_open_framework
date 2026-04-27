"""High-level sync orchestrator used by the CLI."""

from __future__ import annotations

from pathlib import Path

from aml_framework.sanctions.base import SanctionsSource
from aml_framework.sanctions.cache import SanctionsCache, SyncResult


def sync_source(
    source: SanctionsSource,
    *,
    lists_dir: Path,
    list_name: str | None = None,
    url: str | None = None,
    payload: bytes | None = None,
) -> SyncResult:
    """Fetch (or use given payload), parse, and cache a sanctions feed.

    Pass `payload=...` to skip the network call (used in tests and for
    operators who download via mirror or proxy and feed bytes directly).
    """
    list_name = list_name or source.name
    if payload is None:
        payload = source.fetch(url)
    entries = source.parse(payload)
    cache = SanctionsCache(lists_dir=lists_dir)
    return cache.write(list_name, entries, source_url=url)
