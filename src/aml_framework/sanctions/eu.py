"""EU Consolidated sanctions list adapter.

The EU Financial Sanctions List is published as XML by the European
Commission (FSF) at
    https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content

Each `<sanctionEntity>` contains one or more `<nameAlias>` blocks plus a
`<subjectType>` (P=Person, E=Enterprise) and optional citizenship/address
country. We extract the primary name (first nameAlias.wholeName) plus
aliases.

The full schema (xmlSanctionsListSchema.xsd) carries dates, BIC codes,
identification documents, and remarks. v1 keeps the same minimal subset
we use for OFAC so the cache + diff path is uniform across sources.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from aml_framework.sanctions.base import SanctionEntry

DEFAULT_EU_URL = (
    "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content"
)

_SUBJECT_TYPE_MAP = {
    "P": "individual",
    "E": "entity",
    "V": "vessel",
}


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


class EUConsolidatedSource:
    """Parser for the EU Consolidated XML feed."""

    name = "eu"
    list_source = "EU_CONSOL"
    default_url = DEFAULT_EU_URL

    def fetch(self, url: str | None = None, *, timeout: float = 30.0) -> bytes:
        from urllib.request import Request, urlopen

        target = url or self.default_url
        req = Request(target, headers={"User-Agent": "aml-open-framework/1.0"})
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - explicit EU URL
            return resp.read()

    def parse(self, payload: bytes) -> list[SanctionEntry]:
        root = ET.fromstring(payload)
        entries: list[SanctionEntry] = []
        for elem in root.iter():
            if _strip_ns(elem.tag) != "sanctionEntity":
                continue
            entry = self._parse_entity(elem)
            if entry is not None:
                entries.append(entry)
        return entries

    def _parse_entity(self, entity: ET.Element) -> SanctionEntry | None:
        names: list[str] = []
        country = ""
        subject_type = "individual"
        list_id = entity.attrib.get("logicalId") or entity.attrib.get("euReferenceNumber")
        program = entity.attrib.get("regulation") or entity.attrib.get("designationDetails")

        for child in entity.iter():
            tag = _strip_ns(child.tag)
            if tag == "subjectType":
                code = child.attrib.get("code") or (child.text or "").strip()
                subject_type = _SUBJECT_TYPE_MAP.get(code, subject_type)
            elif tag == "nameAlias":
                name = child.attrib.get("wholeName") or ""
                if name.strip():
                    names.append(name.strip())
            elif tag == "citizenship":
                code = child.attrib.get("countryIso2Code", "").upper()
                if code and not country:
                    country = code
            elif tag == "address":
                code = child.attrib.get("countryIso2Code", "").upper()
                if code and not country:
                    country = code

        if not names:
            return None

        primary = names[0]
        aliases = tuple(n for n in names[1:] if n != primary)
        return SanctionEntry(
            name=primary.upper(),
            list_source=self.list_source,
            country=country,
            type=subject_type,
            aliases=aliases,
            program=program,
            list_id=list_id,
        )
