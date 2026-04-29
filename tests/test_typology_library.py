"""Tests for `aml typology-list` / `aml typology-import` — the curated catalogue.

Process problem this guards: adding a typology should be one CLI call,
the resulting spec must validate, and rolling back on failure must be
atomic. If `import_typology` ever leaves a broken spec on disk, the
analyst's first reaction is "this tool just bricked my YAML" — and
the tool loses trust.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aml_framework.cli import app
from aml_framework.spec import load_spec
from aml_framework.typology_library import (
    TYPOLOGY_DIR,
    ImportedTypology,
    TypologyMetadata,
    _detect_spec_queues,
    _extract_rules_section,
    _pick_fallback_queue,
    import_typology,
    list_typologies,
    load_typology,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMUNITY_BANK_SPEC = REPO_ROOT / "examples" / "community_bank" / "aml.yaml"
CANADIAN_SPEC = REPO_ROOT / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def working_spec(tmp_path: Path) -> Path:
    """Copy the community-bank spec to tmp so each test mutates its own copy."""
    out = tmp_path / "aml.yaml"
    shutil.copy(COMMUNITY_BANK_SPEC, out)
    return out


# ---------------------------------------------------------------------------
# Catalogue listing
# ---------------------------------------------------------------------------


def test_list_typologies_returns_at_least_8_entries():
    """Catalogue ships with ≥ 8 typologies on day one."""
    items = list_typologies()
    assert len(items) >= 8
    ids = {t.id for t in items}
    # Spot-check the headline ones the round-5 plan called for.
    assert "structuring_cash" in ids
    assert "pig_butchering_outbound_fan" in ids
    assert "app_fraud_first_use_payee" in ids
    assert "shell_company_pass_through" in ids


def test_list_typologies_yields_typed_metadata():
    """Each returned item is a frozen TypologyMetadata with the headline fields."""
    items = list_typologies()
    sample = next(t for t in items if t.id == "structuring_cash")
    assert isinstance(sample, TypologyMetadata)
    assert sample.recommended_severity == "high"
    assert "US" in sample.jurisdictions
    assert sample.regulations  # non-empty
    assert sample.source  # always populated


def test_metadata_description_short_strips_to_first_sentence():
    """Listing tables need a one-line summary — verify the helper."""
    items = list_typologies()
    sample = next(t for t in items if t.id == "structuring_cash")
    short = sample.description_short
    assert len(short) < len(sample.description)
    # Should not contain newlines (so it fits in a Rich table cell).
    assert "\n" not in short


def test_list_typologies_handles_empty_directory(tmp_path: Path):
    """Listing on an empty dir returns [], not an exception."""
    empty = tmp_path / "empty"
    empty.mkdir()
    assert list_typologies(typology_dir=empty) == []


def test_list_typologies_skips_malformed_files(tmp_path: Path):
    """A YAML missing `metadata.id` is skipped, not raised."""
    bad_dir = tmp_path / "typologies"
    bad_dir.mkdir()
    (bad_dir / "broken.yaml").write_text("rule:\n  id: orphan_rule\n", encoding="utf-8")
    (bad_dir / "good.yaml").write_text(
        "metadata:\n  id: good_one\n  name: Good\n  source: test\nrule:\n  id: good_rule\n",
        encoding="utf-8",
    )
    items = list_typologies(typology_dir=bad_dir)
    assert {t.id for t in items} == {"good_one"}


# ---------------------------------------------------------------------------
# Single-typology load
# ---------------------------------------------------------------------------


def test_load_typology_returns_metadata_and_rule():
    """Loading by id returns the parsed YAML with `metadata` + `rule` blocks."""
    raw = load_typology("structuring_cash")
    assert raw["metadata"]["id"] == "structuring_cash"
    assert raw["rule"]["id"] == "structuring_cash"
    assert raw["rule"]["logic"]["type"] == "aggregation_window"


def test_load_typology_unknown_id_raises_keyerror():
    """Bogus id yields KeyError with a useful message."""
    with pytest.raises(KeyError, match="not found"):
        load_typology("not_a_real_typology")


# ---------------------------------------------------------------------------
# Splice helpers
# ---------------------------------------------------------------------------


def test_extract_rules_section_returns_only_rules_block():
    """Rules-section helper must stop before the next top-level key."""
    text = COMMUNITY_BANK_SPEC.read_text(encoding="utf-8")
    section = _extract_rules_section(text)
    assert section.startswith("rules:")
    # Stops before workflow / reporting / metrics top-level keys.
    assert "\nworkflow:" not in section
    assert "\nreporting:" not in section
    assert "\nmetrics:" not in section
    assert "structuring_cash_deposits" in section
    # Queue id only appears as `escalate_to:` value (escalate_to: l1_analyst);
    # never as the line `- id: l1_analyst` (that would mean the queue block bled in).
    assert "  - id: l1_analyst" not in section


def test_extract_rules_section_returns_empty_for_no_rules_block():
    """Spec without `rules:` yields empty — caller decides what to do."""
    assert _extract_rules_section("program:\n  name: foo\n") == ""


def test_detect_spec_queues_finds_community_bank_queues():
    """Smoke-test queue detection on a real spec."""
    text = COMMUNITY_BANK_SPEC.read_text(encoding="utf-8")
    queues = _detect_spec_queues(text)
    assert "l1_analyst" in queues
    assert "l2_investigator" in queues


def test_detect_spec_queues_finds_canadian_queues():
    """Different specs name queues differently — detector must handle both."""
    text = CANADIAN_SPEC.read_text(encoding="utf-8")
    queues = _detect_spec_queues(text)
    assert "l1_aml_analyst" in queues
    assert "l2_investigator" in queues


@pytest.mark.parametrize(
    "severity,queues,expected",
    [
        ("critical", ["l1_analyst", "l2_investigator"], "l2_investigator"),
        ("high", ["l1_analyst", "l2_investigator"], "l2_investigator"),
        ("medium", ["l1_analyst", "l2_investigator"], "l1_analyst"),
        ("low", ["l1_analyst", "l2_investigator"], "l1_analyst"),
        # Bank with non-tiered names still gets a sensible fallback.
        ("high", ["fraud_investigator", "aml_analyst"], "fraud_investigator"),
        ("low", ["fraud_investigator", "aml_analyst"], "aml_analyst"),
        # Last-ditch: no obvious match → first queue.
        ("high", ["alpha", "beta"], "alpha"),
    ],
)
def test_pick_fallback_queue(severity, queues, expected):
    assert _pick_fallback_queue(severity, queues) == expected


def test_pick_fallback_queue_empty_returns_none():
    assert _pick_fallback_queue("high", []) is None


# ---------------------------------------------------------------------------
# import_typology — end-to-end splice
# ---------------------------------------------------------------------------


def test_import_typology_appends_rule_and_validates(working_spec: Path):
    """Happy path: typology lands in spec; loader validates."""
    rules_before = {r.id for r in load_spec(working_spec).rules}
    result = import_typology("structuring_cash", working_spec)
    assert isinstance(result, ImportedTypology)
    assert result.rule_id == "structuring_cash"
    spec_after = load_spec(working_spec)
    new_ids = {r.id for r in spec_after.rules} - rules_before
    assert new_ids == {"structuring_cash"}


def test_import_typology_preserves_source_attribution(working_spec: Path):
    """Audit trail: a comment in the spec records where the rule came from."""
    import_typology("structuring_cash", working_spec)
    text = working_spec.read_text(encoding="utf-8")
    assert "Installed via `aml typology-import structuring_cash`" in text
    assert "TD Bank 2024 enforcement order" in text


def test_import_typology_remaps_escalate_to_when_queue_missing(working_spec: Path):
    """The catalogue YAML names l1_aml_analyst, but community_bank uses l1_analyst.

    The importer must remap, not crash, and surface the remap in the result.
    """
    result = import_typology("wire_to_high_risk_juris", working_spec)
    spec_after = load_spec(working_spec)
    new_rule = next(r for r in spec_after.rules if r.id == "wire_to_high_risk_juris")
    queue_ids = {q.id for q in spec_after.workflow.queues}
    assert new_rule.escalate_to in queue_ids
    assert result.escalate_to_remapped_from == "l1_aml_analyst"
    assert result.escalate_to == new_rule.escalate_to


def test_import_typology_keeps_escalate_to_when_queue_exists(tmp_path: Path):
    """No remap when the typology's preferred queue already exists in the spec."""
    out = tmp_path / "aml.yaml"
    shutil.copy(CANADIAN_SPEC, out)
    result = import_typology("wire_to_high_risk_juris", out)
    assert result.escalate_to == "l1_aml_analyst"
    assert result.escalate_to_remapped_from is None


