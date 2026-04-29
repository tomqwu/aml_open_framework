# Export formats — what we ship and why

## TL;DR

| Format | Status | When to use |
|---|---|---|
| **HTML (live deck)** | ✅ shipped — `index.html` | Default. Browser presentation, fullscreen, keyboard nav |
| **PDF** | ✅ shipped — `aml-open-framework-v2.pdf` | Email attachment, print, share-link, regulator submission |
| **PPTX (editable)** | ⛔ skipped (see below) | — |

## Why no editable PPTX

The skill's `html2pptx.js` translator imposes 4 hard constraints on the source HTML — and the V2 deck violates all four because it was authored as a designer-grade HTML deck, not a pptxgenjs target:

1. **Body must be 960pt × 540pt** (LAYOUT_WIDE).
   V2 is 1920px × 1080px (the standard "designer canvas"). 19 slides would all need re-sizing.
2. **No CSS gradients.**
   V2 uses `linear-gradient` for terminal chrome (10+ slides), and the chrome IS the design signature.
3. **All text in `<p>` / `<h1-h6>` / `<ul>` / `<ol>`.**
   V2 has hundreds of `<div>`-direct text nodes (eyebrows, slide numbers, captions, table cells). Every one would need a wrapper.
4. **Backgrounds/borders only on `<div>`, not on text tags.**
   V2 puts borders on `.eyebrow`, panels, terminal blocks — many would need re-structuring.

The skill doc estimates "**2-3 hours per slide**" for retrofit = 40-60 hours for 19 slides, and the retrofit produces a stripped-down deck (no terminal chrome shadow, no gradients, simpler layouts) that loses the visual signature that makes V2 read as "designer-grade."

## What you can do instead

If a colleague wants to **edit copy**:
- Open `slides/<n>-<name>.html` directly. Plain HTML, plain CSS — any text editor.
- Re-render via `bash _render.sh` (Playwright + Chrome required).

If they want to **re-arrange slides**:
- Edit `index.html` `DECK_MANIFEST` array.

If they want to **embed in their own PowerPoint**:
- Best path: export the PDF, "Insert → Object → from File → PDF" into their PPTX, page by page. Loses interactivity but keeps fidelity.
- Or: open each slide HTML, screenshot, paste image into PowerPoint.

If we ever need a true editable PPTX in the future, the right call is:
- Author a **separate PPTX-friendly variant from scratch** following the 4 constraints
- Don't try to retrofit V2

This is the same trade-off the skill itself documents (`references/editable-pptx.md` § "Why 4 hard constraints aren't a bug, they're a physical PPTX format constraint").
