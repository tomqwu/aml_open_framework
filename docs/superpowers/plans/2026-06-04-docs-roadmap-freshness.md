# Docs & Roadmap Freshness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the docs/screenshots fully current with what's shipped (v0.1.50), and surface the un-tracked ML/AI roadmap (Next/Later tiers) as GitHub issues so "what hasn't been done yet" is visible and assignable.

**Architecture:** Pure documentation + issue-filing remediation from a verified audit (4 parallel auditors + trust-but-verify reconciliation). No production code changes. Each task fixes one confirmed gap and is guarded by the relevant doc test where one exists (`test_dashboard_tour_coverage.py`, `test_docs_links.py`, `test_docs_cli_coverage.py`).

**Tech Stack:** Markdown, Playwright (one screenshot regen), `gh` CLI, pytest.

---

## Verified gap inventory (the audit, reconciled)

| # | Gap | Evidence | Test-enforced? |
|---|---|---|---|
| G1 | Stale page counts | `CLAUDE.md:182` "43…41 operational"; `README.md:103` "41 operational pages"; `README.md:179` "43 pages: 41 operational". Reality: **44 files / 42 operational** (`dashboard-tour.md:3` already correct). | No (prose) |
| G2 | `docs/screenshots/0_start.png` is stale | Captured ~2h before the Direction-C mobile redesign (#493); shows the OLD Start layout, not the ink-hero + bottom tab bar now live in v0.1.50. | `test_docs_links.py` (link not broken — but image is stale) |
| G3 | 12 page screenshots exist but aren't embedded in the tour | `22,23,24,32,44,45,46,47,48,49,50,52_*.png` exist in `docs/screenshots/` but no `![…](screenshots/…)` in `dashboard-tour.md` (incl. NEW **Triage Queue** `52_triage_queue.png`). | No |
| G4 | Audience-table persona row missing | Tour claims "13 distinct personas" but the table shows **12** rows — `data_engineer` ("Data Engineer") is absent. | Count string is tested (passes); table completeness is not |
| G5 | progress.md missing the mobile Direction-C entry | `progress.md:23-27` covers only the FIRST ☰ z-index nav fix; the **Direction-C redesign** (bottom tab bar, full-bleed, Start ink hero) + the **v0.1.48/49/50** deploys are undocumented. | No |
| G6 | Roadmap Next/Later tiers are untracked | All Now-tier (N1, M1–M4) shipped; **zero GH issues** exist for the 4 Next-tier + 3 Later-tier roadmap items. | No |
| G7 (opt) | No how-to recipes for the new features | `enable-prioritization` / `run-champion-challenger` / `point-in-time-enrichment` are in spec-reference + README but lack task-oriented how-tos. Low priority. | No |

> Discarded (auditor error, verified false): a claim that M4 lives in `engine/point_in_time.py` — it does not exist; M4 is in `spec/models.py` + `generators/sql.py`. No action.

## File Structure

- **Modify** `CLAUDE.md`, `README.md` — page counts (G1).
- **Replace** `docs/screenshots/0_start.png` — regen (G2).
- **Modify** `docs/dashboard-tour.md` — 12 screenshot embeds (G3) + 1 persona row (G4).
- **Modify** `docs/progress.md` — Direction-C entry (G5).
- **Create** GH issues (G6) — no file.
- **Create** `docs/how-to/*.md` ×3 (G7, optional).

---

### Task 1: Fix stale page counts (G1)

**Files:** Modify `CLAUDE.md:182`, `README.md:103`, `README.md:179`

- [ ] **Step 1: Confirm the true count**

Run: `ls src/aml_framework/dashboard/pages/*.py | grep -v __init__ | wc -l`
Expected: `44`. (Of these, 2 are TOUR_EXEMPT navigation surfaces — Start, Today — so 42 operational. `docs/dashboard-tour.md:3` already says "42 purpose-built pages (44 page files on disk)".)

- [ ] **Step 2: Edit the three stale strings**

`CLAUDE.md:182` — change `43 Streamlit pages across 8 categories (41 operational + 2 navigation surfaces Start here/Today)` → `44 Streamlit pages across 8 categories (42 operational + 2 navigation surfaces Start here/Today)`.

`README.md:103` — change `All 41 operational pages (+2 nav surfaces Start here/Today)` → `All 42 operational pages (+2 nav surfaces Start here/Today)`.

`README.md:179` — change `Streamlit web dashboard (43 pages: 41 operational + Start here/Today, …)` → `Streamlit web dashboard (44 pages: 42 operational + Start here/Today, …)`.

- [ ] **Step 3: Verify no stale strings remain + tour test still green**

Run: `grep -nE "41 operational|43 (Streamlit )?page|43 pages" README.md CLAUDE.md`
Expected: no matches.
Run: `.venv/bin/python -m pytest tests/test_dashboard_tour_coverage.py tests/test_docs_links.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: correct dashboard page counts to 44/42 (Triage Queue + Start added)"
```

---

### Task 2: Regenerate the stale Start screenshot (G2)

**Files:** Replace `docs/screenshots/0_start.png`

- [ ] **Step 1: Launch the current dashboard**

Run: `.venv/bin/aml dashboard examples/community_bank/aml.yaml --port 8570 > /tmp/fresh_dash.log 2>&1 &`
Poll until `curl -s -o /dev/null -w "%{http_code}" http://localhost:8570/` returns `200`.

- [ ] **Step 2: Capture the new Start (Direction-C) hero**

Run this Playwright capture (mirrors `scripts/capture_dashboard_screenshots.py`'s dynamic resize):

```python
# /tmp/cap_start.py
from playwright.sync_api import sync_playwright
OUT = "docs/screenshots/0_start.png"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto("http://localhost:8570/", wait_until="load", timeout=30000)
    page.wait_for_selector("[data-testid='stHeading'], h1", state="visible", timeout=20000)
    page.wait_for_timeout(1800)
    h = page.evaluate("() => { const m=document.querySelector('[data-testid=\"stMain\"]'); return m?m.scrollHeight:900; }")
    page.set_viewport_size({"width": 1440, "height": min(max(int(h)+80, 900), 16000)})
    page.wait_for_timeout(400)
    page.screenshot(path=OUT, full_page=True)
    print("h1:", page.inner_text("h1")); b.close()
```
Run: `.venv/bin/python /tmp/cap_start.py`
Expected: prints `h1: Start here` (or the ink-hero wordmark); the PNG now shows the current Start with the ink-hero band + stat cards.

- [ ] **Step 3: Eyeball it (REQUIRED — assert perceivable, not just present)**

Open `docs/screenshots/0_start.png` and confirm it shows the **current** Start (ink hero / "Show me it's real" / stat cards), not the old plain layout. If it's wrong, fix the capture and re-run. Then `pkill -f 8570`.

- [ ] **Step 4: Verify + commit**

Run: `.venv/bin/python -m pytest tests/test_docs_links.py -q` → PASS (the `![Start here](screenshots/0_start.png)` link still resolves).
```bash
git add docs/screenshots/0_start.png
git commit -m "docs: regenerate Start screenshot for the Direction-C mobile redesign"
```

---

### Task 3: Embed the 12 missing page screenshots in the tour (G3)

**Files:** Modify `docs/dashboard-tour.md`

- [ ] **Step 1: Recompute the exact not-embedded list**

Run:
```bash
for f in docs/screenshots/*.png; do b=$(basename "$f"); grep -q "$b" docs/dashboard-tour.md || echo "$b"; done | grep -vE "ca_|eu_|sidebar|workflows/|00_today.png|0_start.png"
```
Expected (verified 2026-06-04): `22_analyst_review_queue.png 23_tuning_lab.png 24_investigations.png 32_lineage_explorer.png 44_decision_trail.png 45_fp_analysis.png 46_experiment_tracking.png 47_threshold_sensitivity.png 48_equivalence.png 49_anomaly_discovery.png 50_drift_monitor.png 52_triage_queue.png`. (Exclude `00_today.png` — Today is a TOUR_EXEMPT nav surface; `0_start.png` is already embedded.)

- [ ] **Step 2: Add a screenshot embed under each matching `### ` section**

For each file above, find its tour section heading and add the image immediately after the section's descriptive paragraph. Section title ↔ file mapping (titles are the page's tour heading):
- `### Triage Queue` → `![Triage Queue](screenshots/52_triage_queue.png)`
- `### Analyst Review Queue` (heading may be "Analyst Review Queue (…)") → `![Analyst Review Queue](screenshots/22_analyst_review_queue.png)`
- `### Tuning Lab` → `![Tuning Lab](screenshots/23_tuning_lab.png)`
- `### Investigations` (heading "Investigations (Round-6)") → `![Investigations](screenshots/24_investigations.png)`
- `### Lineage Explorer` → `![Lineage Explorer](screenshots/32_lineage_explorer.png)`
- `### Decision Trail` → `![Decision Trail](screenshots/44_decision_trail.png)`
- `### FP Analysis` → `![FP Analysis](screenshots/45_fp_analysis.png)`
- `### Experiment Tracking` → `![Experiment Tracking](screenshots/46_experiment_tracking.png)`
- `### Threshold Sensitivity` → `![Threshold Sensitivity](screenshots/47_threshold_sensitivity.png)`
- `### Equivalence` → `![Equivalence](screenshots/48_equivalence.png)`
- `### Anomaly Discovery` → `![Anomaly Discovery](screenshots/49_anomaly_discovery.png)`
- `### Drift Monitor` → `![Drift Monitor](screenshots/50_drift_monitor.png)`

(Match the existing embed style in the file, e.g. `![Alert Queue](screenshots/03_alert_queue.png)`. If a heading text differs slightly, grep for it: `grep -n "^### " docs/dashboard-tour.md`.)

- [ ] **Step 3: Verify links resolve + tour count unchanged**

Run: `.venv/bin/python -m pytest tests/test_docs_links.py tests/test_dashboard_tour_coverage.py -q`
Expected: PASS (every new `![…](screenshots/…)` points at an existing file; the `**42 purpose-built pages**` count is untouched).
Run: `for f in docs/screenshots/*.png; do b=$(basename "$f"); grep -q "$b" docs/dashboard-tour.md || echo "still missing: $b"; done | grep -vE "ca_|eu_|sidebar|workflows/|00_today.png"`
Expected: no output (all page screenshots now embedded).

- [ ] **Step 4: Commit**

```bash
git add docs/dashboard-tour.md
git commit -m "docs(tour): embed the 12 page screenshots that had files but no references"
```

---

### Task 4: Add the missing Data Engineer persona row (G4)

**Files:** Modify `docs/dashboard-tour.md` (the audience-filtering table, ~line 324)

- [ ] **Step 1: Confirm the missing persona**

Run: `.venv/bin/python -c "from aml_framework.dashboard.audience import AUDIENCE_PAGES; print(len(AUDIENCE_PAGES), sorted(AUDIENCE_PAGES))"`
Expected: `13` personas including `data_engineer`. Then `grep -c "^| \*\*" docs/dashboard-tour.md` shows the table has 12 persona rows → `data_engineer` is the missing one.

- [ ] **Step 2: Add the row**

In the audience-filtering table (after the existing rows), add a Data Engineer row using that persona's first ~3 pages from `AUDIENCE_PAGES["data_engineer"]` (read them): e.g.
```
| **Data Engineer / Head of Data** | Data Integration → Data Quality → Customer 360 → Lineage Explorer |
```
(Use the actual page titles from `AUDIENCE_PAGES["data_engineer"]`.)

- [ ] **Step 3: Verify + commit**

Run: `.venv/bin/python -m pytest tests/test_dashboard_tour_coverage.py -q` → PASS (the "13 distinct personas" string is unchanged; the table now matches it).
```bash
git add docs/dashboard-tour.md
git commit -m "docs(tour): add the missing Data Engineer persona row to the audience table"
```

---

### Task 5: progress.md — record the mobile Direction-C redesign (G5)

**Files:** Modify `docs/progress.md`

- [ ] **Step 1: Add a new top entry**

The existing entry (`progress.md:23-27`) covers only the first ☰ z-index nav fix. Add a new `> **…**:` blockquote entry at the very top (newest-first, `---`-separated), summarizing: the **mobile Direction-C redesign** (a `/huashu-design` session that mocked 3 directions; the user picked C) — a persistent **bottom tab bar** (Today · Alerts · Cases · Audit · More) injected in `app.py` as `target="_top"` anchor links with the active tab computed server-side from `pg.url_path`; **full-bleed** mobile (removed the dark side-gutters); a **minimal mobile topbar**; and the **Start ink-hero band + live stat cards**. Note the discoverability iteration (faint chevron → obvious ☰ button → bottom nav) and the testing lesson (a passing tap-by-selector e2e gave a false green; new tests assert `is_visible()` + in-viewport bbox). Record the deploys: **v0.1.48/v0.1.49** (Start screen + ☰ menu) and **v0.1.50** (Direction-C), both rolled to `ca-aml-api-dev` + `ca-aml-dashboard-dev` and smoke-verified at 375px. Refresh the snapshot date to 2026-06-04 if needed.

- [ ] **Step 2: Verify links + commit**

Run: `.venv/bin/python -m pytest tests/test_docs_links.py -q` → PASS.
```bash
git add docs/progress.md
git commit -m "docs(progress): record the mobile Direction-C redesign + v0.1.48-50 deploys"
```

---

### Task 6: File GitHub tracking issues for the un-tracked roadmap (G6)

**Files:** none (GH issues)

> The Now tier (N1, M1–M4) is fully shipped and closed. The Next + Later tiers have **zero** issues. File one tracking issue per item so the backlog is visible/assignable. Reference the roadmap spec on the `design/mlai-roadmap` branch.

- [ ] **Step 1: File the 4 Next-tier issues**

```bash
gh issue create --title "Roadmap (Next): equivalence divergence clustering" --label "enhancement" --body "ML/AI roadmap Next tier. The 4-way equivalence classifier (engine/equivalence.py: MATCH/NEW_ONLY/LEGACY_ONLY/DIFF) exists, but NOT the shape-based **clustering** of NEW_ONLY/LEGACY_ONLY divergences so a DS triages defects in minutes, not weeks. Highest-value Next item per the 2026-06-04 freshness audit. Roadmap: design/mlai-roadmap:docs/superpowers/specs/2026-06-02-aml-mlai-roadmap-design.md."
gh issue create --title "Roadmap (Next): ML FP-reduction + risk segmentation (governed suppression)" --label "enhancement" --body "ML/AI roadmap Next tier (Pillar 5). Customer-cohort segmentation + per-segment thresholds/eligibility so ML can de-prioritize/suppress (never auto-close) — addresses investigator overload. NOT STARTED. Roadmap: design/mlai-roadmap spec."
gh issue create --title "Roadmap (Next): typology auto-discovery → candidate-rule pipeline" --label "enhancement" --body "ML/AI roadmap Next tier (Pillar 7). Unsupervised clustering of unexplained activity into candidate typologies that flow through spec → validation → approval → promotion. NOT STARTED. Roadmap: design/mlai-roadmap spec."
gh issue create --title "Roadmap (Next): model-risk monitoring automation (drift/outcome lifecycle)" --label "enhancement" --body "ML/AI roadmap Next tier (Pillar 7). M3 shipped champion-challenger outcome artifacts; extend to a full automated drift/outcome/approval lifecycle as evidence artifacts. PARTIAL. Roadmap: design/mlai-roadmap spec."
```

- [ ] **Step 2: File the 3 Later-tier issues**

```bash
gh issue create --title "Roadmap (Later): graph-ML mule-ring detection on the entity network" --label "enhancement" --body "ML/AI roadmap Later tier. Graph-ML over the resolved-entity network (Network Explorer exists; graph ML doesn't) for mule-ring/community detection. NOT STARTED."
gh issue create --title "Roadmap (Later): GenAI investigation copilot (governed, SR-26-2 carve-out)" --label "enhancement" --body "ML/AI roadmap Later tier. A governed GenAI copilot (summarize case / what typology / show the mule network) with human-reviewed-draft governance under the SR-26-2 GenAI carve-out (SR 11-7 / E-23 / SS1/23). NOT STARTED."
gh issue create --title "Roadmap (Later): buyer-segment specs (AUSTRAC Tranche 2, GENIUS/PPSI)" --label "enhancement" --body "ML/AI roadmap Later / buyer tier. New example specs for AUSTRAC Tranche 2 DNFBPs and GENIUS Act PPSI stablecoin issuers. NOT STARTED."
```

- [ ] **Step 3: Verify**

Run: `gh issue list --state open --json number,title --jq '.[] | "#\(.number) \(.title)"'`
Expected: the 7 new roadmap issues listed.

---

### Task 7 (OPTIONAL): How-to recipes for the new features (G7)

> Low priority — these features are documented in `spec-reference.md` + README (and pass `test_docs_cli_coverage.py`); how-tos are a discoverability nicety. Do only if explicitly requested.

**Files:** Create `docs/how-to/enable-prioritization.md`, `docs/how-to/run-champion-challenger.md`, `docs/how-to/point-in-time-enrichment.md`

- [ ] **Step 1:** For each, follow the existing how-to template (read `docs/how-to/add-a-rule.md` for the "When you need this / Prereqs / Time / Steps / Verify / Common problems / Next steps" skeleton) and write the recipe: (a) enable `program.prioritization`, (b) `aml run --labels labels.csv --challenger-weights '{…}'` → `priority_outcome.json`, (c) declare `effective_dated` + an `aggregation_window.enrich` as-of join.
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/test_docs_links.py tests/test_docs_cli_coverage.py -q` → PASS.
- [ ] **Step 3:** Commit `docs(how-to): recipes for prioritization, champion-challenger, point-in-time`.

---

## Self-Review

**Spec coverage:** every confirmed audit gap maps to a task — G1→T1, G2→T2, G3→T3, G4→T4, G5→T5, G6→T6, G7→T7 (optional). The discarded false claim (`engine/point_in_time.py`) is explicitly excluded.

**Placeholder scan:** none — exact file:line targets, the literal before/after strings for the counts, the verified screenshot list, the exact `gh issue create` commands, and the enforcing-test commands are all concrete. The two places needing live lookup (the data_engineer page titles in T4; the exact tour heading text in T3) carry an explicit grep/read step rather than a guess.

**Type/string consistency:** "44 files / 42 operational" is used consistently (T1) and matches `dashboard-tour.md:3` (already correct, left untouched). Screenshot filenames in T3 match the verified `ls` output. Issue titles in T6 match the roadmap tiers in the audit table.

## PR / wrap-up

- This is docs + issues only — no runtime change → **no Azure deploy** (the docs-deploy workflow republishes the MkDocs site on merge automatically).
- Drive through Codex + CI + merge per the repo gate. The roadmap-issue task (T6) needs no PR — the `gh issue create` calls can run before/after the docs PR merges.
