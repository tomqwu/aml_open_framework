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


@pytest.mark.skipif(not TERRAFORM_AVAILABLE, reason="terraform not installed")
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
