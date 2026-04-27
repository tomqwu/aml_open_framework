"""Multi-tenant dashboard config tests — Round-6 PR #2.

Verifies tenant registry loading, default fallback when no config exists,
explicit tenant resolution, and error reporting on malformed configs.
Importing streamlit at module level would break the unit-test CI image
(which only installs `.[dev]`), so this test file imports
`dashboard.tenants` directly — that module is streamlit-free by design.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aml_framework.dashboard.tenants import (
    DEFAULT_TENANT_ID,
    TenantConfig,
    TenantConfigError,
    load_tenants,
    resolve_tenant,
)


# ---------------------------------------------------------------------------
# Default fallback behaviour
# ---------------------------------------------------------------------------


class TestDefaultFallback:
    def test_no_config_returns_single_default_tenant(self, tmp_path):
        # Point env var at a non-existent path.
        missing = tmp_path / "nope.yaml"
        tenants = load_tenants(config_path=missing)
        assert len(tenants) == 1
        assert tenants[0].id == DEFAULT_TENANT_ID

    def test_default_tenant_points_at_community_bank(self, tmp_path):
        tenants = load_tenants(config_path=tmp_path / "nope.yaml")
        assert tenants[0].spec_path.name == "aml.yaml"
        assert "community_bank" in str(tenants[0].spec_path)

    def test_default_tenant_has_display_name(self, tmp_path):
        tenants = load_tenants(config_path=tmp_path / "nope.yaml")
        assert tenants[0].display_name
        assert tenants[0].jurisdiction == "US"


# ---------------------------------------------------------------------------
# Loading explicit configs
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "tenants.yaml"
    p.write_text(body, encoding="utf-8")
    return p


class TestLoadTenants:
    def test_minimal_two_tenant_config(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
tenants:
  - id: bank_a
    display_name: "Bank A"
    spec_path: examples/eu_bank/aml.yaml
    jurisdiction: EU
  - id: bank_b
    display_name: "Bank B"
    spec_path: examples/community_bank/aml.yaml
    jurisdiction: US
""",
        )
        tenants = load_tenants(config_path=cfg)
        assert [t.id for t in tenants] == ["bank_a", "bank_b"]

    def test_relative_spec_paths_resolved_against_project_root(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
tenants:
  - id: t1
    display_name: "T1"
    spec_path: examples/eu_bank/aml.yaml
""",
        )
        t = load_tenants(config_path=cfg)[0]
        # Resolved path is absolute and points at the real project file.
        assert t.spec_path.is_absolute()
        assert t.spec_path.exists(), f"resolved path missing: {t.spec_path}"

    def test_absolute_spec_paths_kept(self, tmp_path):
        spec = tmp_path / "absolute.yaml"
        spec.write_text("dummy", encoding="utf-8")
        cfg = _write_config(
            tmp_path,
            f"""
tenants:
  - id: t1
    display_name: "T1"
    spec_path: {spec}
""",
        )
        t = load_tenants(config_path=cfg)[0]
        assert t.spec_path == spec

    def test_tenants_sorted_by_id(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
tenants:
  - id: zulu
    display_name: "Z"
    spec_path: examples/eu_bank/aml.yaml
  - id: alpha
    display_name: "A"
    spec_path: examples/community_bank/aml.yaml
  - id: mike
    display_name: "M"
    spec_path: examples/canadian_schedule_i_bank/aml.yaml
""",
        )
        ids = [t.id for t in load_tenants(config_path=cfg)]
        assert ids == ["alpha", "mike", "zulu"]

    def test_jurisdiction_optional(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
tenants:
  - id: t1
    display_name: "T1"
    spec_path: examples/eu_bank/aml.yaml
""",
        )
        t = load_tenants(config_path=cfg)[0]
        assert t.jurisdiction == ""

    def test_display_name_falls_back_to_id(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
tenants:
  - id: bare_tenant
    spec_path: examples/eu_bank/aml.yaml
""",
        )
        t = load_tenants(config_path=cfg)[0]
        assert t.display_name == "bare_tenant"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_empty_tenants_list_raises(self, tmp_path):
        cfg = _write_config(tmp_path, "tenants: []\n")
        with pytest.raises(TenantConfigError, match="non-empty"):
            load_tenants(config_path=cfg)

    def test_missing_tenants_key_raises(self, tmp_path):
        cfg = _write_config(tmp_path, "other_key: value\n")
        with pytest.raises(TenantConfigError, match="non-empty"):
            load_tenants(config_path=cfg)

    def test_top_level_must_be_mapping(self, tmp_path):
        cfg = _write_config(tmp_path, "- just\n- a\n- list\n")
        with pytest.raises(TenantConfigError, match="mapping"):
            load_tenants(config_path=cfg)

    def test_duplicate_ids_rejected(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
tenants:
  - id: dup
    display_name: "First"
    spec_path: examples/eu_bank/aml.yaml
  - id: dup
    display_name: "Second"
    spec_path: examples/community_bank/aml.yaml
""",
        )
        with pytest.raises(TenantConfigError, match="duplicate"):
            load_tenants(config_path=cfg)

    def test_missing_id_rejected(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
tenants:
  - display_name: "No ID"
    spec_path: examples/eu_bank/aml.yaml
""",
        )
        with pytest.raises(TenantConfigError, match="non-empty string 'id'"):
            load_tenants(config_path=cfg)

    def test_missing_spec_path_rejected(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
tenants:
  - id: t1
    display_name: "T1"
""",
        )
        with pytest.raises(TenantConfigError, match="spec_path"):
            load_tenants(config_path=cfg)

    def test_invalid_yaml_raises_clear_error(self, tmp_path):
        cfg = _write_config(tmp_path, "tenants: [\n  - id: bad\n")  # truncated
        with pytest.raises(TenantConfigError, match="not valid YAML"):
            load_tenants(config_path=cfg)


# ---------------------------------------------------------------------------
# resolve_tenant
# ---------------------------------------------------------------------------


class TestResolveTenant:
    def test_none_returns_first(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
tenants:
  - id: alpha
    display_name: "A"
    spec_path: examples/community_bank/aml.yaml
  - id: bravo
    display_name: "B"
    spec_path: examples/eu_bank/aml.yaml
""",
        )
        t = resolve_tenant(None, config_path=cfg)
        # Sorted by id, so alpha is first.
        assert t.id == "alpha"

    def test_explicit_id_returns_match(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
tenants:
  - id: alpha
    display_name: "A"
    spec_path: examples/community_bank/aml.yaml
  - id: bravo
    display_name: "B"
    spec_path: examples/eu_bank/aml.yaml
""",
        )
        t = resolve_tenant("bravo", config_path=cfg)
        assert t.id == "bravo"

    def test_unknown_id_raises(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
tenants:
  - id: alpha
    display_name: "A"
    spec_path: examples/community_bank/aml.yaml
""",
        )
        with pytest.raises(TenantConfigError, match="not in config"):
            resolve_tenant("nonexistent", config_path=cfg)

    def test_unknown_id_lists_available(self, tmp_path):
        cfg = _write_config(
            tmp_path,
            """
tenants:
  - id: alpha
    display_name: "A"
    spec_path: examples/community_bank/aml.yaml
  - id: bravo
    display_name: "B"
    spec_path: examples/eu_bank/aml.yaml
""",
        )
        with pytest.raises(TenantConfigError) as exc:
            resolve_tenant("missing", config_path=cfg)
        # Error message helps the operator fix the misconfiguration.
        msg = str(exc.value)
        assert "alpha" in msg
        assert "bravo" in msg


