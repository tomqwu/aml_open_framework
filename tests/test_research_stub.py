"""Unit tests for the deterministic research-stub generator (#512).

These run under ``.[dev]`` (no streamlit). The imported
``aml_framework.dashboard.regulatory_calendar`` module is streamlit-free, so
the generator and these tests import cleanly without a skip guard.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

# scripts/ is a dev/CI utility dir, intentionally NOT shipped in the stripped
# runtime Docker image (which runs `pytest tests/` as a smoke check). Skip the
# whole module when the generator isn't on disk so the image build stays green;
# the generator is exercised by the unit + coverage CI jobs, not this image.
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "generate_research_stub.py"
if not _SCRIPT.exists():  # pragma: no cover
    pytest.skip(
        "research-stub generator not present (stripped runtime image)",
        allow_module_level=True,
    )

from aml_framework.dashboard.regulatory_calendar import load_calendar  # noqa: E402
from scripts.generate_research_stub import (  # noqa: E402
    band_for,
    band_transitions,
    generate,
    month_anchor,
    prev_month_anchor,
    render_stub,
)

# Real source_url values from the packaged calendar — the ONLY URLs the stub
# is allowed to emit. Any http(s) link in the stub must be one of these.
_CALENDAR = load_calendar()
_REAL_SOURCE_URLS = {d.source_url for d in _CALENDAR}


def test_prev_month_anchor_january_rollover():
    assert prev_month_anchor("2026-01") == date(2025, 12, 1)
    assert prev_month_anchor("2026-07") == date(2026, 6, 1)
    assert month_anchor("2026-07") == date(2026, 7, 1)


def test_generate_writes_expected_sections(tmp_path):
    target, written = generate(month="2026-07", out_dir=tmp_path, slug="aml-data-problem")
    assert written is True
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert "# Data is the AML problem — 2026-07" in text
    assert "## What changed since last month" in text
    assert "## Deadline countdown" in text
    # At least one real deadline description from the packaged calendar.
    descriptions = [d.description for d in _CALENDAR]
    assert any(desc in text for desc in descriptions)


def test_idempotent_does_not_overwrite(tmp_path):
    target, written_first = generate(month="2026-07", out_dir=tmp_path)
    assert written_first is True
    sentinel = "HUMAN EDITED — DO NOT CLOBBER\n"
    target.write_text(sentinel, encoding="utf-8")
    mtime_before = target.stat().st_mtime_ns

    target2, written_second = generate(month="2026-07", out_dir=tmp_path)
    assert target2 == target
    assert written_second is False
    # Content and mtime unchanged — the human edit survives.
    assert target.read_text(encoding="utf-8") == sentinel
    assert target.stat().st_mtime_ns == mtime_before


def test_deterministic_byte_identical(tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    target_a, _ = generate(month="2026-07", out_dir=dir_a)
    target_b, _ = generate(month="2026-07", out_dir=dir_b)
    assert target_a.read_text(encoding="utf-8") == target_b.read_text(encoding="utf-8")
    # render_stub itself is pure for a fixed month + calendar.
    assert render_stub("2026-07", _CALENDAR) == render_stub("2026-07", _CALENDAR)


def test_what_changed_band_delta_is_well_formed():
    """The "What changed" section either lists a real transition or emits the
    sentinel — never empty/malformed. For 2026-07 the packaged calendar must
    cross at least one boundary, so we assert a non-empty transition list and
    that the section names it."""
    text = render_stub("2026-07", _CALENDAR)
    transitions = band_transitions(
        _CALENDAR,
        as_of_now=month_anchor("2026-07"),
        as_of_prev=prev_month_anchor("2026-07"),
    )
    assert transitions, "2026-07 must cross a band boundary on the packaged calendar"
    # The section names each transitioning deadline.
    for d, _prev, _now in transitions:
        assert d.description in text
    # Sentinel only appears when there are no transitions.
    assert "No deadline band changes this month." not in text


def test_what_changed_sentinel_when_no_transitions(tmp_path):
    """A month far in the past (everything already expired in both anchors)
    yields no NEW tighter-band transitions → the sentinel line renders."""
    # Pick a month well after all deadlines: bands are "expired" at both
    # anchors, so rank does not strictly increase → no transitions.
    text = render_stub("2027-01", _CALENDAR)
    assert (
        band_transitions(
            _CALENDAR,
            as_of_now=month_anchor("2027-01"),
            as_of_prev=prev_month_anchor("2027-01"),
        )
        == []
    )
    assert "No deadline band changes this month." in text


def test_band_for_expired_and_active():
    d = _CALENDAR[0]
    assert band_for(d, as_of=date(2020, 1, 1)) in {"info", "warning", "error"}
    assert band_for(d, as_of=date(2099, 1, 1)) == "expired"


def test_stub_has_todo_placeholders_and_no_fabricated_urls():
    text = render_stub("2026-07", _CALENDAR)
    assert "TODO(human)" in text
    # Three placeholder prose sections.
    assert text.count("<!-- TODO(human):") >= 3

    # Every http(s) URL in the stub must be a real calendar source_url.
    import re

    urls = re.findall(r"https?://\S+", text)
    # Strip trailing markdown ")" from "[source](url)".
    cleaned = {u.rstrip(")") for u in urls}
    assert cleaned, "stub should contain the calendar source links"
    assert cleaned <= _REAL_SOURCE_URLS, (
        f"stub emitted non-calendar URLs (possible fabricated citation): "
        f"{cleaned - _REAL_SOURCE_URLS}"
    )


def test_cli_main_writes_and_then_skips(tmp_path, capsys):
    from scripts.generate_research_stub import main

    rc = main(["--month", "2026-07", "--out-dir", str(tmp_path)])
    assert rc == 0
    out_first = capsys.readouterr().out
    assert "wrote" in out_first

    rc2 = main(["--month", "2026-07", "--out-dir", str(tmp_path)])
    assert rc2 == 0
    out_second = capsys.readouterr().out
    assert "skipped" in out_second
    assert "already exists" in out_second


def test_cli_main_rejects_bad_month(tmp_path):
    from scripts.generate_research_stub import main

    rc = main(["--month", "not-a-month", "--out-dir", str(tmp_path)])
    assert rc == 2


def test_cli_calendar_override(tmp_path):
    """The --calendar override path loads a caller-supplied YAML."""
    import textwrap

    from scripts.generate_research_stub import main

    cal_path = tmp_path / "custom_calendar.yaml"
    cal_path.write_text(
        textwrap.dedent(
            """\
            deadlines:
              - id: custom-one
                description: "Custom override deadline"
                deadline: 2026-07-15
                urgency_days: 30
                source_url: "https://example.gov/custom"
                framework_alignment:
                  pages: ["Triage Queue"]
            """
        ),
        encoding="utf-8",
    )
    rc = main(
        [
            "--month",
            "2026-07",
            "--out-dir",
            str(tmp_path),
            "--calendar",
            str(cal_path),
        ]
    )
    assert rc == 0
    text = (tmp_path / "2026-07-aml-data-problem.md").read_text(encoding="utf-8")
    assert "Custom override deadline" in text
    assert "https://example.gov/custom" in text


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
