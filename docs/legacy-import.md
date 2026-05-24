# Importing from legacy SAS / Actimize / Mantas

If you're moving off SAS / Oracle FCCM / IMS / Actimize / Mantas, the
first 2-3 weeks of a migration usually go into re-typing legacy
detectors into `aml.yaml` by hand. `aml import-legacy` automates the
mechanical part: it takes a CSV or JSON dump of your legacy rules and
emits a starter `rules:` block where every legacy rule becomes a stub
the operator iterates on.

## Two commands

```bash
aml inventory legacy_rules.csv             # read-only summary — how big is the migration?
aml import-legacy legacy_rules.csv -o spec_skeleton.yaml
```

`aml inventory` is the sizing call: total rules parsed, shape
breakdown (SQL / threshold / narrative / empty), duplicate-id check,
and how many rows have no regulator citation attached. Run it first;
re-run after each pass of dump cleanup to watch the "needs manual"
bucket shrink.

`aml import-legacy` writes the skeleton. It will refuse to overwrite
an existing output file unless you pass `--overwrite`.

## Supported shapes

The wizard handles three common shapes per row:

| Shape | Recognised columns | Output |
|---|---|---|
| **SQL-bearing** | `rule_id`, `name`, `sql_text` (or `sql` / `query` / `legacy_sql`) | `logic.type: custom_sql`, SQL preserved verbatim |
| **Threshold-bearing** | `rule_id`, `threshold_block` (or `thresholds` / `parameters`) as JSON | `aggregation_window` stub with the legacy threshold tucked into `having` |
| **Narrative-only** | `rule_id`, `description` (or `narrative` / `notes`) | Placeholder + `# TODO: convert narrative` so you can `grep TODO` for what still needs manual conversion |

Rows with both SQL and a threshold block prefer SQL (legacy SQL is
treated as the source of truth). Rows with only a `rule_id` still
import as a placeholder so the operator can find every legacy ID
somewhere in the skeleton.

## Header aliasing

Headers are normalised case-insensitively and tolerate spaces or
dashes: `Rule ID` / `RULE_ID` / `rule id` all map to `rule_id`.
Common aliases:

- `rule_id` ← `id`, `ruleid`, `rule`, `scenario_id`
- `name` ← `rule_name`, `scenario_name`, `label`, `title`
- `legacy_sql` ← `sql`, `sql_string`, `sql_text`, `query`
- `threshold_block` ← `threshold`, `thresholds`, `threshold_json`, `parameters`, `params`
- `narrative` ← `description`, `rule_description`, `notes`, `comment`
- `regulator_refs` ← `regulator_ref`, `regulation_refs`, `regulations`, `citations`

`regulator_refs` accepts a pipe / semicolon / comma-separated string
**or** a JSON list. Unknown columns are silently ignored so a noisy
dump doesn't fail to import.

## JSON dumps

Both shapes are accepted:

```json
[
  {"rule_id": "R001", "name": "...", "legacy_sql": "SELECT ..."}
]
```

```json
{
  "rules": [
    {"rule_id": "R001", "name": "...", "threshold_block": {"having": {"count": {"gte": 10}}}}
  ]
}
```

## Malformed rows surface as warnings

A row with a broken threshold JSON or a missing `rule_id` becomes a
*warning* surfaced under `aml inventory` — not a crash. The good rows
still import. Use the inventory command to triage warnings before
running the full import.

When a row has both SQL and a malformed threshold block, the SQL is
kept (legacy dumps often ship parameter blobs alongside SQL) and the
bad threshold is logged as a warning.

## Threshold blocks

A row with a `threshold_block` cell goes into an `aggregation_window`
stub. The wizard tries to use legacy `having` / `window` / `source` /
`group_by` / `filter` keys directly when present, and the **full
original blob is preserved as a `legacy_threshold_block:<json>` tag
on the stub** (a single string under `tags`, since `Rule` forbids
extra top-level fields). Find every preserved blob with
`grep legacy_threshold_block: skeleton.yaml`. Rows whose source
block has only metadata (no real metric like `count` / `sum_amount`)
are tagged `needs_manual_conversion` AND set to `status:
experimental` so the engine skips them until the operator promotes
to `active` after finishing the conversion.

## Duplicate rule IDs

If two legacy rules sanitise to the same spec ID (e.g. `R-1` and
`R_1` both become `r_1`), the second is suffixed with `_<n>` so the
runner doesn't silently overwrite alerts from one rule with the
other. A `legacy_dup_of:<original>` tag is added to the duplicates
for traceability.

## Rule-ID sanitisation

The AML spec requires `Rule.id` to match `^[a-z][a-z0-9_]*$`. Legacy
IDs that don't fit (`R001`, `scenario-1`, `CASH.STRUCT.01`, `42`)
are rewritten to lowercase + underscored so the emitted skeleton is
validation-ready:

| Legacy ID | Emitted `id` | Tag preserved on stub |
|---|---|---|
| `R001` | `r001` | `legacy_id:R001` |
| `CASH.STRUCT.01` | `cash_struct_01` | `legacy_id:CASH.STRUCT.01` |
| `scenario-1` | `scenario_1` | `legacy_id:scenario-1` |
| `42` | `legacy_42` | `legacy_id:42` |

The original ID is always preserved as a `legacy_id:` tag so `grep`
finds it in the skeleton.

## What the skeleton is NOT

The skeleton intentionally fails `aml validate` if used raw — that's
the design. You're expected to:

1. Merge the skeleton into your real `aml.yaml` (data contracts,
   workflow, reporting forms all stay yours).
2. Replace every `TODO` marker with a real value:
   - `regulation_refs` (the legacy system rarely encodes this)
   - `escalate_to` (queue routing is a governance decision)
   - `severity` (defaults to `medium` — adjust per rule)
3. For threshold-bearing stubs, fill in `source` (the data-contract
   ID) and verify `group_by` / `window` against your warehouse.
4. For narrative-only stubs, rewrite the `aggregation_window`
   placeholder against the data contract and remove the
   `needs_manual_conversion` tag once done.
5. Run `aml validate spec.yaml` — the validator points at every
   field that still needs attention.
6. Tune thresholds with `aml tune` / the Tuning Lab dashboard page
   before promoting to production.

## Why this matters

Migration friction is the dominant reason real banks stay on legacy
platforms past their EOL date. This wizard doesn't pretend to be a
full translator — it does the mechanical 80% (parse, classify,
preserve thresholds and SQL verbatim) and leaves the governance 20%
(regulation citations, queue routing, severity) for the operator
because those are *risk decisions*, not text transformations.
