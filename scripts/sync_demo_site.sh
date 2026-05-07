#!/usr/bin/env bash
# Sync the demo site from this repo to tomqwu/aml_open_framework_demo.
#
# Why this exists: the demo at https://tomqwu.github.io/aml_open_framework_demo/
# lives in a separate repo with no automated cross-repo publish. After
# trying a GH Actions workflow (#233) and reverting to local publishing,
# this script is the canonical way to push docs/pitch/ changes to the
# demo. Run it after merging a PR that touches docs/pitch/landing/ or
# docs/pitch/deck-v2/.
#
# Usage:
#     make sync-demo
#     # or directly:
#     ./scripts/sync_demo_site.sh
#
# Requires:
#     - gh CLI authenticated (`gh auth status`)
#     - Push access to tomqwu/aml_open_framework_demo
#
# Behaviour:
#     - Clones the demo repo to a temp dir.
#     - Mirrors the relevant subtrees (landing → root, deck-v2 →
#       technical/, business-slides → business/) with `cp` per file
#       so demo-only paths (business/video/) are preserved.
#     - Skips if there's nothing to commit.
#     - Opens a PR titled "Sync from main @ <sha>" and auto-merges it.
#
# Mapping (main → demo):
#     docs/pitch/landing/index.html              → index.html
#     docs/pitch/landing/research/**             → research/**
#     docs/pitch/deck-v2/(everything except      → technical/**
#       business-slides, board-video,
#       _export_pdf.mjs)
#     docs/pitch/deck-v2/business-slides/**      → business/**
#       (excluding video/ — preserved from demo)

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SRC="$ROOT/docs/pitch"
TMP=$(mktemp -d -t aml-demo-sync-XXXXXX)
DST="$TMP/aml_open_framework_demo"

cleanup() {
  rm -rf "$TMP"
}
trap cleanup EXIT

echo "▶ Cloning tomqwu/aml_open_framework_demo to $DST"
gh repo clone tomqwu/aml_open_framework_demo "$DST" -- --quiet --depth 1

cd "$DST"
SHORT_SHA=$(cd "$ROOT" && git rev-parse --short HEAD)
HEAD_MSG=$(cd "$ROOT" && git log -1 --pretty=%s)
BRANCH="sync/main-${SHORT_SHA}"
git checkout -b "$BRANCH" >/dev/null

echo "▶ Mirroring subtrees"

# Landing → root
cp "$SRC/landing/index.html" "$DST/index.html"
rsync -a --delete \
  "$SRC/landing/research/" "$DST/research/"

# deck-v2 → technical/
rsync -a --delete \
  --exclude='business-slides/' \
  --exclude='board-video/' \
  --exclude='_export_pdf.mjs' \
  "$SRC/deck-v2/" "$DST/technical/"

# business-slides → business/, preserving demo-only video/
rsync -a --delete \
  --exclude='video/' \
  "$SRC/deck-v2/business-slides/" "$DST/business/"

# Show pending changes for the operator's confidence.
echo ""
echo "▶ Pending changes in demo repo:"
git -c color.ui=always status --short | sed 's/^/    /'
echo ""

if git diff --quiet && git diff --cached --quiet; then
  echo "✓ No changes to sync — demo is already up to date."
  exit 0
fi

git add -A

git commit -m "Sync from main @ ${SHORT_SHA} — ${HEAD_MSG}" \
           -m "Triggered locally via scripts/sync_demo_site.sh" \
           >/dev/null

git push -u origin "$BRANCH" --quiet

PR_URL=$(gh pr create \
  --title "Sync from main @ ${SHORT_SHA} — ${HEAD_MSG}" \
  --body "Local sync via \`make sync-demo\` from \`tomqwu/aml_open_framework@${SHORT_SHA}\`.

Mirrors \`docs/pitch/\` subtrees with \`cp\`/\`rsync\` per the documented mapping. Demo-only paths (\`business/video/\`) are preserved." \
  --head "$BRANCH" \
  --base main 2>&1 | tail -1)

echo "▶ PR opened: $PR_URL"

# Try auto-merge first; if it's not enabled, fall back to direct merge.
PR_NUM=$(echo "$PR_URL" | grep -oE '[0-9]+$')
if gh pr merge "$PR_NUM" --squash --auto >/dev/null 2>&1; then
  echo "✓ Auto-merge enabled — will land when checks pass."
else
  echo "▶ Auto-merge unavailable; merging directly."
  gh pr merge "$PR_NUM" --squash >/dev/null
  echo "✓ Merged."
fi

echo "✓ Demo site sync complete. GitHub Pages rebuilds in 1–2 min:"
echo "    https://tomqwu.github.io/aml_open_framework_demo/"