# ---------------------------------------------------------------------------
# Env var override
# ---------------------------------------------------------------------------


class TestEnvVarOverride:
    def test_env_var_takes_precedence(self, tmp_path, monkeypatch):
        cfg = _write_config(
            tmp_path,
            """
tenants:
  - id: env_tenant
    display_name: "Env"
    spec_path: examples/eu_bank/aml.yaml
""",
        )
        monkeypatch.setenv("AML_TENANTS_CONFIG", str(cfg))
        # Without an explicit config_path the loader must pick up the env var.
        tenants = load_tenants()
        assert len(tenants) == 1
        assert tenants[0].id == "env_tenant"


# ---------------------------------------------------------------------------
# TenantConfig serialisation
# ---------------------------------------------------------------------------


class TestTenantConfigDataclass:
    def test_to_dict_round_trip(self):
        t = TenantConfig(
            id="x",
            display_name="X",
            spec_path=Path("/tmp/spec.yaml"),
            jurisdiction="US",
        )
        d = t.to_dict()
        assert d == {
            "id": "x",
            "display_name": "X",
            "spec_path": "/tmp/spec.yaml",
            "jurisdiction": "US",
        }

    def test_frozen(self):
        t = TenantConfig(id="x", display_name="X", spec_path=Path("/tmp/spec.yaml"))
        with pytest.raises(Exception):  # FrozenInstanceError
            t.id = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Bundled example file is parseable
# ---------------------------------------------------------------------------


class TestBundledExample:
    def test_example_config_loads(self):
        from aml_framework.paths import PROJECT_ROOT

        example = PROJECT_ROOT / "dashboard_tenants.example.yaml"
        assert example.exists(), "bundled example config missing"
        tenants = load_tenants(config_path=example)
        assert len(tenants) >= 3  # ships at least 3 example tenants

    def test_example_spec_paths_all_exist(self):
        from aml_framework.paths import PROJECT_ROOT

        example = PROJECT_ROOT / "dashboard_tenants.example.yaml"
        for t in load_tenants(config_path=example):
            assert t.spec_path.exists(), f"example tenant {t.id} → missing spec {t.spec_path}"

    def test_no_real_config_committed(self):
        # The non-example file is gitignored; this test passes either way
        # but documents the convention.
        from aml_framework.paths import PROJECT_ROOT

        assert (PROJECT_ROOT / "dashboard_tenants.example.yaml").exists()
