# How to walk the lineage chain for a case

> **When you need this:** An examiner asks "show me why this case fired — every source row, every transform, every rule version, every decision event."
>
> **Prereqs:** A finished run directory with a `case_id` in scope.
>
> **Time:** ~30 sec per case (CLI). ~1 min in the dashboard.

The 7-link lineage chain: **case → rule_id → rule_version → spec_content_hash → input_file_hashes → run timestamp → byte-stable replay**.

---

## Steps

> **TODO** — placeholder. The three access paths:
>
> 1. **CLI**: `aml lineage <run_dir> <case_id>` — prints the chain as a table
> 2. **Dashboard**: Lineage Explorer page (pages/9_*.py) — paste a case_id, click "Walk"
> 3. **API**: `GET /api/v1/runs/{run_id}/cases/{case_id}/lineage` — JSON response, suitable for embedding in your case-management tool

---

## Verify it worked

> **TODO** — every link in the chain resolves to a concrete artifact. The `engine/audit.py::walk_lineage` helper (PR-DATA-4) is the canonical implementation.

---

## Common problems

> **TODO** — pre-PR-DATA-4 runs lack `rule_version` stamping. Modern runs always have it; old archives may not.

---

## Next steps

- See [How to verify the audit chain](verify-audit-chain.md) to prove the lineage data hasn't been tampered with.
- See [How to export a case pack](export-case-pack.md) to hand the lineage chain to a regulator as a self-contained ZIP.
