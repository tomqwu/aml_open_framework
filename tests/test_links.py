"""Unit tests for ``aml_framework.links``.

R32 / Codex P2 on PR #446. Pins:

* ``docs_url()`` resolves via ``AML_DOCS_URL`` first, then legacy
  ``AML_KB_URL``, then the public GitHub Pages default.
* Always returns with a trailing slash so callers can ``urljoin``
  sub-paths without trailing-slash brittleness.
* Both the FastAPI landing-page CTA and the dashboard sidebar end
  up at the same URL when the operator sets a single override.
"""

from __future__ import annotations

from urllib.parse import urljoin

import pytest

from aml_framework.links import DEFAULT_DOCS_URL, docs_url


class TestDocsUrl:
    @pytest.fixture(autouse=True)
    def _clear_env(self, monkeypatch):
        monkeypatch.delenv("AML_DOCS_URL", raising=False)
        monkeypatch.delenv("AML_KB_URL", raising=False)

    def test_default_is_public_docs_site(self):
        assert docs_url() == DEFAULT_DOCS_URL
        assert docs_url().endswith("/")

    def test_aml_docs_url_overrides_default(self, monkeypatch):
        monkeypatch.setenv("AML_DOCS_URL", "https://docs.example.test/")
        assert docs_url() == "https://docs.example.test/"

    def test_aml_kb_url_legacy_alias_honored(self, monkeypatch):
        # PR-U4 used AML_KB_URL; R32 renamed it. Legacy env stays
        # functional so existing operator overrides don't silently
        # break on upgrade.
        monkeypatch.setenv("AML_KB_URL", "https://legacy-kb.example.test/")
        assert docs_url() == "https://legacy-kb.example.test/"

    def test_aml_docs_url_wins_over_legacy(self, monkeypatch):
        # When both are set, the canonical R32 name takes precedence.
        monkeypatch.setenv("AML_DOCS_URL", "https://new.example.test/")
        monkeypatch.setenv("AML_KB_URL", "https://old.example.test/")
        assert docs_url() == "https://new.example.test/"

    def test_trailing_slash_normalized_when_missing(self, monkeypatch):
        # Codex P2 round 1 on PR #446 — operator set
        # AML_DOCS_URL=https://docs.example.test/aml (no trailing /)
        # produced https://docs.example.test/amlhow-to/ when the sidebar
        # naively concatenated "how-to/". Now normalized at the helper.
        monkeypatch.setenv("AML_DOCS_URL", "https://docs.example.test/aml")
        assert docs_url() == "https://docs.example.test/aml/"

    def test_trailing_slash_preserved_when_present(self, monkeypatch):
        monkeypatch.setenv("AML_DOCS_URL", "https://docs.example.test/aml/")
        assert docs_url() == "https://docs.example.test/aml/"

    def test_urljoin_subpath_yields_well_formed_url(self, monkeypatch):
        # End-to-end pin of the actual sidebar code path. Even when the
        # operator omits the trailing slash, urljoin produces a clean
        # sub-path URL (the bug Codex flagged).
        monkeypatch.setenv("AML_DOCS_URL", "https://docs.example.test/aml")
        assert urljoin(docs_url(), "how-to/") == "https://docs.example.test/aml/how-to/"

    def test_empty_string_env_falls_back_to_default(self, monkeypatch):
        # An empty env value is treated as "not set" — guards against
        # docker-compose/helm `env: AML_DOCS_URL=` lines that would
        # otherwise produce a malformed empty URL.
        monkeypatch.setenv("AML_DOCS_URL", "")
        assert docs_url() == DEFAULT_DOCS_URL
