# Audit & Evidence Design

Most AML fines involve one of two failures:

1. The control *existed on paper* but its implementation had drifted, or
2. The control ran but the institution couldn't *prove* what it had done
   when the regulator asked.

This framework fixes (1) with spec-driven generation and (2) with a
deterministic, append-only evidence ledger.

## What gets recorded per run

Every `aml run` produces an evidence bundle containing:

| File                        | Contents                                                        |
|-----------------------------|-----------------------------------------------------------------|
| `manifest.json`             | spec git SHA, spec content hash, engine version, timestamps     |
| `spec_snapshot.yaml`        | byte-exact copy of the spec used                                |
| `input_manifest.json`       | per-contract: row count, column checksum, earliest/latest ts    |
| `rules/<rule_id>.sql`       | the SQL actually executed for that rule                         |
| `alerts/<rule_id>.jsonl`    | one JSON line per alert, deterministic ordering                 |
| `alerts/<rule_id>.hash`     | SHA-256 of the JSONL; the "output hash"                         |
| `cases/<case_id>.json`      | case file: triggering txns, KYC snapshot, prior-alert history   |
| `decisions.jsonl`           | reviewer decisions appended over time, never mutated            |
| `dq_exceptions.jsonl`       | per-run data-quality violations (always present, may be empty); each record carries `severity` (`critical` / `high` / `medium` / `low` / `info`, default `high`) threaded from the originating `quality_checks` entry (PR-B5 / #370) so investigators triage critical contract breaks separately from cosmetic format defects |
| `field_lineage.jsonl`       | alert-field → (source contract, column, transform) mapping      |
| `sla_report.json`           | Pillar-6 SLA-monitor report: alert-disposition breaches + batch-lateness signal (always written; empty when `program.sla` is unset) |
| `run_cost_volume.json`      | row counts per table + wall-clock / peak-memory / per-rule timing|
| `monitoring_digest.json`    | post-run rollup: alerts per rule/queue/severity, top-3 firers, DQ totals, per-rule diff vs prior run (hash pinned on the manifest) |
| `defect_log.jsonl`          | Pillar-2 defect tickets: severity + 11-category classifier + data/rule/mapping triage + lifecycle (open/acknowledged/resolved/closed/wont_fix); always written, hash pinned on the manifest |
| `reconciliation_report.json`| Pillar-4 row-count survival per contract across bronze→silver→gold→alert + signed drop attribution (hash pinned on the manifest) |
| `signatures/manifest.sig`   | detached signature over `manifest.json` (if signing key set)    |

## Granular evidence exports (PR-D4, #377)

A full-run `aml audit-pack` ZIP can be tens of megabytes. When a regulator
asks for evidence on one alert or a hand-picked batch, ship the subset:

```
aml export-case  spec.yaml <run-dir> <case_id>            # one case
aml export-batch spec.yaml <run-dir> --cases c1,c2,c3     # multi-case batch
```

Both commands produce deterministic ZIPs containing only the requested
case file(s), the rule SQL that produced each alert, the canonical alert
attached to each case, the per-case decision sub-chain, lineage
(`rule_version`, `matched_row_ids`, source `input_files`), and the spec
snapshot. Pass `--signing-key` (or set `AML_CASE_PACK_SIGNING_KEY`) to
attach an HMAC-SHA256 signature over the bundle hash to `manifest.json`.
Missing case ids fail loudly — `export-batch` refuses to ship a partial
pack. When the run was produced with `AML_PII_MASKING=1`, the pack
re-applies the run's `pii_map.jsonl` so plaintext PII never leaves the
masking boundary; the manifest records `pii_masked: true` in that case.

## Determinism properties

- **Ordered input.** Rows going into any rule are sorted by the rule's natural
  key before hashing. Same input set → same input hash regardless of upstream
  order.
- **Ordered output.** Alerts are emitted sorted by `(rule_id, entity_id,
  window_end)`. Same alerts → same output hash.
- **Pinned spec.** The spec snapshot is stored verbatim in the bundle. A
  reviewer can diff two bundles' snapshots to see the exact policy change
  between runs.

## Re-execution check

```
aml replay .artifacts/evidence-2026-04-23.zip
```

Replays the bundled spec against the bundled input snapshot and asserts the
recomputed output hash equals the stored one. A mismatch is a reportable
control-integrity failure.

## Immutability model

The on-disk ledger is append-only by convention (no update/delete code path),
but file-system immutability is *not* enough for audit — a bad actor with
shell access could rewrite history. Production deployments should:

- Stream `manifest.json` + hashes to WORM-class storage (S3 Object Lock,
  Azure Immutable Blob, on-prem WORM).
- Sign each manifest with an offline key; rotate per retention policy.
- Forward decision events to a SIEM with its own retention guarantee.

The framework provides the artifacts; the institution provides the
tamper-evident substrate.

## What an auditor can answer with a bundle

- "Which exact rule wording produced alert A-1234?" — `spec_snapshot.yaml` +
  `alerts/<rule_id>.jsonl`.
- "What regulation clause was this control designed to satisfy?" —
  `spec_snapshot.yaml -> rules[*].regulation_refs`.
- "Who approved the threshold change last quarter?" — git log of
  `aml.yaml` plus PR review history.
- "Can we reproduce last April's numbers?" — `aml replay` against the April
  bundle.
- "Was this customer alerted before?" — `cases/` prior-alert history field,
  cross-referenced to earlier bundles by `customer_id`.
