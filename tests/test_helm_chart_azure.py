"""PR-AZ-3: Helm chart Azure / AKS rendering.

Runs `helm template` against the chart with the Azure example values
and asserts the workload-identity ServiceAccount, pod label, and
env-var threading all render. Skip if `helm` isn't on PATH (CI image
doesn't ship helm).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHART = PROJECT_ROOT / "deploy" / "helm"
AZURE_VALUES = CHART / "values-azure.example.yaml"


HELM_AVAILABLE = shutil.which("helm") is not None


@pytest.mark.skipif(not HELM_AVAILABLE, reason="helm not installed on this CI image")
class TestHelmAzureRendering:
    def _render(self, values: Path = AZURE_VALUES) -> str:
        result = subprocess.run(
            ["helm", "template", "aml", str(CHART), "-f", str(values)],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def test_azure_example_file_renders_clean(self):
        # If this fails, helm template surfaces the validation error.
        self._render()

    def test_service_account_rendered_with_workload_identity_annotation(self):
        out = self._render()
        # API + dashboard each get one ServiceAccount.
        assert out.count("kind: ServiceAccount") >= 2
        assert "azure.workload.identity/client-id" in out

    def test_pod_label_for_workload_identity_set(self):
        out = self._render()
        assert 'azure.workload.identity/use: "true"' in out

    def test_azure_env_vars_threaded_to_pods(self):
        out = self._render()
        assert "AZURE_KEY_VAULT_NAME" in out
        assert "AZURE_STORAGE_ACCOUNT_NAME" in out


@pytest.mark.skipif(not HELM_AVAILABLE, reason="helm not installed on this CI image")
class TestHelmDefaultStillWorks:
    """Empty `azure:` block produces an Azure-agnostic chart identical
    to the on-prem deployment. Critical: don't accidentally make the
    Azure features required."""

    def test_default_values_render_clean(self, tmp_path):
        # Default values.yaml has azure.workloadIdentityClientId="".
        # No Azure ServiceAccounts, no workload-identity labels.
        result = subprocess.run(
            ["helm", "template", "aml", str(CHART)],
            capture_output=True,
            text=True,
            check=True,
        )
        out = result.stdout
        # Workload-identity bits must NOT appear when the Azure block
        # is empty — otherwise we'd break non-Azure deployments.
        assert "azure.workload.identity/client-id" not in out
        assert 'azure.workload.identity/use: "true"' not in out
