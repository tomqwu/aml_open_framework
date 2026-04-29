# Board video — McKinsey-style 64s walkthrough

A 64-second board-pack-style video for AML executives (CCO · MLRO · Audit
Committee). Built ground-up from the primary-source research in
`docs/research/2026-04-aml-process-pain.md`, not by re-recording the
deck-v2 slides.

## Files

| File | Use | Size |
|---|---|---|
| `board-video.mp4` | Canonical · 1920×1080 · 25 fps · BGM mixed | 7.5 MB |
| `board-video-60fps.mp4` | High-frame-rate variant for B站 / portfolio | 7.6 MB |
| `board-video-preview.gif` | 23 s · 720 wide · X / GitHub README inline | 2.2 MB |
| `board-video.html` | Source · self-driving timeline of 8 scenes | — |
| `frame-{1..8}-*.png` | Per-scene snapshots for documentation | — |
| `_render-frames.mjs` | Helper that captures the 8 frames | — |

## Why it exists

The earlier deck-v2 walkthrough video (`../video/walkthrough.mp4`) is a
useful artifact for engineers and 2LoD reviewers — but it speaks in CLI
output and audit-chain language. That register sits poorly with a CCO,
MLRO, or Audit Committee chair.

This video re-narrates the same project for that audience. McKinsey
board-pack visual grammar:

- White background, navy ink (`#051c2c`), single warm accent (`#dd5c34`)
- All-sans typography (Inter), no editorial flourish
- "Exhibit N" label top-left of every frame
- "Source:" line bottom of every frame, citing primary publications
- Action titles (full thesis sentence with one accent word)
- KEY TAKEAWAY callout for non-trivial conclusions
- Pyramid principle — 1 thesis → 3 supporting points

## Narrative arc (8 scenes, 63 s)

| # | Exhibit | Action title | Primary source |
|---|---|---|---|
| 1 | Cover | "An AML program **every decision** can be replayed." | Synthesis of FCA / FinCEN / LexisNexis |
| 2 | The 2:1 rule | "Process and governance gaps account for **~2:1** of every consent-order finding." | TD / RBC / Wells / NatWest / Citibank consent orders 2024-25 |
| 3 | The cost in three sizes | "$3.09B / $61B / 95% — the bill arrives in three sizes." | FinCEN Oct 2024 · LexisNexis Feb 2024 · Flagright |
| 4 | What leaders actually say | Four verbatim CCO/regulator quotes (PAIN-1/2/6/8) | FCA Mar 2024 · FinCEN Oct 2024 · ACAMS · FinCEN Sep 2025 RFI |
| 5 | The thesis | "One specification serves three reviewers — **without re-translation**." | Framework spec model + FCA / K&L Gates 2024 |
| 6 | Pain → Capability map | "Each pain has a single, evidenced answer — **one file** away." | PAIN doc 1, 2, 4, 6 |
| 7 | What the operator inherits | "The framework arrives **built**, not blueprinted." | Live counts from `main` branch |
| 8 | Engagement | "The next step takes **five minutes**." | Three-paths CTA |

## Pipeline

```bash
# 1. Record harness (64s @ 1920×1080)
NODE_PATH=$(pwd)/node_modules node $SKILL/scripts/render-video.js \
  board-video/board-video.html --duration=64 --width=1920 --height=1080

# 2. Mix BGM (tutorial mood — soft ambient, low-presence; volume 55% so
#    a presenter could narrate over it without re-mixing)
ffmpeg -i board-video/board-video.mp4 -i bgm-tutorial.mp3 \
  -filter_complex "[1:a]aloop=loop=-1:size=2e+09,atrim=0:64,afade=t=in:st=0:d=0.3,afade=t=out:st=63:d=1,volume=0.55[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac board-video-bgm.mp4

# 3. 60 fps variant (frame-doubling, no minterpolate — broadest compat)
ffmpeg -i board-video.mp4 -filter:v fps=60 -c:v libx264 -crf 18 \
  -c:a copy board-video-60fps.mp4

# 4. GIF preview from 6 hero moments (~23s, 720 wide, palette-optimised)
ffmpeg -i board-video.mp4 -vf "select='lt(t,4)+between(t,9,12)+...'..." \
  board-video-preview.gif
```

## When to use which

- **Engineers / 2LoD review** → `../video/walkthrough.mp4` (deck-v2 walkthrough, CLI-heavy)
- **Board / executive committee** → `board-video.mp4` (this file)
- **Social share / X / LinkedIn** → `board-video-preview.gif` (autoloops, no audio, 23 s of hero moments)
- **B站 / portfolio reel** → `board-video-60fps.mp4` (smoother motion at 60 fps)

## Watermark

This video does **not** carry the `Created by Huashu-Design` watermark
because it is a board-pack deliverable for a real institution audience —
the watermark would read as an external producer credit and erode the
"prepared by your AML program" framing. (The skill's animation default
applies to social/promo content; for client deliverables remove it.)

## Re-recording when research updates

When `docs/research/2026-04-aml-process-pain.md` or
`docs/case-studies/td-2024.md` is revised:

1. Update the relevant scene's quote / number / source line in
   `board-video.html`
2. Re-run pipeline steps 1-4 above
3. Diff `frame-N-*.png` snapshots to confirm only the intended scene
   changed
