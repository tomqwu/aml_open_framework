"""OFAC SDN Advanced XML adapter.

OFAC publishes the canonical SDN list at
    https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/sdn_advanced.xml

The XML is large (~50 MB) and follows the Sanctions List Data Format (SDN
Advanced). We extract the minimum needed for `list_match` rules: primary
name, party type, and the country reference for each `<DistinctParty>`.

The full SDN Advanced schema includes nested `<Documentation>`, `<Feature>`,
`<NamePart>` with role codes, and external `<ReferenceValueSet>` lookups for
country ISO codes. v1 of this adapter parses primary names + the simple
`PrimaryName` role and emits one entry per DistinctParty. Aliases are
collected for downstream fuzzy match but not exploded into separate rows.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from aml_framework.sanctions.base import SanctionEntry

DEFAULT_OFAC_URL = (
    "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/sdn_advanced.xml"
)

# OFAC publishes under the sdnList namespace; we strip namespaces during
# parsing to keep XPath simple. Real production parsers may want to
# preserve them.
_PARTY_TYPE_MAP = {
    "Individual": "individual",
    "Entity": "entity",
    "Vessel": "vessel",
    "Aircraft": "aircraft",
}


def _strip_ns(tag: str) -> str:
    """`{http://...}DistinctParty` → `DistinctParty`."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


class OFACAdvancedXMLSource:
    """Parser for OFAC SDN Advanced XML format."""

    name = "ofac"
    list_source = "OFAC_SDN"
    default_url = DEFAULT_OFAC_URL

    def fetch(self, url: str | None = None, *, timeout: float = 30.0) -> bytes:
        """HTTP GET the OFAC SDN XML. Imports stdlib lazily so unit tests
        that only call `parse` don't hit the network module."""
        from urllib.request import Request, urlopen

        target = url or self.default_url
        req = Request(target, headers={"User-Agent": "aml-open-framework/1.0"})
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - explicit OFAC URL
            return resp.read()

    def parse(self, payload: bytes) -> list[SanctionEntry]:
        """Convert SDN Advanced XML bytes to entries.

        Tolerates trimmed fixture XML used in tests (only requires the
        DistinctParty elements that contain a primary name); OFAC's full
        document follows the same structure with extra metadata blocks
        we deliberately ignore.
        """
        root = ET.fromstring(payload)
        entries: list[SanctionEntry] = []
        for elem in root.iter():
            if _strip_ns(elem.tag) != "DistinctParty":
                continue
            entry = self._parse_party(elem)
            if entry is not None:
                entries.append(entry)
        return entries

    def _parse_party(self, party: ET.Element) -> SanctionEntry | None:
        """Extract one party. Returns None if no usable name found."""
        names: list[str] = []
        party_type: str | None = None
        country: str = ""
        list_id: str | None = party.attrib.get("FixedRef")

        for child in party.iter():
            tag = _strip_ns(child.tag)
            if tag == "DocumentedNameType":
                # OFAC schema variation: <DocumentedNameType>Primary Name</...>
                if child.text and "Primary" in child.text:
                    pass  # marker; following NamePart blocks are primary
            elif tag == "NamePartValue":
                if child.text:
                    names.append(child.text.strip())
            elif tag == "PartySubType":
                # OFAC uses <PartySubType><Value>Individual</Value></...>.
                value = child.findtext("./{*}Value") or child.findtext("./Value")
                if value:
                    party_type = _PARTY_TYPE_MAP.get(value.strip(), party_type)
            elif tag == "Value" and party_type is None:
                # Fallback: bare <Value>Individual</Value> directly under party
                if child.text and child.text.strip() in _PARTY_TYPE_MAP:
                    party_type = _PARTY_TYPE_MAP[child.text.strip()]
            elif tag == "Country":
                if child.text and not country:
                    country = child.text.strip()[:2].upper()
            elif tag == "ISO2":
                if child.text and not country:
                    country = child.text.strip().upper()

        if not names:
            return None

        primary = " ".join(names).strip()
        aliases = tuple(n for n in names[1:] if n != primary)

        return SanctionEntry(
            name=primary.upper(),
            list_source=self.list_source,
            country=country,
            type=party_type or "individual",
            aliases=aliases,
            list_id=list_id,
        )
