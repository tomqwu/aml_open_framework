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
