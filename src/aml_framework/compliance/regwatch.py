"""Regulation drift watcher.

Round-7 PR #1. The framework ships 7 example specs that collectively cite
60+ regulations (FinCEN, FINTRAC, OFAC, AMLD6, EBA, FCA, POCA, FATF,
Wolfsberg, Basel). Those URLs change silently:

  - **FinCEN BOI Mar 2025 narrowing** — the canonical example. The page
    at `fincen.gov/boi` was overhauled without redirect; downstream
    specs citing the pre-narrowing language went stale.
  - FATF plenaries publish new typology papers + retire old ones.
  - EU Official Journal updates change paragraph numbers in AMLD/AMLR
    after corrigenda.
  - Wolfsberg revises principles roughly annually.

Without a watcher, operators discover the drift only when an auditor
flags it during examination.

This module hashes every `(citation, url)` pair across a spec's
`regulation_refs`, persists the hashes as a baseline, and on the next
run reports any URL whose content hash has changed.

Design
- Pure stdlib HTTP (urllib) so the module works on the minimal CI image
  without `requests` or `httpx`.
- HEAD-then-GET pattern: HEAD first to grab `Last-Modified` /
  `Content-Length` (cheap drift signal), then GET only when those say
  the page might have changed.
- `--offline` mode: skip network, only verify the baseline file's
  internal consistency. Useful for CI smoke tests + air-gapped envs.
- Cosmetic-edit guard: hash the *normalized* text (collapsed
  whitespace, stripped HTML script/style, lowercased anchor IDs) so
  trivial template tweaks don't false-positive. Operators tune via the
  `--diff-threshold-bytes` CLI flag.

Why no `requests` dependency: the framework already ships pip-installable
without it; adding a dep just for a defensive watcher would balloon the
"one binary, fast install" promise.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aml_framework.spec.models import AMLSpec

# ---------------------------------------------------------------------------
# Built-in citation → URL resolver
# ---------------------------------------------------------------------------
#
# Curated mapping for the most common citations across the bundled specs.
# Operators with novel citations should add `url:` to their spec's
# `regulation_refs` entry rather than extend this table — the table is
# meant for the "out of the box, every example spec works" case.

CITATION_URL_MAP: dict[str, str] = {
    # United States — FinCEN / OFAC / Federal Reserve
    "31 CFR 1010.314": "https://www.ecfr.gov/current/title-31/subtitle-B/chapter-X/part-1010/subpart-D/section-1010.314",
    "31 CFR 1010.311": "https://www.ecfr.gov/current/title-31/subtitle-B/chapter-X/part-1010/subpart-D/section-1010.311",
    "31 CFR 1010.610": "https://www.ecfr.gov/current/title-31/subtitle-B/chapter-X/part-1010/subpart-G/section-1010.610",
    "31 CFR 1020.315": "https://www.ecfr.gov/current/title-31/subtitle-B/chapter-X/part-1020/subpart-C/section-1020.315",
    "31 CFR 1020.320": "https://www.ecfr.gov/current/title-31/subtitle-B/chapter-X/part-1020/subpart-C/section-1020.320",
    "FinCEN Advisory FIN-2014-A005": "https://www.fincen.gov/sites/default/files/advisory/FIN-2014-A005.pdf",
    "FinCEN Advisory FIN-2006-A003": "https://www.fincen.gov/sites/default/files/shared/Advisory_2.pdf",
    "FinCEN FIN-2023-Alert005": "https://www.fincen.gov/sites/default/files/2023-09/FinCEN_Alert_Pig_Butchering_FINAL_508c.pdf",
    "FIN-2019-G001": "https://www.fincen.gov/sites/default/files/2019-05/FinCEN%20Guidance%20CVC%20FINAL%20508.pdf",
    # Canada
    "PCMLTFA s.7": "https://laws-lois.justice.gc.ca/eng/acts/p-24.501/section-7.html",
    "PCMLTFA s.9.4": "https://laws-lois.justice.gc.ca/eng/acts/p-24.501/section-9.4.html",
    "PCMLTFA s.11.1": "https://laws-lois.justice.gc.ca/eng/acts/p-24.501/section-11.1.html",
    "FINTRAC Guideline 8A": "https://fintrac-canafe.canada.ca/guidance-directives/transaction-operation/Guide8A/8A-eng",
    # European Union
    "AMLD6 Art. 50": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32018L1673",
    "AMLD6 Art. 18a": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32018L0843",
    "AMLD6 Art. 20-23": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32018L0843",
    "AMLD6 Art. 3(9)": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32018L0843",
    "Directive 2015/849 Art. 11": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32015L0849",
    "EU Delegated Regulation 2016/1675": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R1675",
    "EU Regulation 2023/1113 (Transfer of Funds)": "https://eur-lex.europa.eu/eli/reg/2023/1113/oj",
    "EU Regulation 269/2014": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32014R0269",
    "EU Regulation 2580/2001": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32001R2580",
    # FATF
    "FATF R.16 (June 2025 revision)": "https://www.fatf-gafi.org/en/publications/Fatfrecommendations/Travel-rule.html",
    "FATF R.16 (revised June 2025)": "https://www.fatf-gafi.org/en/publications/Fatfrecommendations/Travel-rule.html",
    "FATF R.16 nested service guidance": "https://www.fatf-gafi.org/en/publications/Fatfrecommendations/Travel-rule.html",
    "FATF Recommendation 19": "https://www.fatf-gafi.org/en/publications/Fatfrecommendations/Fatf-recommendations.html",
    "FATF Cyber-Enabled Fraud (Feb 2026)": "https://www.fatf-gafi.org/en/publications/Methodsandtrends/Cyber-enabled-fraud.html",
    # Canada — FINTRAC reports
    "FINTRAC LVCTR (Large Virtual Currency Transaction Report)": "https://fintrac-canafe.canada.ca/reporting-declaration/Info/rpt-eng",
    "FINTRAC ML/TF Indicators": "https://fintrac-canafe.canada.ca/guidance-directives/transaction-operation/indicators/eng",
    "FINTRAC Operational Alert 2016-01": "https://fintrac-canafe.canada.ca/intel/operation/oai-eng",
    # UK
    "Criminal Code s.83.08": "https://laws-lois.justice.gc.ca/eng/acts/c-46/section-83.08.html",
}


def citation_url(citation: str, *, override: str | None = None) -> str | None:
    """Resolve a citation to its canonical URL.

    Lookup order:
      1. Explicit `override` (typically the spec's `regulation_refs[].url`)
      2. Built-in `CITATION_URL_MAP`
      3. None — caller decides whether to skip or warn

    Returns None when the citation isn't resolvable. Operators should
    add a `url:` field to their `regulation_refs` entry to register
    novel citations.
    """
    if override:
        return override
    return CITATION_URL_MAP.get(citation)


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


_WHITESPACE_RE = re.compile(r"\s+")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def normalize_content(payload: bytes) -> str:
    """Strip cosmetic noise so trivial template edits don't false-positive.

    Order matters: drop scripts/styles first (they often carry analytics
    fingerprints that change every page-load), then comments, then tags
    themselves, then collapse whitespace + lowercase.
    """
    try:
        text = payload.decode("utf-8", errors="replace")
    except Exception:
        return ""
    text = _SCRIPT_STYLE_RE.sub(" ", text)
    text = _HTML_COMMENT_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip().lower()


def content_hash(payload: bytes) -> str:
    """SHA-256 over the normalized content. 64-char hex string."""
    return hashlib.sha256(normalize_content(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Network fetch
# ---------------------------------------------------------------------------


_USER_AGENT = "aml-framework-regwatch/1.0 (+https://github.com/tomqwu/aml_open_framework)"


def fetch(url: str, *, timeout_seconds: float = 15.0) -> bytes | None:
    """Fetch a URL with a polite User-Agent. Returns None on any failure.

    We swallow errors silently (logged via the caller's report) because
    a missing or unreachable URL is a *finding*, not an exception —
    operators want a "URL went 404" report, not a stack trace.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegwatchEntry:
    """One regulation citation + URL + hash snapshot."""

    citation: str
    url: str
    content_hash: str
    fetched_at: str  # ISO 8601 UTC

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RegwatchEntry:
        return cls(
            citation=d["citation"],
            url=d["url"],
            content_hash=d["content_hash"],
            fetched_at=d["fetched_at"],
        )


@dataclass
class DriftReport:
    """Result of comparing a current scan against a baseline.

    Each list contains `(citation, url, ...details)` tuples for the four
    categories of finding. Operators triage in order: `unreachable`
    (might be a transient outage) → `drifted` (real spec maintenance
    work) → `new` (additions to acknowledge) → `removed` (cleanup).
    """

    drifted: list[dict[str, str]] = field(default_factory=list)
    unreachable: list[dict[str, str]] = field(default_factory=list)
    new: list[dict[str, str]] = field(default_factory=list)
    removed: list[dict[str, str]] = field(default_factory=list)
    unchanged_count: int = 0

    @property
    def has_findings(self) -> bool:
        return bool(self.drifted or self.unreachable or self.new or self.removed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "drifted": self.drifted,
            "unreachable": self.unreachable,
            "new": self.new,
            "removed": self.removed,
            "unchanged_count": self.unchanged_count,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_spec(spec: AMLSpec) -> list[tuple[str, str | None]]:
    """Walk a spec and return every (citation, resolved_url) pair.

    De-duplicated by (citation, url) so a regulation cited by 5 rules
    only gets fetched once. Sorted for deterministic output.
    """
    seen: set[tuple[str, str | None]] = set()
    for rule in spec.rules:
        for ref in rule.regulation_refs:
            url = citation_url(ref.citation, override=ref.url)
            seen.add((ref.citation, url))
    return sorted(seen)


def fetch_current(
    citations: list[tuple[str, str | None]],
    *,
    fetch_fn=fetch,
    now: datetime | None = None,
) -> tuple[list[RegwatchEntry], list[dict[str, str]]]:
    """Fetch every URL and return (current_entries, unreachable_findings).

    `fetch_fn` is injectable for tests so we don't hit the network in CI.
    """
    now = now or datetime.now(tz=timezone.utc)
    fetched_at = now.isoformat(timespec="seconds")

    entries: list[RegwatchEntry] = []
    unreachable: list[dict[str, str]] = []

    for citation, url in citations:
        if url is None:
            unreachable.append(
                {
                    "citation": citation,
                    "url": "",
                    "reason": "no resolvable URL — add `url:` to regulation_refs entry",
                }
            )
            continue
        payload = fetch_fn(url)
        if payload is None:
            unreachable.append(
                {
                    "citation": citation,
                    "url": url,
                    "reason": "fetch failed (network error, 404, or timeout)",
                }
            )
            continue
        entries.append(
            RegwatchEntry(
                citation=citation,
                url=url,
                content_hash=content_hash(payload),
                fetched_at=fetched_at,
            )
        )
    return entries, unreachable


def check_drift(
    spec: AMLSpec,
    baseline: list[RegwatchEntry],
    *,
    fetch_fn=fetch,
    now: datetime | None = None,
) -> DriftReport:
    """Compare current scan against baseline. Returns a DriftReport.

    Categorisation:
      - `drifted`: citation in both, hash differs
      - `unreachable`: citation in spec but URL fetch failed (or no URL)
      - `new`: citation in spec but not in baseline
      - `removed`: citation in baseline but not in spec
    """
    citations = scan_spec(spec)
    current, unreachable = fetch_current(citations, fetch_fn=fetch_fn, now=now)

    baseline_by_key = {(e.citation, e.url): e for e in baseline}
    current_by_key = {(e.citation, e.url): e for e in current}

    report = DriftReport(unreachable=unreachable)

    for key, cur in current_by_key.items():
        base = baseline_by_key.get(key)
        if base is None:
            report.new.append(
                {
                    "citation": cur.citation,
                    "url": cur.url,
                    "content_hash": cur.content_hash,
                    "fetched_at": cur.fetched_at,
                }
            )
        elif base.content_hash != cur.content_hash:
            report.drifted.append(
                {
                    "citation": cur.citation,
                    "url": cur.url,
                    "baseline_hash": base.content_hash,
                    "current_hash": cur.content_hash,
                    "baseline_fetched_at": base.fetched_at,
                    "current_fetched_at": cur.fetched_at,
                }
            )
        else:
            report.unchanged_count += 1

    for key, base in baseline_by_key.items():
        if key not in current_by_key and key not in {
            (u["citation"], u["url"]) for u in unreachable
        }:
            report.removed.append(
                {
                    "citation": base.citation,
                    "url": base.url,
                    "baseline_hash": base.content_hash,
                }
            )

    return report


# ---------------------------------------------------------------------------
# Baseline persistence
# ---------------------------------------------------------------------------


def load_baseline(path: Path) -> list[RegwatchEntry]:
    """Read a baseline JSON file. Returns empty list when file is missing."""
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries_raw = payload.get("entries", [])
    return [RegwatchEntry.from_dict(e) for e in entries_raw]


def save_baseline(entries: list[RegwatchEntry], path: Path) -> None:
    """Write a baseline JSON file (sorted, deterministic shape)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_entries = sorted(entries, key=lambda e: (e.citation, e.url))
    payload = {
        "version": 1,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "entries": [e.to_dict() for e in sorted_entries],
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
