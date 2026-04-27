"""Entity resolution layer.

Modern AML platforms (Quantexa, Hawk, Unit21) lead with graph context —
the same customer appearing under different IDs, or two customers sharing
a device / phone / address are common laundering patterns. This module
builds two artifacts inside the engine's in-memory DuckDB:

- A `resolved_entity` view giving every customer a `resolved_entity_id`.
  In v1 this equals `customer_id`; future versions can cluster via
  union-find over the link table.
- A `resolved_entity_link` table of pairwise links between customers
  that share a non-null linking attribute (phone, email, device_id,
  address — only the columns the spec actually declares).

`network_pattern` rules (PR16) will run recursive CTEs over this table.
The shape is intentionally simple: production deployments swap in a
real ER service (Senzing, Quantexa, Liminal) by overriding
`resolve_entities`.
"""

from __future__ import annotations

import duckdb

from aml_framework.spec.models import AMLSpec

# Columns that, when present on the `customer` contract, are treated as
# linking attributes for entity resolution. Customers sharing a non-null
# value on any of these columns become connected in `resolved_entity_link`.
_LINKING_COLUMNS = ("phone", "email", "device_id", "address", "tax_id", "wallet_address")


def _has_customer_table(con: duckdb.DuckDBPyConnection) -> bool:
    rows = con.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'customer'"
    ).fetchall()
    return bool(rows)


def _customer_columns(con: duckdb.DuckDBPyConnection) -> set[str]:
    rows = con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'customer'"
    ).fetchall()
    return {r[0] for r in rows}


def resolve_entities(con: duckdb.DuckDBPyConnection, spec: AMLSpec) -> None:
    """Build `resolved_entity` view + `resolved_entity_link` table.

    No-op when the spec doesn't declare a `customer` contract or when no
    linking attributes are present. Idempotent: safe to call repeatedly.
    """
    del spec  # reserved for future use (custom resolution config in spec)

    if not _has_customer_table(con):
        # The link table is still useful even with no customers yet — leave a
        # stub so downstream rules can join without conditional logic.
        con.execute(
            "CREATE OR REPLACE TABLE resolved_entity_link"
            " (left_customer_id VARCHAR, right_customer_id VARCHAR,"
            "  attribute VARCHAR, weight DOUBLE)"
        )
        con.execute(
            "CREATE OR REPLACE VIEW resolved_entity AS"
            " SELECT NULL::VARCHAR AS customer_id, NULL::VARCHAR AS resolved_entity_id WHERE 1=0"
        )
        return

    cols = _customer_columns(con)
    available = [c for c in _LINKING_COLUMNS if c in cols]

    # Resolved-entity view: one row per customer, resolved_entity_id == customer_id.
    # Future: replace with union-find-derived ID after clustering.
    con.execute(
        "CREATE OR REPLACE VIEW resolved_entity AS"
        " SELECT customer_id, customer_id AS resolved_entity_id FROM customer"
    )

    # Pairwise links over each linking attribute.
    if not available:
        con.execute(
            "CREATE OR REPLACE TABLE resolved_entity_link"
            " (left_customer_id VARCHAR, right_customer_id VARCHAR,"
            "  attribute VARCHAR, weight DOUBLE)"
        )
        return

    union_parts = []
    for attr in available:
        # Self-join: any two customers sharing a non-null value on `attr`.
        # weight = 1.0 for now; future: per-attribute weighting from spec.
        union_parts.append(
            f"SELECT a.customer_id AS left_customer_id,"
            f" b.customer_id AS right_customer_id,"
            f" '{attr}' AS attribute, 1.0 AS weight"
            f" FROM customer a JOIN customer b ON a.{attr} = b.{attr}"
            f" WHERE a.customer_id < b.customer_id AND a.{attr} IS NOT NULL"
        )
    con.execute(
        f"CREATE OR REPLACE TABLE resolved_entity_link AS {' UNION ALL '.join(union_parts)}"
    )
