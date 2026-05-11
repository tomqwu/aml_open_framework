"""PR-AZ-5: lint guard on the deploy/terraform/ module.

Runs `terraform fmt -check -recursive` to assert the .tf files are
formatted. Skips when terraform isn't on PATH (CI image ships
without terraform; verified by the user manually before deploy).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TF_DIR = PROJECT_ROOT / "deploy" / "terraform"

TERRAFORM_AVAILABLE = shutil.which("terraform") is not None
# The Docker image (used by the docker-build CI job) intentionally omits
# `deploy/terraform/` to keep the runtime layer slim — these are
# repo-state guards, not runtime guards. Skip when the directory isn't
# present; the unit-test CI job exercises them with the full repo.
TF_DIR_PRESENT = (TF_DIR / "main.tf").exists()


@pytest.mark.skipif(not TERRAFORM_AVAILABLE, reason="terraform not installed")
@pytest.mark.skipif(not TF_DIR_PRESENT, reason="deploy/terraform/ not in this filesystem")
class TestTerraformFormat:
    def test_fmt_check_passes(self):
        result = subprocess.run(
            ["terraform", "fmt", "-check", "-recursive", str(TF_DIR)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"terraform fmt -check failed:\n{result.stdout}\n{result.stderr}\n"
            f"Run `terraform fmt -recursive deploy/terraform/` to fix."
        )


@pytest.mark.skipif(not TF_DIR_PRESENT, reason="deploy/terraform/ not in this filesystem")
class TestTerraformFilesPresent:
    """Doesn't need terraform installed — pure file existence check."""

    def test_required_files_present(self):
        for fname in ("providers.tf", "main.tf", "variables.tf", "outputs.tf", "README.md"):
            assert (TF_DIR / fname).exists(), f"deploy/terraform/{fname} missing"

    def test_module_call_uses_landing_zone_source(self):
        body = (TF_DIR / "main.tf").read_text(encoding="utf-8")
        assert "tomqwu/cloud_landing_zone_for_ai_coding" in body
        assert "modules/app-onboard" in body

    def test_landing_zone_constraint_compliance(self):
        """Landing zone CLAUDE.md forbids AKS, requires Container Apps,
        Postgres B1ms with Entra ID auth, diagnostics → platform LAW."""
        body = (TF_DIR / "main.tf").read_text(encoding="utf-8")
        # Compute: Container Apps only.
        assert "azurerm_container_app" in body
        assert "azurerm_kubernetes_cluster" not in body, "AKS forbidden by landing zone"
        # DB: Postgres B1ms.
        assert "B_Standard_B1ms" in body
        # Entra ID auth on Postgres.
        assert "active_directory_auth_enabled = true" in body
        assert "password_auth_enabled         = false" in body
        # Diagnostics to platform LAW.
        assert "azurerm_monitor_diagnostic_setting" in body
        assert "log_analytics_workspace_id" in body

    def test_db_backend_mutex_precondition_present(self):
        """enable_postgres and enable_cosmos must be mutually exclusive.

        Mirrors the fail-fast in deploy/helm/templates/api-deployment.yaml.
        The check is a `terraform_data` block (not a precondition on the
        Postgres resource) so the guard fires even when enable_postgres is
        false.
        """
        body = (TF_DIR / "main.tf").read_text(encoding="utf-8")
        assert 'resource "terraform_data" "db_backend_mutex"' in body
        assert "condition     = !(var.enable_postgres && var.enable_cosmos)" in body
        assert "mutually exclusive" in body

    def test_database_url_injected_on_both_container_apps(self):
        """When `var.enable_postgres = true`, both the API and the
        dashboard Container Apps must inject `DATABASE_URL` via the
        same `database-url` secret. Pins the resolution of the
        dashboard ↔ DB persistence asymmetry documented in PR #273:
        without the dashboard env var, the dashboard pod fell back
        to local SQLite while the API wrote to Postgres. Mirrors
        the Helm-side `TestHelmPostgresFirstPrecedence` (#271).

        Scoped per `azurerm_container_app` resource so a duplicated
        block on the API side alone can't make the assertion pass
        with the dashboard still missing it."""
        import re

        body = (TF_DIR / "main.tf").read_text(encoding="utf-8")

        # Each Container App resource is one `resource "azurerm_container_app"`
        # block. Split the body on the resource header and inspect the API
        # and dashboard halves separately.
        api_idx = body.find('resource "azurerm_container_app" "api"')
        dash_idx = body.find('resource "azurerm_container_app" "dashboard"')
        assert api_idx >= 0, "expected `azurerm_container_app.api` resource"
        assert dash_idx >= 0, "expected `azurerm_container_app.dashboard` resource"
        # The dashboard resource follows the API resource in main.tf;
        # API block is everything between its header and the dashboard header.
        api_block = body[api_idx:dash_idx]
        # The dashboard block runs from its header to the next top-level
        # resource declaration (or end of file).
        next_resource = re.search(r"\nresource \"", body[dash_idx + 1 :])
        dash_end = (dash_idx + 1 + next_resource.start()) if next_resource else len(body)
        dash_block = body[dash_idx:dash_end]

        for label, block in (("api", api_block), ("dashboard", dash_block)):
            assert 'secret_name = "database-url"' in block, (
                f"{label} Container App must inject DATABASE_URL via the "
                f"`database-url` secret when var.enable_postgres is true"
            )
            # Regex tolerates terraform fmt's alignment-dependent spacing.
            assert re.search(r'name\s+=\s+"database-url"', block), (
                f"{label} Container App must define its own `database-url` "
                f"secret block (Container Apps secrets are resource-scoped)"
            )
            assert "local.postgres_database_url" in block, (
                f"{label} Container App's `database-url` secret must read "
                f"from `local.postgres_database_url` so the value can't "
                f"drift between pods"
            )
