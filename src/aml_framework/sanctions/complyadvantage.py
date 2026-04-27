"""ComplyAdvantage webhook adapter.

ComplyAdvantage pushes entity additions/changes via webhook (JSON body,
HMAC-SHA256 signature in `X-CA-Signature`). This adapter is a stub: no
live API call (their endpoint is gated behind paid credentials), but the
parser + signature verifier are real so a deployment can wire the
webhook handler to the framework's CSV store immediately.

Payload shape (per ComplyAdvantage Monitor webhook v3):
    {
      "event": "monitor_match",
      "data": {
        "matches": [
          {
            "entity_id": "...",
            "name": "...",
            "country_codes": ["RU"],
            "entity_type": "person" | "company",
            "sources": ["OFAC SDN List", "EU Consolidated List"],
            ...
          }
        ]
      }
    }
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from aml_framework.sanctions.base import SanctionEntry

_ENTITY_TYPE_MAP = {
    "person": "individual",
    "company": "entity",
    "vessel": "vessel",
    "organisation": "entity",
}


class ComplyAdvantageWebhookSource:
    """Parser + signature verifier for ComplyAdvantage Monitor webhooks.

    `fetch()` is a stub — webhook payloads arrive via POST. Real
    deployments handle them in their HTTP layer and call `parse(body)`
    after verifying the signature with `verify_signature`.
    """

    name = "complyadvantage"
    list_source = "COMPLYADVANTAGE"

    def fetch(self, url: str | None = None, *, timeout: float = 30.0) -> bytes:
        raise NotImplementedError(
            "ComplyAdvantage delivers via webhook. POST handler should call "
            "parse() with the request body after verifying the signature."
        )

    def parse(self, payload: bytes) -> list[SanctionEntry]:
        try:
            body = json.loads(payload)
        except json.JSONDecodeError:
            return []

        matches = (body.get("data") or {}).get("matches") or []
        if not isinstance(matches, list):
            return []

        entries: list[SanctionEntry] = []
        for m in matches:
            entry = self._parse_match(m)
            if entry is not None:
                entries.append(entry)
        return entries

    @staticmethod
    def verify_signature(payload: bytes, signature_header: str, secret: str) -> bool:
        """Constant-time HMAC-SHA256 comparison.

        ComplyAdvantage formats the header as `sha256=<hex>`. We accept
        the bare hex form too for simpler integration tests.
        """
        if signature_header.startswith("sha256="):
            signature_header = signature_header[len("sha256=") :]
        expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature_header.strip())

    def _parse_match(self, match: dict[str, Any]) -> SanctionEntry | None:
        name = match.get("name")
        if not name:
            return None
        entity_type = _ENTITY_TYPE_MAP.get((match.get("entity_type") or "").lower(), "individual")
        countries = match.get("country_codes") or []
        country = ""
        if isinstance(countries, list) and countries:
            country = str(countries[0]).upper()[:2]
        sources = match.get("sources") or []
        source_label = self.list_source
        if isinstance(sources, list) and sources:
            source_label = f"{self.list_source}:{sources[0]}"

        return SanctionEntry(
            name=str(name).upper(),
            list_source=source_label,
            country=country,
            type=entity_type,
            list_id=match.get("entity_id"),
        )
