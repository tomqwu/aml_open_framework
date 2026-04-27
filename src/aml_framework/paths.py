"""Single source of truth for filesystem locations the framework consults.

Three callers used to compute `Path(__file__).resolve().parents[3]` to find
the project root, and one used `parents[1]` for the package's `data/lists`
directory. Defining them once means a refactor that nests the package
deeper only breaks here.
"""

from __future__ import annotations

from pathlib import Path

# .../src/aml_framework/paths.py → parents[2] is the project root.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

# .../src/aml_framework/paths.py → parents[0] is the package directory.
PACKAGE_ROOT: Path = Path(__file__).resolve().parent

# Bundled JSON schema for `aml.yaml`.
SCHEMA_PATH: Path = PROJECT_ROOT / "schema" / "aml-spec.schema.json"

# Reference lists shipped with the package (sanctions, PEP, etc).
REFERENCE_LISTS_DIR: Path = PACKAGE_ROOT / "data" / "lists"
