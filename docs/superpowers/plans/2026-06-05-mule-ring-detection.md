# Graph Mule-Ring Detection — Plan (#498)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Fresh implementer per task + two-stage review.

**Goal:** Detect mule rings / suspicious account communities in the customer identity-link graph and emit a governed, offline `mule_rings.json` via `aml detect-mule-rings`, surfaced on Network Explorer. Closes #498.

**Architecture:** Pure-stdlib, DETERMINISTIC builder `engine/mule_ring.py` — union-find connected components over the `resolved_entity_link` edges (customers sharing phone/email/device/address/tax_id/wallet — built by `engine/entity_resolution.resolve_entities`), then flag components that look like rings (size ≥ N, internal edge density). NO sklearn/networkx, NEVER in the deterministic engine run path — runs OFFLINE via CLI (the #496/#497 precedent). Advisory/explanatory only — a lens for investigators, never an auto-decision/auto-escalation.

**Tech Stack:** Python 3.10+, pydantic v2 (frozen, extra="forbid"), stdlib only in the builder; DuckDB in the CLI (offline tooling) to materialise edges; typer CLI.

**Locked decisions:** offline (not in the run path); deterministic union-find + density (no random/seed); advisory only; ring_id = stable hash of sorted members; off-by-default tooling (operator runs the CLI).

---

### Task 1: Engine — `detect_mule_rings` (pure, deterministic)

**Files:** Create `src/aml_framework/engine/mule_ring.py`; Test `tests/test_mule_ring.py`.

Pure: takes an edge list (list of (a,b) customer-id pairs) + optional per-customer weight, returns a frozen `MuleRingReport`. No I/O, no clock, no random. Union-find for components; within a component, count internal edges + size; a component is a "ring" when `size >= min_ring_size` AND `density >= min_density` (density = edges / max_possible_edges for the component, undirected). Deterministic: sort members, sort rings by (-size, ring_id).

- [ ] Write failing tests:
  - empty edges → no rings;
  - a triangle (3 mutually-linked customers) with min_ring_size=3 → one ring, size 3, density 1.0, members sorted;
  - two separate components → handled independently; only those meeting size+density are rings;
  - a long thin chain (low density) below `min_density` → not a ring;
  - deterministic `model_dump()` across two calls and across shuffled edge input order;
  - ring_id stable = hash of sorted members (same members → same id).
- [ ] Implement: models `MuleRing` (ring_id:str, members:list[str], size:int, internal_edges:int, density:float, label:str) and `MuleRingReport` (rings:list[MuleRing], n_entities:int, n_rings:int). `detect_mule_rings(edges, *, min_ring_size=3, min_density=0.5) -> MuleRingReport`. Union-find (deterministic, sorted iteration); dedupe undirected edges; density = internal_edges / (size*(size-1)/2); ring_id = `"MR-" + sha256(",".join(sorted(members)))[:10]`; sort rings (-size, ring_id); members sorted. Mirror the pure/deterministic/_Base style of `engine/equivalence_clustering.py`.
- [ ] Tests green, lint, commit `feat(engine): deterministic mule-ring community builder (#498)`.

---

### Task 2: CLI — `aml detect-mule-rings`

**Files:** Modify `src/aml_framework/cli.py`; Test `tests/test_cli_detect_mule_rings.py`.

Offline, mirrors `aml discover-typologies` / `aml equivalence` (takes a run_dir + spec; loads data; builds edges; writes artifact).

- [ ] Add `detect_mule_rings_cmd(spec_path, run_dir, output=<run_dir>/mule_rings.json, data_source="synthetic", data_dir, seed=42, min_ring_size=3, min_density=0.5, as_of)`:
  - Read `as_of` from `<run_dir>/manifest.json` when `--as-of` not given (deterministic, mirror `discover-typologies`).
  - Load the spec + resolve its data into a DuckDB connection (reuse the data-load idiom other commands use — `resolve_source`/the connection the engine builds). Call `engine.entity_resolution.resolve_entities(con, spec)` to materialise `resolved_entity_link`. Query it → a deduped edge list of (customer_id_a, customer_id_b) pairs (a<b). If no linking columns exist (no `resolved_entity_link` / empty), emit a clear "no identity-link edges — nothing to cluster" message and exit 0 without writing.
  - `report = detect_mule_rings(edges, min_ring_size=..., min_density=...)`. Atomic-write `mule_rings.json` (tempfile + os.replace; no-write on zero rings; mirror discover-typologies). Print a rich summary + a GOVERNANCE note: "Advisory — detected communities are an investigative lens, not an auto-decision; confirm before action."
- [ ] CliRunner tests: a run/spec with shared-attribute customers → command runs, emits valid JSON (≥0 rings); zero-ring case → no file + exit 0 + message; manifest-`as_of` byte-identical to explicit `--as-of`.
- [ ] Tests green, lint, commit `feat(cli): aml detect-mule-rings — offline governed community detection (#498)`.

---

### Task 3: Dashboard + docs

**Files:** Modify `pages/10_Network_Explorer.py`; docs.

- [ ] Network Explorer: add a "Detected mule rings" section — when `<run_dir>/mule_rings.json` exists, render a metrics row (n_rings, largest ring size) + a table (ring_id, size, density, members) and a one-line advisory caption. Graceful when absent: a one-line `st.info` pointing to `aml detect-mule-rings`. Aggregate-only `section_explainer` (n_rings, n_entities — no PII beyond the customer_ids already shown across the dashboard). Page-level explainer `collapsed=True`. No module-level streamlit in importable libs.
- [ ] Docs: new `docs/how-to/detect-mule-rings.md` (indexed) — run → `aml detect-mule-rings <spec> <run-dir>` → read `mule_rings.json` / Network Explorer → investigate (advisory). CLAUDE.md Key Design Decision bullet (offline, deterministic, advisory, union-find over identity links). `docs/dashboard-tour.md` Network Explorer sentence. `docs/progress.md` #498 entry. README CLI line `aml detect-mule-rings`.
- [ ] Docs-coverage + convention tests green. Commit `docs(mule-ring): how-to + CLAUDE/tour/progress/readme + Network Explorer surface (#498)`.

---

### Task 4: Full CI gate

- [ ] `make ci-lint ci-unit ci-coverage` green; `make ci-e2e` green (Network Explorer renders). Final whole-branch review → finishing-a-development-branch → PR (closes #498) → Codex → CI → merge → deploy reflex.

## Self-Review
- Spec: builder ✓ (T1), CLI artifact ✓ (T2), dashboard + docs ✓ (T3), gate ✓ (T4).
- Determinism: pure union-find + density, sorted, hashed ring_id; CLI reads deterministic `resolved_entity_link`; offline (not in the run path); no sklearn/networkx.
- Governance: advisory/lens only, never auto-escalates; off-by-default tooling.
- Dependency safety: builder + tests stdlib-only (runs in `.[dev]`); DuckDB only in the offline CLI.
- Type consistency: `detect_mule_rings(...)` + `MuleRing`/`MuleRingReport` identical across engine, CLI, dashboard, tests.
