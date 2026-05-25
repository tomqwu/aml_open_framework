# How to export per-case / per-batch evidence packs

> **When you need this:** A regulator/auditor asks for evidence on a SPECIFIC case (or a hand-selected batch), not the whole run. The full audit pack is 50+ MB; a single-case pack is ~50 KB.
>
> **Prereqs:** A finished run directory under `.artifacts/` and the `case_id` (or list of `case_id`s) you want to bundle. `aml export-case` and `aml export-batch` shipped in PR-D4 / Round 28.
>
> **Time:** ~30 sec per export.

A per-case pack is the surgical alternative to `aml auditor-pack`: spec snapshot + the one case file + the filtered decision sub-chain + lineage + rule SQL + alert payload — and **only** that case's evidence (no sibling leak).

---

## Steps

### 1 · Identify the case_id(s)

A `case_id` is the basename of any `cases/<id>.json` file in the run directory. List them quickly:

```bash
ls .artifacts/run-2026-05-25T10-15-30Z/cases/ | sed 's/\.json$//' | head
# C0042-cash_structuring-001
# C0043-cash_structuring-001
# C0044-rapid_pass_through-001
# ...
```

### 2 · Export a single case

**Important — pass the spec snapshot from the run, NOT current `aml.yaml`.** The CLI uses the first argument to render `program.md` and manifest metadata; if `aml.yaml` has drifted since the run, you'd ship a pack with current program metadata mixed with historical alert evidence. Always point at `.artifacts/<run-dir>/spec_snapshot.yaml`:

```bash
aml export-case .artifacts/run-2026-05-25T10-15-30Z/spec_snapshot.yaml .artifacts/run-2026-05-25T10-15-30Z C0042-cash_structuring-001
# → ./case-C0042-cash_structuring-001.zip
```

Override the output path with `--out`:

```bash
aml export-case .artifacts/run-2026-05-25T10-15-30Z/spec_snapshot.yaml .artifacts/run-... C0042-cash_structuring-001 \
  --out /tmp/regulator-requests/2026-05-25-C0042.zip
```

### 3 · Export a batch (hand-picked cases)

```bash
aml export-batch .artifacts/run-2026-05-25T10-15-30Z/spec_snapshot.yaml .artifacts/run-2026-05-25T10-15-30Z \
  --cases C0042-cash_structuring-001,C0044-rapid_pass_through-001,C0050-pep_screening-001 \
  --out 2026-05-25-fincen-pack.zip
```

`--cases` is a comma-separated list. Missing case ids **fail loudly** so the investigator never ships a half-empty pack.

### 4 · Sign the manifest (optional)

