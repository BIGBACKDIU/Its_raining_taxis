#!/usr/bin/env bash
# Redeploy the presentation (decision 181): copy the built deck and publish it to Vercel production.
# Usage: scripts/deploy_deck.sh   (rebuild first with .venv/bin/python -m analysis.build_present)
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT=raining-taxis-deck
SCOPE=mhfurui-7256s-projects
if command -v vercel >/dev/null 2>&1; then VERCEL=(vercel); else VERCEL=(npx -y vercel@65.2.0); fi

mkdir -p deploy/deck
cp outputs/story/present.html deploy/deck/index.html

# A fresh clone has no local link (deploy/deck/.vercel is git-ignored): link to the existing project first.
if [ ! -f deploy/deck/.vercel/project.json ]; then
  "${VERCEL[@]}" link --cwd deploy/deck --project "$PROJECT" --scope "$SCOPE" --yes
fi
# Linking writes a token file and a .gitignore; never publish them (the folder holds index.html only).
rm -f deploy/deck/.env.local deploy/deck/.gitignore

"${VERCEL[@]}" deploy deploy/deck --prod --yes
