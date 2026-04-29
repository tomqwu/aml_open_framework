#!/usr/bin/env bash
# Render every slide HTML in slides/ to a sibling PNG via Playwright.
set -euo pipefail
cd "$(dirname "$0")"

for f in slides/*.html; do
  out="${f%.html}.png"
  echo "→ $f"
  npx -y playwright screenshot \
    --viewport-size=1920,1080 \
    --wait-for-timeout=2000 \
    "file://$(pwd)/$f" "$out" >/dev/null 2>&1
done
echo "Done. $(ls slides/*.png | wc -l) PNGs in slides/."
