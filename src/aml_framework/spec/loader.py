"""Load and validate an aml.yaml spec.

Two-layer validation:
1. JSON Schema — structural contract, the thing external tools validate against.
2. Pydantic model — adds cross-reference checks (rules reference real
   data_contracts, escalate to real queues).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from aml_framework.spec.models import AMLSpec

_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "aml-spec.schema.json"


def _load_schema() -> dict:
    with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_spec(path: str | Path) -> AMLSpec:
    """Read, validate, and return an AMLSpec from a YAML file."""
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)

    # PyYAML auto-converts ISO dates to date objects; JSON Schema expects
    # strings. Round-trip through JSON with `default=str` to normalise.
    data = json.loads(json.dumps(data, default=str))

    schema = _load_schema()
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        msgs = [
            f"  - {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors
        ]
        raise ValueError(
            f"aml.yaml failed JSON Schema validation ({len(errors)} error(s)):\n" + "\n".join(msgs)
        )

    return AMLSpec.model_validate(data)


def spec_content_hash(path: str | Path) -> str:
    """SHA-256 of the spec file bytes. Used in audit manifests."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
