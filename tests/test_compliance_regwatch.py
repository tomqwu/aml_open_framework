"""Regulation drift watcher tests — Round-7 PR #1.

Covers the pure-function surface (no network) by injecting `fetch_fn`.
The hash-determinism, drift detection, baseline round-trip, and
cosmetic-edit-tolerance checks all run on the unit-test CI image.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from aml_framework.compliance.regwatch import (
    CITATION_URL_MAP,
    DriftReport,
    RegwatchEntry,
    check_drift,
    citation_url,
    content_hash,
    fetch_current,
    load_baseline,
    normalize_content,
    save_baseline,
    scan_spec,
)
from aml_framework.spec import load_spec

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_US = PROJECT_ROOT / "examples" / "community_bank" / "aml.yaml"
SPEC_EU = PROJECT_ROOT / "examples" / "eu_bank" / "aml.yaml"


# ---------------------------------------------------------------------------
# citation_url resolver
# ---------------------------------------------------------------------------


class TestCitationResolver:
    def test_known_us_citation_resolves(self):
        url = citation_url("31 CFR 1010.314")
        assert url is not None
        assert "ecfr.gov" in url

    def test_known_eu_citation_resolves(self):
        url = citation_url("AMLD6 Art. 50")
        assert url is not None
        assert "eur-lex.europa.eu" in url

    def test_known_fatf_citation_resolves(self):
        url = citation_url("FATF R.16 (June 2025 revision)")
        assert url is not None
        assert "fatf-gafi.org" in url

    def test_unknown_citation_returns_none(self):
        assert citation_url("Bogus Citation 9999") is None

    def test_override_takes_precedence(self):
        url = citation_url(
            "31 CFR 1010.314",
            override="https://example.com/custom",
        )
        assert url == "https://example.com/custom"

    def test_override_used_for_unknown_citations(self):
        url = citation_url("Bogus Citation", override="https://x.example/")
        assert url == "https://x.example/"


# ---------------------------------------------------------------------------
# content_hash + normalize_content
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_identical_payload_same_hash(self):
        a = b"<html><body>Some text</body></html>"
        b = b"<html><body>Some text</body></html>"
        assert content_hash(a) == content_hash(b)

    def test_whitespace_difference_ignored(self):
        a = b"<html><body>Some  text</body></html>"
        b = b"<html><body>Some text</body></html>"
        # Collapsed whitespace makes these hash identically.
        assert content_hash(a) == content_hash(b)

    def test_script_tag_stripped(self):
        a = b"<html><script>tracker_id_1</script>real content</html>"
        b = b"<html><script>tracker_id_2</script>real content</html>"
        # Different script bodies, same real content → same hash.
        assert content_hash(a) == content_hash(b)

    def test_html_comments_stripped(self):
        a = b"<html><!-- build sha abc123 -->Real text</html>"
        b = b"<html><!-- build sha def456 -->Real text</html>"
        assert content_hash(a) == content_hash(b)

    def test_real_content_change_detected(self):
        a = b"<html>Original wording</html>"
        b = b"<html>Revised wording</html>"
        assert content_hash(a) != content_hash(b)

    def test_hash_is_64_hex_chars(self):
        h = content_hash(b"anything")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_normalize_lowercases(self):
        assert "abc" in normalize_content(b"ABC")

    def test_invalid_utf8_does_not_crash(self):
        # Garbage bytes — we should still get a hash, not an exception.
        h = content_hash(b"\xff\xfe\xfd")
        assert len(h) == 64


# ---------------------------------------------------------------------------
# scan_spec — walk a real spec
# ---------------------------------------------------------------------------


class TestScanSpec:
    def test_us_spec_returns_citations(self):
        spec = load_spec(SPEC_US)
        pairs = scan_spec(spec)
        assert pairs, "US spec should yield at least one citation"
        # Every pair is (citation, url-or-None).
        for citation, url in pairs:
            assert isinstance(citation, str) and citation
            assert url is None or isinstance(url, str)

    def test_us_spec_resolves_known_citations(self):
        spec = load_spec(SPEC_US)
        pairs = scan_spec(spec)
        resolved = [(c, u) for c, u in pairs if u is not None]
        # The US spec uses 31 CFR citations which are in CITATION_URL_MAP.
        assert resolved, "at least one citation should resolve to a URL"

    def test_eu_spec_resolves_known_citations(self):
        spec = load_spec(SPEC_EU)
        pairs = scan_spec(spec)
        resolved = [(c, u) for c, u in pairs if u is not None]
        assert resolved

    def test_dedup(self):
        # Two rules in the same spec citing the same regulation should
        # yield one (citation, url) pair, not two.
        spec = load_spec(SPEC_US)
        pairs = scan_spec(spec)
        assert len(pairs) == len(set(pairs))

    def test_sorted_output(self):
        spec = load_spec(SPEC_US)
        pairs = scan_spec(spec)
        assert pairs == sorted(pairs)


# ---------------------------------------------------------------------------
# fetch_current with injected fetch_fn
# ---------------------------------------------------------------------------


def _stub_fetch_factory(payloads: dict[str, bytes]):
    """Returns a fetch_fn that yields canned responses keyed by URL."""

    def _fetch(url: str) -> bytes | None:
        return payloads.get(url)

    return _fetch


class TestFetchCurrent:
    def test_all_urls_succeed(self):
        citations = [
            ("Reg A", "https://a.example/"),
            ("Reg B", "https://b.example/"),
        ]
        fetch_fn = _stub_fetch_factory(
            {
                "https://a.example/": b"content A",
                "https://b.example/": b"content B",
            }
        )
        entries, unreachable = fetch_current(
            citations, fetch_fn=fetch_fn, now=datetime(2026, 4, 27, tzinfo=timezone.utc)
        )
        assert len(entries) == 2
        assert not unreachable
        # fetched_at is a real ISO timestamp.
        for e in entries:
            assert e.fetched_at.startswith("2026-04-27")

    def test_failed_fetch_reports_unreachable(self):
        citations = [
            ("Reg A", "https://a.example/"),
            ("Reg B", "https://b.example/"),
        ]
        fetch_fn = _stub_fetch_factory({"https://a.example/": b"content A"})  # B missing
        entries, unreachable = fetch_current(citations, fetch_fn=fetch_fn)
        assert len(entries) == 1
        assert len(unreachable) == 1
        assert unreachable[0]["citation"] == "Reg B"

    def test_no_url_marked_unreachable(self):
        citations = [("Reg X", None)]
        entries, unreachable = fetch_current(citations, fetch_fn=lambda url: None)
        assert not entries
        assert len(unreachable) == 1
        assert "no resolvable URL" in unreachable[0]["reason"]


# ---------------------------------------------------------------------------
# check_drift — the load-bearing function
# ---------------------------------------------------------------------------


class TestCheckDrift:
    def _make_spec_two_rules(self):
        # We can't easily synthesize a spec without the YAML — load EU.
        return load_spec(SPEC_EU)

    def test_no_drift_when_baseline_matches(self):
        spec = self._make_spec_two_rules()
        citations = scan_spec(spec)
        # Force every URL to return identical content.
        fetch_fn = _stub_fetch_factory({u: b"same" for _, u in citations if u})
        baseline_entries, _ = fetch_current(
            citations, fetch_fn=fetch_fn, now=datetime(2026, 4, 1, tzinfo=timezone.utc)
        )
        report = check_drift(
            spec,
            baseline_entries,
            fetch_fn=fetch_fn,
            now=datetime(2026, 4, 27, tzinfo=timezone.utc),
        )
        assert not report.drifted
        assert report.unchanged_count > 0

    def test_drift_detected_when_content_changes(self):
        spec = self._make_spec_two_rules()
        citations = scan_spec(spec)
        first_url = next(u for _, u in citations if u)
        # Baseline payload set.
        baseline_payloads = {u: b"baseline content" for _, u in citations if u}
        baseline_entries, _ = fetch_current(
            citations, fetch_fn=_stub_fetch_factory(baseline_payloads)
        )
        # Drift: change the first URL's content.
        current_payloads = dict(baseline_payloads)
        current_payloads[first_url] = b"NEW WORDING"
        report = check_drift(spec, baseline_entries, fetch_fn=_stub_fetch_factory(current_payloads))
        assert any(d["url"] == first_url for d in report.drifted)

    def test_unreachable_separate_from_drift(self):
        spec = self._make_spec_two_rules()
        citations = scan_spec(spec)
        first_url = next(u for _, u in citations if u)
        # Baseline.
        baseline_entries, _ = fetch_current(
            citations,
            fetch_fn=_stub_fetch_factory({u: b"x" for _, u in citations if u}),
        )
        # Current: drop the first URL from the response set (404).
        current_payloads = {u: b"x" for _, u in citations if u and u != first_url}
        report = check_drift(spec, baseline_entries, fetch_fn=_stub_fetch_factory(current_payloads))
        # The dropped URL is unreachable, not drifted.
        assert any(u["url"] == first_url for u in report.unreachable)
        assert not any(d["url"] == first_url for d in report.drifted)

    def test_has_findings_property(self):
        empty = DriftReport()
        assert not empty.has_findings
        with_drift = DriftReport(drifted=[{"a": "b"}])
        assert with_drift.has_findings


# ---------------------------------------------------------------------------
# Baseline persistence
# ---------------------------------------------------------------------------


class TestBaselinePersistence:
    def test_round_trip(self, tmp_path):
        entries = [
            RegwatchEntry(
                citation="Reg A",
                url="https://a.example/",
                content_hash="abc" * 21 + "x",  # 64 chars
                fetched_at="2026-04-27T12:00:00+00:00",
            ),
            RegwatchEntry(
                citation="Reg B",
                url="https://b.example/",
                content_hash="def" * 21 + "x",
                fetched_at="2026-04-27T12:00:00+00:00",
            ),
        ]
        path = tmp_path / "baseline.json"
        save_baseline(entries, path)
        loaded = load_baseline(path)
        assert loaded == entries

    def test_load_missing_baseline_returns_empty(self, tmp_path):
        assert load_baseline(tmp_path / "nope.json") == []

    def test_baseline_file_is_deterministic(self, tmp_path):
        # Same input → same bytes (sorted entries, sorted JSON keys).
        entries_a = [
            RegwatchEntry("Z", "https://z/", "z" * 64, "2020-01-01T00:00:00+00:00"),
            RegwatchEntry("A", "https://a/", "a" * 64, "2020-01-01T00:00:00+00:00"),
        ]
        path_a = tmp_path / "a.json"
        save_baseline(entries_a, path_a)
        # Reverse the input order — should produce identical file because
        # save_baseline sorts internally.
        path_b = tmp_path / "b.json"
        save_baseline(list(reversed(entries_a)), path_b)
        # Compare entries fields (generated_at differs since it's now()).
        a_payload = json.loads(path_a.read_text())
        b_payload = json.loads(path_b.read_text())
        assert a_payload["entries"] == b_payload["entries"]


# ---------------------------------------------------------------------------
# CITATION_URL_MAP completeness checks
# ---------------------------------------------------------------------------


class TestCitationMapCoverage:
    def test_map_has_us_canada_eu_uk_fatf(self):
        # Spot-check at least one citation from each major regime.
        for citation in (
            "31 CFR 1010.314",  # US
            "PCMLTFA s.7",  # CA
            "AMLD6 Art. 50",  # EU
            "FATF R.16 (June 2025 revision)",  # FATF
        ):
            assert citation in CITATION_URL_MAP, f"missing canonical citation: {citation}"

    def test_every_mapped_url_has_https(self):
        for citation, url in CITATION_URL_MAP.items():
            assert url.startswith("https://"), (
                f"citation {citation!r} mapped to non-HTTPS URL {url!r}"
            )