For chain-of-custody, attach an HMAC-SHA256 signature so the recipient can prove the bundled **file set** (the `bundle_hash` covers every file's SHA-256 + the file list) hasn't been altered after handoff. Note: the HMAC covers `bundle_hash` only — other manifest metadata (e.g. timestamps, descriptive fields) could theoretically be edited without invalidating the signature. For full-manifest integrity, hash the entire manifest out-of-band as well.

```bash
export AML_CASE_PACK_SIGNING_KEY="$(openssl rand -hex 32)"
aml export-case .artifacts/run-2026-05-25T10-15-30Z/spec_snapshot.yaml .artifacts/run-... C0042-... --signing-key "$AML_CASE_PACK_SIGNING_KEY"
```

`generators/audit_pack.py::_attach_signature` HMAC-SHA256s **only `manifest["bundle_hash"]`** (the canonical aggregate hash, not the whole manifest), and writes the result into `manifest["signature"]` with two fields: `algorithm` (`"HMAC-SHA256"`) and `value` (hex digest). The recipient verifies by:

```python
import hashlib, hmac, json
# 1) Recompute bundle_hash from the actual ZIP entries — do NOT trust
#    the value in manifest["bundle_hash"]. An attacker who edits files
#    in the ZIP but leaves the manifest bundle_hash untouched would
#    pass an HMAC check on the supplied value.
recomputed = hashlib.sha256(json.dumps(manifest["files"], sort_keys=True).encode()).hexdigest()
assert recomputed == manifest["bundle_hash"], "bundle_hash mismatch — pack tampered"
# 2) Then HMAC the (now-verified) bundle_hash:
expected = hmac.new(shared_key.encode(), recomputed.encode(), hashlib.sha256).hexdigest()
assert expected == manifest["signature"]["value"]
```

Share the key out-of-band (not in the ZIP).

---

## What's in the pack

Unzip and inspect. Entries are written at the ZIP root (no enclosing folder) — layout from `generators/audit_pack.py::_case_pack_files()`:

```
(zip root)
├── manifest.json                          # filtered hashes; optional HMAC signature
├── program.md                              # program intent + scope context
├── spec_snapshot.yaml                      # the exact spec content that produced this case
                                            #   (included by build_case_pack / build_batch_pack
                                            #    whenever the runner emitted it — required for
                                            #    deterministic replay; see walk-lineage.md §4)
├── cases/
│   └── C0042-cash_structuring-001.json
├── decisions/
│   └── C0042-cash_structuring-001.jsonl   # filtered to only this case's decisions
├── alerts/
│   └── C0042-cash_structuring-001.jsonl   # case-canonical (filenames keyed by case_id, not rule)
├── lineage/
│   └── C0042-cash_structuring-001.json    # slim summary: {case_id, rule_id, rule_version, matched_row_ids, input_files}
│                                          #   (NOT the full walk_lineage() chain — that's derived on demand)
└── rules/
    └── cash_structuring.sql                # rule SQL (keyed by rule_id, not case_id)
```

Filenames inside `cases/`, `decisions/`, `alerts/`, `lineage/` are keyed by `case_id` so a batch pack lays out one per-case file under each directory rather than one combined file per type. PII masking: `_apply_pii_map()` substitutes on the case / decision / alert / lineage JSON file CONTENTS and on ZIP entry names. **Not masked**: `rules/<rule_id>.sql` and `spec_snapshot.yaml` are copied verbatim — if a `custom_sql` literal embeds a customer id or a spec field carries a recognizable string, those files leak the plaintext through to the recipient. Audit the spec + rule SQL for embedded identifiers before sharing a masked-run pack.

---

## Verify it worked

Three checks:

1. **Unzip + walk the manifest** — every file listed in `manifest.json` exists in the ZIP and its SHA-256 matches the recorded hash. (`aml verify-decisions` is geared at a full run dir, not the filtered case-pack subchain — do the manifest walk by hand.)
2. **Decision-chain spot-check** — `jq -c .` over `decisions/<case_id>.jsonl` shows only events for that case. No sibling case ids leak in.
3. **Sibling-leak smoke test** — file names alone don't prove the alerts inside are correctly filtered. Read the contents of each `alerts/<case_id>.jsonl` and confirm every row belongs to the requested case. Alerts carry `customer_id`; the case's customer lives at `cases/<case_id>.json::alert.customer_id` (no top-level `customer_id`):

   `customer_id` alone is not enough — a leaked sibling alert for the same customer (e.g. two `custom_sql` windows) would pass that check. Compare the FULL alert payload to `cases/<id>.json::alert`:

   ```bash
   for f in alerts/*.jsonl; do
     case_id=$(basename "$f" .jsonl)
     expected=$(jq -cS '.alert' "cases/$case_id.json")
     # Sort each alert row's keys canonically before comparing
     mapfile -t rows < <(jq -cS . "$f")
     for row in "${rows[@]}"; do
       if [ "$row" != "$expected" ]; then
         echo "❌ $f leaked siblings: row $row does not match case alert"
       fi
     done
   done
   ```

   Empty output = no sibling leak. (If a case has multiple alert rows by design, drop the strict equality and compare on the union of `matched_row_ids` + `window_end` + `customer_id`.)

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `case_id not found` | Typo, or the run dir is older than the case | `ls .artifacts/<run>/cases/` to confirm |
| Multi-case batch missing one entry | Wrong `case_id` in `--cases` | The command exits non-zero on the missing case — re-check the spelling |
| `PiiMapCorruptError` on export | `pii_map.jsonl` sidecar truncated mid-write | Re-finalize the run (`aml run`) — the masking sidecar is regenerated atomically |
| Pack contains a sibling alert that wasn't requested | Pre-PR-D4 codex-pass-1 bug; should not reproduce on R28+ | Confirm the run was produced by ≥ Round 28; re-run if not |
| Recipient can't verify HMAC | Signing key wasn't shared out-of-band | Share the key via a separate channel from the ZIP |

---

## Next steps

- See [How to verify the audit chain](verify-audit-chain.md) for full-run verification + external-pin patterns.
- See [How to walk the lineage chain](walk-lineage.md) to trace what's INSIDE the pack before sending.
- For full-run bundles (regulator examination, not a single-case request), use `aml auditor-pack` instead.
