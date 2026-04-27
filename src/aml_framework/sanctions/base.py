"""Sanction entry record + source protocol shared by all adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SanctionEntry:
    """A single individual / entity / vessel on a sanctions list.

    Designed to round-trip through the engine's `data/lists/*.csv` schema
    (`name,list_source,country,type`) without information loss for the core
    fields. Extra metadata (aliases, program code, upstream UID) is kept
    for downstream consumers but not required by `list_match` matching.
    """

    name: str
    list_source: str
    country: str = ""
    type: str = "individual"  # individual | entity | vessel | aircraft | wallet
    aliases: tuple[str, ...] = field(default_factory=tuple)
    program: str | None = None  # OFAC program code (e.g. RUSSIA-EO14024)
    list_id: str | None = None  # upstream UID for traceability

    def csv_row(self) -> dict[str, str]:
        """Render to the flat CSV columns the engine reads."""
        return {
            "name": self.name,
            "list_source": self.list_source,
            "country": self.country,
            "type": self.type,
        }


@runtime_checkable
class SanctionsSource(Protocol):
    """Adapter protocol — fetch + parse for one upstream feed."""

    name: str
    list_source: str  # value to set on every emitted entry's `list_source`

    def fetch(self, url: str | None = None, *, timeout: float = 30.0) -> bytes:
        """Download the upstream payload. May raise on network error.

        Implementations should accept `url=None` to use a built-in default
        (the source's published endpoint); pass an explicit URL to override
        for sandboxes or proxies.
        """
        ...

    def parse(self, payload: bytes) -> list[SanctionEntry]:
        """Convert payload bytes to a list of entries. Pure, no IO."""
        ...
