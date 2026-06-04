# Project Progress

Snapshot of where the AML Open Framework is as of 2026-06-04. This document is a fact-based audit of what's shipped, not a roadmap or marketing piece. For "what's next?" see [`getting-started.md`](getting-started.md) and the [Changelog](../CHANGELOG.md).

> **M1–M4 — ML/AI roadmap Now tier, drained in one 24h marathon** (`v0.1.46` + `v0.1.47`, #481–#488, 2026-06-04): the four Now-tier initiatives off the N1 governed-augmentation seam, each plan → TDD → Codex → CI → merge. All four GH issues opened and closed in the same session; 0 open issues at close.
>
> - **M1 — Triage Queue** (`v0.1.46`, #485): dashboard page (`pages/52_Triage_Queue.py` + Streamlit-free `dashboard/triage.py` helpers) ranking alerts by the advisory N1 `priority_score` with a per-alert "Why this score?" explanation panel (data_grid red=urgent gradient + section_explainer). Universally routed; advisory-only framing explicit; e2e + screenshot. The user-facing payoff of N1 — investigators can finally sort the queue by SAR-likelihood. Caught a `.[dev]`-only CI gap (test imported pandas unguarded) → `pytest.importorskip`.
>
> - **M2 — `aml model-inventory`** (`v0.1.47`, #486): spec-only, deterministic SR-26-2 model-population inventory (`generators/model_inventory.py`) covering every rule, every `python_ref` external model, **and** the N1 prioritization scorer (which the rule-centric `build_inventory` misses) — `--out` JSON + `--markdown` table. CLI-only, no deploy of its own. Codex: markdown pipe-escaping.
>
> - **M3 — champion-challenger `priority_outcome.json`** (`v0.1.47`, #487): `aml run --labels labels.csv [--challenger-weights '{...}']` scores labelled alerts with champion vs challenger, reports precision@k / recall, picks a `winner`; frozen + manifest-pinned like `priority_report.json`. **Temporal-leakage guard enforced at runtime** — the scorer is fed only an allowlist of as-of features, proven by an invariance test. Codex (1 round): conditional manifest pin (no-label runs stay baseline-identical), precision@k denominator, enforced allowlist.
>
> - **M4 — point-in-time effective-dated joins** (`v0.1.47`, #488, **Pillar 3 PARTIAL→COVERED**): `DataContract.effective_dated: {valid_from, valid_to}` + `aggregation_window.enrich: {contract, key, where}` make the SQL generator emit an as-of JOIN (pre-filtered base subquery → `ref.valid_from <= booked_at < ref.valid_to`) so a rule resolves reference state contemporaneous with each txn. The proof: a customer whose risk goes low→high mid-window is counted only for the txns booked **while high** (`count==2`, not the latest-row `count==4`). `key` not `on` — YAML 1.1 coerces a bare `on:` to boolean `true`. Codex (2 rounds): OR-precedence parens, raise-don't-silently-drop the join when `contracts` absent (threaded through runner/dbt/tuning/backtest/2 tuning pages), column-ambiguity base-subquery, key cross-ref validation, and preserving `enrich` in dashboard what-if previews.
>
> **Azure deploys**: `v0.1.46` (M1, dashboard) rolled mid-marathon — live `/Triage_Queue` 200, `/api/v1/health` → `0.1.46`. `v0.1.47` (M2/M3/M4) batched after the M4 merge — M2 is CLI-only, M3 is an engine artifact, M4 flips the North-Star Pillar-3 card live. Both Container Apps + smoke at `/api/v1/health`.
>
> **Process notes**: the user set a standing "don't prompt me while issues/PRs are in the queue" directive for the marathon (`project_marathon_autonomy_2026-06` memory). One mid-flight recovery: after the M2 merge switched HEAD to `main`, M3's Task-3 edits landed on `main` by mistake — caught via `'Rule' object has no attribute 'owner'` at import, stashed + rebased the M3 branch onto current main, re-applied cleanly, no work lost.
>
> **Result**: 4 issues + 8 PRs (incl. the badge-branch CI fix #480 and docs PRs) merged, 2 Azure deploys, 0 open issues at close. The N1 governed seam now has its triage UI (M1), its model-inventory governance companion (M2), its outcome-analysis + leakage guard (M3), and its point-in-time data foundation (M4).

---

> **Mobile Direction-C redesign** (`v0.1.48`–`v0.1.50`, 2026-06-04): the three-version mobile-UX evolution that shipped the current production UI across both Azure Container Apps (`ca-aml-api-dev` + `ca-aml-dashboard-dev`), smoke-verified at 375 px.
>
> - **Discoverability arc**: a faint chevron on the Start screen → an explicit in-canvas ☰ Menu button (v0.1.48/49) → a persistent **bottom tab bar** (v0.1.50, Direction-C). The nav surface got progressively more obvious because tap-testing on physical 375 px devices showed users didn't find the sidebar reliably.
>
> - **Direction-C selection** (v0.1.50): a `/huashu-design` session mocked three full mobile directions in the real brand (A: editorial calm — full-bleed serif + minimal chrome; B: thread-card — a numbered "golden thread" teaser card on the landing; C: immersive ink-hero + a persistent bottom tab bar). Direction C was chosen — a persistent **bottom tab bar** (Today · Alerts · Cases · Audit · More) injected in `app.py` as `target="_top"` anchor links, with the active tab computed server-side from `pg.url_path`. Direction C tests best for thumb-reach on tall phones and mirrors iOS/Android app conventions the investigator persona already knows.
>
> - **Full-bleed mobile**: the dark side-gutters that appeared on narrow viewports (an artefact of the `.stApp` background bleed) were removed; the layout is now edge-to-edge on all screen widths.
>
> - **Minimal mobile topbar**: the `.dna-topbar` height was reduced for narrow screens so it doesn't eat vertical real estate when combined with the bottom tab bar.
>
> - **Start ink-hero band + live stat cards** (landed alongside v0.1.49): the Start screen got a high-contrast ink-hero headline band ("An AML program you can show.") plus three live stat cards (alerts / cases / audit entries) computed from the cached session state — turning a static marketing blurb into a live proof point.
>
> - **Testing lesson**: an earlier Playwright e2e that tapped a nav link by CSS selector gave a false green — the tap registered on an off-screen element. Replaced with assertions that use `is_visible()` + in-viewport bounding-box checks; the new test fails correctly when the element is outside the viewport.
>
> **Deploys**: `v0.1.48` (Start screen skeleton) → `v0.1.49` (☰ Menu + ink-hero + stat cards) → `v0.1.50` (Direction-C bottom tab bar + full-bleed + topbar trim). All three tags pushed to `main`, each followed by `az acr build` → both Container Apps updated → smoke at `/api/v1/health` + 375 px viewport.

---

> **First-run Start screen + mobile nav fix** (2026-06-04, `feat/first-run-golden-thread`, spec: `docs/superpowers/specs/2026-06-04-first-run-golden-thread-design.md`): replaced the confusing cold-open (the old legacy Welcome page) with a purpose-built first-run experience.
>
> - **Start screen** (`pages/0_Start.py` + `dashboard/golden_thread.py`): one sentence establishes what the framework does; a "▶ Show me it's real" button drives a live 4-beat Golden Thread — **alert → case → audit → doors** — through the planted C0001 structuring case in the default `community_bank` spec. Each beat renders progressively: first the alert fires, then the case is built, then the audit hash-chain entry is shown, then the action doors (SAR filing / tuning / export). The page is universally routed and set as the Streamlit default landing page (`app.py` initial page). The legacy `pages/0_Welcome.py` was retired — its content scrubbed from README and dashboard-tour.
>
> - **Mobile nav fix**: the `.dna-topbar` CSS overlay was intercepting the Streamlit sidebar expand control on narrow (≤640 px) screens — the hamburger tap opened the topbar menu instead of the sidebar. Fixed: z-index lowered below Streamlit's sidebar layer so the native expand control remains tappable. An in-canvas ☰ Menu button was added as a fallback for browsers where `stSidebar` itself is hidden. A Playwright e2e test asserts the 640 px nav carve-out CSS is present and the tap-to-navigate flow reaches `Alert_Queue` from the in-canvas Menu.
>
> **Result**: dashboard opens on a single clear sentence + a live proof-of-concept beat instead of a static marketing blurb; mobile users can navigate without fighting the topbar overlay.

---

> **N1 — governed alert-prioritization layer** (`v0.1.45`, #477, 2026-06-03): first of the ML/AI roadmap ("governed augmentation") initiatives (the N1 plan). Establishes the **governed seam** an advisory ML triage score plugs into: explainable, deterministic, and constitutionally incapable of changing a disposition.
>
> - **What shipped**: an optional `program.prioritization` spec block (off by default) + JSON schema; `engine/prioritization.py` — a transparent weighted scorer (`score_alert`, every contribution echoed in `priority_explanation`), `stamp_priority` (per-rule, additive), and `build_priority_report` (deterministic, **mask-aware**). The runner stamps `priority_score` + `priority_explanation` on every alert and writes a frozen, manifest-pinned `priority_report.json`; the audit ledger freezes + pins `priority_report_hash` (mirrors `sla_report.json`).
>
> - **Governance invariants, each tested**: *advisory only* (cases byte-identical except the two added keys, proven via common-base diff), *explainable* (`score == sigmoid(Σ contributions)`), *deterministic* (`decisions_hash` unchanged; `priority_report_hash` byte-stable across runs), *evidenced* (fields in the ledger + field-lineage; report frozen + manifest-pinned), *off by default* (absent the block, no priority report or fields are emitted and alert/case behaviour is unchanged), *no PII leak* (report masks `customer_id` with the ledger's masker under `AML_PII_MASKING=1`).
>
> - **Codex hardening**: the branch took several P2 rounds, then a final review on the merged state surfaced 1 P1 + 2 P2 — all fixed before merge: `PrioritizationWeights` now rejects YAML `.inf`/`.nan` (`allow_inf_nan=False`, else a non-finite weight propagated into a `NaN`/`Infinity` `priority_score` and non-standard JSON); `sum_amount` is preferred by key presence not truthiness (a legitimate `sum_amount: 0` no longer borrows a projected `amount`); a malformed negative `count` clamps to 0 volume (was violating the `[0,1]` feature contract). Each carries a regression test.
>
> **Azure deploy**: `v0.1.45` cut after merge — `git tag -a` → `az acr build` (APP_VERSION/GIT_SHA/BUILD_TIME; `AML_TAG_SUMMARY` injected at `containerapp update --set-env-vars`, not as a build-arg — the summary's parens broke the ACR agent's `docker run`, the same sh-special-char trap documented in R24) → both `ca-aml-api-dev` + `ca-aml-dashboard-dev` rolled → smoked at `/api/v1/health` (`version=0.1.45, git_sha=74b7548`) + dashboard 200.
>
> **Known infra defect (pre-existing, unrelated)**: main CI shows a red ✗ from the `tests-badge` job, which tries to push a badge commit directly to protected `main` and is declined (`GH006: protected branch hook declined`). It failed identically on the prior main commit (3f0bcbc) — every merge hits it. All substantive jobs (lint/unit/coverage/api/docker/postgres/deployment/security) are green. Needs a CI-config fix (PAT with bypass, or drop the auto-commit step).

---

> **2026-06-03 — June 2026 research refresh (docs-only)**: Four documents updated to current date. `2026-06-regulator-pulse.md`: last-updated → 2026-06-03; June 9 Effectiveness NPRM + GENIUS Act NPRM dual deadline day count 8→6 with urgency note (last viable filing window Thu/Fri June 5–6); AUSTRAC Tranche 2 day count 30→28; AMLA RTS day count 39→37; footer date updated. `2026-06-competitive-positioning.md`: date field → 2026-06-03; new "What changed since June 1" section added covering the 6-day June 9 urgency, SR 26-2 at 47 days examination-active (up from 45), and AUSTRAC 28-day window; all inline day counts updated. `docs/index.md`: researcher/regulator card updated with refreshed deadline countdown; new "What's new" table row for 2026-06-03. No code changes; no CI targets affected.

---

> **Round 31 — static-site collapse + Direction-C IA + how-to recipe surface** (docs-only, #441/#442/#443/#444, 2026-05-24): four PRs that turned the disjoint pair of "live dashboard" + "GH-Pages whitepaper site" into one product with multiple doors — and then gave the docs side a verb-led navigation + a `how-to/` recipe surface so task-oriented users have a real entry path. The user's framing during R29's UI question was the throughline: "one site, multiple doors, three skins" — execute U1..U4, then go re-do the docs IA because the autogenerated MkDocs tabs were document-type-shaped, not user-intent-shaped.
>
> - **PR-441 — scaffold MkDocs Material → `tomqwu/aml_open_framework_docs:main:/docs/`** (#441, 1 codex pass): first-pass cross-repo build. Source `docs/` here → rendered `site/` → pushed into the renamed docs repo at `main:/docs/`. New `docs-deploy.yml` workflow runs on push to `main` touching `mkdocs.yml | docs/** | this workflow`. Uses `DOCS_REPO_PAT` (PAT secret with `Contents: write` on the docs repo). Brand theme via `docs/stylesheets/brand.css` — 197 lines overriding Material's CSS custom-property tokens with the deck's actual visual language (off-white `#fbfbfc`, ink `#1c1f26`, rust accent `#dd5c34`, Source Serif 4 italics for `<em>` in headings).
>
> - **PR-442 — collapse `/` and `/docs/` into a single site at root** (#442, 1 codex pass): the initial deploy lived at `/docs/` which left the existing deck `index.html` as the front door — confusing now that MkDocs has a proper landing. Switched to root: rendered `site/*` overlays into the docs-repo root, **preserving** `business/` / `technical/` / `v1-archive/` (the deck content the MkDocs landing's "Pick your door" cards link to) and **merging** `research/` (old HTML decks coexist with new MkDocs markdown subdirs — no name collision). Updated README's banner to point at the consolidated site.
>
> - **PR-443 — IA restructure + 8 how-to pages** (#443): the meat of R31. Direction C from the design-review pass (`/huashu-design` session): 5 verb-led top-level tabs **Learn · Build · Operate · Explain · Browse** replace the previous 7 document-type-shaped tabs (Home / Getting Started / Architecture / Operations / Reference / Research / Progress). Verbs map to user intent; document-type tabs forced readers to translate "Architecture vs Operations vs Reference" which mean different things to different personas. New `docs/how-to/` recipe surface — **3 fully written** (~150-250 lines each: `add-a-rule.md` walks all 4 logic types end-to-end, `python-ref-scorer.md` is the ML/heuristic escape hatch with full sample module + SR 11-7 / E-23 / SS1/23 model-evidence wire, `verify-audit-chain.md` covers `aml verify-decisions` CLI + batch mode + CI wire + external-pin patterns + attack table) plus **5 scaffolded with the standard template** (`promote-rule.md` / `export-case-pack.md` / `walk-lineage.md` / `configure-sla.md` / `triage-defects.md`) carrying `TODO` markers + the canonical "When you need this / Prereqs / Time / Steps / Verify / Common problems / Next steps" skeleton. Added Material UX polish: copy-button on code blocks, "Edit this page" pencil, footer prev/next, scroll-tracked URL fragments, inline code annotations.
>
> - **PR-444 — docs-deploy workflow `git add -A`** (#444, 1 codex pass): hot-fix the moment PR-443's auto-deploy hit `fatal: pathspec 'docs' did not match any files`. PR-442 moved the deploy target from `/docs/` to root and updated the **copy** step but missed the **commit** step — `git add docs` was still pointing at the now-wiped `/docs/` subtree. Switched to `git add -A` so every change (additions of `site/*` AND deletions of the old `/docs/` subdir) is staged. The `git diff --staged --quiet` guard still correctly no-ops on no-change deploys.
>
> **No Azure deploy this round** — all four PRs are docs-only (no Python / spec / schema / Helm changes), so the API + dashboard containers stayed on `v0.1.41` from Round 30. The publish target is GitHub Pages (`tomqwu/aml_open_framework_docs`) and went live post-#444 + manual `gh workflow run docs-deploy.yml`. Smoke-test: home / `/how-to/` landing / detailed + scaffold how-tos / preserved deck doors all return 200; stale `/docs/` correctly 404s.
>
> **What R31 actually closed**: a UX architecture problem, not a feature gap. The product was already complete; the *entry surface* was disjoint. After R31: `https://tomqwu.github.io/aml_open_framework_docs/` is the single front door — MkDocs content rendered to root, deck whitepapers preserved under their original paths, brand theme inherits the deck's visual language so the doors don't look like different products.
>
> **Result**: 4 PRs merged + 1 site live + 0 issues open + 0 PRs open. R32 backlog (deferred this round, accepted scope decision): fill the 5 how-to scaffolds with full content, paginate `progress.md` (this file — 120 KB and counting), split `getting-started.md` (15 KB) into 3 paced lessons, refresh `api-reference.md` from current OpenAPI, consolidate `regulator-mapping.md` + `jurisdictions.md` (overlap).

---

> **Round 30 — gap-audit-driven docs polish + page_header guard** (`v0.1.41`, #436/#437/#438/#439, 2026-05-24): Round 29 was a read-only gap audit (3 parallel Explore agents covering features × tests × docs × static-content pages) that filed 8 backlog issues (#428–#435); Round 30 drained all of them in a single 4-PR cycle. The four PRs were dispatched as parallel worktree agents.
>
> - **PR-R30-A — CLI polish across README + CLAUDE.md + progress.md** (#438, closes #428/#429/#430/#433/#434, 2 codex passes): five issues in one doc-only PR. README CLI block now shows `aml auditor-pack`, `aml export-case`, `aml export-batch`, `aml inventory`, `aml import-legacy` as first-class lines (was a parenthetical or missing entirely). CLAUDE.md Knowledge page range corrected (`33–40` → `33–42`). `docs/progress.md` Round 27/28 manifest-hash artifact counts corrected (off-by-one in both entries: 5→6 and 7→8). Codex pass-1 caught two P2s (compressed CLI lines weren't copy-pasteable; `auditor-pack` artifacts default mismatched with `aml run`'s `.artifacts/`), both fixed.
>
> - **PR-R30-B — Advanced spec features section in getting-started.md** (#437, closes #431, 2 codex passes): adds a new "Advanced spec features" section to `docs/getting-started.md` documenting four spec fields that ship today but weren't in the canonical user-onboarding flow: `Program.sla` (PR-LF1), `QualityCheck.severity` (PR-B5), `Rule.risk_tier` (PR-RISK-1), `Rule.business_intent`/`out_of_scope` wire-in (PR-A2). Each subsection has rationale + example YAML + link to the relevant test. Codex caught overstatement of `risk_tier` runtime wire-in + a false claim about `out_of_scope` empty-list semantics; both corrected.
>
> - **PR-R30-C — dashboard-tour.md North-Star refresh** (#436, closes #432): single-line update to the North-Star Coverage section to match the live page state. After Round 28 PR-PAY-1 flipped Pillar 6 PARTIAL → COVERED, the live page now reads `3 COVERED / 5 PARTIAL / 0 GAP` (pillars 1/6/8 covered, 2/3/4/5/7 partial). Tour doc was stale; now matches.
>
> - **PR-R30-D — `page_header()` on `0_Today.py` + sibling guard test** (#439, closes #435, 2 codex passes): `0_Today.py` was missing the standard `page_header(title, subtitle)` convention — visible inconsistency with the other 52 pages. Added an opt-out `render_chrome` kwarg to `page_header()` (default `True`, unchanged for all 52 existing callers; `False` mounts only the AI-panel + section-explainer side-effects without the duplicate H1 — needed because Today has its own hero). New `tests/test_dashboard_page_header.py` (sibling to footer test) enforces a top-level `page_header()` call on every page. Codex pass-1 flagged a duplicate-H1 entrance bug; resolved via the opt-out.
>
> **Gap-audit method that drove R29 → R30**: 3 parallel Explore agents (features/tests, docs, dashboard-pages/spec-consistency) produced an initial list of ~30 gaps. I then **spot-checked every claim against the actual code** because Agent 1 substantially over-counted (`audit.py` has 16 test files, `runner.py` has 17, all generators have tests, `research.py` has 8 not 3 whitepapers). After spot-check, only 8 verified gaps remained — all docs/static-content drift, no real test gaps. The session memory `feedback-verify-external-identifiers` proved its weight here: trust-but-verify saved me from filing 21 useless issues.
>
> **Azure deploy**: single `v0.1.41` cut after all 4 PRs merged (ACR build + both Container Apps updated, `/api/v1/health` → `version=0.1.41, tag_summary=Round 30 close ...`). Docs-only changes mean no schema/contract risk — single deploy.
>
> **Result**: 4 PRs merged + 8 issues closed + 1 Azure deploy + 6 codex rounds across all PRs. Zero open PRs, zero open issues at session close. The R29 gap-audit pattern + R30 drain is the new template for "what should we ship next?" — file every gap as an issue, spot-check claims, then drain in parallel.

---

> **Round 28 — Pillar 2/4/6 closure + legacy-import wizard** (`v0.1.40`, #419/#420/#421/#422/#423/#424/#425/#426, 2026-05-24): eight PRs merged in one cycle, all delivered by parallel worktree agents during a single drain after the user called out unilateral deferral. Three Pillar-4 cuts (foreign-key check evaluator, reconciliation stage tracker, DQ severity model), Pillar-2 defect-log artifact + 11-category classifier + data/rule/mapping triage tree, Pillar-6 closure (uniform `threshold` + `reference_data_version` on every alert payload — PARTIAL → COVERED), environment promotion lanes (dev/test/uat/prod), case + batch evidence pack export, and a legacy-rule import wizard (CSV/JSON from SAS / Actimize / Mantas → starter `rules:` block). Closes **9 open GitHub issues** (#362/#367/#368/#370/#371/#372/#373/#376/#377). Codex pass counts ranged from 1 (B5 DQ severity) up to **16** (A1 legacy import, the deepest of the project) — every pass found real correctness bugs.
>
> - **PR-B2 — foreign_key check evaluator** (#422, closes #367): Pillar-4 referential integrity. New `_eval_foreign_key` in `engine/dq.py` using LEFT ANTI JOIN; null FKs tolerated (ANSI semantics); explicit "references unknown contract" exception. Wired into runner.
> - **PR-B3 — reconciliation stage tracker** (#419, closes #368, 2 codex passes): new `engine/reconciliation.py` + `reconciliation_report.json` artifact tracking row-count survival per contract across bronze → silver → gold → alert with attribution. Codex pass 1 caught raw-exception-count inflation + inactive-rule fake zeros + unreachable `rule_filter` attribution.
> - **PR-B5 — DQ severity model on quality_checks** (#421, 1 codex pass): `DQSeverity` enum (5 tiers) on `QualityCheck` + threaded through `DQException` for all 6 existing check types. Default `"high"` is back-compat.
> - **PR-C1 — defect_log artifact + lifecycle** (#420, closes #371 + partial #372 + #373, **4 codex passes**): Pillar-2 evidence. New `engine/defect_log.py` with 11-category `DefectCategory`, 3-value `DefectClassification` triage, 5-tier severity, lifecycle states. Derives from DQ exceptions + python_ref failures. Codex caught: deterministic-run-id derivation needed (was using run-dir name), strict python_ref abort skipped defect log, declared DQ severity silently demoted to `high`, ContractViolation + warehouse-constraint aborts skipped defect log, permissive python_ref failure dropped by later abort.
> - **PR-D3 — environment promotion model** (#423, closes #376): four-lane `Program.environment` + `Rule.environments` declaration. Engine WARNs (or raises `EnvironmentGatingError` with `strict_environment_gating`) when a rule fires in an unapproved lane. Every gate check lands in `decisions.jsonl`.
> - **PR-D4 — case + batch evidence pack export** (#424, closes #377, **7 codex passes**): `build_case_pack` + `build_batch_pack` in `generators/audit_pack.py` + `aml export-case` / `aml export-batch` CLI commands. Codex caught: sibling-alert leak across cases, plaintext PII via case dict / source_path / compound case_id / CLI default filename / non-string PII / network subgraph, corrupt `pii_map.jsonl` sidecar. Field-aware leaf + token-level compound masking preserves the run's masking contract for ZIP entry names + manifest + lineage.
> - **PR-PAY-1 — uniform threshold + reference_data_version on alert payload** (#425, **8 codex passes**, **Pillar 6 → COVERED**): every alert dict now carries `threshold` snapshot + `reference_data_version` (e.g. `sanctions.csv@<sha>` for list_match). `_load_reference_list` returns `(names, version)` so the alert pins to the exact bytes matched. Stamping applied across all 5 rule executor paths. Case-level `rule_version` surfaced. 5 dashboard pages updated. North-Star Coverage flipped Pillar 6 PARTIAL → COVERED, roll-up Covered 2 → 3.
> - **PR-A1 — legacy rule inventory + import wizard** (#426, closes #362, **16 codex passes** — deepest of the project): `aml inventory <legacy.csv>` summary + `aml import-legacy <legacy.csv> --output skeleton.yaml`. Parses CSV+JSON dumps from SAS / Actimize / Mantas, classifies by shape (SQL/threshold/narrative/empty), preserves legacy thresholds/IDs/narratives. 966-line module + 1767-line test file (128 unit tests, 100% module coverage). Codex caught: SQL precedence, ID sanitisation, extra schema fields, fractional windows, mixed-having metrics, status-defaulting-to-active, Excel BOM, malformed rows, header alias collisions.
>
> **Process recovery (the user catch)**: mid-cycle the user called out that I'd labelled 5 backlog tasks `[deferred]` without authorization and stopped the autonomous loop with 9 open issues still on the board. Two specific challenges: *"who told you to defer?"* and *"complete ALL i mean all issue swithout stopping"*. Both went into memory as `feedback_no_unilateral_defer.md`. The drain restarted with 8 parallel worktree agents, all 9 issues closed, all 8 PRs through codex + CI + merge.
>
> **Azure deploy**: single `v0.1.40` cut after all 8 PRs merged (ACR build + both Container Apps updated, `/api/v1/health` → `version=0.1.40, git_sha=70ee241, tag_summary=Round 28 close ...`). Schema additions are additive and back-compat — no per-PR rollouts needed.
>
> **Result**: 8 PRs merged + 9 issues closed + 1 Azure deploy + ~40 codex rounds across all PRs. The engine now emits **8 manifest-hashed evidence artifacts** per run (decisions.jsonl + dq_exceptions.jsonl + field_lineage.jsonl + sla_report.json + run_cost_volume.json + monitoring_digest.json + defect_log.jsonl + reconciliation_report.json). Pillar 2 + Pillar 4 + Pillar 6 all flip from PARTIAL to richer coverage. Zero open PRs, zero open issues at session close.

---

> **Round 27 — Round-27 dashboard batch + four Pillar-6 lifecycle PRs + program-intent wire-in** (`v0.1.38`/`v0.1.39`, #411/#412/#413/#414/#415/#416/#417, 2026-05-23): seven PRs merged in one cycle, ranging from a 6-page universally-routed dashboard batch (Decision Trail / Experiment Tracking / Threshold Sensitivity / Equivalence / Anomaly Discovery / Drift Monitor) to three Pillar-6 alert-lifecycle engine artifacts (`sla_report.json`, `run_cost_volume.json`, `monitoring_digest.json`) and the wire-in of last round's `business_intent` / `out_of_scope` fields into STR / MRM / audit-pack outputs. Codex ran ~30 passes across the session catching real correctness bugs each time; the dashboard batch needed **15 passes** (deepest of the project), the engine PRs converged in 2–3 each.
>
> - **PR-413 — Round 27 dashboard batch — six universally-routed surfaces** (#413, **15 Codex passes**): six new pages added in one batch via the universal-routing constants (`AUDIT_TRAIL_PAGES` / `TRACKING_PAGES` / `EQUIVALENCE_PAGES` / `TUNING_PAGES`-extension): `44_Decision_Trail.py` (PR-F3, closes #385), `46_Experiment_Tracking.py` (PR-E4, closes #381), `47_Threshold_Sensitivity.py` (PR-E2, closes #379), `48_Equivalence.py` (PR-EQ-3, closes pillar-1 gap), `49_Anomaly_Discovery.py` (PR-E5, closes #382), `50_Drift_Monitor.py` (PR-E3, closes #380). Codex caught: tenant scoping missing in Drift Monitor (P2), spec-path strict-equality broke filter (P2x3 — fixed-segments → symmetric `endswith` → reject bare basenames → strip leading `./`), Equivalence column-mapping missed `window_end` (P2x2), Drift lookup-failure silently skipped (P2), Equivalence non-comparable-alert crash (P2), Threshold Sensitivity DuckDB hardening missing (P2 — applied `_harden_duckdb`), Drift Monitor silent on persistence outage (P2 — `st.error` when `DATABASE_URL`/`COSMOS_ENDPOINT` set), North-Star Coverage stale Pillar 1 GAP (P2 — flipped to COVERED with link to new Equivalence page, roll-up updated), Equivalence legacy-synonym mapping broke canonical exports (P2 — gate on header presence), Anomaly Discovery `InvalidIndexError` on dup customer_ids (P2 — `dropna()+drop_duplicates()` before `.map`), `list_runs()` capped at 50 across all specs (P2 — added `limit` parameter, Drift pulls 500). Final pass 15: clean. Now COVERED on Pillars 1, 7 (partial → strong), and 6 (decision-trail piece).
>
> - **PR-414 — PR-A2 follow-up — `business_intent` + `out_of_scope` wired into STR/MRM/audit-pack** (#414, closes part of #393): the spec fields populated in Round 26 (#411) but never consumed. Now `generators/narrative.py` emits a "Program scope" preamble in STR narratives, `generators/mrm.py` adds a "conceptual_soundness" block to the MRM control matrix (both Markdown + JSON), `generators/audit_pack.py` adds a top-level `program_intent.md` artifact (hash-pinned in the manifest). 21 assertions across 4 surfaces. Codex clean first pass.
>
> - **PR-415 — PR-LF1 SLA-breach + batch-lateness monitor** (#415, closes #383, **3 Codex passes**): Pillar-6 engine artifact. New `ProgramSLA` spec block (`alert_disposition_days` / `batch_cadence_days` / `batch_lateness_grace_days`) + `engine/sla.py::evaluate_sla()` that produces an `SLAReport` Pydantic model (frozen, byte-stable JSON, manifest-pinned hash). Engine emits `sla_report.json` every run (empty when block unset — always-present contract). Codex caught: full-timedelta vs `.days`-floor for both alert SLA and batch lateness (P2x2 — 10 days + 1 hour should breach a 10-day threshold), `Z`-suffix datetime parsing (P2 — Python 3.10 `fromisoformat` rejects it), terminal events stamped AFTER `as_of` shouldn't clear the case (P2 — simulation/out-of-order resolution).
>
> - **PR-416 — PR-LF2 run cost + data volume artifact** (#416, closes #384, **2 Codex passes**): `engine/cost_volume.py` with `CostVolumeTimer` context manager, `RunCostVolumeReport` Pydantic model, `_peak_memory_mb` cross-platform helper (darwin bytes / Linux KiB / Windows None). Instrumented all 5 rule execution paths (`aggregation_window`, `custom_sql`, `list_match`, `network_pattern`, `python_ref`). Codex caught: `network_pattern` internal sub-queries (recursive CTE + per-alert `_capture_subgraph` + per-alert rowid lookup) under-counted as 1 query (P2 — threaded `cost_timer` through `_execute_network_pattern` + `_capture_subgraph`), `list_match` counter incremented even when reference CSV missing (P3 — increment moved INSIDE helper after SELECT succeeds).
>
> - **PR-417 — PR-LF4 post-run monitoring digest** (#417, closes #386, **2 Codex passes**): `engine/monitoring_digest.py` with `MonitoringDigest` Pydantic model rolling up alerts (per-rule/queue/severity, top-3 firers) + DQ totals + diff-against-most-recent-prior-run-for-the-same-spec. `lookup_prior_run` is fully tolerant of all failure modes (no `DATABASE_URL`, persistence misconfigured, malformed manifest). Codex caught: `db.list_runs` only accepted `tenant_id` not `limit` (P2 — moot after #413's `limit` parameter merged), `alerts_per_rule` lived only on disk → prior-run diff fell back to zero baseline (P2 — persisted on the manifest too).
>
> - **PR-412 — PR-B1 validity check evaluator** (#412, closes #366): `engine/dq.py` enum / regex / range evaluators added alongside the existing `not_null` / `unique` / `freshness` / `malformed` checks. Pillar 4 deep cut.
>
> - **PR-411 — PR-A2b populate `business_intent` + `out_of_scope` on example specs** (#411, closes #393): populated all 10 example specs with the new Round 26 fields. Made #414's wire-in actually meaningful.
>
> **Azure deploys**: `v0.1.38` cut after #413 merged (ACR build + both Container Apps updated, `/api/v1/health` → `version=0.1.38, git_sha=103f3f4, tag_summary=Round 27 ...`); `v0.1.39` cut after #415/#416/#417 finished merging (engine-only changes, additive). Both single deploys per merge wave, not per PR — schema additions don't churn `rule_version_hash` and runtime contracts are back-compat.
>
> **Workflow notes**:
> - Used **4 parallel worktree agents** during the Codex usage-cap window (13:38→16:56 EDT, ~3h 20m blackout): PR-A2 follow-up, PR-LF1, PR-LF2, PR-LF4. All four delivered draft PRs that became open-and-mergeable as soon as quota refreshed; codex passes ran sequentially through the day.
> - The dashboard batch (#413) was originally six individual PRs (#401, #405, #406, #408, #409, #410) — closed and re-shipped as one batch because the merge-train fanout problem (each PR touched shared wiring: `app.py`, `audience.py`, `tests/test_e2e_dashboard.py`, `dashboard-tour.md`) created N(N-1)/2 conflict resolutions. Single-batch ship was a clear win; ~30 fewer rebase rounds.
> - Round 27 closed five `[deferred]` pillar tasks (#5 PR-A2 follow-up, #18 Decision Trail, #14 evidence pack, #34/#35/#36 each PR). Pillar 1 (Equivalence) flipped GAP → COVERED with the new dashboard surface.
>
> **Result**: 7 PRs merged + ~30 Codex rounds + 2 Azure deploys. The engine now emits 6 manifest-hashed evidence artifacts per run (`decisions.jsonl`, `dq_exceptions.jsonl`, `field_lineage.jsonl`, `sla_report.json`, `run_cost_volume.json`, `monitoring_digest.json`) — every one of which is tamper-evident via the SHA-256 chain. The dashboard grew from 47 to 53 pages. Pillar 1 closes; Pillar 6 lifecycle becomes a real product surface (SLA monitor + run cost + decision trail + monitoring digest all shipped in one round).

---

> **Round 26 — schema bumps + equivalence engine + dashboard north-star + systemic bottom-page fix** (`v0.1.37`, #395/#391/#390/#396/#388/#394/#392/#398, 2026-05-22): eight PRs through the local-Codex review gate in one cycle. Two spec extensions (Rule `business_intent`/`out_of_scope` + Program `nfrs`), a pure-module legacy↔new alert equivalence classifier, a new universally-routed north-star pillar coverage page, additive DQ observability into the audit ledger, the README test-badge schedule fix, and the THIRD attempt at the bottom-page-clip bug — this time replacing reactive padding-bumps with a three-layer contract enforced by AST source-guards. Codex round counts ran from 1 (deck-class fixes) up to **9** for the equivalence classifier, the deepest review of the session.
>
> - **PR-EQ-2 — legacy↔new alert equivalence classifier** (#388): new `engine/equivalence.py` with `classify_alerts(new_alerts, legacy_alerts, rule_map, rule_severities)` → 4-way classification (MATCH / NEW_ONLY / LEGACY_ONLY / DIFF). Pure module, no `engine/runner.py` changes — PR-EQ-1's determinism contract holds. **9 Codex rounds** caught real semantic and data-shape bugs: severity must source from the `rule_severities` spec map not just the alert payload (P2), many-to-one rule mappings dropped alerts and unattributed LEGACY_ONLY rows (P2x2), unmapped-severity fallback was inconsistent across paths (P3), TZ-aware vs naive datetime spelling produced spurious NEW_ONLY+LEGACY_ONLY pairs instead of MATCH (P2), order-dependent pairing under many-to-one needed severity-preference + alphabetical tiebreak (P2x2), `RunResult.alerts` dict shape unsupported (P2), payload `rule_id` was trusted over dict-key (P2), duplicate legacy+new rows over-counted divergence (P2x2), CSV loader hard-coded column names ignoring the spec's `key_columns` (P2 — added `column_mapping`), headerless CSV silently returned `[]` (P2), missing `rule_id`/`customer_id` should fail fast not coerce to `""` (P2x2). Every finding has a regression test. PR-EQ-3 (dashboard surface) carried to a future round — when it ships, Pillar 1 Equivalence-before-optimization moves Gap → Partial.
>
> - **PR-NS-1 — north-star pillar coverage page** (#390): new universally-routed dashboard page mapping the 8 AML/TM+DS north-star pillars (`project_aml_north_star`) to live evidence in the current run. 4 Codex passes caught: e2e PAGES registry not synced (P1), direct `st.page_link` calls bypassed the `link_to_page` helper for persona-hidden targets (P2), hard-coded persona/page counts (P3), and three over-claimed coverage rollups on Pillars 2/5/6 (P2 each). Final honest roll-up: **1 Covered** (Pillar 8 Serve five roles) / **6 Partial** (Pillars 2,3,4,5,6,7) / **1 Gap** (Pillar 1 Equivalence-before-optimization). Five follow-ups now have explicit task entries: PR-A2 STR/MRM/audit-pack wire-in for `business_intent`+`out_of_scope`, PR-EQ-3 equivalence surface (→ Pillar 1 Partial), first-class `risk_tier` on Rule (→ Pillar 5 Covered), uniform `threshold`+`reference_data_version` on alert payload (→ Pillar 6 Covered), first-class defect tickets + approvals (→ Pillar 2 Covered).
>
> - **PR-B4 — DQ exception visibility (additive, no row drops)** (#396, closes #369): engine-time DQ evaluator emits `dq_exception` events into the audit ledger plus a new `dq_exceptions.jsonl` artifact. Observability-only — no row drops — matching Option B in the original issue. 4 Codex passes caught: missing-key `not_null` was silently skipped (P2), the evaluator was scheduled AFTER `_build_warehouse` so a NOT NULL constraint crashed before the evaluator could see the violation (P1 — reordered), PII leakage of `failing_value` on unique-violation events (P1 — redacted), and `dq_exceptions.jsonl` was missing from the manifest+freeze hash list, leaving the artifact post-finalization-editable (P2). Plus a P2 `df_decisions["queue"]` KeyError on DQ-only runs.
>
> - **PR-A2 — optional `business_intent` + `out_of_scope` on Rule** (#392, closes #363): new optional Rule fields for examiner-facing rationale + explicit-scope. 3 Codex passes caught: schema description over-promised downstream surfaces the patch didn't implement (P2 — narrowed and wired into `compute_spec_diff`), and `rule_version_hash` would churn for every existing rule because Pydantic serializes default `business_intent: None` + `out_of_scope: []` (P1 — exclude defaults from hash, mirrored for dict-callers). STR / MRM / audit-pack wire-in carried to a future round.
>
> - **PR-D2 — optional `Program.nfrs` block** (#394, closes #375): new optional `program.nfrs` with `rto_minutes` / `rpo_minutes` / `sla_p95_ms` / `throughput_per_min` / `retention_days` / `notes`. Engine ignores at runtime; surfaces consume. 2 Codex passes caught: `compute_spec_diff` ignored the new block so NFR-only changes were invisible to audit (P2 — wired in), and the wire-in then emitted a bogus `nfrs.notes` row with identical empty before/after when adding a fresh NFR block (P2 — same-string early-exit).
>
> - **systemic bottom-page-clip fix (no more patchwork)** (#398): user reported the bottom-page clip bug for the **third** time after #305 and #310 patches. Replaced reactive `padding-bottom` bumps with a three-layer contract: (1) CSS `.block-container::after` 10rem pseudo-element spacer (immune to margin collapse), (2) `page_footer()` component with a visible "End of page" affordance plus persona/version context, (3) four AST source-guards in `tests/test_dashboard_page_footer.py` enforcing per-page: footer import, top-level call, last-statement, AND `st.stop()` preceded by `page_footer()`. 3 Codex passes caught: the E2E test was false-green because legacy `padding-bottom: 8rem` alone cleared the 80px threshold (P3 — now asserts `getComputedStyle(c, '::after').height >= 144px`), and helper-driven `empty_state(stop=True)` bypassed the source-guard (P1 — centralized: `empty_state(stop=True)` now calls `page_footer()` before its internal `st.stop()`).
>
> - **tests-badge schedule + workflow_dispatch fallback** (#391, closes #389): README test badges (unit / api / e2e / coverage) had been stale because `GITHUB_TOKEN` auto-merges don't fire push events, so the badge-publish workflow never ran post-merge. Added a `schedule` cron + `workflow_dispatch` recovery path. 2 Codex P2s closed: e2e-dashboard wasn't gated on the new triggers (run-cost discipline), and `workflow_dispatch` from a feature branch could push badge JSONs to a non-main branch (added a branch guard).
>
> - **`_inspect_context` defensive None-`customer_id` branch** (#395): tiny coverage backfill pinning a previously-unhit defensive `None` path so `--cov-fail-under=99` stays green without a fragile branch-exclusion.
>
> **Azure deploy**: single `v0.1.37` cut covering all 8 PRs after #398 landed — semver tag → `az acr build` (with `APP_VERSION` / `GIT_SHA` / `BUILD_TIME`) → both Container Apps rolled with `AML_TAG_SUMMARY` → smoked at `/api/v1/health` for version match. Round 25 closed at `v0.1.34`; the schema + engine changes here are additive and don't require per-PR rollouts, so a single deploy is honest.
>
> **Workflow notes from this session**:
> - Mid-session the user told me explicitly: *"issues backlog you should move them around if things change"* — the backlog is living state, not append-only. Task list reorganized; closed-out items removed, blockers reordered against current dependencies. End-of-session: 4 active + 5 deferred items tracked.
> - The user also asked: *"did you span multiple parallel on all tasks without dependencies?"* — I admitted partially. Codex companion is single-threaded (a real constraint — Codex calls must serialize), but I had serialized a batch of independent page-edits when I should have spawned a parallel Agent. Going forward: default to Agent-in-parallel for batches of independent files; reserve serial execution for Codex review, the merge train, and conflict resolution.
>
> **Result**: 8 PRs merged + 1 covering Azure deploy + ~30+ Codex rounds across all PRs (every round caught a real defect; the equivalence classifier needed 9, every other PR converged in 2–4). Two spec extensions land additively without churning `rule_version_hash` across the existing rule corpus. The `dq_exception` event now flows into the manifest-hashed audit artifact set. The bottom-page-clip bug is closed structurally — the AST source-guards make a fourth regression a test failure, not a user-reported defect. Five follow-up items now have first-class task entries against named pillars; PR-EQ-3 + the four pillar wire-ins are the path from 6 Partial → 4+ Covered in upcoming rounds.

---

> **ML scorer expansion epic — 3 python_ref scorers + unified-product completion + deck-PDF fix** (`v0.1.30`..`v0.1.34`, #354-#358, 2026-05-20 → 2026-05-21): five PRs shipped end-to-end through the Codex → CI → Azure deploy gate in one cycle. Closes two long-standing dead-ground-truth plants (C0007 + C0011) and completes the unified-product epic (PR-U4 retires the GH-Pages demo; PR-U5 fixes a user-reported deck rendering bug).
>
> - **PR-ML-1 — pass-through funnel scorer** (#354, `v0.1.30`): closes R1b, the pass-through funnel rule that R1 descoped after 5 rounds of Codex SQL windowing edge cases. New `src/aml_framework/models/passthrough_scorer.py` — procedural python_ref with "first out-event marks the phase boundary" formulation. 10 Codex rounds caught real bugs across the surface area: lineage-key shape (rowid int vs txn_id str), 30d lookback (was 7d), cross-channel discipline (was channel-agnostic → false-positives on same-rail churn), Decimal threshold (float drift at $30k boundary), unknown-channel rejection, known-channel allowlist, set-inequality cross-channel for mixed-rail funding. Round 11 clean. Wired into `canadian_schedule_i_bank` alongside the existing `rapid_pass_through` custom_sql; community_bank wire-in deferred (synthetic data uses out-of-contract channels). 26 tests, 100% coverage. C0007 (TD-pattern) + 7 replica-band customers fire on canonical seed-42.
>
> - **PR-ML-2 — mule-return-burst scorer** (#355, `v0.1.31`): closes the framework's longest-running dead ground truth — C0011 (`ROAMR LTD`) has had 3 planted pacs.004 returns (AC03/AC04/MD07 to CH-jurisdiction SHELL VEHICLE beneficiaries) since the Round-5 plant, but no spec consumed the `txn_return` table. PR-ML-2 declares the contract on `uk_bank/aml.yaml` and ships `mule_return_burst_scorer` python_ref with **layered qualification**: Path A (snippet-equivalent count≥3) + Path B (cross-signal: count≥2 + beneficiary-country fan-out≥2 + shell-name density≥2). 3 Codex rounds caught: empty-contract crash (information_schema probe + zero-column placeholder), `matched_row_ids` walked to wrong table (renamed to `matched_return_ids` + uses pacs.004 `return_id` strings), customer_id resolution via `customer.full_name` join (`ROAMR LTD` → `C0011`), path-safe BYOD originator names. First-ever C0011 alert on canonical seed-42.
>
> - **PR-ML-3 — investment-scam amplifier** (#356, `v0.1.32`): python_ref alongside the existing `invs_velocity_investment_scam` aggregation_window rule in `eu_bank`. Same Path A (≥3 INVS outflows summing ≥$5k) PLUS Path B cross-signal (≥2 outflows + counterparty-concentration ≥50% + foreign-destination ≥80% + acceleration-or-single-known-counterparty). 8 Codex rounds caught: scorer-was-noop on eu_bank (optional Path B columns split from required Path A), NULL counterparty bucket leak, partial-missing-counterparty leak, unknown-counterparty concentration leak, country case-sensitivity (`DE` vs `de`), ISO 20022 `counterparty_account` fallback for pacs.008 ingestion, NULLIF(TRIM()) for warehouse-blank handling, spec contract declarations. Round 9 clean. C0010 fires Path A (count=3, sum=8300) — the SQL rule and amplifier both fire on the planted shape.
>
> - **PR-U4 — retire GH Pages + /app + /knowledge redirects** (#357, `v0.1.33`): completes the unified-product epic ("one product, two doors, three skins"). The Knowledge content (PR-U2's 8 whitepapers + PR-U3's 2 decks = 10 native pages) is now the canonical source. `_DEFAULT_KB_URL` repointed from `tomqwu.github.io/aml_open_framework_demo/` to dashboard `/Architecture`. New `GET /app` + `GET /knowledge` 302 redirects (marketing-stable URLs). Knowledge default derives from effective `AML_APP_URL` so non-dev deployments don't accidentally point at dev. 9 landing-page tests including `monkeypatch.delenv` autouse fixture for env-isolation (Codex P3 round 2 catch). 3 Codex rounds; the GH-Pages demo can now be retired.
>
> - **PR-U5 — deck PDF iframe (fix stretched images)** (#358, `v0.1.34`): user-reported on the v0.1.29 deploy that `st.image(slide_png, use_container_width=True)` was stretching the 1920×1080 deck captures to fill the dashboard column on wide desktops, blurring them past readable. Replaced the PNG slide gallery with a native browser PDF iframe via base64 data URI (`<iframe src="data:application/pdf;base64,...#view=FitH">`). Browsers render PDFs with built-in zoom, page nav, full-screen, search — no Streamlit infrastructure, no cross-origin static-server wiring. 26 deck tests pass; Codex round 1 clean.
>
> **Azure deploys**: 5 cycles in one session — `v0.1.30` (#354), `v0.1.31` (#355), `v0.1.32` (#356), `v0.1.33` (#357), `v0.1.34` (#358). Each: semver tag → `az acr build` (with APP_VERSION/GIT_SHA/BUILD_TIME) → both Container Apps rolled with `AML_TAG_SUMMARY` per release → smoked at `/api/v1/health` for version match. PR-U4 additionally smoke-verified `GET /app` + `GET /knowledge` GET redirects (HEAD returns 405 — minor polish item). PR-U5 smoke-verified `/Business_Deck` + `/Technical_Deck` HTTP 200.
>
> **Workflow self-heal — the drain-worklog discipline corrected**: 3 separate slips this session where I defaulted to "stopping here, waiting for user direction" after a deploy. Each time the user re-prompted with "what do you mean you need more direction, you have pending tasks?" / "why you stop when there are tasks in the queue?". Memory `feedback_drain_worklog_no_permission.md` strengthened: after every PR ships + deploy verifies live, immediately start the next queued task without acknowledgement. The reflexive deploy-on-green rule applies one level up too — between PRs, the same default is to drain.
>
> **Result**: 5 PRs merged + 5 functional Azure deploys verified live + 35+ Codex rounds across all PRs (every round caught a real defect; convergence reached on round 8-11). Tests 2,409 → ~2,500 (per ci-coverage). 2 long-running dead-ground-truth plants (C0007 R1b, C0011 ROAMR) now produce alerts on canonical seed-42 for the first time on `main`. The unified-product epic ("one product, two doors, three skins") is complete: dashboard is canonical, GH Pages can be retired.

---

> _Prior:_ **Unified-product PR-U3 — Knowledge · Business Deck + Technical Deck** (#352, `v0.1.29`, 2026-05-20): two new Knowledge pages embed the board-pack business deck (12 slides + 64s board video + PDF) and the engineer/MLRO technical deck (18 slides + 92s walkthrough + PDF) — assets already in `docs/pitch/deck-v2/`, surfaced via `Path(__file__).parents[4]` and Streamlit's `st.image`/`st.video`/`st.download_button`. Image+video oriented (no prose-extract step like PR-U2's research substrate); graceful fallback if assets aren't bundled (slim wheel case). KNOWLEDGE_PAGES extended; the universal-routing idiom in `app.py` picks them up across every persona without touching the per-persona operational cap. New `TestDeckKnowledgePages` (9 source guards) + extended `_EXPECTED_PAGE_LEVEL`, dashboard-tour, and e2e PAGES list. Live-smoked at `/api/v1/health`=0.1.29 + `GET /Business_Deck` + `GET /Technical_Deck` = 200. Knowledge category now **10 pages** (PR-U2's 8 whitepapers + PR-U3's 2 decks). PR-U4 (retire GH Pages, wire `/app` routing) is now unblocked.
>
> **5-year-lookback operator runbook** (#350 + #351, docs-only, 2026-05-20): `docs/five-year-lookback.md` — operator runbook mirroring the reference Azure modernization playbook ([`aml_learning_for_fintech/docs/02-5year-lookback-azure-modernization.md`](https://github.com/tomqwu/aml_learning_for_fintech/blob/main/docs/02-5year-lookback-azure-modernization.md)) for executing a regulatory 5-year TM lookback *using this framework*. The doc went through **7 rounds of Codex source-of-truth review** — each round caught real CLI/spec drift (manifest shape, `--data-source duckdb` flag missing `--db-path`, `validate-data` being CSV-only, `aggregation_window` auto-PIT vs. `custom_sql` author-PIT, the WORM-bucket `--expected-hash` discipline for `verify-decisions`, the `not_null`/`unique`-only DQ evaluator scope). Shipped with a top-of-doc **"verify before quoting in evidence packs"** banner so operators re-check command/flag/manifest-field/event details against the live source before citing in regulator artefacts. No code change; no deploy.
>
> **Bug-fix sweep from user screenshots** (`v0.1.26`..`v0.1.28`, 2026-05-19): three user-reported defects fixed and deployed serially. (a) Model Performance page table clipping — `data_grid` `auto_height` was off for the model inventory + per-rule alert grids; row-count-gated `auto_height=len(alert_df) <= 10` keeps big alert sets paginated while small ones fit naturally (`v0.1.26`, #347). (b) `[object Object]` in `sum_amount` cell when a `python_ref` scorer emitted `{"value": X, "unit": "USD"}` — added `_scalar_amount` helper that extracts the nested numeric, plus conditional spread so alerts without `sum_amount` don't gain fabricated zero columns (`v0.1.27`, #348). (c) Section-explainer "Generating explanation…" caption was a black box during long backend roundtrips — now captions the chosen backend (`ollama`/`openai`/`template`) and a wait-window hint (`v0.1.28`, #349). Each shipped after Codex caught a real intermediate over-claim (auto_height unbounded would render hundreds of alerts in one page; naive `to_numeric(...).fillna(0)` silently dropped dict values to 0; three rejected in-process timeout designs before settling on caption-only).
>
> **Topbar — clickable logo + tag-summary chip** (`v0.1.24` + `v0.1.25`, 2026-05-19): topbar wordmark now links to `/` with anchor-scoped CSS (`v0.1.24`, #345) — was a dead element before. Next to the version chip, a deploy-time **AML_TAG_SUMMARY** string surfaces on every page (`v0.1.25`, #346) — injected via `az containerapp update --set-env-vars` not `--build-arg` (the latter doesn't preserve quoting on values with spaces/apostrophes/parens — `az acr build` cx17/cx18/cx19 each surfaced a new sh-special char on retry). `release.py:get_tag_summary()` reads the env at runtime; `/api/v1/health` exposes it for operators.
>
> **Gate cluster + main-red recovery + PR-U2 LANDED** (#337/#338/#339/#340/#341/#342 → `v0.1.18`..`v0.1.22`, 2026-05-18): six PRs drained through the serial Codex gate in one cycle — README live-demo link (#337), `aggregation_window` `matched_row_ids` correctness fix that replays the rule filter so audit evidence matches the alert's own SQL (#341), responsive-redesign e2e net (#339 PR-M1 — tiered 8-archetype regression with `xfail(strict=True)` so a future fix forces mark removal), and **PR-U2 LANDED** (#340 `v0.1.22`) bringing the 8 ported Knowledge whitepapers live after six Codex rounds caught real defects (docker-build slim-image skip-guard, dropped `<h4>` headings, 404 footer source links, internal cross-links not remapped to Streamlit routes, the universal Regulator Pulse brief sourced from stale static-site HTML, the real whitepaper headline + relative archive links unresolved). One deterministic main-red broke `e2e-dashboard` post-merge — #342 fix: a single shared module-scoped `_playwright` fixture (PR-M1's new fixture held instance #1 open while standalone tests opened a second `sync_playwright()` in the same thread → 12 deterministic "Sync API inside the asyncio loop" failures). The active-PR monitor heartbeat caught it without a silent stall.
>
> **Workflow self-heal: ACR queue liveness probe + reflexive deploy** (memory updates, 2026-05-19): the silent stall the user originally flagged is a pipeline that depended on one background notification to fire the next serial action. `feedback_azure_local_deploy_after_ci.md` now requires `az acr task list-runs --top 3 -o table` as a server-side liveness probe (cx15 zombied for ~30 min on 2026-05-19; local subprocess stdout never grew but the queue was Queued/never-Started). The active-PR monitor heartbeat re-derives live truth every wake and treats "green main with no deploy" AND "red main post-merge" as self-detected, self-corrected conditions — never trusting one notification.
>
> _Prior:_ **Dataset re-base — 100 customers, scaled positives** (`v0.1.16`, 2026-05-18): the synthetic generator defaults moved 30→100 customers and 400→2,000 noise txns (~438→1,311 txns on the canonical run), and a deterministic, RNG-free **scale-up replica band** on slots C0030–C0059 clones the six always-on community-bank typologies so positives scale with the larger, negative-majority population instead of being diluted. The deliberate, user-approved **re-base** Round 22 explicitly deferred. Codex review hardened it across six rounds: (1) a ≥90-day onboarding floor so no txn predates account opening (audit-credibility), (2) replica slots stripped of incidental prior noise so each carries only its planted shape — without this only 1 of 5 `unusual_volume_spike` clones alerted; now all 30 replicas alert cleanly, (3) the Network Explorer e2e re-anchored off a date/size-sensitive token, (4–6) doc-honesty: the dataset's ground-truth model was reframed (user decision) — planted C0001–C0059 are the **labelled** positives; the rest are **unlabelled realistic background**, NOT a zero-alert guarantee. At the scaled volume some background coincidentally trips a tight rule even at seed 42 — accepted as the realistic false-positive surface FP-analysis/tuning/backtest exist for (the engine never assumes planted-exclusivity). Committed `data/input/` CSVs regenerated, the Round-22 "no-rebase" guard re-anchored (1,311 txns / 342 cash / 100 customers + replica coverage), `test_data_fixtures_and_mock` counts updated. Self-consistency determinism tests auto-re-based. The `≥60` guard gates only the replica band — this is an intentional *global* re-base (new defaults + universal ≥90d onboarding floor apply to all calls; explicit-arg callers keep the same txn count but customer rows re-base via the floor, which is fine: no test pins exact onboarded_at). Codex flagged the earlier "byte-identical small-n" wording as an over-claim — corrected here and in CLAUDE.md. Canonical run now 45 alerts / 45 cases / 90 decisions. Tests 2,404 → 2,409.
>
> _Prior — nav + deploy-time fix_ (#332, `v0.1.15`): `st.navigation()` now runs before the slow cold-start `initialize_session()` so a freshly deployed container no longer shows Streamlit's auto "app" pages-nav; topbar + `/api/v1/health` now show the image build time (`AML_BUILD_TIME`).
>
> _Prior:_ **Round 22 follow-up — `data_grid` auto-height** (#330, `v0.1.14`, 2026-05-18): the five Data Integration tables sized their AG Grid container with a px estimate (`min(35*rows+60, cap)`) that undershot AG Grid's real chrome, so small tables (e.g. the 2-row Contract roll-up) clipped rows and rendered a blank whitespace box. Added an opt-in `auto_height` to `data_grid()` (AG Grid `domLayout='autoHeight'`, no pagination footer) and switched all five tables to it. Codex review went two rounds deep here — it grepped the bundled st-aggrid CSS and found AG Grid's auto-height stylesheet stamps `min-height:150px` on `.ag-center-cols-container`/`-viewport`/`-clipper`/`.ag-body-viewport`; all four are now cleared under `auto_height`. The other ~8 brittle-height callers are large/unbounded tables where the cap+scroll is intentional — left as-is. Tests 2,400 → 2,404.
>
> _Prior:_ **Round 22 — Data Integration epic: more rails, fixtures, honest cloud-mock, richer UI** (#325–#327) shipped 2026-05-17: PR-A added modern payment rails (rtp / crypto / prepaid) + 3 planted typologies to the synthetic generator + canonical spec **additively — zero RNG re-base** (user-chosen over a dataset re-base), with 3 new rules (#325 / `v0.1.12`); PR-B added a deterministic `make fixtures` parquet/duckdb generator + an EXPLICIT, honestly-labelled local-mock path for the 8 cloud/warehouse source types (no credential fake) + a new ISO-20022 sample (#326, dev tooling — no deploy); PR-C surfaced both on the Data Integration page — per-source demonstrable-data status + a volume-by-channel chart (#327 / `v0.1.13`). Two Azure deploys; Codex caught a real rule-typology mismatch (the crypto pass-through rule was looser than its cash→crypto description), fixed before merge. Tests grew 2,357 → 2,400.
>
> _Prior:_ **Round 21 — non-blocking AI + real coverage gate + OS-following dark theme** (#316–#323, 2026-05-16 → 2026-05-17): async section explanations + real ≥99% gate (`v0.1.8`), then a 3-PR dark-theme arc — foundation (`v0.1.9`), theme-neutral charts after a determinism-driven pivot away from a reload-based dark bridge (`v0.1.10`), secondary-chrome sweep (`v0.1.11`).

---

## At a Glance

| Metric | Round 6 (2026-04-27) | Round 7 closed | Dashboard plan closed (2026-04-29) | Dashboard UX + GenAI push (2026-04-30) | Brand + UX consolidation (2026-05-01) | Round 10 — Data layer (2026-05-02) | Round 11 — Hardening + API + charts + docs (2026-05-04 → 2026-05-05) |
|---|---|---|---|---|---|---|---|
| Source code | 19,642 LOC across 18 modules | + ~2,500 LOC | + ~700 LOC | + ~3,500 LOC (PR-A → PR-L) | + ~2,650 LOC (PR-M → PR-T, 31 files) | + ~2,920 LOC (PR-DATA-1 → PR-DATA-10b, 19 files) | + ~1,700 LOC (PR #204-#211 + #217-#219, 26 files) |
| Tests | 991 | + ~110 | 1,161 passing | **1,750 passing** | **1,791 passing** | **1,848 passing** | **1,985 passing** (unit + API; +98 e2e collected separately) |
| Test files | 34 | 39 | 43 | 56 | 90 | 96 | 100 |
| Example specs | 7 | 9 | 9 | 9 | **10** | 10 | 10 |
| Unique regulation citations | 61+ | ~75+ | ~75+ | ~75+ | ~80+ | ~85+ (BCBS 239, FATF R.18, OSFI E-23/B-13, EBA outsourcing, Wolfsberg CBDDQ) | ~105+ (added PCMLTFR/OSFI/SEMA/FCA/PSR/OFSI) |
| Dashboard pages | 24 | 24 | 24 | **29** (+ Metrics Taxonomy, AI Assistant, screenshots-pending) | 29 (count unchanged; 31 page files inc. 2 nav surfaces) | **30** (+ Information Sharing) | **32** (sync + Data Integration in e2e; all counts unified) |
| Merged PRs (cumulative) | 18 (#46–#73) | + #74–#79 | + #80–#87 | + #150–#161 (PR-A → PR-L) | + #162–#168 (PR-M → PR-T) | + #177–#183 (PR-DATA-1 → PR-DATA-10b) | + #204-#211 (#216) + #217 + #218 + #219 |

---

## Module Surface

```
src/aml_framework/
├── api/              FastAPI REST layer (JWT auth, multi-tenant DB, rate limiting)
├── attestations/     MLRO sign-off ledger — hash-chained attestations.jsonl (Round 10)
├── cases/            Investigation aggregator, SLA timer, STR bundling, filing sidecars (Round 6/10)
├── assistant/        GenAI co-pilot (template/ollama/openai backends, sidebar on every page)
├── dashboard/        44-page Streamlit web app (mobile-responsive, multi-tenant, GenAI panel)
├── data/             Synthetic generator + 8 source loaders + ISO 20022 parser
│   ├── iso20022/     pacs.008, pacs.009, pain.001, pacs.004 ingestion (Round 5)
│   └── lists/        Sanctions, adverse media, sanctioned wallets, purpose codes
├── engine/           Rule executor on DuckDB, audit ledger with SHA-256 hash chain
├── generators/       SQL, DAG stubs, control matrix, STR narratives, board PDF,
│                     goAML XML, AMLA STR, MRM bundle, effectiveness pack
├── integrations/     Jira, Slack/Teams, SIEM/CEF connectors
├── metrics/          Metric evaluation engine + RAG bands + audience routing
├── models/           ML scoring callables for python_ref rules + travel-rule validator
├── narratives/       LLM-backed narrative drafting (Ollama, OpenAI backends)
├── pkyc/             Perpetual KYC trigger engine
├── sanctions/        OFAC SDN refresh + fuzzy match
├── spec/             JSON Schema + Pydantic validation + reusable rule library
└── vasp/             Public-data VASP attribution (Chainalysis alternative)
```

---

## Round-by-Round Delivery

### Round 5 — Payment Rails Ingestion (5 PRs, ~16 days)

Goal: ingest the messages banks actually move money with, after SWIFT's MX-only cutover (2025-11-22).

| PR | Feature | Driving signal |
|---|---|---|
| #56 | ISO 20022 `pacs.008` + `pacs.009` ingestion adapter | SWIFT MX-only cutover |
| #57 | FATF R.16 Travel Rule field validator (`python_ref` callable) | FATF Feb 2026 plenary deficiency call-out |
| #58 | ISO 20022 purpose-code typology library (4 reusable snippets) | ExternalPurpose1Code now mandatory |
| #59 | `pain.001` corporate-batch ingestion | Wolfsberg Feb 2026 correspondent-banking guidance |
| #60 | `pacs.004` payment-return + return-reason mining library (3 snippets) | UK PSR APP-fraud reimbursement (Apr 2026 full effect) |

**Result**: framework can natively consume every major ISO 20022 message type. Travel-rule completeness is automated. Two reusable spec-library files ship 7 typology rule snippets keyed to FATF / FinCEN / UK PSR / Wolfsberg guidance.

### Round 6 — Case Management as First-Class Surface (5 PRs, ~17 days)

Goal: make investigation (not alert) the unit of analyst work, per FinCEN's 2024 effectiveness rule.

| PR | Feature | Driving signal |
|---|---|---|
| #61 | Investigation aggregator (`cases/aggregator.py`) | FinCEN NPRM measures effectiveness per investigation |
| #62 | Multi-tenant dashboard surfacing (sidebar selector) | API had it; dashboard didn't |
| #63 | SLA timer + escalation engine (`cases/sla.py`) | FCA Mar 2026 Dear CEO letter on SAR backlogs |
| #64 | Case-to-STR auto-bundling (`cases/str_bundle.py`) | Wolfsberg Feb 2026 "submission-ready packages" |
| #65 | Investigations dashboard page #24 | Operator surface for the above |

**Result**: cases now aggregate into investigations with deterministic IDs. Live SLA tracking surfaces backlog state per-queue. Self-contained STR ZIPs bundle narrative + goAML XML + Mermaid diagrams + manifest hash. New dashboard page consolidates the workflow.

### Workflow Polish (4 PRs)

| PR | Feature |
|---|---|
| #67 | README refactor 582 → 123 lines + Getting Started guide + Dashboard Tour + Jurisdictions doc |
| #69 | `aml --help` typer/click compatibility fix; crypto_vasp doc gap |
| #70 | Mobile-responsive dashboard overlay (closes #66) |
| #71 | Workflow audit: executive font scale + 4 pages made interactive + missing pages registered |
| #72 | Synthetic data enriched with ISO 20022 fields + planted INVS positive |

**Result**: new-user onboarding path is 15 minutes. Mobile viewports work. Executive personas (SVP/CTO/CCO/VP/Director) get auto-scaled fonts. Default `aml run --seed 42` demo now exercises all Round 5/6 features.

### Round 7 — Research-driven defensive layer (5 PRs, ~21 days)

Goal: ship the top-5 features ranked by impact ÷ effort in the [2026-04 competitive positioning research](research/2026-04-competitive-positioning.md). All five anchored to a 2026 regulatory clock the research surfaced as load-bearing.

| PR | Feature | Driving signal |
|---|---|---|
| #74 | Regulatory-change diff watcher (`compliance/regwatch.py`) | FinCEN BOI Mar 2025 narrowing + April 2026 NPRM 12-month tail |
| #75 | AMLA STR/RTS effectiveness telemetry pack (`metrics/outcomes.py`) | AMLA RTS due 2026-07-10 + FinCEN NPRM enumerates same metrics |
| #76 | TBML + UK APP-fraud example specs | FATF Feb 2026 plenary + PSR Apr 2026 full-effect reimbursement |
| #77 | PSD3 / Verification-of-Payee adapter (DRAFT) | PSD3/PSR Council/Parliament agreement end-Q2 2026; VoP applies +24 months |
| #78 | FINTRAC pre-examination audit pack (`generators/audit_pack.py`) | FINTRAC January 2026 examination manual update |

**Result**: framework now has a defensive layer that sits *above* the spec — drift detection against silently-changing regulator pages, regulator-format effectiveness JSON, jurisdiction-templated examination evidence packs. This is the layer commercial vendors don't ship because they own the rule library themselves; the framework needs it precisely because it doesn't.

**Cross-feature integration** (closed in Dashboard Workflow & Design plan, 2026-04-28):
- Dashboard page surfacing the outcomes funnel ✅ Phase B-2
- Dashboard panel for regwatch drift findings ✅ Phase B-2
- One-click audit-pack download from Audit & Evidence ✅ Phase B-3
- VoP outcomes panel on Sanctions Screening ✅ Phase B-3

### Dashboard Workflow & Design plan (8 PRs, 2026-04-27 → 2026-04-28)

Goal: ensure proper workflow + design across the dashboard. Audit identified 5 hidden modules, broken cross-page navigation, muddled persona arcs, and crash-prone empty-state behavior.

| PR | Phase | Feature |
|---|---|---|
| #80 | A | Cross-cutting helpers: `link_to_page`, `read_param`, `consume_param`, `severity_color`, `sla_band_color`, `empty_state` |
| #81 | B-1 | SLA timer + STR-bundle download on case-facing pages (#4, #21, #17) |
| #82 | B-2 | Effectiveness funnel on Executive Dashboard + regulation-drift panel on Audit & Evidence |
| #83 | B-3 | FINTRAC audit-pack download on Audit & Evidence + VoP outcomes on Sanctions Screening |
| #84 | C | Cross-page drill-downs / deep links — Alert Queue + Network Explorer + Customer 360 + Executive |
| #85 | D | Persona workflow rebalance — every persona ≤8 pages, coherent task arcs |
| #86 | E | Empty-state defenses on engine-side pages (#5, #10, #11) + design consistency test guards |
| #87 | E follow-up | `risk_color()` resolver + 7 pages migrated off inline color dicts; test ALLOWED set drained |

**Result**: every Round-6/7 module is now reachable from the dashboard (was the original Phase B goal). Cross-entity drill-downs eliminate the audit's worst dead-ends (~20-30s saved per drill, dozens per shift). Three pages that crashed on degenerate specs now degrade gracefully. Color/SLA palette has a single source of truth — any new inline color dict fails CI. Tests grew 1089 → 1161 across the 8 PRs.

### Dashboard UX + GenAI push (12 PRs, 2026-04-30)

Goal: close the remaining clickability/colour/cross-link gaps from a fresh page-by-page audit, then surface the dashboard's existing GenAI substrate as a co-pilot on every page. Single day, 12 PRs auto-merging on green per the project memory rule.

| PR | Workstream |
|---|---|
| #150 | PR-A · Row-click drill-through across 5 triage tables (Alert Queue, Customer 360, My Queue, Investigations, BOI Workflow) |
| #151 | PR-B · Severity + RAG cell colouring on 6 read-only tables (centralised Styler helpers — `severity_cell_style`, `rag_cell_style`, `metric_gradient_style`, `event_type_cell_style`) |
| #152 | PR-C · Cross-page navigation + research-link sweep — `see_also_footer` on 6 pages |
| #154 | PR-D · Empty-state polish — `empty_state()` helper applied across 6 pages |
| #153 | PR-E · Chart palette + tooltips + SLA-band shading + best-F1 annotation |
| #155 | PR-F · Regulation citation hyperlinks via new `citation_link()` helper |
| #156 | PR-G · KPI card drill-through on My Queue / BOI Workflow / Alert Queue |
| #157 | PR-H · ID-linking sweep + Tuning Lab `rule_id` deep-link reader |
| #158 | PR-I · **Metrics Taxonomy** catalogue page (#28) — sister to Typology Catalogue, browseable definitional view of every metric the spec declares |
| #159 | PR-J · `dashboard-tour.md` drift fix + `test_dashboard_tour_coverage.py` prevention pattern. Closed Issue #68. |
| #160 | PR-K · **GenAI Assistant MVP** — sidebar panel on every dashboard page via a single line in `page_header()`. New `assistant/` sibling module to `narratives/` with template/ollama/openai backends. Spec-configurable audit log via `program.ai_audit_log: hash_only \| full_text`. New page #29 for backend status + transcript + run-level audit trail. |
| #161 | PR-L · Docs sync (this snapshot, README, spec-reference) |

**Result**: dashboard now ships with click-everywhere navigation, a coherent colour discipline (RAG / severity / SLA from centralised tokens, no inline hex), an audit-doc-defendable Metrics Taxonomy reference, and a GenAI co-pilot that mounts on every page without per-page edits. The `narratives/` substrate that previously powered only the Case Investigation STR drafter is now reused for the assistant — same Citation model, same backend factory, same audit-log discipline. Tests grew 1,646 → 1,750 (+104) across the 12 PRs.

### Brand + UX consolidation (7 PRs, 2026-05-01)

Goal: port the landing-site brand DNA (deck → dashboard CSS), then absorb the regressions that surfaced once the topbar / Today-hero rebuild went live. Smaller wave than PR-A→L; mostly CSS, fixes, and one e2e expansion.

| PR | Workstream |
|---|---|
| #162 | PR-M · Port deck DNA to live CSS (typography scale, spacing, accent ramp) |
| #163 | PR-N · Landing-site brand applied — wordmark + cream/orange palette |
| #164 | PR-O · Preserve sidebar expand control after collapse (regression from N) |
| #165 | PR-Q · Landing-style topbar + ivory sidebar + Today hero |
| #166 | PR-R · Fix Today cards crashing for VP / SVP / Director / Developer / FinTech personas (KeyError on persona-filtered metrics) |
| #167 | PR-S · Fix `link_to_page()` crash when target page is hidden by persona filter |
| #168 | PR-T · e2e persona × page coverage matrix + HTML-leak detector + KPI render fix |

**Result**: dashboard chrome now matches the landing-site brand. Two persona-side crashes that surfaced after the topbar/Today-hero rebuild are fixed and protected by a 31×12 persona-page e2e coverage matrix. The HTML-leak detector catches a class of bug where Streamlit components render unrendered Markdown/HTML strings into the page (a regression vector that's easy to introduce when porting CSS-heavy components). Tests grew 1,750 → 1,791 (+41) across the 7 PRs; test files went 56 → 90 (the e2e expansion split into per-persona modules). Three follow-up README polish commits (`Where this fits in your stack`, `In-bank, not SaaS`, Quickstart venv guidance) shipped directly to main outside the PR cadence.

### Round 10 — Data layer hardening (7 PRs, 2026-05-02)

Goal: close the gap between the "Data is the AML problem" whitepaper's claims (`docs/research/2026-05-aml-data-problem.md`, shipped in PR #174) and what the code actually backs. A code audit against the doc found 3 STRONG / 5 PARTIAL / 3 STUB verdicts across 11 DATA-N sections; this round addresses the 6 with material gaps.

| PR | Workstream | DATA-N | Whitepaper claim before / after |
|---|---|---|---|
| #177 | PR-DATA-1 · Fail-closed contract validation | DATA-1 | "Validator fails closed" — partial → **strong** |
| #178 | PR-DATA-2 · pKYC integration + per-attribute freshness pinning (`max_staleness_days` + `last_refreshed_at_column`) | DATA-2 | "Per-attribute freshness pinning" — stub → **strong** |
| #179 | PR-DATA-4 · Per-decision audit metadata + `walk_lineage()` helper | DATA-4 | "Walk-back from any KPI to producing run + rule version + spec hash + input file hashes" — partial → **strong** |
| #180 | PR-DATA-9 · Real STR/SAR filing-latency capture (filing sidecars) | DATA-9 | "STR filing-latency p95 is a first-class metric" — proxy → **real wall-clock** |
| #181 | PR-DATA-8 · MLRO attestation workflow + `aml run --strict` gate | DATA-8 | "MLRO signs against Manifest hash" — stub → **strong** (hash-chained `attestations.jsonl`) |
| #182 | PR-DATA-10a · `information_sharing` spec syntax + `aml share-pattern` / `aml verify-pattern` CLI | DATA-10 | "Cross-bank info-sharing reference surface" — sandbox-only-as-library → **policy boundary in spec + CLI seam** |
| #183 | PR-DATA-10b · Information Sharing dashboard (page #31) | DATA-10 | Operational view (declared partners + recent share-pattern artifacts) |

**Result**: 6 DATA-N sections promoted from stub/partial to strong. New module `attestations/` (17 modules total). New engine submodule `engine/freshness.py`. New cases sidecar `cases/<case_id>__filing.json`. Three new CLI commands (`attest`, `share-pattern`, `verify-pattern`); two new audit-event types (`contract_violation`, `pkyc_trigger`). Audit-ledger schema bumped to version 2 with `rule_version` stamped on every `case_opened` event. Tests grew 1,791 → 1,848 (+57) across 6 new test files; test files went 90 → 96. The `aml run --strict` opt-in flag refuses to execute against unattested specs — the first concrete Manifest-version gate the framework ships.

The whitepaper's three remaining claims (DATA-3 reconciliation, DATA-5 sovereignty, DATA-11 spec-as-data-contract) were already STRONG; DATA-6 (AI presumes data) is closed transitively by PR-DATA-1's fail-closed validation; DATA-7 (Engineering vs Compliance ownership) is technical-pattern-strong via the data-contract architecture, with the residual gap being organisational and out of code scope.

### Round 11 — Hardening + API + charts + docs (10 PRs, 2026-05-04 → 2026-05-05)

Goal: close the residual gaps surfaced by a fail-closed / compliance-posture review (#204-#211), finish the chart-library migration started in Round-9, harden the REST API surface for production deploys, and unify the 21 stale page/test/jurisdiction counts that had drifted across docs and the landing site.

| PR | Workstream |
|---|---|
| #213 | `fix(api)`: gate demo auth in production — refuse demo-mode credentials when `ENV=production` |
| #214 | `fix(data)`: fail closed on unloadable data contracts (raise instead of silent fallback) |
| #215 | `fix(engine)`: fail closed on `python_ref` scorer failure by default — opt-in to soft-fail |
| #216 | Compliance hardening — gap-review batch closing #204-#211: SQL proxy dispatch correctness, strict CSV row validation, dashboard page-inventory drift test, jurisdiction overclaim cleanup, citation-URL completeness (PCMLTFR/OSFI/SEMA/FCA/PSR/OFSI), sanctions alias persistence, audit/filing JSONL append-only ledger, dashboard data-source mode tracking |
| #217 | `fix(charts)`: finish ECharts + AG Grid migration — zero Plotly references, zero `st.dataframe` calls remain |
| #218 | `fix(api)`: harden uploads + OIDC — strict audience validation, configurable artifact root for run persistence, Helm `values.yaml` keys + deployment template, `.env.example` + deployment.md updates, +89 lines of new API tests |
| #218 | `docs`: refresh all docs and landing site — 21 stale metrics unified across README/landing/dashboard-tour/getting-started/CONTRIBUTING/CHANGELOG/progress.md (page count 31→32, test count 1,790/1,910/1,850 → 1,980, jurisdictions claim → "5 jurisdictions with 10 bundled specs", deck slide page-counts) |
| #219 | `fix(ci)`: filter the exact transient browser-only `Failed to fetch` pageerror in dashboard e2e while preserving Streamlit exception and other pageerror failures |

**Result**: the framework now fails *closed* across three more boundaries (demo-auth in prod, data-contract load, python_ref scorer error) — completing the policy that started with PR-DATA-1. Every chart and every table on the dashboard is now ECharts / AG Grid (no Plotly, no `st.dataframe`). The REST API artifact-root configuration unblocks production K8s deploys where pod ephemerality requires runs to persist outside `/tmp`. Twenty-one stale numeric claims across docs were reconciled in a single sweep so future drift is detectable; CI flake on transient browser fetch errors no longer noise-trips the e2e gate. Tests grew 1,848 → 1,985 (+137) across 10 PRs.

### Round 12 — End-to-end lineage (11 PRs, 2026-05-07)

Goal: close the gap between "we have a hash-chained audit log" and "we can walk an examiner from any alert to its source row." Eleven PRs across backend (Phase A), dashboard surfacing (Phase B), a new dedicated page (Phase C), and marketing (Phase D).

| PR | Phase | Workstream |
|---|---|---|
| #222 | A | PR-LIN-1 · Surface rendered SQL via `walk_lineage()` (lifts `rules/<rule_id>.sql` into the chain dict) |
| #223 | A | PR-LIN-2 · Stamp source path + schema_columns + schema_hash on `record_input()` (8 source types via new `infer_source_paths()` helper) |
| #224 | A | PR-LIN-3 · Stamp `rule_version` on every decision event (escalate / closed / rule_failed), not just `case_opened` |
| #225 | A | PR-LIN-4 · Capture `matched_row_ids` per alert across `aggregation_window` / `custom_sql` / `list_match` / `network_pattern` (python_ref deferred — would break callable contract) |
| #226 | B | PR-LIN-5 · Audit & Evidence — SQL viewer + matched-row grid + source-provenance columns on the existing lineage walk-back panel |
| #227 | B | PR-LIN-6 · Case Investigation — "Why this fired" panel above Transaction Timeline (matched-row count + severity + rule_version + collapsible rule SQL) |
| #228 | B | PR-LIN-7 · Data Integration — Source → Contract → DuckDB Table mapping section; DATA-3 / DATA-4 status flipped from "stub" to "shipped" |
| #229 | C | PR-LIN-8 · New Lineage Explorer page #32 — Mermaid graph + run anchors + source provenance + rule SQL + matched rows + decision timeline + JSON download. Registered in app.py + e2e PAGES + analyst persona |
| #230 | D | PR-LIN-9 · Landing page — third hero "Trace every alert. Down to the row." + new research card + `#/research/lineage` hash route |
| #231 | D | PR-LIN-10 · `research/lineage.html` deep-dive — 7-link evidence chain, 12 stamped fields, regulator anchors (BCBS 239 P3-P5, FinCEN April 2026 NPRM, SR 26-2, OSFI E-23) |
| #232 | D | PR-LIN-11 · New technical slide `24-lineage-walkback.html` (Act IV) + by-the-numbers slide refresh (test count 1,632 → 2,000+, pages 26 → 32, specs 9 → 10, CLI 24 → 38, licence MIT → Apache 2.0) |

**Result**: the audit question "show me why this alert fired" now has a one-paste-box answer. The 7-link chain (source file → contract → DuckDB table → rule → alert with `matched_row_ids` → case → STR) is hash-stamped end-to-end, reproducible from spec + data + as_of, and downloadable as JSON for offline review. Three existing dashboard pages got the relevant slice of the chain inline; the new Lineage Explorer page consolidates the deeper drill. The 12-field per-decision payload is now the framework's documented audit shape. DATA-3 (cross-system reconciliation) and DATA-4 (lineage walk-back from KPI) are shipped, not stubs. Tests grew 1,985 → ~2,020 (+35) across 11 PRs.

### Round 13 — Lineage coverage gaps · dashboard, exports, CLI, API (9 PRs, 2026-05-07)

Goal: close the gap between "the lineage primitives exist" and "every surface a regulator, analyst, or integration consumer might touch shows the chain." A 3-pronged audit after Round 12 found that 14 of 32 dashboard pages carried zero lineage, all 3 regulator-facing exports were lineage-blind, and there were no CLI commands or API endpoints for lineage at all.

| PR | Phase | Workstream |
|---|---|---|
| #237 | E | PR-LIN-12 · Triage path lineage — Alert Queue + My Queue + Analyst Review Queue gain `Matched rows` + `Rule version` columns / Source-lineage expander; Case Investigation deep-links to Lineage Explorer |
| #238 | E | PR-LIN-13 · Entity-context lineage — Investigations + Network Explorer + Customer 360 gain inline columns + per-case Lineage Explorer deep-links |
| #239 | E | PR-LIN-14 · Analytical-arc lineage — Rule Performance gains `Rule version` (via `rule_version_hash`) column; Sanctions Screening gains `Source rowid` from `matched_row_ids[0]`; Run History + Tuning Lab gain Lineage Explorer pointers |
| #240 | E | PR-LIN-15 · Headline + AI lineage — Today + Executive Dashboard + AI Assistant gain Lineage Explorer entry-points; AI Assistant citations get a "Verify against audit trail" deep-link per `referenced_case_id` |
| #241 | F | PR-LIN-16 · STR bundle `manifest.json` carries a `case_lineage` block (rule_version + matched_row_ids + per-contract source_path/schema_hash/content_hash). Regulator extracting the ZIP can answer "which rule version, which source rows" without re-running |
| #242 | F | PR-LIN-17 · Audit pack ships a new `case_lineage_summary.json` section. FINTRAC examiner gets the chain per case from the bundle alone |
| #243 | F | PR-LIN-18 · Effectiveness pack — Control Output Quality pillar gains `alerts_by_rule_with_lineage` finding (per-rule alert_count + rule_version + sample_matched_rows). Closes FinCEN April 2026 NPRM standard's "show your work" gap on aggregate metrics |
| #244 | G | PR-LIN-19 · CLI — `aml lineage <case_id>` (JSON or table) + `aml verify-decisions [--expected-hash]`. Wraps `walk_lineage()` and `AuditLedger.verify_decisions()` for scriptable use; tamper detection exits non-zero |
| #245 | G | PR-LIN-20 · API — `GET /api/v1/runs/{run_id}/cases/{case_id}/lineage`. Auth gated; tenant-isolated; 404s on unknown run / missing run_dir / unknown case_id; 401 without auth |

**Result**: lineage is now reachable from every dashboard surface (14 pages updated), every regulator-facing export (STR bundle / FINTRAC audit pack / FinCEN effectiveness pack), the CLI (`aml lineage`, `aml verify-decisions`), and the API (`GET .../cases/{id}/lineage`). The audit chain is no longer "primitives in the data" — it's "addressable from anywhere a consumer might be." Tests grew ~2,020 → 2,050 (+30) across 9 PRs.

### Round 14 — Final lineage coverage audit (2 PRs, 2026-05-07)

Goal: after Round 13, audit every dashboard page for lineage suitability and close real gaps. User asked for completeness; the honest answer is *coverage by relevance, not by URL count*. A 3-pronged audit of the 16 pages NOT touched by Rounds 12+13 produced this verdict:

| PR | Workstream |
|---|---|
| #249 | PR-LIN-23 · 5 case-aware pages get lineage hooks: Risk Assessment (row-click drill → Alert Queue), Model Performance + Comparative Analytics + FinTech Cockpit + Metrics Taxonomy (`→ Open Lineage Explorer` pointer). 12 new ALLOWED_GRACEFUL_GAPS entries for personas seeing these pages without Lineage Explorer in their nav. |
| #250 | PR-LIN-24 · Round 14 docs section (this entry) + CHANGELOG block explaining the coverage policy. |

**Pages explicitly excluded — 10 pages** that carry no case-level domain to walk back from. Listed here so future audits don't re-litigate:

| Page | Why no lineage |
|---|---|
| **0_Welcome** | Orientation router; pure persona routing, zero case context |
| **2_Program_Maturity** | Spec-level aggregate posture; not case-driven |
| **8_Framework_Alignment** | Prescriptive regulator-mapping matrix; no case evidence |
| **9_Transformation_Roadmap** | Project planning; not investigation |
| **11_Live_Monitor** | Ephemeral simulator; alerts not persisted to audit trail |
| **14_Data_Quality** | SRE / data-contract focus; validates sources, not subjects |
| **16_Rule_Tuning** | What-if threshold tool; not tied to actual alerts |
| **20_Spec_Editor** | YAML authoring; cases live downstream once rule deploys |
| **27_Regulator_Pulse** | Regulator-news doctrine; cross-links to responding pages already |
| **31_Information_Sharing** | Cross-bank policy/config; obfuscated, no case mapping by design |

**Already covered before this round (1 page):** 25_BOI_Workflow drills via Customer 360, which has the Round-12 lineage panel. Chain is complete.

**Result**: every page where lineage is *meaningful* now reaches Lineage Explorer. The 10 excluded pages remain link-free deliberately — adding generic pointers there would dilute the meaning of "lineage." After Round 14, the lineage workstream is **closed.** Future page additions follow the established pattern (link_to_page with case_id when available, generic pointer otherwise). Tests grew 2,050 → 2,055 (+5) across 2 PRs.

### Round 15 — Azure bank-deploy stack (4 PRs, 2026-05-07)

Goal: make the framework deployable on Microsoft Azure with zero static secrets. After Rounds 12–14 closed the lineage workstream, the user asked to integrate with Azure platform tools/systems. Azure spans 7+ surfaces (data, identity, secrets, deploy, AI, SIEM, governance); user picked all four high-value buckets and split them across two rounds — bank-deploy now (Round 15), AI + Sentinel + Purview later (Round 16).

| PR | Workstream |
|---|---|
| #251 | PR-AZ-1 · Data sources — `azure_blob` + `adls` (DuckDB azure extension over `abfss://` URIs) + `synapse` + `azuresql` (pyodbc with ActiveDirectoryMsi auth on AKS workload identity). 4 new dispatch branches in `resolve_source()` + 4 new `infer_source_paths()` cases so the Round-12 lineage chain picks up Azure-sourced runs unchanged. New `[azure]` extras in pyproject.toml. |
| #252 | PR-AZ-2 · `aml_framework.secrets.SecretsProvider` — Key Vault first, env-var fallback. DefaultAzureCredential picks up workload identity on AKS; falls back gracefully when SDK init fails. JWT_SECRET, OPENAI_API_KEY, demo-user passwords all routed through the provider. Naming translation `_` → `-` for Key Vault compatibility. |
| #253 | PR-AZ-3 · AKS Helm chart additions — `azure:` block in values.yaml (5 optional fields), workload-identity ServiceAccount + pod label rendered conditionally, AZURE_KEY_VAULT_NAME / AZURE_STORAGE_ACCOUNT_NAME / AZURE_SYNAPSE_CONN / AZURE_SQL_CONN env vars threaded to API + dashboard pods. New `values-azure.example.yaml` with az CLI cookbook. New "Deploying on Azure / AKS" section in `docs/deployment.md`. |
| #254 | PR-AZ-4 · Round 15 docs sync (this entry) — progress.md + CHANGELOG + README + architecture.md. |

**Result**: a regulated bank with an Azure tenant can deploy this on AKS today. Workload identity removes static credentials end-to-end; Key Vault houses the JWT signing key + OpenAI API key; Entra ID OIDC handles API auth via the existing generic OIDC support (no code changes — config only). Lineage chains from Round 12 work unchanged on Azure-sourced runs (`source_path: azure_blob:abfss://...`). Tests grew 2,055 → 2,076 (+21) across 4 PRs.

**Round 16 (queued, not shipped):** Azure OpenAI as a 4th assistant backend; Microsoft Sentinel SIEM via Log Analytics Data Collector; Azure Monitor / Application Insights via OpenTelemetry; Microsoft Purview lineage push via Atlas API. The Purview piece is the **differentiated** one — pushing `walk_lineage()` chains to Purview means AML lineage shows up in the same governance pane as a bank's other data assets.

### Round 16 — Land on the user's Azure backbone, Phase A (4 PRs, 2026-05-07)

Goal: deploy the framework on the user's prebuilt landing zone at [tomqwu/cloud_landing_zone_for_ai_coding](https://github.com/tomqwu/cloud_landing_zone_for_ai_coding). Round 15 shipped the AKS Helm chart for self-managed Azure / on-prem K8s; this round adds the **Container Apps** path that the landing zone constrains us to.

Surprise constraint: the landing zone's `CLAUDE.md` explicitly forbids AKS — *"compute: only Azure Functions Flex Consumption, Container Apps, or Static Web Apps."* Round 15's Helm chart still ships for non-landing-zone deployments; Round 16 Phase A adds an alternative.

| PR | Workstream |
|---|---|
| #255 | PR-AZ-5 · Terraform deployment module under `deploy/terraform/` calling `module.onboard` from the landing zone (vends RG + UAMI + per-app Key Vault + FICs). Provisions Postgres Flexible Server B1ms with Entra-ID-only auth, Container Apps for API + dashboard with UAMI assigned, diagnostic settings → platform Log Analytics workspace, Key Vault secret placeholders for JWT-SECRET / OPENAI-API-KEY (with `lifecycle.ignore_changes` so operator-set values survive). |
| #256 | PR-AZ-6 · GitHub Actions pipeline `deploy-azure-landing-zone.yml` — three jobs: `plan` (PR comments) → `build_and_push` (ACR via OIDC) → `apply` (gated by `platform-prod` Environment, with revision-rollover nudge + `/health` smoke check). All auth via federated identity credential — no secrets stored in the repo. **Removed in Round 18 (PR #295):** Azure deploy is now local-only; CI does not hold Azure credentials. |
| #257 | PR-AZ-7 · OpenTelemetry → Azure Monitor wiring. New `src/aml_framework/observability/` module with `init_observability()` — lazy-imports `azure.monitor.opentelemetry`, no-op when `APPLICATIONINSIGHTS_CONNECTION_STRING` is unset, idempotent + exception-swallowing. Wired from `api/main.py` + `dashboard/app.py`. New `azure-monitor-opentelemetry` in `[azure]` extras. |
| #258 | PR-AZ-8 · Round 16 Phase A docs sync (this entry). |

**Result**: a `terraform apply` against the user's tenant lands the framework end-to-end on Container Apps + Postgres + per-app Key Vault, with the Round-12 lineage chain intact (case_id → Lineage Explorer renders against cloud-deployed dashboard) and the Round-15 Azure data sources working unchanged. Cost ~$33/mo idle on top of the landing zone's $5 baseline. Tests grew 2,076 → 2,084 (+8) across 4 PRs.

**Phase B (queued, not shipped):** Azure OpenAI as 4th assistant backend, Microsoft Sentinel via the platform Log Analytics workspace, Microsoft Purview lineage push. Lives in a future plan.

### Round 17 — Plant coverage + persistence asymmetry + housekeeping (9 PRs, 2026-05-08 → 2026-05-09)

Goal: close the MRM-trustability gap on under-covered specs (us_rtp_fednow, trade_based_ml, uk_app_fraud) by planting ground-truth positives that match each rule's window/threshold semantics, plus a persistence-layer cleanup that surfaced from Azure deployment work.

`#272` was bundled into `#271` and `#280` into `#279` via stacked-PR cascades, so 7 squash commits land on main for these 9 PR numbers.

| PR | Workstream |
|---|---|
| #271 | Flip persistence backend precedence to postgres > cosmos in `_active_backend()`. Helm `api-deployment.yaml` + `dashboard-deployment.yaml` mirror the flip so what `kubectl describe` shows matches what the Python runtime picks under dual-config. One-time WARN log when both `DATABASE_URL` and `COSMOS_ENDPOINT` are set so an operator migrating Cosmos→Postgres sees the silent backend switch in startup logs. New `TestCrudFunctionsRouteToPostgresUnderDualConfig` covers all 7 public CRUD funcs. |
| #272 | (bundled into #271 via stacked-PR cascade) Dashboard startup-log test class (`TestDashboardStartupLogsBackend`) verifies the dashboard pod's `Persistence backend: %s` line emits to the `aml.dashboard` logger. Class-scoped `_restore_sys_modules` fixture prevents streamlit imports leaking into other test files' "no streamlit" assertions. |
| #273 | Document the dashboard ↔ DB persistence asymmetry: terraform-deployed dashboard pods received `COSMOS_ENDPOINT` but not `DATABASE_URL`, silently falling back to local SQLite when `enable_postgres = true`. CLAUDE.md note + `deploy/terraform/README.md` known-issue section pointing at the fix path (Helm side already addressed in #271; Terraform Container Apps side queued). |
| #275 | Plant trade-based ML positives (C0020-C0022) + UK APP fraud positives (C0016-C0019) + the `hs_code_baseline` reference table for over/under-invoicing rule joins. New `is_null` SQL filter operator (with strict bool guard against YAML-quoting accidents) so `phantom_shipping`'s `invoice_id: { is_null: true }` filter compiles correctly. |
| #276 | Plug cross-spec contamination from C0012-C0019 planted positives: at certain seeds the noise loop's 4-week background activity pushed those customers' `unusual_volume_spike` baseline_avg over the 5× ratio threshold, leaking false positives into uk_bank, canadian_schedule_i_bank, canadian_bank, and community_bank. Same `txns = [t for t in txns if t["customer_id"] not in <ids>]` guard pattern that PR #275 used for C0020-C0022, now widened to C0012-C0019. |
| #277 | Align C0012/C0013 RTP plant timestamps with the rule windows: `aggregation_window` uses a sliding `[as_of - parse_window, as_of)` (verified at `src/aml_framework/generators/sql.py:154-163`); the prior C0012 plant at `as_of - timedelta(days=1, hours=1)` was 25h back — 1h outside `first_use_payee_large_amount_rtp`'s 24h window — and C0013's burst at `-1d -14h` was 38h outside `velocity_spike_on_receive_rtp`'s 1h window. Two new window-pinning regression tests catch any future drift. |
| #278 | `.gitignore` additions for `terraform.tfstate*`, `deploy/terraform/*.tfplan`, `_temp/`, `/aml_open_framework/` (embedded git-repo experiment), `uv.lock` — files accumulating untracked across recent rounds that risk an absent-minded `git add -A` polluting a future commit. |
| #279 | Populate `counterparty_id` in the synthetic txn data — declared nullable in `us_rtp_fednow`'s `data_contract` but never emitted by `_make_txn`. Three rules use it: `unusual_send_hour_for_customer_rtp` SELECTs it; `first_use_payee_large_amount_rtp` and `ramp_up_then_drain_rtp` `GROUP BY (customer_id, counterparty_id)`. Without real values, the latter two collapsed every txn into a single `(customer, NULL)` group. Also re-anchored C0012's plant hour to a guaranteed-outside-typical-window value regardless of as_of, so `unusual_send_hour_for_customer_rtp` fires under default `aml run` invocations (was firing only when as_of was at midnight). |
| #280 | (bundled into #279 via stacked-PR cascade) Plant C0023 ("Ramp Source LLC") with 4 small RTP outbounds totaling $1,550 to `CP-RAMP-2026-001` for `ramp_up_then_drain_rtp` coverage. Intentional cross-rule firing: `cyber_enabled_fraud`'s broader `ramp_up_then_drain` rule is a strict superset, so this same plant fires it too — net coverage gain on that spec. |

**Result**: us_rtp_fednow's within-spec coverage on planted customers grew from 0/5 to 4/5 (still needs a customer-contract `device_id` linking column to fire `mule_receiver_fan_out_rtp`); trade_based_ml fires 3/5 of its rules end-to-end on the plants (over_invoicing, phantom_shipping, multiple_invoicing); uk_app_fraud fires 4/4. Cross-spec leak guards at C0012-C0022 stop the noise from those plants nudging unrelated specs' all-txn rules. Tests grew 2,084 → 2,168.

**Out of scope (queued):** `mule_receiver_fan_out_rtp` plant (needs `phone`/`email`/`device_id` linking column on the `customer` contract); `unusual_send_hour_for_customer_rtp` cleanup of the `t.counterparty_id` SELECT now that the column is populated (not strictly needed but tidies the SQL).

### Round 17.5 — Live Azure landing-zone deploy (3 PRs, 2026-05-11)

Goal: prove the Round 16 Phase A scaffolding works end-to-end against the user's actual Azure tenant. First live `terraform apply` surfaced three runtime issues no unit test had caught — each shipped as a focused fix PR.

| PR | Workstream |
|---|---|
| #282 | wire `DATABASE_URL` into the dashboard Container App. Helm was fixed in #271; Terraform-deployed dashboard pods still injected only `COSMOS_ENDPOINT`, so on the Postgres path the dashboard silently fell back to local SQLite. New `local.postgres_database_url` hoisted so the value can't drift between API and dashboard. Test asserts both Container App blocks read the same local. |
| #283 | fetch Entra-ID token for Postgres on Azure deploys. The Terraform-generated DSN included `authentication=azure_ad` which psycopg2's DSN parser rejects. `_get_pg_conn()` now detects the marker, strips it via proper URL parsing (not regex), mints a token via `DefaultAzureCredential().get_token("https://ossrdbms-aad.database.windows.net/.default")`, and passes it as `password=` to psycopg2. Five tests pin the strip behavior across marker-position variants + userinfo false-positive. |
| #284 | set `AZURE_CLIENT_ID` on both Container Apps + use AD-admin `principal_name` (not object_id) as Postgres user. With UAMI auth, `DefaultAzureCredential` needs `AZURE_CLIENT_ID` set to know which UAMI to pick. Then Postgres validates AD admins by `principal_name`, not by object_id, so the DSN's user component was wrong. Hoisted to `local.postgres_admin_principal_name` shared by the AD admin resource AND the DSN — test asserts both read the same local. |

**Result**: live deploy at https://ca-aml-api-dev.wittyhill-44456789.canadacentral.azurecontainerapps.io with `/api/v1/health` returning `{"status":"ok","version":"0.1.0"}`. Dashboard healthy at the matching domain. Both pods read/write Postgres `psql-aml-dev-2lusik` via UAMI Entra-ID auth. ~$33/mo idle. Tests grew 2,168 → 2,178.

### Round 18 — Plant fan-out + Azure Phase B differentiation (6 PRs, 2026-05-12)

Goal: close Round 17's `mule_receiver_fan_out_rtp` coverage gap (4/5 → 5/5) and ship the three Azure-shop integrations Round 16 Phase B queued (Azure OpenAI assistant, Sentinel SIEM connector, Purview lineage push).

| PR | Workstream |
|---|---|
| #285 | Pin `counterparty_id` as evidence column on `unusual_send_hour_for_customer_rtp`. Adds inline comment on the rule + fast SQL-string test + heavier engine-run test that asserts the alert payload carries a non-empty counterparty_id. Regression-safe after #279. |
| #286 | Plant 4-mule `device_id` cluster (C0024-C0027) sharing `DEV-MULE-2026-001`. Adds `device_id` (pii: true) to the us_rtp_fednow customer contract + `_customer_row()`. Network_pattern rule `mule_receiver_fan_out_rtp` now fires 4 alerts (one per mule). Intentional cross-spec firings on `cyber_enabled_fraud.pig_butchering_payout_fan` + `crypto_vasp.nested_wallet_ring` — same pattern as #280's C0023 coverage extension. Single-gate guard at `n_customers >= 28`. |
| #287 | Azure OpenAI as 4th GenAI assistant backend. Mirrors the existing `openai.py` Chat Completions shape but routes to per-deployment Azure endpoints. Two auth paths: api-key (header: `api-key`) or Entra-ID bearer token at scope `https://cognitiveservices.azure.com/.default`. Endpoint/deployment/key resolved via SecretsProvider (Key Vault on the deployed Container App). 8 tests cover both auth paths + actionable-error path for unmintable AAD tokens. |
| #288 | Sentinel SIEM connector — active push complement to the existing CEF-export `integrations/siem.py`. POSTs structured AML decision events to the platform Log Analytics workspace via the v1 Data Collector API at `<workspace>.ods.opinsights.azure.com/api/logs`. Shared-key HMAC-SHA256 auth (v1 API doesn't accept Bearer tokens; Logs Ingestion API migration deferred to Round 19). Opt-in via `AZURE_SENTINEL_WORKSPACE_ID`. Module docstring + in-code NOTE explain the deferred audit-ledger emit-hook wiring. |
| #289 | Purview lineage push via Atlas REST API. Maps `walk_lineage()` chains to Atlas entity dicts: `Process(rule:<id>)` with `inputs` (source DataSets) and `outputs` (case DataSet). `qualifiedName` uses a stable `aml://<spec>/<part>/...` scheme so re-pushes update rather than duplicate. `ruleVersion` + `specContentHash` stamped on Process attributes so auditors see which spec snapshot drove each case. Auth via DefaultAzureCredential at scope `https://purview.azure.net/.default`. Opt-in via `PURVIEW_ENDPOINT`. 7 tests cover entity-builder shape, qualifiedName stability, sparse-chain handling. |

**Result**: us_rtp_fednow within-spec coverage goes 4/5 → **5/5**. Azure-shop integration surface adds three connectors (assistant, SIEM, governance lineage) all gated by env vars so non-Azure deployments aren't affected. Tests grew 2,178 → 2,187.

**Deferred to Round 19** (originally scoped in plan but not executed):
- Spec-specific synthetic noise patterns for uk_app_fraud / trade_based_ml / us_rtp_fednow (PR 18.3) — medium-scope refactor; current noise loop works.
- Performance baseline + locust harness (PR 18.7) — infra work.
- `python_ref` matched-row lineage hook (PR 18.8) — opt-in `_inspect_context()` contract.
- PII masking policy layer for audit ledger (PR 18.9) — cross-cutting feature.
- Engine backend abstraction (PR 18.10) — multi-week scope (Snowflake/BigQuery compile targets).
- `aml generate-dbt` (PR 18.11) — dbt-model emit command.
- Audit-ledger emit hooks for the Sentinel + Purview connectors — load-bearing engine change; the surfaces shipped without callers so the wiring can be reviewed in isolation. Future integrators must wrap calls in `try/except` and log-and-continue.
- Logs Ingestion API (DCE/DCR) migration for Sentinel — unlocks Entra-ID auth on the SIEM push but requires terraform-preprovisioned Data Collection Endpoint + Rule.

### Round 19 — GenAI UX polish + CI streamlining (3 PRs, 2026-05-13 → 2026-05-14)

Goal: fix the live-site regression where per-section AI explanations rendered above the page hero (or never resolved on first paint), and stop paying the ~12-min Playwright e2e cost on every PR push.

| PR | Workstream |
|---|---|
| #306 | Revert PR #304's async `ThreadPoolExecutor` dispatch back to synchronous `assistant.reply()` inside `st.spinner()`. The async model returned in ~5 ms but the reply never surfaced without an interaction-driven rerun — operators saw a permanent spinner. A 1-sec polling fragment had fixed visibility but killed the Playwright suite via networkidle starvation (100/100 → 15/100). Synchronous baseline trades ~2-3 sec first-paint per unique section for actually-visible AI output. Kept: process-global `_PROCESS_CACHE` (cross-session), `_resolve_model` complexity-tier routing, audit hook. Module dropped from 445 lines → 320 with 100% test coverage. |
| #307 | Gate `e2e-dashboard` to push-to-main only via `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`. PR feedback drops ~15 min → ~5 min. Local `make pre-push` still runs e2e — CLAUDE.md "PR/CI is the last gate, not a feedback loop" makes the local hook the canonical contract. Main-push e2e remains as post-merge safety net; Azure auto-deploy gates on main green so a broken e2e blocks deploy rather than reaching live. Branch protection on main updated via `gh api` to drop `e2e-dashboard` from required status checks (without that, every future PR would be permanently waiting on the now-skipped required check). |
| #308 | Move page-level `section_explainer(...)` below each page's hero/intro on 32 dashboard pages. Streamlit renders in script order — the explainer was firing before `page_header()` / dna-hero / `show_audience_context()` on most pages. AST-respecting script relocated the call to right after the last intro marker; stable `section_id` preserved so the cross-session `_PROCESS_CACHE` + audit trail stay continuous. 3 pages (`1_Executive_Dashboard`, `3_Alert_Queue`, `5_Rule_Performance`) already called section_explainer deep-inline after specific charts and were untouched. |

**Azure redeploy**: two `az acr build` + `az containerapp update` cycles ran during the round (after #306 merge, again after #308 merge). Image tags use `+` → `-` sanitization since Docker tags reject PEP440 local-version markers. Dashboard Container App's `OLLAMA_API_KEY` secret + env-var binding added (was missing — explained the live site's template-backend placeholder text in the user's screenshot evidence). Both apps now live on `aml-framework:0.1.1.dev5-g83045d6de` at https://ca-aml-api-dev.wittyhill-44456789.canadacentral.azurecontainerapps.io/api/v1/health and the matching dashboard host.

**Result**: AI explanations render below the hero on every page, fire synchronously on first paint with a visible spinner, and cache cross-session so revisits are <1 ms. PR feedback time cut by ~60% with the same coverage guarantee. Tests grew 2,187 → 2,272 (+85, mostly section_explainer test simplification + the sync-flow test rewrite).

### Round 20 — GenAI advisor reliability + visibility + FAB entry point (4 PRs, 2026-05-14)

Goal: chase down a user-visible bug ("each page has AI summary with low confidence, not sure which model was used") and the screenshot evidence that the AI Explanation block on every live page rendered canned template text despite `AML_AI_BACKEND=ollama` on the Container App. Surface the real failure, route the sidebar advisor through the deep model tier, and add a floating-action-button entry point so the chat is reachable without scrolling past Streamlit's 32-page nav.

| PR | Workstream |
|---|---|
| #310 | Bottom-padding regression on short empty-state pages. `My Queue` ended flush against the viewport; PR #305's 4rem bump wasn't enough. `padding-bottom` to 8rem, `min-height: calc(100vh - var(--dna-topbar-h))` so short pages fill the viewport. CSS-only in `dashboard/components.py`. Tagged `v0.1.3`. |
| #311 | Surface real LLM backend errors. `_call_backend` in `section_explainer` AND `_handle_ai_submission` in the sidebar advisor both silently caught every exception and returned a TemplateBackend reply — auth / model / network failures on ollama or openai were invisible. Replace silent fallback with visible `st.error(...)` banners naming backend, model, and exception. Side-effect bug: `TemplateBackend.__init__` didn't accept `model=` kwarg (every section_explainer call passed one because `_resolve_model` always returns a string); added `model` kwarg that the template ignores. Codex review caught a regression — `_resolve_model` reads `AML_OLLAMA_MODEL_*` env vars whose values name ollama model strings, so forwarding `model=` to OpenAI would 400 and Azure OpenAI rejects the kwarg. Gated on `backend_name == "ollama"`. Also clears stale `ai_transcript[page]` on submission failure so a prior reply doesn't render below the new error banner. Tagged `v0.1.4`. |
| #312 | Sidebar advisor wired through the deep model tier. `_handle_ai_submission` was calling `get_assistant(backend_name)` with NO `model=`, so OllamaBackend fell back to `AML_OLLAMA_MODEL` (set to `gpt-oss:120b` on the live Container App, overriding `AML_OLLAMA_MODEL_DEEP=deepseek-v4:pro`). Thread `_resolve_model("deep")` for ollama backends only. Surface the resolved model in the sidebar pill (`AI Assistant · ollama · deepseek-v4:pro`) and as a chip next to the confidence badge in `_render_assistant_reply`. Page 29 (AI Assistant) replaced its single `Model:` row with three (fast tier inline / deep tier sidebar / legacy fallback if set). HTML-escape both the backend and model labels via `html.escape` before interpolating into `unsafe_allow_html=True` markdown — operator-controlled env vars could otherwise inject markup. Tagged `v0.1.5`. |
| #313 | Floating-action-button entry point. User screenshot showed the sidebar `ai_panel` is invisible: Streamlit's `st.navigation()` widget claims the top of the sidebar with the 32-page grouped nav and the ai_panel renders below — operators have to scroll a full viewport down to reach it. Added `ai_panel_fab(page)`: `st.container(key="ai_fab_container")` produces a `<div class="st-key-ai_fab_container">` whose injected CSS pins it `position: fixed; bottom: 1.5rem; right: 1.5rem`; the popover button inside is styled as a rounded blue pill with a shadow. `st.popover` (NOT `st.dialog` — dialogs auto-close on the Ask submission rerun, hiding the reply). Widget keys suffixed `_fab_` so the FAB and the existing sidebar advisor can coexist on the same page without duplicate-key collision; both share `ai_transcript[page]` so a reply asked via either surface shows on both. `pyproject.toml` streamlit floor bumped 1.35 → 1.39 because `st.container(key=...)` requires 1.39+ (Codex caught the silent-failure scenario on older allowed installs). Tagged `v0.1.6`. |

**Azure redeploys**: four `az acr build` + `az containerapp update` cycles ran during the round, one per merge — `v0.1.3` (bottom padding), `v0.1.4` (errors visible), `v0.1.5` (sidebar Pro + model UI), `v0.1.6` (FAB). Each tag pushed via `git tag -a` first so `setuptools-scm` produces a clean version on `/api/v1/health`. Both `ca-aml-api-dev` and `ca-aml-dashboard-dev` rolled together each cycle.

**Codex review iterations**: three rounds of `/codex:review --base main` per PR (#311, #312, #313) caught four real blockers before merge — ollama-only model routing, false `openai · deepseek-v4:pro` pill label, streamlit version floor, and the OpenAI pill regression test. Each block was addressed with a follow-up commit and re-reviewed.

**Memory updates**: `feedback_azure_local_deploy_after_ci.md` strengthened to "deploy on green is reflexive, not optional" per user directive — plan mode no longer blocks the post-merge ship. `feedback_auto_merge.md` index entry corrected (it had said "no auto-merge" but the body had been "merge on green" since 2026-05-08).

**Result**: AI is now diagnosable on the live stack — operators see the real ollama error (or success) instead of canned template text. Sidebar replies come from DSv4 Pro with the model attribution visible next to the confidence badge. Floating button gives a one-click entry point regardless of scroll position. Tests grew 2,272 → 2,294 (+22). CLAUDE.md updated: "outline approach inline in 1-2 sentences then implement; do not call exit_plan_mode."

### Round 21 — non-blocking AI + real coverage gate + OS-following dark theme (6 PRs, 2026-05-16 → 2026-05-17)

Goal: make the per-section AI non-blocking (page renders first, the explanation fills in) with visible "thinking" feedback; fix the now-genuinely-enforced 99% coverage gate; and build a real OS-following dark theme after a live screenshot showed the dashboard illegible (dark-navy ink on a dark canvas) in OS dark mode.

| PR | Workstream |
|---|---|
| #316 | ollama model tag hyphen fix — ollama.com tags use `deepseek-v4-flash` / `deepseek-v4-pro` (hyphen), not the colon form. Env vars + code defaults corrected; surfaced a broader lesson (see Memory). Tagged `v0.1.7`. |
| #318 | Non-blocking async `section_explainer`: `ThreadPoolExecutor` dispatch keyed by `(page, section_id, persona, data_hash)`, a `@st.fragment(run_every="1.2s")` poller that promotes resolved futures under a two-phase claim-lock, dispatch-time audit-context snapshot, `st.error` on failure. The Ask button greys to a "Thinking…" spinner state. This is the *async fill* the Round-19 revert (#306) had deferred — done right this time with `domcontentloaded` + a shell-selector e2e wait instead of `networkidle` (which the 1-sec fragment had starved). Five Codex rounds: silent fallback, ollama-only routing, drain race, non-atomic publish, audit-once. |
| #319 | Genuinely raise repo coverage to 99.32%. A pytest-cov quirk that had masked the `--cov-fail-under=99` gate vanished in a runner update, exposing real ≈98.5% coverage. Closed with real tests (no pragma-gaming). Tagged with #318 as `v0.1.8`. |
| #320 | **Dark-theme PR-1 — foundation.** `:root` defines light `--dna-*` vars; `@media (prefers-color-scheme: dark)` redefines every role-bearing var; previously-hardcoded inline colours (KPI value/label, hero tint, topbar) refactored to read the vars so they flip. `.streamlit/config.toml` reduced to `primaryColor` + `font` only (a static bg/text pin can't be scheme-aware — it was the original lock). Codex caught topbar/header/native-metric still hardcoded; fixed. `--dna-card-border` added as a solid dark mid-grey clearing WCAG 1.4.11 3:1 (the translucent `--dna-rule` couldn't on near-black). Tagged `v0.1.9`. |
| #322 | **Dark-theme PR-2 — theme-neutral charts.** Canvas-rendered ECharts can't read the CSS dark theme. The first approach — a client `prefers-color-scheme` bridge that set a query param and reloaded — was **abandoned mid-PR**: Codex showed the reload re-runs the AML engine with a fresh `as_of` (state cached only in `st.session_state`), so windowed rules evaluate over a shifted window and the immutable audit ledger records two divergent runs — a determinism-contract break unacceptable in a compliance tool. Pivoted to theme-neutral: transparent chart background (the CSS-themed card shows through) + a retuned `CATEGORICAL_PALETTE` and `DNA_CHART_*` tokens whose relative luminance sits in a band clearing WCAG 1.4.11 3:1 on **both** the cream and the `#212832` dark card; the opaque tooltip is self-contained. Real WCAG luminance maths in the unit tests mirror the e2e dark test. Six Codex rounds (incl. a heatmap-default-ramp bypass via the public wrapper). Tagged `v0.1.10`. |
| #323 | **Dark-theme PR-3 — secondary-chrome sweep.** Routed the deep-link colour, "(no prior runs)" / AI-assistant / citation-count labels, and the sparkline neutral through PR-1's dark-aware tokens. Codex HOLD caught a real trap: functional labels first routed onto `--dna-ink-faint` (PR-1's *intentional* de-emphasis token, 2.33:1 on cream — fails even non-text 3:1), fixed to `--dna-ink-dim` (clears 4.5:1 text on both). Tagged `v0.1.11`. |

**Deliberately deferred** (documented in-code, not silently changed): semantic SEVERITY/RAG/`breached` colours stay a regulator-standard convention (forcing dual-safe would break "breach reads red" and touches DOM badge consumers) — own follow-up; and AG Grid dark theming (`data_grid.py`) — streamlit-aggrid renders in its own iframe so the parent `--dna-*` vars don't cascade in, a separate cross-iframe PR-3b.

**Azure redeploys**: five `git tag -a` + `az acr build` + `az containerapp update` (both `ca-aml-api-dev` + `ca-aml-dashboard-dev`) cycles, `v0.1.7` → `v0.1.11`. The `v0.1.10` build first shipped `0.1.0+local` because `az acr build` was invoked without the `--build-arg APP_VERSION=… GIT_SHA=…` the Dockerfile expects (the image carries no `.git`); rebuilt with the args and rolled by image digest (a same-tag push doesn't force a new Container App revision). Both apps verified live at `/api/v1/health` reporting clean `0.1.11` / `543157a`.

**Doc-scope note**: `CHANGELOG.md` `[Unreleased]` is pre-existing drift-stale — its newest entry is Round 16; Rounds 17–21 are unrecorded there. This is **intentionally not backfilled** in this focused progress-doc update (5 rounds of CHANGELOG history is its own dedicated catch-up); `docs/progress.md` remains the canonical state-of-project snapshot in the interim.

**Result**: page-level AI no longer blocks first paint and shows a thinking state; the 99% gate is real and enforced; the dashboard follows OS dark mode with WCAG-conformant contrast on every primary surface and chart, with two scoped follow-ups tracked in-code. Tests grew 2,294 → 2,357 (+63). Memory added: verify external identifiers empirically; drain the worklog without asking permission; **commit before any Codex review** (the local Codex companion runs destructive `git reset`/`checkout` that discards uncommitted work — this cost one re-apply of a Codex-HOLD fix).

### Round 22 — Data Integration epic (3 PRs, 2026-05-17)

Goal: act on "dig into more features on the Data Integration tab — enable more testing data and channels for each type." Investigation established the determinism trap up front (the synthetic generator seeds RNG once, then a ~400-txn noise loop consumes it sequentially *before* the planted positives), so the user was asked to choose the approach; they picked **additive, determinism-preserving** over a full dataset re-base.

| PR | Workstream |
|---|---|
| #325 | **PR-A — additive rails + typologies (`v0.1.12`).** `_NEW_RAILS = [rtp, crypto, prepaid]` kept OUT of `_CHANNELS` (so the seeded noise loop's `random.choice(_CHANNELS)` draw is byte-identical — no re-base). New plants C0028 (crypto VASP rapid pass-through + prepaid-load structuring) and C0029 (RTP instant-payment burst) appended AFTER the C0022 block using only hardcoded amounts/offsets (zero `random.*`); only 2 free customer slots, so C0028 carries two typologies; a new-rail background block is RNG-free (`tid % N`) and excludes the cross-spec-guarded plant ids. Canonical spec: channel enum extended + 3 new rules (`crypto_vasp_rapid_passthrough` custom_sql, `rtp_instant_payment_burst` + `prepaid_load_structuring` aggregation_window) mirroring existing rule shapes; all citations resolve via the existing `CITATION_URL_MAP` (crypto rule cites the already-mapped FINTRAC LVCTR — no URL invented). Codex HOLD: the crypto rule was looser than its "cash-in → crypto-out" description (no `channel='cash'`, only the crypto leg gated) — fixed to require `channel='cash'` + both legs ≥ $30k. Reproducibility test stayed green (no re-base); test_api rule-count golden 10 → 13. |
| #326 | **PR-B — fixtures + honest cloud local-mock (dev tooling, no deploy).** `data/fixtures.py` + `make fixtures` / `python -m`: deterministic parquet (one file/contract) + duckdb (one table/contract) from `generate_dataset(seed=42, as_of=pinned)` via pyarrow (type-faithful). `data/fixtures/` gitignored — parquet/duckdb aren't byte-deterministic, so committing them would fight the determinism contract; regen is one reproducible command. An EXPLICIT local-mock path for the 8 cloud/warehouse types: the literal `mock`/`mock:<x>` as the conn/bucket arg serves the seeded data via in-memory DuckDB with a loud "LOCAL MOCK (no live credentials)" warning — a real conn string/URI never equals `mock` so production paths are byte-untouched (75 insertions / 0 deletions), and several `# pragma: no cover` infra stubs became really-tested. New `sample_pacs008_rtp_crypto.xml` ISO-20022 sample for the PR-A typology. Codex MERGE + 2 non-blocking nits fixed test-only (per-test duckdb skip-guard so the pure sentinel-safety tests run on lean CI; semantic ISO assertions). |
| #327 | **PR-C — richer Data Integration UI (`v0.1.13`).** Two additive, self-contained sections on `pages/30_Data_Integration.py` (104 insertions / 0 deletions): "Demonstrable test data per source type" (every connector + how to get demo data locally — live-checks CSV/fixtures presence, points cloud types at `--data-dir mock`) and "Volume by payment channel" (groups the wired source's txns by rail → the theme-neutral `bar_chart` from dark PR-2, so the PR-A rails are visible here, with an `empty_state` fallback). 7 file-text source guards; render covered by the existing Data Integration e2e. |

**Azure redeploys**: two cycles — `v0.1.12` (#325) and `v0.1.13` (#327), both apps rolled by image digest with the correct `--build-arg APP_VERSION/GIT_SHA` from the start (the Round-21 `v0.1.10` lesson). PR-B shipped no deploy: the live dashboard uses synthetic/CSV, so the fixtures + opt-in mock are dev/demo tooling with no live behavioural change (same precedent as the docs PRs). Both apps verified live at `/api/v1/health` reporting clean `0.1.13` / `5c3e08c`.

**Result**: every one of the 9 source types is now demonstrable locally with zero live credentials; modern rails (rtp/crypto/prepaid) flow through the deterministic synthetic data, trip dedicated rules, and are visible on the Data Integration page — all without re-basing the reference dataset (every pre-existing alert-count/hash golden untouched). Tests grew 2,357 → 2,400 (+43). The CHANGELOG `[Unreleased]` drift (stale at Round 16) remains a tracked, deliberately-deferred catch-up — `docs/progress.md` is the canonical snapshot in the interim.

---

### Round 23 — gate-drain cluster + main-red recovery + workflow self-heal (6 PRs, 2026-05-19)

Goal: drain a stack of parallel-authored draft PRs through the local-Codex gate and per-PR Azure deploys, after the user flagged that a prior deploy had silently stalled (R1 `v0.1.19` finished CI green but never deployed). The fix was structural, not a promise — see the workflow self-heal below.

| PR | Workstream |
|---|---|
| #341 | **engine: `aggregation_window` `matched_row_ids` (`v0.1.20`).** Replay the rule `filter` + use an inclusive `booked_at <= window_end` boundary when stamping matched row ids so the audit evidence matches the alert's own SQL. Codex-clean first pass. |
| #338 | **metrics-M1 backfill (`v0.1.21`).** Curated core-metrics into 4 zero-metric specs. Codex P2: `high_severity_alert_ratio` was structurally always-green in the 3 all-high-severity specs (numerator == denominator → constant 1.0, `green:{lte:1.0}` evaluated before unreachable `gt:1.0` amber/red) — a false-assurance risk metric in a director/SVP report. Dropped it from cyber_enabled_fraud/uk_app_fraud/trade_based_ml (kept for us_rtp_fednow, which excludes its one `medium` rule so the share is a real fraction with reachable bands); added an "OMIT for all-high-severity specs" guard note to `core_metrics.yaml`; pinned the contract both ways in the backfill test. |
| #339 | **responsive PR-M1 e2e net (test-only, no deploy).** Codex P2 ×2: non-strict xfails let a future XPASS silently count as pass (made the STRICT tier `strict=True` so a fixed page forces mark removal); and the bounce-to-main token guard searched whole `body` (sidebar nav lists every page title) — scoped all three tiers' token checks to `[data-testid='stMain']`. |
| #337 | **docs — live-demo link (no deploy).** README + GH-Pages landing point at the running Azure dashboard. Codex-clean. |
| #340 | **PR-U2 native Knowledge section (`v0.1.22`).** 8 GitHub-Pages research whitepapers ported to native Streamlit pages (33–40) via a build-time HTML→Markdown substrate. Six Codex rounds, each a real defect: docker-build skip-guard (slim image lacks `scripts/`), dropped `<h4>` headings, 404 footer source links, internal cross-links not remapped to Streamlit routes, the universal Regulator Pulse brief sourced from the stale static-site HTML (re-pointed at the canonical README-advertised `docs/research/2026-05-regulator-pulse.md`, verbatim — zero regulatory-data fabrication), dropped `r-feat`/`r-spa`/vendor card content, numbered-stem cross-links vs the registered title `url_path`, and the real whitepaper headline (`display_title`/`eyebrow`) never rendered + relative archive `.md` links unresolved. |
| #342 | **MAIN-RED RECOVERY — single `sync_playwright` per mobile module (folded into `v0.1.22`).** #339's net added a module-scoped `iphone_se_page` fixture that `yield`s inside `with sync_playwright()`, holding instance #1 open for the whole module; the 5 pre-existing standalone mobile tests each opened their own second `sync_playwright()` while it was alive — illegal in one thread → 12 deterministic "Sync API inside the asyncio loop" failures. It reached `main` because `e2e-dashboard` is not a required merge check, so the cluster auto-merged it unverified. Fix: one shared module-scoped `_playwright` fixture all tests draw browsers from (canonical sync pattern). |

**Azure redeploys**: four cycles — `v0.1.19` (the originally-stalled R1 deploy, shipped on detection), `v0.1.20` (#341), `v0.1.21` (#338), `v0.1.22` (#340 + #342). #339 (test-only) and #337 (docs) carried no runtime delta — no deploy, by the same precedent as prior docs/test PRs. Each functional deploy: semver `git tag` → `az acr build` (with `APP_VERSION`/`GIT_SHA`/`BUILD_TIME`) → both `ca-aml-api-dev` + `ca-aml-dashboard-dev` rolled → smoked at `/api/v1/health`; `v0.1.22` additionally smoke-verified `GET /Architecture` → 200 (a new Knowledge route — confirms the explicit `url_path` resolves live, not a bounce-to-main).

**Workflow self-heal (the real fix to the user's complaint)**: the silent stall was a pipeline that depended on a single background notification to trigger the next serial action. `memory/feedback_active_pr_monitor.md` was strengthened so a self-healing reconcile heartbeat re-derives live truth every wake and treats **"green main with no deploy"** AND **"red main post-merge"** as self-detected, self-corrected conditions — never trusting one notification, always reconciling PRs + main-CI + the live `/api/v1/health` version. This round exercised it end-to-end: it caught the overdue `v0.1.19`, drove six PRs through the serial Codex gate, and auto-recovered a deterministic post-merge `e2e-dashboard` break (#342) without a silent stall.

**Result**: 6 PRs merged, 4 functional Azure deploys verified live (final `v0.1.22` / `d8e9493`), one compliance-correctness defect (always-green risk metric) caught pre-merge, one deterministic main-red regression root-caused and fix-forwarded. Follow-up tracked separately: making the dashboard topbar wordmark a clickable home link (the landing brand already is; the `/` hero span is the home page itself).

---

## What the Framework Does Today

### For the policy author (CCO / MLRO)
- Authors a versioned `aml.yaml` — every rule cites a specific regulation
- Two-layer validation (JSON Schema + Pydantic cross-references)
- Reusable rule snippet library (`spec/library/`) for ISO 20022 typologies
- Reviewable diff between spec versions (`aml diff`)

### For the data engineer
- Generates SQL, DAG stubs, and control matrix from spec
- 8 supported data sources: synthetic, CSV, Parquet, DuckDB, S3, GCS, Snowflake, BigQuery
- Native ISO 20022 ingestion (pacs.008/009/pain.001/pacs.004)
- Schema validation at load time

### For the analyst (L1/L2)
- 44-page web dashboard with persona-filtered navigation
- Row-click drill-through on every triage table (no more selectbox-below-table)
- Investigation-level review (not just alerts)
- Per-case live SLA + escalation recommendations
- Network-pattern explainability with Mermaid diagrams
- One-click STR submission bundle
- GenAI co-pilot in the sidebar — auto-scoped to current page + run, with citation chips linking back into the dashboard

### For the auditor / regulator
- Append-only decisions ledger with SHA-256 hash chain
- Reproducible runs (same spec + data + seed → identical hashes)
- Regulator-ready evidence ZIP (`aml export`)
- goAML 5.0.2 XML and AMLA RTS JSON exports
- **End-to-end lineage walk-back** (Round 12 + 13): paste any `case_id` → 7-link chain (source file → contract → DuckDB table → rule SQL → matched source rowids → alert → case → STR), each link hash-stamped + reproducible, downloadable as JSON. Surfaces on Audit & Evidence, Case Investigation "Why this fired" panel, the dedicated Lineage Explorer page (#32), AND on Alert Queue / My Queue / Investigations / Customer 360 / Network Explorer / Sanctions Screening / Rule Performance / Run History / Tuning Lab / Today / Executive Dashboard / AI Assistant / Analyst Review Queue inline columns + breadcrumbs (Round 13). STR bundle / FINTRAC audit pack / FinCEN effectiveness pack carry the chain in their manifests. CLI: `aml lineage <case_id>` + `aml verify-decisions`. API: `GET /api/v1/runs/{run_id}/cases/{case_id}/lineage`.

### For the ML modeler
- `python_ref` rule type with security gate (callables restricted to `aml_framework.models.*`)
- MRM bundle generator (SR 26-2 / OCC Bulletin 2026-13 dossiers)
- Tuning Lab — threshold sweep with shadow diff + precision/recall
- Effectiveness Evidence Pack (FinCEN April 2026 NPRM artifact)

### For the operations team
- Multi-tenant dashboard (single process, multiple programs)
- Mobile-responsive layout
- REST API with JWT/OIDC auth, rate limiting, run persistence
- Integrations: Jira, Slack/Teams, SIEM/CEF
- Docker + Helm chart for K8s deployment

---

## Shipped Capabilities by Regulatory Regime

| Regulator / regime | What's covered |
|---|---|
| **FinCEN BSA** (US) | 6-pillar mapping including the April 2026 proposed 6th pillar; SAR/CTR exports; investigation-aggregation per the 2024 effectiveness rule |
| **FinCEN April 2026 NPRM** | Effectiveness Evidence Pack generator (`aml effectiveness-pack`) |
| **OFAC** | Fuzzy + exact name screening; SDN list refresh from upstream XML |
| **FINTRAC + OSFI** (CA) | PCMLTFA section-level citations; STR/LCTR/EFTR; OSFI B-8 alignment; TD case-study patterns spec |
| **AMLD6 + EBA** (EU) | Article-level citations; AMLA RTS JSON draft (effective July 2026); 5-year retention |
| **FCA + POCA + PSR** (UK) | UK SAR via NCA; PSR APP-fraud reimbursement signals (return-reason mining); FCA Mar 2026 SAR-backlog response |
| **FATF** | R.16 Travel Rule validator; R.15-16 crypto adaptations (`crypto_vasp` spec); Feb 2026 Cyber-Enabled Fraud typologies |
| **Wolfsberg** | Feb 2026 correspondent-banking gaps (pain.001 ingestion, submission-ready STR packages) |
| **SR 26-2 / OCC 2026-13** | MRM bundle generator for python_ref models |

---

## Test Coverage

```
test_engine.py                  108  Engine, audit ledger, hash chain, all 5 rule types
test_iso20022.py                 34  pacs.008/009 parsing
test_pain001.py                  29  Corporate batch ingestion
test_pacs004.py                  36  Payment-return ingestion + library
test_iso20022_purpose_codes.py   16  Purpose-code library + planted positive
test_travel_rule.py              29  FATF R.16 validator
test_cases_aggregator.py         34  Investigation grouping (3 strategies)
test_cases_sla.py                25  SLA classification + escalation + backlog
test_cases_str_bundle.py         23  Per-investigation ZIP determinism
test_dashboard_workflows.py      15  Audience map + executive scale + page registration
test_dashboard_tenants.py        26  Multi-tenant config validation
test_dashboard_mobile_css.py     10  Mobile responsive overlay
test_e2e_dashboard.py            30  Playwright — every page renders
test_e2e_dashboard_mobile.py      9  Mobile viewports (375/414/768)
test_dashboard_investigations    9   Investigations page wiring
test_docs_links.py               19  Link rot prevention
test_api.py                      54  FastAPI auth, runs, validation, rate limiting
test_data_sources.py             37  All 8 source types
test_generators.py               26  All export formats
test_metrics.py                  30  Metric evaluation + RAG + audience
test_integrations.py             24  Jira, Slack/Teams, SIEM/CEF
test_spec.py                     28  Spec validation + EU/UK runs + AMLD6 alignment
test_performance.py               2  10k+ row engine throughput
… plus 19 other test files       … 
```

Total (post Round 7 + dashboard plan): 1,161 tests passing, 43 test files.

Dashboard-plan tests added (2026-04-27 → 2026-04-28):
```
test_dashboard_components_helpers.py   21  Phase A — 6 helpers + namespace tests
test_dashboard_sla_integration.py      18  Phase B-1 — SLA on 3 pages
test_dashboard_outcomes_panel.py       13  Phase B-2 — funnel + regwatch
test_dashboard_audit_pack_button.py    11  Phase B-3 — FINTRAC + VoP panel
test_dashboard_drill_downs.py          17  Phase C — deep-link wiring
test_dashboard_design_consistency.py   10  Phase E — page_header + empty_state + resolvers
```

---

## What's NOT in the Framework (by design)

These are documented "won't ship" decisions, not gaps:

- **Generative AI rule-*authoring*** (English → YAML rule). Would destroy the "human-readable spec written by a human" moat that's the framework's whole differentiation. *The dashboard's GenAI assistant (PR-K) is read-only — it answers questions about the spec + run, it does not propose rule edits. Rules stay human-authored.*
- **Native graph DB backend** (Neo4j / TigerGraph). DuckDB-with-graph-views is fast enough for FI-scale datasets, and "one binary, one DuckDB file" deployability is the moat.
- **Alert-scoring ML model in-tree**. Would erode the deterministic re-run guarantee that the MRM bundle (PR #53) builds on. We document the `python_ref` seam; institutions ship their own model.

See `memory/project_round5to9_plan.md` (private) for the full "three new traps" rationale.

---

## Open Items

- Issue #66 — closed 2026-04-27 (PR #70 mobile-responsive)
- Issue #68 — closed 2026-04-30 (PR #159 / PR-J). Docs-sweep half: only `dashboard-tour.md` had drifted; fixed + added `test_dashboard_tour_coverage.py` so future drift fails CI immediately rather than waiting 30 days for a manual sweep ticket. Mobile half: confirmed already satisfied by `#66` / PR #70.
- No other tracked issues open as of this snapshot

## Round 8 / 9 — Remaining Planned Work

The deep-research-agent's 5-round plan (in `memory/project_round5to9_plan.md`) is now substantially shipped. Round 10 (data-layer hardening) closed the cross-border information-sharing item (9.5) by shipping the spec syntax + CLI + dashboard surface (PR-DATA-10a/b). Status as of 2026-05-02:

| Round | Item | Estimate | Status |
|---|---|---|---|
| 8.1 | UK APP-fraud spec | 3d | shipped — Round 7 PR #76 |
| 8.2 | RTP/FedNow push-fraud detector pack | 3d | **shipped** — `examples/us_rtp_fednow/aml.yaml` |
| 8.3 | Regulatory-change diff watcher (regwatch) | 3d | shipped — Round 7 PR #74 |
| 8.4 | Fraud-AML unified case linkage | 3d | **shipped** — `cases/linkage.py` (cyber_enabled_fraud spec is the only consumer; a cross-spec example would deepen this) |
| 8.5 | Beneficial Ownership (BOI) workflow page | 3d | **shipped** — `dashboard/pages/25_BOI_Workflow.py` |
| 9.1 | FINTRAC pre-examination audit pack | 3d | shipped — Round 7 PR #78 |
| 9.2 | Open Compliance API draft | 3d | **shipped** — `api/openapi-compliance.yaml` |
| 9.3 | Guided demo CLI (`aml demo`) | 3d | **shipped** — `cli.py` |
| 9.4 | Synthetic data quality upgrade for new specs | 3d | partial |
| 9.5 | Cross-border information-sharing sandbox (FATF R.18) | 5d | **shipped** — `compliance/sandbox.py` |

The only Round-8/9 item with meaningful work left is 9.4 (~3 engineer-days) — a synthetic-data quality pass for the newer specs (`us_rtp_fednow`, `uk_app_fraud`, `trade_based_ml`) so each ships with its own planted-positives demo run, not just the inherited `community_bank` data. 8.4 is flagged "shipped but partial" because the unified case-linkage code is in but only `cyber_enabled_fraud` exercises it; a fraud↔AML cross-spec example would be the next deepening step.

---

## Documentation Index

Every doc has a single-line "use when" hook in [`README.md`](../README.md). The full set:

- `README.md` — hub-style entry point with documentation map
- `docs/getting-started.md` — 15-min onboarding path
- `docs/architecture.md` — reference design
- `docs/dashboard-tour.md` — all 42 operational pages organized by workflow (drift-protected by `test_dashboard_tour_coverage.py`)
- `docs/jurisdictions.md` — US / CA / EU / UK / crypto / cyber-fraud specs
- `docs/personas.md` — role-based workflows
- `docs/spec-reference.md` — field-by-field `aml.yaml` guide
- `docs/api-reference.md` — REST endpoint catalogue
- `docs/audit-evidence.md` — evidence bundle specification
- `docs/metrics-framework.md` — metric types, RAG, audience routing
- `docs/regulator-mapping.md` — coverage matrix
- `docs/deployment.md` — Docker + Helm
- `docs/case-studies/` — TD 2024 enforcement walkthrough
- `docs/progress.md` — this file
