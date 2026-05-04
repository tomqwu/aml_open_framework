# Data Input

Drop CSV or Parquet files here for batch ingestion.

## Convention

One file per data contract, named by contract ID:

```
data/input/
  txn.csv          # Transactions (matches data_contracts.txn)
  customer.csv     # Customers (matches data_contracts.customer)
```

## Usage

```bash
aml run examples/canadian_schedule_i_bank/aml.yaml --data-source csv --data-dir data/input/
```

## Column headers

Must match the column names declared in the spec's `data_contracts` section.
See the spec file for required columns, types, and constraints.

## Empty or missing inputs

CSV, Parquet, DuckDB, warehouse, and cloud sources fail closed by default for
every declared data contract. A missing file, missing table, failed query, or
warehouse/cloud read error stops the run instead of silently materialising an
empty table that could produce zero alerts.

If a contract is intentionally optional for a specific deployment, make that
explicit in the spec:

```yaml
data_contracts:
  - id: optional_reference
    source: raw.optional_reference
    allow_empty: true
    columns:
      - { name: reference_id, type: string, nullable: false }
```

Use `allow_empty: true` only when the empty/missing source is an expected,
reviewable condition; otherwise fix the upstream data mapping or permissions.
