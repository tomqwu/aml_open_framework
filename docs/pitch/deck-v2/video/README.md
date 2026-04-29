# Deck V2 — video walkthrough

92-second auto-advance walkthrough of all 19 slides, recorded from the
real V2 deck HTMLs (no separate animation code path — what you see in the
slides at `../slides/*.html` is what plays in the video).

## Files

| File | Format | Size | Use |
|---|---|---|---|
| `walkthrough.mp4` | 1920×1080 · 25 fps · H.264 · BGM mixed | 21 MB | Canonical · embed in README, share on LinkedIn / email |
| `walkthrough-60fps.mp4` | 1920×1080 · 60 fps · H.264 · BGM | 21 MB | Higher-FPS for B站 / portfolio reels |
| `walkthrough-preview.gif` | 720 wide · 12 fps · ~22s of hero frames | 4.7 MB | X / Twitter / README preview · auto-loops |
| `walkthrough.html` | The recording harness | — | Source — drives `render-video.js` |

## How it was made

```bash
# 1. Record harness (parent HTML loads each slide in iframe, auto-advances)
NODE_PATH=$(pwd)/node_modules node $SKILL/scripts/render-video.js \
  video/walkthrough.html --duration=92 --width=1920 --height=1080

# 2. Mix BGM (educational mood — warm + inviting, fits framework teaching tone)
ffmpeg -i walkthrough.mp4 -i bgm-educational.mp3 \
  -filter_complex "[1:a]aloop=loop=-1:size=2e+09,atrim=0:92,afade=t=in:st=0:d=0.3,afade=t=out:st=91:d=1[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k walkthrough-with-bgm.mp4

# 3. 60 fps variant
ffmpeg -i walkthrough-with-bgm.mp4 -filter:v fps=60 -c:v libx264 -crf 18 \
  -c:a copy walkthrough-60fps.mp4

# 4. Short GIF preview (5 hero frames stitched, ~22s, 720 wide)
ffmpeg -i walkthrough.mp4 -vf "select=...,fps=12,scale=720:-1,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse" \
  walkthrough-preview.gif
```

## Pacing notes

Per-slide dwell time is weighted by content density (see `walkthrough.html`):

- **Hero / CTA** (01, 18, 19): 3.8–4.0 s
- **Pain panels** (02, 03): 5.0–5.2 s
- **Thesis** (04, 05): 5.0–5.5 s
- **Daily ritual** (06, 07, 08, 09): 4.8–5.0 s
- **Detection substrate** (10, 11, 12): 4.8–6.0 s (10 longest — table reading)
- **Institution-fit** (13, 14, 15): 4.8–5.5 s
- **Tech substrate** (16, 17): 5.0–5.5 s

Each slide's CSS fade-in animations fire on iframe load, giving natural
intro motion without a separate Stage / Sprite system. Hard cuts between
slides — the per-slide fade-in is the rhythm.

## Watermark

`Created by Huashu-Design` is rendered into the bottom-right of every
frame (skill default for animation outputs). To remove: edit
`walkthrough.html` and re-record.

## Re-recording when slides change

Whenever any slide HTML changes:

```bash
cd docs/pitch/deck-v2
NODE_PATH=$(pwd)/node_modules node /path/to/render-video.js video/walkthrough.html --duration=92
# then BGM mix step + 60fps step + GIF step
```

The walkthrough.html harness doesn't need editing unless slide order
or count changes.