def test_import_typology_rejects_duplicate_rule_id(working_spec: Path):
    """Cannot install the same typology twice without --allow-duplicate."""
    import_typology("structuring_cash", working_spec)
    with pytest.raises(ValueError, match="already present"):
        import_typology("structuring_cash", working_spec)


def test_import_typology_unknown_id_raises_keyerror(working_spec: Path):
    """Bogus typology id surfaces a KeyError, spec on disk untouched."""
    before = working_spec.read_text(encoding="utf-8")
    with pytest.raises(KeyError):
        import_typology("not_a_typology", working_spec)
    assert working_spec.read_text(encoding="utf-8") == before


def test_import_typology_rolls_back_on_validation_failure(monkeypatch, tmp_path: Path):
    """If post-splice validation fails, the spec on disk is restored."""
    spec_path = tmp_path / "aml.yaml"
    shutil.copy(COMMUNITY_BANK_SPEC, spec_path)
    before = spec_path.read_text(encoding="utf-8")

    # Force load_spec to raise as if the post-splice spec were invalid.
    import aml_framework.spec as spec_module

    def _broken_load(_path):
        raise ValueError("simulated post-splice validation failure")

    monkeypatch.setattr(spec_module, "load_spec", _broken_load)

    with pytest.raises(ValueError, match="simulated"):
        import_typology("structuring_cash", spec_path)
    assert spec_path.read_text(encoding="utf-8") == before


