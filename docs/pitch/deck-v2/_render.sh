#!/usr/bin/env bash
# Render every slide HTML in slides/ to a sibling PNG via Playwright.
# Run from docs/pitch/deck-v2/.
set -euo pipefail
cd "$(dirname "$0")"

for f in slides/*.html; do
  out="${f%.html}.png"
  if [ -f "$out" ] && [ "$out" -nt "$f" ]; then
    continue  # png is fresher than html — skip
  fi
  echo "→ $f"
  npx -y playwright screenshot \
    --viewport-size=1920,1080 \
    --wait-for-timeout=1500 \
    "file://$(pwd)/$f" "$out" >/dev/null 2>&1
done
echo "Done. $(ls slides/*.png | wc -l) PNGs in slides/."
