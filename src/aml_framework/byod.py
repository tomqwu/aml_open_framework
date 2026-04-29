"""Bring-your-own-data wizard — map a real warehouse to spec contracts.

Process problem this solves
---------------------------
After `aml init` (PR-F1) gives a developer a working starter spec,
the longest pole in adoption becomes "point this at our real data."
Today, the developer reads `data_contracts[*].columns` in their spec,
opens their warehouse's column catalogue in another window, and
hand-translates field names. Mistakes are silent: a typo in a column
mapping just means the rule never fires, and nobody notices until the
auditor asks.

This module reads the developer's actual data files (CSV / Parquet /
DuckDB), profiles each column (type + null-rate + sample values),
guesses a likely mapping for every contract column the spec
declares, and emits a `data_mapping.yaml` the developer reviews +
edits. Then `aml validate-data` (existing CLI command) verifies the
mapping is complete before the engine runs.

What this module does NOT do
----------------------------
- Guess across multiple files when the same column appears in two
  places — caller picks the source file per contract.
- Enforce business rules (e.g., "this column should be a positive
  decimal") — the spec's `quality_checks` already do that.
- Connect to live database connections — only file-based sources for
  now (CSV / Parquet / DuckDB on disk). Snowflake / BigQuery come
  later via `data/sources.py`.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

# Field-name aliases the matcher knows about. Keys are spec-contract
# canonical column names; values are the variants we've seen in real
# warehouses. Conservative on purpose — false positives in mapping
# silently break detection, so we'd rather suggest nothing than
# suggest the wrong thing.
COLUMN_ALIASES: dict[str, list[str]] = {
    "txn_id": ["transaction_id", "trx_id", "txid", "trx", "txn", "id"],
    "customer_id": ["cust_id", "client_id", "account_holder_id", "customer_no", "cif"],
    "amount": ["amt", "value", "transaction_amount", "amount_usd", "amount_local"],
    "currency": ["ccy", "currency_code", "iso_currency"],
    "channel": ["product", "transaction_type", "tx_type", "method"],
    "direction": ["dr_cr", "debit_credit", "flow", "tx_direction"],
    "booked_at": ["transaction_date", "booking_date", "value_date", "txn_ts", "ts", "datetime"],
    "counterparty_id": ["beneficiary_id", "payee_id", "counterparty_no"],
    "counterparty_name": ["payee_name", "beneficiary_name"],
    "counterparty_country": ["payee_country", "beneficiary_country"],
    "full_name": ["customer_name", "client_name", "name"],
    "country": ["customer_country", "country_code", "residence_country"],
    "risk_rating": ["risk_tier", "kyc_risk", "customer_risk"],
    "onboarded_at": ["account_open_date", "onboarding_date", "established"],
    "pep_status": ["pep_flag", "is_pep"],
    "edd_last_review": ["edd_date", "last_kyc_review", "kyc_refreshed_at"],
    "business_activity": ["industry", "sic_code", "naics_code", "naics"],
    "uetr": ["unique_e2e_ref", "end_to_end_id"],
    "purpose_code": ["payment_purpose", "iso_purpose"],
    "debtor_iban": ["debtor_account", "originator_iban"],
    "debtor_country": ["originator_country"],
    "debtor_bic": ["originator_bic"],
    "creditor_bic": ["beneficiary_bic"],
    "counterparty_account": ["beneficiary_account", "creditor_account"],
}


# ---------------------------------------------------------------------------
# Profiling
# ---------------------------------------------------------------------------

PythonType = Literal["string", "integer", "decimal", "timestamp", "boolean", "unknown"]


@dataclass(frozen=True)
class ColumnProfile:
    """What we know about one column in one source file."""

    name: str
    inferred_type: PythonType
    null_rate: float  # 0.0 = no nulls, 1.0 = all null
    sample_values: list[str] = field(default_factory=list)
    n_unique: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "inferred_type": self.inferred_type,
            "null_rate": round(self.null_rate, 3),
            "n_unique": self.n_unique,
            "sample_values": list(self.sample_values),
        }


def _infer_type(values: list[str]) -> PythonType:
    """Cheap type inference. Looks at non-empty samples and picks the
    narrowest type that fits all of them. 'integer' beats 'decimal'
    only when there are no decimal points anywhere in the sample."""
    non_empty = [v for v in values if v != "" and v is not None]
    if not non_empty:
        return "unknown"

    def _is_int(s: str) -> bool:
        return s.lstrip("-").isdigit()

    def _is_decimal(s: str) -> bool:
        if "." not in s:
            return False
        try:
            float(s)
            return True
        except ValueError:
            return False

    def _is_boolean(s: str) -> bool:
        return s.strip().lower() in {"true", "false", "0", "1", "y", "n"}

    def _is_timestamp(s: str) -> bool:
        # Cheap: any 4-digit year prefix + a separator (- or /).
        if len(s) < 8:
            return False
        if not s[:4].isdigit():
            return False
        return s[4] in "-/" or s[4:6].isdigit()

    if all(_is_int(v) for v in non_empty):
        return "integer"
    if all(_is_int(v) or _is_decimal(v) for v in non_empty):
        return "decimal"
    if all(_is_boolean(v) for v in non_empty):
        return "boolean"
    if all(_is_timestamp(v) for v in non_empty):
        return "timestamp"
    return "string"


def profile_csv(path: Path, *, max_rows: int = 5000) -> dict[str, ColumnProfile]:
    """Profile a CSV file. Reads up to `max_rows` rows for sampling."""
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return {}
        columns: dict[str, list[str]] = {name: [] for name in reader.fieldnames}
        for i, row in enumerate(reader):
            if i >= max_rows:
                break
            for col in columns:
                columns[col].append(row.get(col, "") or "")
    out: dict[str, ColumnProfile] = {}
    for col, values in columns.items():
        non_empty = [v for v in values if v]
        null_rate = 1.0 - (len(non_empty) / max(len(values), 1))
        unique = sorted(set(non_empty))
        sample = unique[:3]
        out[col] = ColumnProfile(
            name=col,
            inferred_type=_infer_type(values),
            null_rate=null_rate,
            sample_values=sample,
            n_unique=len(unique),
        )
    return out


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ColumnMapping:
    """Suggested mapping for one spec-contract column."""

    spec_column: str
    spec_type: str  # what the spec declares
    suggested_source_column: str | None  # None when no good match
    confidence: float  # 0.0 = no signal, 1.0 = exact name match
    reason: str  # human-readable explanation
    profile: ColumnProfile | None = None  # the matched source column's profile

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "spec_column": self.spec_column,
            "spec_type": self.spec_type,
            "suggested_source_column": self.suggested_source_column,
            "confidence": round(self.confidence, 2),
            "reason": self.reason,
        }
        if self.profile is not None:
            d["source_profile"] = self.profile.to_dict()
        return d


def suggest_mapping(
    spec_column: str,
    spec_type: str,
    source_columns: dict[str, ColumnProfile],
) -> ColumnMapping:
    """Pick the source column most likely to satisfy this spec column.

    Decision order (highest-confidence first):
      1. Exact name match
      2. Match against COLUMN_ALIASES
      3. Substring match (spec column appears in source name or vice versa)
      4. Type-only match — pick a source column with matching type if no
         name signal at all (low confidence; flagged for human review)
    """
    spec_lower = spec_column.lower()

    # 1. Exact match.
    for src_name, profile in source_columns.items():
        if src_name.lower() == spec_lower:
            return ColumnMapping(
                spec_column=spec_column,
                spec_type=spec_type,
                suggested_source_column=src_name,
                confidence=1.0,
                reason="Exact name match.",
                profile=profile,
            )

    # 2. Alias match.
    aliases = [a.lower() for a in COLUMN_ALIASES.get(spec_column, [])]
    for src_name, profile in source_columns.items():
        if src_name.lower() in aliases:
            return ColumnMapping(
                spec_column=spec_column,
                spec_type=spec_type,
                suggested_source_column=src_name,
                confidence=0.85,
                reason=f"Alias match — {src_name!r} is a known synonym for {spec_column!r}.",
                profile=profile,
            )

    # 3. Substring match.
    for src_name, profile in source_columns.items():
        sl = src_name.lower()
        if spec_lower in sl or sl in spec_lower:
            return ColumnMapping(
                spec_column=spec_column,
                spec_type=spec_type,
                suggested_source_column=src_name,
                confidence=0.6,
                reason=f"Substring match between {spec_column!r} and {src_name!r}.",
                profile=profile,
            )

    # 4. Type-only match (only when one source column matches; else no suggestion).
    type_matches = [(n, p) for n, p in source_columns.items() if p.inferred_type == spec_type]
    if len(type_matches) == 1:
        src_name, profile = type_matches[0]
        return ColumnMapping(
            spec_column=spec_column,
            spec_type=spec_type,
            suggested_source_column=src_name,
            confidence=0.3,
            reason=(
                f"Single source column matches the declared type {spec_type!r}; "
                "no name signal — please verify."
            ),
            profile=profile,
        )

    # 5. No match.
    return ColumnMapping(
        spec_column=spec_column,
        spec_type=spec_type,
        suggested_source_column=None,
        confidence=0.0,
        reason="No matching source column — fill in manually.",
    )


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContractMappingReport:
    """Mapping outcome for one data contract in the spec."""

    contract_id: str
    source_file: Path
    mappings: list[ColumnMapping] = field(default_factory=list)

    @property
    def unmapped_required(self) -> list[ColumnMapping]:
        return [m for m in self.mappings if m.suggested_source_column is None]

    @property
    def low_confidence(self) -> list[ColumnMapping]:
        return [
            m for m in self.mappings if m.suggested_source_column is not None and m.confidence < 0.7
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "source_file": str(self.source_file),
            "mappings": [m.to_dict() for m in self.mappings],
            "unmapped_count": len(self.unmapped_required),
            "low_confidence_count": len(self.low_confidence),
        }


def map_spec_to_data_dir(spec: Any, data_dir: Path) -> list[ContractMappingReport]:
    """Walk every data contract in the spec, find the matching source
    file in `data_dir` (by contract id), profile it, and suggest a
    mapping for every column the spec declares.

    Source-file resolution: looks for ``{contract_id}.csv`` first, then
    ``{contract_id}.parquet``, then any file beginning with the
    contract id. Skipped contracts produce a report with no mappings
    and a synthetic ``source_file`` pointing at the missing path.
    """
    out: list[ContractMappingReport] = []
    for contract in spec.data_contracts:
        candidate = _resolve_data_file(data_dir, contract.id)
        if candidate is None:
            out.append(
                ContractMappingReport(
                    contract_id=contract.id,
                    source_file=data_dir / f"{contract.id}.csv",
                    mappings=[
                        ColumnMapping(
                            spec_column=col.name,
                            spec_type=col.type,
                            suggested_source_column=None,
                            confidence=0.0,
                            reason=f"No source file found for contract {contract.id!r}.",
                        )
                        for col in contract.columns
                    ],
                )
            )
            continue

        if candidate.suffix == ".csv":
            profile_map = profile_csv(candidate)
        else:
            # Parquet / DuckDB profiling deferred — F2 ships with CSV
            # only since that's where 90% of first-week onboardings sit.
            profile_map = {}

        mappings = [suggest_mapping(col.name, col.type, profile_map) for col in contract.columns]
        out.append(
            ContractMappingReport(
                contract_id=contract.id,
                source_file=candidate,
                mappings=mappings,
            )
        )
    return out


def _resolve_data_file(data_dir: Path, contract_id: str) -> Path | None:
    for ext in (".csv", ".parquet"):
        p = data_dir / f"{contract_id}{ext}"
        if p.exists():
            return p
    matches = sorted(data_dir.glob(f"{contract_id}*"))
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# YAML emission
# ---------------------------------------------------------------------------


def render_mapping_yaml(reports: list[ContractMappingReport]) -> str:
    """Render the mapping reports as a `data_mapping.yaml` file.

    The output is the developer's working artifact: they review +
    edit each suggested mapping, then `aml validate-data` checks
    completeness before the engine runs.
    """
    lines: list[str] = [
        "# Generated by `aml byod` — review every suggestion before running the engine.",
        "# Each `source_column: null` entry needs a real column name from your warehouse.",
        "",
        "version: 1",
        "",
        "contracts:",
    ]
    for report in reports:
        lines.append(f"  - id: {report.contract_id}")
        lines.append(f"    source_file: {report.source_file}")
        lines.append("    columns:")
        for m in report.mappings:
            src = m.suggested_source_column or "null  # FILL THIS IN"
            lines.append(f"      - spec_column: {m.spec_column}")
            lines.append(f"        spec_type: {m.spec_type}")
            lines.append(f"        source_column: {src}")
            lines.append(f"        confidence: {m.confidence}")
            lines.append(f"        # {m.reason}")
        lines.append("")
    return "\n".join(lines)