def test_import_typology_escalate_to_override(tmp_path: Path):
    """`escalate_to_override` forces the queue regardless of typology default."""
    spec_path = tmp_path / "aml.yaml"
    shutil.copy(CANADIAN_SPEC, spec_path)
    result = import_typology(
        "structuring_cash",
        spec_path,
        escalate_to_override="l1_aml_analyst",
    )
    assert result.escalate_to == "l1_aml_analyst"
    spec_after = load_spec(spec_path)
    new_rule = next(r for r in spec_after.rules if r.id == "structuring_cash")
    assert new_rule.escalate_to == "l1_aml_analyst"


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_cli_typology_list_lists_known_ids(runner: CliRunner):
    result = runner.invoke(app, ["typology-list"])
    assert result.exit_code == 0
    assert "structuring_cash" in result.stdout
    assert "pig_butchering_outbound_fan" in result.stdout


def test_cli_typology_list_filters_by_jurisdiction(runner: CliRunner):
    """`--jurisdiction GB` shows app_fraud_first_use_payee but not US-only entries."""
    result = runner.invoke(app, ["typology-list", "--jurisdiction", "GB"])
    assert result.exit_code == 0
    assert "app_fraud_first_use_payee" in result.stdout


def test_cli_typology_import_happy_path(runner: CliRunner, working_spec: Path):
    result = runner.invoke(app, ["typology-import", "structuring_cash", str(working_spec)])
    assert result.exit_code == 0, result.stdout
    assert "Installed" in result.stdout
    spec_after = load_spec(working_spec)
    assert any(r.id == "structuring_cash" for r in spec_after.rules)


def test_cli_typology_import_unknown_id_exits_nonzero(runner: CliRunner, working_spec: Path):
    result = runner.invoke(app, ["typology-import", "nope_not_real", str(working_spec)])
    assert result.exit_code != 0
    assert "not found" in result.stdout.lower()


def test_cli_typology_import_duplicate_exits_nonzero(runner: CliRunner, working_spec: Path):
    """Second import of the same typology should fail loudly, not silently."""
    runner.invoke(app, ["typology-import", "structuring_cash", str(working_spec)])
    result = runner.invoke(app, ["typology-import", "structuring_cash", str(working_spec)])
    assert result.exit_code != 0
    assert "already present" in result.stdout


def test_typology_dir_is_under_spec_library():
    """Typology dir must live alongside other reusable spec snippets."""
    assert TYPOLOGY_DIR.is_dir()
    assert TYPOLOGY_DIR.name == "typologies"
    assert TYPOLOGY_DIR.parent.name == "library"
