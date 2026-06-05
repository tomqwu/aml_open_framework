# 10-Hour Autonomous Marathon Plan (2026-06-04 → 06-05)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Execute continuously, NO prompts to the user. Release stable increments to Azure as each workstream goes green. Steps use `- [ ]` tracking.

**Goal:** In ~10 hours of unattended work: land the in-flight feature, make the mobile/first-impression genuinely easy on an executive's eye, fix the known responsive bugs, keep docs current, drain the roadmap backlog — and deploy each stable increment.

**Architecture:** Independent workstreams, each its own branch → PR → Codex → CI → local e2e (for dashboard changes) → merge → tag+deploy. Front-load the user's named priorities (W1 mobile-for-execs, W2 responsive bug-fix, W3 docs). W4 drains roadmap features only after W1–W3 are shipped. Every dashboard change runs `make ci-e2e` locally before merge ([[project_e2e_only_on_main_push]]).

**Tech Stack:** Streamlit dashboard + brand tokens in `components.py`, FastAPI, pydantic v2 spec, DuckDB engine; Playwright e2e; ACR + Azure Container Apps deploy.

**Governance:** This is a compliance framework — every change keeps determinism, advisory-only ML, PII-masking, and audit invariants. No feature auto-closes alerts. Run the full local CI gate before each push.

**Release discipline:** bump `vX.Y.Z`, `az acr build` from a CLEAN MAIN WORKTREE (not a feature branch), roll both container apps, smoke `/api/v1/health`. Batch a deploy per merged workstream (not per commit).

---

## Workstream 0 — Land #495 (in flight)

**State:** PR #504 open (draft), local e2e green (186 passed), gate green (3633 passed, 99.02%), final review READY TO MERGE, Codex running.

- [ ] Read the Codex verdict (`b3fto3a5a` output). Fix any P1/P2 (fresh implementer → re-review → re-run Codex). If clean: mark #504 ready, confirm CI green + mergeable, squash-merge, delete branch.
- [ ] Sync main; fold #495 into the next deploy (W1 or a standalone tag if W1 will be long).

---

## Workstream 1 — Mobile, easy on an executive's eye (NAMED PRIORITY)

**Why:** Executives open the app on a phone and must instantly grasp "what is this and is it credible," with zero AML jargon overload. Builds on the Direction-C ink-hero Start screen + bottom tab bar + Golden Thread already shipped.

**Branch:** `feat/mobile-exec-polish`

**Discovery first (one Explore subagent):** capture the CURRENT mobile state — screenshot the Start screen + 4 core pages (Today, Alert Queue, Cases/Investigations, Audit & Evidence) at iPhone-SE (375px) and a phone (390px) via Playwright; list every spot where (a) text is below ~14px or low-contrast, (b) a control/table overflows horizontally, (c) the first screen doesn't answer "what does this do" within 5 seconds, (d) the bottom tab bar overlaps content. Output a ranked defect list with screenshots.

Then, per defect (subagent-driven, each its own commit, TDD where a test exists):
- [ ] **Exec-readable typography pass** — ensure mobile body text ≥14px, headings legible, the ink-hero lede passes WCAG AA on the cream + dark canvases (extend `tests/test_dashboard_dark_theme.py` source-pins where applicable). Tighten `@media (max-width:640px)` rules in `components.py`.
- [ ] **5-second clarity on the Start screen** — verify the hero answers what/why/proof above the fold on a phone (headline + one-line lede + 3 stat tiles + one primary CTA), nothing else competing. Trim any jargon. Keep the Golden Thread one tap away.
- [ ] **Bottom-tab-bar + content-spacing fixes** — ensure no page's content hides behind the sticky tab bar; safe-area padding bottom.
- [ ] **Per-page mobile sweep** — for each of the 4 core pages, ensure no horizontal overflow at 375px and primary controls meet the 44px tap-target floor.
- [ ] **e2e:** add/adjust mobile assertions (visible + in-viewport bbox + tap-target + screenshot) — assert perceivability, not just presence ([[feedback_e2e_visibility_not_just_tappable]]). Regenerate the Start screenshot in `docs/screenshots/`.
- [ ] Docs: `docs/dashboard-tour.md` mobile note + `docs/progress.md` entry. `make ci-e2e` green. PR → Codex → merge → deploy.

**Acceptance:** an exec on a phone sees a calm, jargon-free first screen that states what the product does + offers one "show me it's real" action; no page overflows 375px; all core controls ≥44px; dark-mode + light-mode AA contrast on the hero; e2e asserts visibility (not just DOM presence) and screenshots look right on eyeball.

---

## Workstream 2 — Fix the 3 known responsive bugs (NAMED: bug fixes)

