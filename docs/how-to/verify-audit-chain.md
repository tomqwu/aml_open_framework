# How to verify the audit hash chain

> **When you need this:** A regulator/auditor asks "prove this `decisions.jsonl` hasn't been tampered with since the run finished." Or you suspect a stale artifact mounted from S3. Or you're integrating the framework into a tamper-evident archive workflow.
>
> **Prereqs:** A finished run directory (`.artifacts/run-<timestamp>/`) on disk or in object storage. `aml verify-decisions` CLI installed (ships with `pip install -e .`).
>
> **Time:** ~30 seconds for a single run. ~5 min to wire into a CI gate.

The framework's audit ledger is **SHA-256 hash-chained**: every line in `decisions.jsonl` includes the hash of the previous line. The final hash lands on `manifest.json` (the `decisions_hash` field). Tamper with any decision and either:

- The chain breaks (line N+1's `prev_hash` no longer matches line N's hash), OR
- The chain re-validates but `manifest.json::decisions_hash` no longer matches the recomputed final hash.

Either way, a `verify-decisions` run catches it.

---

## Steps

### 1 · Verify a single run

```bash
aml verify-decisions .artifacts/run-2026-05-24T18-03-12Z
```

Expected output:

```
✓ chain valid, 247 decisions, head_hash=8f3a7e9c…
✓ manifest.json::decisions_hash matches recomputed head
✓ manifest.json::dq_exceptions_hash matches sha256(dq_exceptions.jsonl)
✓ manifest.json::field_lineage_hash matches sha256(field_lineage.jsonl)
✓ manifest.json::sla_report_hash matches sha256(sla_report.json)
✓ manifest.json::run_cost_volume_hash matches sha256(run_cost_volume.json)
✓ manifest.json::monitoring_digest_hash matches sha256(monitoring_digest.json)
✓ manifest.json::defect_log_hash matches sha256(defect_log.jsonl)
✓ manifest.json::reconciliation_report_hash matches sha256(reconciliation_report.json)
```

Exit code 0 = chain valid + all artifact hashes match. Non-zero = something diverged.

### 2 · Verify against a stored manifest hash

The strongest assurance comes from pinning `decisions_hash` in an **external** store (database row, WORM bucket, signed log) at run-finalize time. Then later:

```bash
# Pull the expected hash from your external store
EXPECTED=$(psql -tA -c "SELECT decisions_hash FROM run_manifests WHERE run_id = '<run_id>'")

# Verify against it
aml verify-decisions .artifacts/run-... --expected-hash "$EXPECTED"
```

If `manifest.json::decisions_hash` got rewritten alongside `decisions.jsonl` (the only attack that beats internal verification), this catches it.

### 3 · Verify every run in a directory tree

The CLI verifies one run at a time. A `find` loop fans out across an archive:

```bash
set -euo pipefail
# Belt-and-suspenders: a missing/typo'd archive path silently passes
# without the count check (xargs exits 0 on empty input).
count=$(find .artifacts/ -name manifest.json | wc -l)
if [ "$count" -eq 0 ]; then
  echo "::error::No manifest.json under .artifacts/ — refusing to claim verification."
  exit 1
fi
find .artifacts/ -name manifest.json -print0 \
  | xargs -0 -n1 -I{} sh -c 'aml verify-decisions --run-dir "$(dirname "$1")" || exit 255' _ {}
```

For large archives a parallel variant (`xargs -P 8 ...`) drops wall time at the cost of interleaved logs.

### 4 · Wire into CI

Add to your `.github/workflows/audit-check.yml` or scheduled S3 audit:

