"""Consulting-grade content: maturity model, framework alignment, roadmap.

This module re-exports from focused submodules for backward compatibility.
New code should import directly from the submodules.
"""

from __future__ import annotations

# Re-export everything so existing imports continue to work.
from aml_framework.dashboard.frameworks import (  # noqa: F401
    AMLD6_REQUIREMENTS,
    FATF_MAPPING,
    FINCEN_BSA_PILLARS,
    OSFI_B8_PRINCIPLES,
    PCMLTFA_PILLARS,
    WOLFSBERG_MAPPING,
    get_framework_tabs,
)
from aml_framework.dashboard.maturity import (  # noqa: F401
    MATURITY_DIMENSIONS,
    MATURITY_LEVELS,
    compute_maturity_scores,
)
from aml_framework.dashboard.roadmap import (  # noqa: F401
    INDUSTRY_BENCHMARKS,
    ROADMAP_PHASES,
    get_roadmap_phases,
)
