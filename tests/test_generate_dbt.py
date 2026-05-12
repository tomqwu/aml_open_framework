"""dbt project generator tests (PR 18.11).

`generate_dbt_project(spec, spec_path, output_dir, as_of=...)` emits
a self-contained dbt project from an AML spec. Tests pin: every
aggregation_window rule produces a model, custom_sql rules carry
substituted placeholders, python_ref / list_match / network_pattern
get skipped (with the README documenting the gap), schema.yml lists
every emitted model.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aml_framework.generators.dbt import _safe_identifier, generate_dbt_project
from aml_framework.spec import load_spec

SPEC_CA = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
SPEC_RTP = Path(__file__).resolve().parents[1] / "examples" / "us_rtp_fednow" / "aml.yaml"


class TestSafeIdentifier:
    def test_keeps_valid_names_unchanged(self):
        assert _safe_identifier("structuring_cash") == "structuring_cash"

    def test_replaces_hyphens(self):
        assert _safe_identifier("rule-with-dashes") == "rule_with_dashes"

    def test_prefixes_when_starting_non_alpha(self):
        assert _safe_identifier("123_rule").startswith("aml_")


class TestGenerateDbtProject:
    def test_emits_project_yml_and_models(self, tmp_path):
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 28)
        written = generate_dbt_project(spec, SPEC_CA, tmp_path, as_of=as_of)

        # Minimum surface: project file + models dir + schema.yml + README.
        assert "dbt_project.yml" in written
        assert "models/aml/schema.yml" in written
        assert "README.md" in written

        # Every aggregation_window / custom_sql rule has an emitted .sql.
        expected_models = {
            f"models/aml/{_safe_identifier(r.id)}.sql"
            for r in spec.rules
            if getattr(r.logic, "type", None) in ("aggregation_window", "custom_sql")
        }
        emitted = {k for k in written if k.startswith("models/aml/") and k.endswith(".sql")}
        assert emitted == expected_models, (
            f"missing models: {expected_models - emitted}; extra: {emitted - expected_models}"
        )

    def test_aggregation_window_model_carries_engine_sql(self, tmp_path):
        """The aggregation_window renderer reuses the engine's
        `compile_rule_sql` so the dbt model and the engine output are
        wire-identical. Pin that the emitted SQL contains the
        expected SELECT shape."""
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 28)
        written = generate_dbt_project(spec, SPEC_CA, tmp_path, as_of=as_of)
        # Pick a known aggregation_window rule.
        rule = next(r for r in spec.rules if getattr(r.logic, "type", None) == "aggregation_window")
        model_path = written[f"models/aml/{_safe_identifier(rule.id)}.sql"]
        body = model_path.read_text(encoding="utf-8")
        # dbt config block must be present so `dbt run` recognises it.
        assert "config(" in body
        assert "materialized='table'" in body
        # The engine's `-- rule_id:` header must NOT appear (we strip it).
        assert "-- rule_id:" not in body
        # SELECT clause from the compiled SQL must appear somewhere.
        assert "SELECT" in body

    def test_custom_sql_model_substitutes_window_placeholders(self, tmp_path):
        """`{recent_start}` / `{as_of}` placeholders in a custom_sql
        rule must be substituted to concrete timestamps so the dbt
        model is portable."""
        spec = load_spec(SPEC_RTP)
        as_of = datetime(2026, 4, 28)
        written = generate_dbt_project(spec, SPEC_RTP, tmp_path, as_of=as_of)
        rule = next(r for r in spec.rules if getattr(r.logic, "type", None) == "custom_sql")
        model_path = written[f"models/aml/{_safe_identifier(rule.id)}.sql"]
        body = model_path.read_text(encoding="utf-8")
        # Substituted, not left as `{recent_start}`.
        assert "{recent_start}" not in body
        assert "2026-04" in body  # the substituted timestamp landed

    def test_python_ref_and_network_pattern_rules_skipped(self, tmp_path):
        """`python_ref` / `list_match` / `network_pattern` need
        warehouse-side wiring beyond plain SQL — the generator skips
        them rather than emitting a broken model. The skip must NOT
        be silent — the README mentions them."""
        spec = load_spec(SPEC_RTP)
        as_of = datetime(2026, 4, 28)
        written = generate_dbt_project(spec, SPEC_RTP, tmp_path, as_of=as_of)
        # network_pattern rule must NOT appear as a model.
        np_rules = [r for r in spec.rules if getattr(r.logic, "type", None) == "network_pattern"]
        for r in np_rules:
            assert f"models/aml/{_safe_identifier(r.id)}.sql" not in written
        # README mentions the gap so operator isn't surprised.
        readme = written["README.md"].read_text(encoding="utf-8")
        assert "network_pattern" in readme
        assert "python_ref" in readme

    def test_schema_yml_lists_all_emitted_models(self, tmp_path):
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 28)
        written = generate_dbt_project(spec, SPEC_CA, tmp_path, as_of=as_of)
        schema_body = written["models/aml/schema.yml"].read_text(encoding="utf-8")
        for r in spec.rules:
            if getattr(r.logic, "type", None) not in ("aggregation_window", "custom_sql"):
                continue
            name = _safe_identifier(r.id)
            assert f"name: {name}" in schema_body, f"schema.yml missing model {name}"