**Why:** `tests/test_e2e_dashboard_mobile.py::STRICT_STILL_FAILING` = {Executive Dashboard, Alert Queue, Audit & Evidence} genuinely fail the iPhone-SE responsive bar (inner overflow and/or sub-44px tap targets under the thin overlay). These are the PR-M2..M6 backlog.

**Branch:** `fix/mobile-responsive-pages` (may fold into W1's branch if touching the same CSS — decide at execution time to avoid churn).

Per page (Executive Dashboard, Alert Queue, Audit & Evidence):
- [ ] Reproduce the exact failure (run the strict-xfail param for that page; capture the overflow px / undersized control).
- [ ] Fix the real cause in CSS/layout (wide table/chart → `overflow-x`/max-width scoping in `components.py`; undersized control → uniform 44px). Do NOT weaken the assertion, raise tolerance, or drop pages.
- [ ] Promote the page out of `STRICT_STILL_FAILING` (the strict-xfail contract: a fixed page becomes a hard pass in the same change).
- [ ] `make ci-e2e` green (all responsive params pass, 0 in STRICT_STILL_FAILING ideally). PR → Codex → merge → deploy.

**Acceptance:** `STRICT_STILL_FAILING` is empty (or only contains pages with a documented, genuinely-hard constraint); full e2e green; no weakened checks.

---

## Workstream 3 — Docs freshness + bug sweep (NAMED: docs/bugs)

**Branch:** `docs/freshness-and-bugfix-sweep`

- [ ] Run a freshness audit (one subagent): page counts, screenshots vs current UI, `docs/progress.md` up to date through v0.1.51+, roadmap status (#494/#495 done), any stale version strings. Mirror the 2026-06-04 freshness-audit method.
- [ ] Fix every gap found; regenerate stale screenshots.
- [ ] Opportunistic bug sweep: run the full suite + `ruff`; triage any flaky/edge warnings; grep for obvious correctness smells in recently-touched engine code (suppression/clustering) — fix real bugs only, mention (don't fix) unrelated ones.
- [ ] Docs-coverage tests green. PR → Codex → merge (docs-only may skip deploy; the docs-deploy workflow republishes MkDocs).

**Acceptance:** docs tests green; progress.md current; no stale counts/screenshots; any real bug found is fixed with a test.

---

## Workstream 4 — Drain roadmap "everything else" (only after W1–W3 shipped)

Pick highest-value first; each is a full brainstorm-light design → plan → subagent-driven build → PR → Codex → CI → e2e → merge → deploy cycle, governed (advisory ML, deterministic, audited). Stop opening new features when <~1.5h remains; finish/stabilize what's in flight instead.

- [ ] **#497 model-risk monitoring automation** (extends M3 champion-challenger outcome artifacts into a drift/outcome/approval lifecycle as evidence) — strong fit, deterministic, governed.
- [ ] **#496 typology auto-discovery → candidate-rule pipeline** (unsupervised clustering of unexplained activity into candidate typologies flowing through spec→validation→approval; keep the engine path deterministic/stdlib, run any clustering offline as a governed artifact, NOT in the deterministic run pipeline).
- [ ] (Stretch) #498 graph-ML mule-ring, #499 GenAI copilot, #500 buyer specs — only if time remains and stable.

**Acceptance per item:** issue closed; determinism + governance invariants held; full CI + local e2e green; deployed.

---

## Continuous loop (the operating rhythm)

1. Take the highest-priority unstarted task (W0 → W1 → W2 → W3 → W4).
2. Branch; subagent-driven (fresh implementer → spec review → quality review per task).
3. `make ci-lint ci-unit ci-coverage`; for any dashboard change also `make ci-e2e` locally.
4. Push; Codex review; fix blockers; CI green; mergeable; merge; delete branch.
5. When a workstream is fully merged and main is green → tag `vX.Y.Z` + deploy (build from a clean main worktree) + smoke.
6. Update `docs/progress.md`. Never idle: while CI/e2e/build run (~15-20 min each), advance the next independent task.
7. **Release when stable:** only deploy green main; never deploy a half-built feature; features ship off-by-default until complete.

## Self-Review
- Spec coverage: docs ✓ (W3), bug fixes ✓ (W2 + W3 sweep), mobile-easy-on-exec ✓ (W1), "everything else" ✓ (W4 roadmap), release-when-stable ✓ (deploy discipline). In-flight #495 ✓ (W0).
- No-prompt: execution proceeds subagent-driven without the writing-plans execution-choice question (user mandate).
- Risk: mobile work is discovery-driven → W1/W2 start with an Explore/repro step before edits (no blind CSS changes). Determinism/governance guardrails restated for W4 ML features.
- Time-box: W4 stops opening new features at ~1.5h remaining; stabilize over start.
