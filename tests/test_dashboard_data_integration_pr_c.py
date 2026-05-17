"""Source guards for the Data Integration PR-C UI additions.

The page is a Streamlit script (run by Streamlit, never imported by
unit tests), so render is covered by the Playwright e2e. These
fast file-text guards pin that the PR-C sections + their wiring
exist and don't silently regress — same pattern as
test_dashboard_dark_theme.py.
"""

from __future__ import annotations

from pathlib import Path

PAGE = (
    Path(__file__).resolve().parents[1] / "src/aml_framework/dashboard/pages/30_Data_Integration.py"
)


def _body() -> str:
    return PAGE.read_text(encoding="utf-8")


class TestDemonstrableDataSection:
    def test_section_header_present(self):
        assert "### Demonstrable test data per source type" in _body()

    def test_explains_fixtures_and_mock_paths(self):
        b = _body()
        # The section must point at the DI PR-B affordances.
        assert "make fixtures" in b
        assert "--data-dir mock" in b
        assert "data_integration_demo_data" in b

    def test_covers_every_catalogue_source(self):
        b = _body()
        # Built from SOURCE_CATALOGUE so every connector is covered;
        # the _HOW map must name each of the 9 source types.
        for src in (
            "synthetic",
            "csv",
            "parquet",
            "duckdb",
            "snowflake",
            "bigquery",
            "s3",
            "gcs",
            "iso20022",
        ):
            assert f'"{src}":' in b, f"{src} missing from the demo-data _HOW map"


class TestVolumeByChannelSection:
    def test_section_header_present(self):
        assert "### Volume by payment channel" in _body()

    def test_reads_run_txns_and_groups_by_channel(self):
        b = _body()
        assert 'st.session_state.get("df_txns")' in b
        assert 'groupby("channel")' in b
        assert "data_integration_volume_by_channel" in b

    def test_mentions_the_pr_a_rails(self):
        # The point of the chart is to make the new rails visible.
        b = _body()
        assert "rtp" in b and "crypto" in b and "prepaid" in b

    def test_has_empty_state_fallback(self):
        # Must fail soft when the wired source has no channel column.
        b = _body()
        assert "No transaction channel data" in b
