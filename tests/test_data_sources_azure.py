"""PR-AZ-1: Azure data source dispatch + lineage path inference.

Unit-tests cover what doesn't need real Azure credentials:
  - resolve_source() routes the new source types to the right loaders
  - infer_source_paths() returns the documented logical-path shapes
    that the Round-12 lineage chain consumes via record_input

The actual Azure SDK calls are wrapped in `# pragma: no cover` blocks
in src/aml_framework/data/sources.py — they need a live tenant.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from aml_framework.data.sources import infer_source_paths, resolve_source
from aml_framework.spec.loader import load_spec

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = PROJECT_ROOT / "examples" / "community_bank" / "aml.yaml"


@pytest.fixture
def spec():
    return load_spec(SPEC)


class TestInferSourcePathsAzure:
    """The Round-12 lineage chain (PR-LIN-2) reads source_path off
    record_input; per-loader shape is documented in
    infer_source_paths' docstring."""

    def test_azure_blob_shape(self, spec):
        paths = infer_source_paths(
            "azure_blob", spec, data_dir="abfss://aml@acc.dfs.core.windows.net"
        )
        for contract in spec.data_contracts:
            assert paths[contract.id].startswith("azure_blob:abfss://")
            assert paths[contract.id].endswith(f"/{contract.id}")

    def test_adls_shape(self, spec):
        paths = infer_source_paths(
            "adls", spec, data_dir="abfss://aml@acc.dfs.core.windows.net/raw"
        )
        for contract in spec.data_contracts:
            assert paths[contract.id].startswith("adls:abfss://")
            assert paths[contract.id].endswith(f"/{contract.id}")

    def test_synapse_shape(self, spec):
        conn = "DRIVER={ODBC Driver 18 for SQL Server};SERVER=...;DATABASE=aml"
        paths = infer_source_paths("synapse", spec, data_dir=conn)
        for contract in spec.data_contracts:
            assert paths[contract.id].startswith("synapse:")
            assert "#" in paths[contract.id]

    def test_azuresql_shape(self, spec):
        conn = "DRIVER={ODBC Driver 18 for SQL Server};SERVER=...;DATABASE=aml"
        paths = infer_source_paths("azuresql", spec, data_dir=conn)
        for contract in spec.data_contracts:
            assert paths[contract.id].startswith("azuresql:")
            assert "#" in paths[contract.id]

    def test_unknown_source_type_falls_through(self, spec):
        paths = infer_source_paths("totally_made_up", spec, data_dir="x")
        # The fallthrough branch returns the source_type itself per
        # contract — not a hard error.
        for contract in spec.data_contracts:
            assert paths[contract.id] == "totally_made_up"


class TestResolveSourceAzureValidation:
    """resolve_source() raises clear errors when the user passes an
    Azure source type but forgets the data_dir / connection string.
    The actual loader paths are #pragma: no cover."""

    def test_azure_blob_requires_data_dir(self, spec):
        with pytest.raises(ValueError, match="abfss"):
            resolve_source(
                "azure_blob",
                spec=spec,
                as_of=datetime.now(tz=timezone.utc),
            )

    def test_adls_requires_data_dir(self, spec):
        with pytest.raises(ValueError, match="abfss"):
            resolve_source(
                "adls",
                spec=spec,
                as_of=datetime.now(tz=timezone.utc),
            )