```yaml
- name: Verify audit chain
  run: |
    set -euo pipefail
    # Belt-and-suspenders: `find` exits non-zero on a missing path,
    # but `xargs` exits 0 on empty input, so without a count check
    # a typo in $RUN_ARCHIVE_PATH would silently "pass" the audit.
    count=$(find "${{ env.RUN_ARCHIVE_PATH }}" -name manifest.json | wc -l)
    if [ "$count" -eq 0 ]; then
      echo "::error::No manifest.json files found under ${{ env.RUN_ARCHIVE_PATH }} — audit cannot run."
      exit 1
    fi
    find "${{ env.RUN_ARCHIVE_PATH }}" -name manifest.json -print0 \
      | xargs -0 -n1 -I{} sh -c 'aml verify-decisions --run-dir "$(dirname "$1")" || exit 255' _ {}
```

Recommended frequency: daily on the last 7 days of stored runs.

---

## Verify it worked

The verifier exits **0** on pass, **non-zero** on fail, and on fail prints **which line diverged + the expected vs actual hashes**. To smoke-test the verifier itself:

```bash
# Pick any run, corrupt one decision line, re-verify, restore
cp .artifacts/run-.../decisions.jsonl /tmp/decisions.bak
sed -i.bak 's/case_opened/case_oepned/' .artifacts/run-.../decisions.jsonl   # typo on purpose
aml verify-decisions .artifacts/run-...   # should EXIT 1
mv /tmp/decisions.bak .artifacts/run-.../decisions.jsonl
aml verify-decisions .artifacts/run-...   # back to PASS
```

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `chain valid` but `manifest.json::decisions_hash mismatch` | Someone edited `decisions.jsonl` AND re-recorded the head hash in `manifest.json`. The chain inside is internally consistent but it's not the chain the run ORIGINALLY produced. | Pull `decisions_hash` from an external store (DB row, WORM bucket) and pass `--expected-hash`. |
| `manifest.json` doesn't exist | Run aborted before `ledger.finalize()` (e.g. `ContractViolation`, strict `python_ref` raise) | Look for `decisions.jsonl` and `defect_log.jsonl` — abort-path artifacts. **With an out-of-band head hash**: `aml verify-decisions --run-dir <partial-run-dir> --expected-hash <hex>` works against `decisions.jsonl` directly (manifest not required). The explicit `--run-dir` is important when multiple runs sit under `.artifacts/` — the CLI otherwise defaults to the newest and could verify the wrong run. **Without a pinned hash**: the CLI needs `manifest.json`; inspect the partial files with `jq` or open them in the dashboard's Decision Trail page. |
| Verifier complains `field_lineage_hash` is None | Run predates PR-A3 (Round 26+) | Expected. The hash is back-compat optional; only post-A3 runs have it populated. |
| Permission denied on `.artifacts/run-...` | Files were chmod-frozen post-finalize (POSIX read-only) | Read-only is the intended behaviour. Use `sudo` or run verification as the user that ran the spec. |

---

## What the hash chain protects against

| Attack | Caught? |
|---|---|
| Edit one decision line in-place | ✅ Chain breaks at line N+1 |
| Delete a decision line | ✅ Subsequent prev_hash mismatches |
| Insert a fake decision line | ✅ Recomputed head_hash ≠ stored decisions_hash |
| Edit a decision AND re-record the head_hash in `manifest.json` (privileged in-place rewrite) | ⚠️ Caught only if you pinned the hash externally and pass `--expected-hash` |
| Edit `dq_exceptions.jsonl` (artifact hash, not chain) | ✅ `dq_exceptions_hash` recompute fails |
| Restore an entire OLD run dir to overwrite a NEW one | ⚠️ Caught only if you pinned the manifest externally with the run_id |

The chain is **strongest when paired with external pinning**. For real-world deployment, write `manifest.json::decisions_hash` to an immutable store (Postgres with row-level audit, WORM bucket, signed log) at run-finalize time.

---

## Next steps

- **Production deployment**: wire `aml verify-decisions --batch` into your daily scheduled job alongside an external manifest-hash store.
- **STR / regulator filing**: every audit-pack ZIP (`build_audit_pack`) carries the manifest hash inside; the regulator can replay against their copy and yours.
- **Custom verifier**: the verifier is a thin wrapper around `AuditLedger.verify_decisions()`. If you need a Python API rather than CLI, import that function directly.
