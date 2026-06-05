# How to detect mule rings from the identity-link graph

> **When you need this:** Your rules fire on individual customers, but a mule ring is a *community* — a cluster of accounts that share a phone / email / device / address / tax id / wallet and coordinate to move funds. `aml detect-mule-rings` (#498) runs deterministic union-find + density community detection over the customer identity-link graph and writes `mule_rings.json` of candidate rings for an investigator to confirm.
>
> **Prereqs:** A finished run directory under `.artifacts/` (so `<run-dir>/manifest.json` exists — it supplies the default `as_of` for a byte-deterministic re-run). `engine/mule_ring.py::detect_mule_rings` is the canonical builder; the edge list comes from the shared `resolved_entity_link` table. The command is **offline** — it never runs in the engine path, fires an alert, or touches the audit ledger.
>
> **Time:** ~5 min, then as long as the ring review takes — the review is the point.

Governance up front: this command **surfaces a community lens**, it does not escalate. A detected ring is an investigative starting point, NOT an auto-decision — nothing here mutates a spec, fires an alert, or is hashed into the audit ledger. The detection is pure stdlib (deterministic union-find + density, **no networkx / sklearn**), so it is a *triage surface*, not a model in the regulated run path. An investigator confirms each ring before any action — that confirmation is a hard stop.

---

## Steps

### 1 · Run the engine

You need a real run directory first — the command anchors its `as_of` to the run's own `manifest.json` so a re-run is deterministic.

```bash
aml run aml.yaml --seed 42
# → .artifacts/run-2026-06-05T10-15-30Z/  (with manifest.json)
```

### 2 · Detect mule rings over the identity graph

```bash
aml detect-mule-rings aml.yaml .artifacts/run-2026-06-05T10-15-30Z
```

The tool loads the spec's data, builds an in-memory DuckDB warehouse the same way the engine does, lets the shared entity-resolution layer derive `resolved_entity_link` (customers sharing a linking attribute), then clusters dense communities. It writes `mule_rings.json` into the run dir (override with `--output`).

Tune what counts as a ring:

```bash
aml detect-mule-rings aml.yaml .artifacts/run-2026-06-05T10-15-30Z \
  --min-ring-size 4 --min-density 0.6
```

- `--min-ring-size` (default 3) — smallest community that can count as a ring.
- `--min-density` (default 0.5) — minimum internal-edge density (`internal_edges / (size·(size-1)/2)`, 0–1) for a community to qualify as a ring.

Other knobs: `--data-source` / `--data-dir` (point at CSV/Parquet instead of the synthetic source), `--seed`, `--as-of`, `--output` / `-o`.

### 3 · Read `mule_rings.json`

The report is aggregate counts plus one entry per ring, sorted by size desc:

```json
{
  "rings": [
    {
      "ring_id": "MR-be9aa9c755",
      "members": ["C0031", "C0032", "C0033"],
      "size": 3,
      "internal_edges": 3,
      "density": 1.0,
      "label": "3-account ring · 3 links · density 1.00"
    }
  ],
  "n_entities": 12,
  "n_rings": 1
}
```

`size` is the member count; `internal_edges` / `density` tell you how tightly the community is wired (a clique has density 1.0); `members` are the customer ids to pull into the case.

### 4 · Investigate the largest / densest rings

The **Network Explorer** dashboard page (page 10) has a **"Detected mule rings"** section that reads this same `mule_rings.json` — it shows ring count, largest ring size, and a per-ring table (ring_id, size, internal_edges, density, members). Start with the largest and densest rings; each member already appears in Customer 360 and the rest of the dashboard, so you can drill straight into the accounts. Advisory: an investigator confirms the ring before action — it never auto-escalates.

---

## Verify it worked

Three checks:

1. **`mule_rings.json` exists** at `--output` (default `<run-dir>/mule_rings.json`) with `rings` sorted by `size` desc and `n_rings == len(rings)`. The file is a *proposal artifact* — it is NOT one of the manifest-hashed run artifacts and is NOT on the audit chain (offline output, not run evidence).
2. **Determinism** — re-running `aml detect-mule-rings` on the same spec + run dir + flags produces a byte-identical file. The clustering is pure stdlib union-find with min-id roots and content-hash ring ids, so there is nothing stochastic to drift.
3. **No spec mutation / no alerts** — the command writes only the report; it never edits the spec, fires an alert, or appends to `decisions.jsonl`.

---

## Common problems

| Symptom | Cause | Fix |
|---|---|---|
| `No identity-link edges` | The spec declares no linking attributes, or no customers share them | Add linking attributes to the `customer` contract / entity-resolution config; confirm the graph is non-empty |
| `No mule rings detected` | The communities are smaller / sparser than the thresholds | Lower `--min-ring-size` and/or `--min-density` |
| No file written | The run produced zero qualifying rings | Expected — the command writes nothing when `n_rings == 0`; loosen the thresholds if you want to inspect smaller communities |
| Section missing in the dashboard | You haven't run the CLI for this run dir | Run `aml detect-mule-rings <spec> <run-dir>`; the Network Explorer section reads `<run-dir>/mule_rings.json` |

---

## Next steps

- [How to discover candidate typologies from a run](discover-typologies.md) — the sibling offline lens over a run's *unexplained* anomalies; turns surfaced shapes into reviewable rule stubs.
- [How to walk the lineage chain for a case](walk-lineage.md) — once you confirm a ring and open cases, trace each member's alert back to source rows.
- **Dashboard:** the **Network Explorer** page (page 10) renders the same rings plus the temporal-correlation graph, so you can see the identity community and the flow community side by side.
