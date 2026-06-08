"""Synthetic-data entry points.

`generate_dataset` is the shared community-bank generator (the default
for every spec). A small dispatch registry — keyed by `program.name` —
lets the three newer specs (us_rtp_fednow, uk_app_fraud, trade_based_ml)
serve their own isolated planted-positive bands (C9xxx) instead of the
shared community-bank C0xxx band. Any spec NOT in the registry falls
back to `generate_dataset`, byte-identical to before, so the wiring is
non-invasive: no spec-schema field, no change to `resolve_source`
semantics for any other source type.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from aml_framework.data.synthetic import generate_dataset
from aml_framework.data.synthetic_rtp_fednow import generate_rtp_fednow_dataset
from aml_framework.data.synthetic_trade_based_ml import generate_trade_based_ml_dataset
from aml_framework.data.synthetic_uk_app_fraud import generate_uk_app_fraud_dataset

if TYPE_CHECKING:
    from aml_framework.spec.models import AMLSpec

# Maps `spec.program.name` -> its dedicated synthetic generator. Each
# generator has the same (as_of, seed) signature as `generate_dataset`.
_SPEC_GENERATORS: dict[str, Callable[..., dict[str, list[dict[str, Any]]]]] = {
    "us_rtp_fednow_push_fraud": generate_rtp_fednow_dataset,
    "uk_challenger_app_fraud": generate_uk_app_fraud_dataset,
    "tbml_correspondent_bank": generate_trade_based_ml_dataset,
}


def has_registered_generator(spec: AMLSpec) -> bool:
    """True when `spec` has a dedicated planted-positive generator.

    Callers that special-case data resolution (e.g. the dashboard's
    root-CSV preference) use this to keep registered specs on their
    per-spec C9xxx band while leaving every unregistered spec's path
    unchanged.
    """
    return spec.program.name in _SPEC_GENERATORS


def generate_dataset_for_spec(
    spec: AMLSpec,
    as_of: datetime,
    seed: int = 42,
) -> dict[str, list[dict[str, Any]]]:
    """Resolve the synthetic generator for a spec by `program.name`.

    Returns the spec's dedicated planted-positive dataset when one is
    registered; otherwise the shared community-bank `generate_dataset`
    (byte-identical to the legacy path for every unregistered spec).
    """
    generator = _SPEC_GENERATORS.get(spec.program.name)
    if generator is not None:
        return generator(as_of=as_of, seed=seed)
    return generate_dataset(as_of=as_of, seed=seed)


__all__ = [
    "generate_dataset",
    "generate_dataset_for_spec",
    "generate_rtp_fednow_dataset",
    "generate_trade_based_ml_dataset",
    "generate_uk_app_fraud_dataset",
    "has_registered_generator",
]
