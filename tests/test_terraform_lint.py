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
            # The env-var name must be `DATABASE_URL` — what the Python
            # runtime reads via `os.environ.get("DATABASE_URL")` (see
            # src/aml_framework/api/db.py:40). Regex tolerates terraform
            # fmt's alignment-dependent spacing between `name` and `=`.
            assert re.search(r'name\s+=\s+"DATABASE_URL"', block), (
                f"{label} Container App must inject an env var named "
                f"`DATABASE_URL` (the runtime contract)"
            )
            assert 'secret_name = "database-url"' in block, (
                f"{label} Container App must source DATABASE_URL from the "
                f"`database-url` secret when var.enable_postgres is true"
            )
            assert re.search(r'name\s+=\s+"database-url"', block), (
                f"{label} Container App must define its own `database-url` "
                f"secret block (Container Apps secrets are resource-scoped)"
            )
            assert "local.postgres_database_url" in block, (
                f"{label} Container App's `database-url` secret must read "
                f"from `local.postgres_database_url` so the value can't "
                f"drift between pods"
            )

    def test_postgres_admin_name_and_dsn_user_share_one_local(self):
        """Postgres Flexible Server with Entra-ID auth identifies AD
        admins by `principal_name`, not object_id. The DSN's user
        component MUST match the value passed to
        `azurerm_postgresql_flexible_server_active_directory_administrator.
        principal_name` or psql rejects with "password authentication
        failed for user <name>".

        This test pins both literals to the shared
        `local.postgres_admin_principal_name` so a future edit can't
        re-introduce the GUID-vs-name drift that broke the first live
        deploy (the AD admin was registered as `aml-compliance-dev-
        uami` but the DSN used `module.onboard.identity_principal_id`,
        the object_id GUID)."""
        import re

        body = (TF_DIR / "main.tf").read_text(encoding="utf-8")

        # 1. The local must exist.
        assert re.search(r"postgres_admin_principal_name\s*=", body), (
            "expected `local.postgres_admin_principal_name` declaration"
        )

        # 2. The AD admin resource's `principal_name` must read the local.
        ad_admin_match = re.search(
            r'resource\s+"azurerm_postgresql_flexible_server_active_directory_administrator"'
            r'\s+"aml_uami"\s*\{[^}]*?principal_name\s*=\s*([^\n]+)',
            body,
            re.DOTALL,
        )
        assert ad_admin_match, "expected `aml_uami` AD admin resource"
        assert "local.postgres_admin_principal_name" in ad_admin_match.group(1), (
            "AD admin `principal_name` must read `local.postgres_admin_principal_name`; "
            f"got {ad_admin_match.group(1).strip()}"
        )

        # 3. The DSN's user component (the part before `@` in the
        #    postgres://... URL) must reference the same local.
        dsn_match = re.search(
            r'postgres_database_url\s*=\s*var\.enable_postgres\s*\?\s*"([^"]+)"', body
        )
        assert dsn_match, "expected `local.postgres_database_url` assignment"
        dsn = dsn_match.group(1)
        # Pull the user component: `postgresql://<user>@<host>...`.
        user_part = re.match(r"postgresql://([^@]+)@", dsn).group(1)
        assert user_part == "${local.postgres_admin_principal_name}", (
            f"DSN user must be `${{local.postgres_admin_principal_name}}`; got `{user_part}`"
        )

    def test_azure_client_id_env_var_on_both_container_apps(self):
        """User-assigned managed identity needs `AZURE_CLIENT_ID` env
        var set to the UAMI's client_id so `DefaultAzureCredential`
        in the Python runtime picks the right identity. Without it,
        `ManagedIdentityCredential` returns "Unable to load the proper
        Managed Identity" and Postgres Entra-ID auth / Cosmos client
        / Key Vault reads all fail at startup."""
        import re

        body = (TF_DIR / "main.tf").read_text(encoding="utf-8")
        api_idx = body.find('resource "azurerm_container_app" "api"')
        dash_idx = body.find('resource "azurerm_container_app" "dashboard"')
        api_block = body[api_idx:dash_idx]
        next_resource = re.search(r"\nresource \"", body[dash_idx + 1 :])
        dash_end = (dash_idx + 1 + next_resource.start()) if next_resource else len(body)
        dash_block = body[dash_idx:dash_end]

        for label, block in (("api", api_block), ("dashboard", dash_block)):
            assert re.search(r'name\s+=\s+"AZURE_CLIENT_ID"', block), (
                f"{label} Container App must set the AZURE_CLIENT_ID env var "
                f"so DefaultAzureCredential picks the UAMI"
            )
            assert "module.onboard.identity_client_id" in block, (
                f"{label} Container App's AZURE_CLIENT_ID must come from "
                f"`module.onboard.identity_client_id` (the UAMI's client_id)"
            )

    def test_assistant_backend_env_vars_on_both_container_apps(self):
        """The GenAI Assistant routing env vars (AML_AI_BACKEND,
        AML_OLLAMA_URL, AML_OLLAMA_MODEL) must be set on both Container
        Apps so the assistant routes through the same backend whether
        invoked from a dashboard page or a (future) API surface. The
        OLLAMA_API_KEY itself is fetched at runtime from the per-app
        Key Vault — it doesn't need an env block, but the KV secret
        placeholder must exist for the secret name to resolve."""
        import re

        body = (TF_DIR / "main.tf").read_text(encoding="utf-8")
        api_idx = body.find('resource "azurerm_container_app" "api"')
        dash_idx = body.find('resource "azurerm_container_app" "dashboard"')
        api_block = body[api_idx:dash_idx]
        next_resource = re.search(r"\nresource \"", body[dash_idx + 1 :])
        dash_end = (dash_idx + 1 + next_resource.start()) if next_resource else len(body)
        dash_block = body[dash_idx:dash_end]

        expected_envs = {
            "AML_AI_BACKEND": "var.ai_backend",
            "AML_OLLAMA_URL": "var.ollama_url",
            "AML_OLLAMA_MODEL": "var.ollama_model",
        }
        for label, block in (("api", api_block), ("dashboard", dash_block)):
            for env_name, var_ref in expected_envs.items():
                assert re.search(rf'name\s+=\s+"{env_name}"', block), (
                    f"{label} Container App must set the {env_name} env var"
                )
                assert var_ref in block, (
                    f"{label} Container App's {env_name} must read from `{var_ref}`"
                )

        # And the KV placeholder for OLLAMA-API-KEY must exist so the
        # SecretClient.get_secret() lookup the Python SecretsProvider
        # makes returns a real (even if placeholder) value rather than
        # 404.
        assert 'azurerm_key_vault_secret" "ollama_api_key_placeholder"' in body, (
            "expected an `ollama_api_key_placeholder` KV secret resource "
            "so the per-app KV has an OLLAMA-API-KEY entry the operator "
            "can fill via `az keyvault secret set`"
        )
        assert re.search(r'name\s+=\s+"OLLAMA-API-KEY"', body), (
            "KV secret name must be exactly OLLAMA-API-KEY — the Python "
            "SecretsProvider auto-translates OLLAMA_API_KEY to that form."
        )
