# First-Run "Golden Thread" Experience — Design

**Date:** 2026-06-04
**Status:** Approved (brainstorm) → ready for implementation planning
**Problem owner:** the app is shown cold to executives, engineers, and peers who "have no idea what it does" on first look and are overwhelmed by ~44 dashboard pages.

## Problem

When the dashboard is opened cold, a first-time viewer is dropped onto an **operational page** with the **full 44-page sidebar visible** and the persona selector defaulted to **"All pages"** — the most overwhelming possible view. A capable Welcome page exists (`pages/0_Welcome.py`) with a strong one-liner, but it is **not the front door**, is long and text-heavy, and competes with everything else. Net effect: viewers can't answer "what is this?" in the first minute and bounce on the feature count.

**Compounding bug — mobile has no usable navigation.** On a phone viewport the sidebar auto-collapses and the expand control is **intercepted by an overlay** (confirmed by the workaround in `tests/test_e2e_dashboard_mobile.py:63-70`, which navigates by typing URL slugs instead of clicking the menu). A real user on a phone is stranded on whatever page loaded — the harshest version of the same problem, and currently masked by tests that "cheat."

## Goal (the one decision that shapes everything)

A cold viewer should **"instantly get it"** — understand *what this is and why it matters* in ~10 seconds, before any features — then see **proof it's real** via live data, then be gently handed the app. Comprehension first; overwhelm killed.

Decisions locked during brainstorming:
- **One universal message** — a single plain-language sentence, no role branching.
- **Next move = "show me it's real"** — a narrated walk over one *live* example (alert → case → audit), not a slideshow.
- **Delivery = in-app** — a first-run experience inside the Streamlit app (where the confusion happens), using real run data.
- **Mobile nav must genuinely work** — the real native menu, not a band-aid.

## The Experience

A new full-canvas **Start** screen becomes the **default landing** (replacing the drop-onto-an-operational-page). It shows exactly three things:

1. **One sentence:** *"An anti-money-laundering program you can show your regulator — without a six-week reconstruction."*
2. **One-breath "how":** *"You write the rules once. It runs them, builds the cases, and keeps a tamper-proof record of everything."*
3. **One primary button:** **▶ Show me it's real (90 seconds)** + a quiet *Skip to the app →*.

### The Golden Thread (the button plays this)

A narrated walk over **one real planted case from the live run** — canonical choice **C0001, a structuring pattern** (most universally understood typology). Four beats, each = **one real on-screen panel + one sentence of narration**, advanced by a single **Next →**:

1. **"The engine caught this."** The alert in plain English — *"12 cash deposits just under $10,000 in 6 days — classic structuring."* (real alert from the run)
2. **"Here's the case your team works."** The case view — customer, evidence, timeline — *"Everything an investigator needs is already assembled."*
3. **"Here's what you hand the regulator."** The audit trail + hash chain — *"Every decision, replayable byte-for-byte. No six-week reconstruction."*
4. **"Now it's yours."** Two calm doors: **Explore for my role →** (the existing persona selector) and **Browse all tools →**, plus *Replay the tour.*

The 44 pages stay **completely out of sight until Beat 4**. It is one real example, not a mockup — if the run produced that case, the viewer is looking at live data.

## Architecture & Components

Follows the codebase's existing pure-logic/thin-page split (the M1 `dashboard/triage.py` ↔ `pages/52_Triage_Queue.py` pattern).

### 1. `dashboard/golden_thread.py` — pure builder (no `streamlit` import)
- **Responsibility:** given the already-cached run state, select the canonical example and shape the four beats.
- **Interface:** `build_beats(run_state) -> list[Beat]`, where `Beat = {title, narration, panel_kind, payload}` (`payload` = the real alert dict / case dict / audit summary).
- **Selection rule (deterministic, never crashes):** prefer the planted structuring case `C0001` → else highest-`priority_score` alert → else any alert → else a friendly "this run produced no alerts" beat.
- **Dependency:** reads the cache `state.py` already populates (alerts, cases, audit). Streamlit-free → unit-testable under `.[dev]` (add `pytest.importorskip("pandas")` only if it touches pandas).

### 2. `pages/0_Start.py` — thin renderer
- **Responsibility:** render the current beat + wizard controls; nothing else.
- Full-canvas (no sidebar reliance → works on a phone regardless of the nav bug).
- Wizard state in `st.session_state["gt_beat"]`; `Next →` / `Skip to the app →` / Beat-4 doors / *Replay the tour*.
- Uses the existing `page_header` / `page_footer` / `section_explainer` conventions so the guard tests pass with no special-casing.

### 3. `app.py` — default to Start + tame the post-tour view
- `Start` becomes the **first page** in `st.navigation` (Streamlit lands on the first page).
- **Skip / Done lands on the existing `Today` page** (the returning-user daily view) — a concrete, already-curated surface, *not* "All pages" — so even a skipper doesn't hit the 44-page wall. (We reuse Today rather than invent a new "home.")
- The persona selector default is left as-is; the deferral comes from Start being the front door + Skip routing to Today, not from changing persona defaults.
- **Retire `pages/0_Welcome.py`**, folding its best content into Start — avoids three competing intro surfaces (Welcome / Today / Start).

### Gating / persistence
Start always renders, but remembers completion in `st.session_state` so it doesn't nag within a session; a persistent **Replay the tour** lives on Start (and Today). True once-per-browser (localStorage) is an **optional** nicety, explicitly *not* a dependency — a returning user seeing a calm Start page with a Replay button is acceptable.

### Data flow
`state.py` runs the engine once and caches alerts/cases/audit → `golden_thread.py` reads that cache and shapes beats → `pages/0_Start.py` renders. All live, no mocks.

## Mobile Navigation Fix (bundled)

The Golden Thread rescues the *first* impression on a phone (it's full-canvas). This work also fixes the underlying dead end so the app is usable after.

- **Diagnose first (empirical):** probe a real 375px viewport to confirm exactly what intercepts the tap on the collapsed-sidebar expand control. Hypothesis: a higher-`z-index` sticky top-bar/header covers it (the CSS at `components.py:414-422` already forces the control *visible*, so it's present-but-unclickable).
- **Proper fix (headline requirement):** correct the `z-index` / `pointer-events` stacking so the **real native Streamlit menu control is tappable on a phone**. This is the genuine mobile-nav fix the user asked for.
- **Version-proof insurance (kept underneath):** an explicit in-canvas **"☰ Menu"** affordance (expander or compact page-jump `selectbox` of the visible pages) that doesn't depend on the intercepted control — also aids desktop discoverability. Secondary to the native fix.

## Error Handling

- All fallbacks live in the pure builder (testable): missing `C0001` → priority fallback → any alert → friendly no-alerts beat. Start **never** errors regardless of spec.
- A beat panel missing a field → render what's present, skip the rest; narration always shows.

## Testing

- **Unit** (`tests/test_golden_thread.py`): deterministic beat selection; each fallback tier; zero-alert run yields the friendly beat with no crash.
- **Page-convention tests:** Start satisfies the existing header/footer/section-explainer guards.
- **Mobile e2e (the one that matters):** on 375px, (1) Start renders and `Next →` advances through all four beats; (2) **tapping the real menu control navigates to another page** — replacing the URL-slug cheat so the dead end can't silently return.
- **Desktop e2e + screenshot** of Start for the tour docs.
- **Docs:** `docs/dashboard-tour.md` (add Start, retire Welcome, keep the page-count test honest), `README.md` first-impression note, `docs/progress.md` round entry.

## Out of Scope (YAGNI)

- Role-branched messaging (decided: one universal message).
- A separate static/marketing landing stack (decided: in-app, where the confusion is).
- A guided multi-page click-through tour beyond the 4 fixed beats.
- localStorage once-per-browser persistence (optional, not required).

## Success Criteria

- A cold viewer lands on Start, reads one sentence + one button, and can play a 4-beat live alert→case→audit story without touching the sidebar.
- The 44 pages are invisible until the viewer asks for them (Beat 4 / Skip).
- On a 375px phone, a real tap on the menu navigates between pages (proven by e2e).
- Exactly one intro surface (Start); Welcome retired; Today unchanged as the returning-user view.
