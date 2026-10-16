#!/usr/bin/env bash
# Build the saved scientific explorer and deploy to the configured Pages project.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/work"
STAGE="$(mktemp -d "$ROOT/work/public-site.XXXXXX")"
python3 "$ROOT/dashboard/build_public.py" --out "$STAGE/site"
wrangler pages deploy "$STAGE/site" \
  --project-name="${CLOUDFLARE_PAGES_PROJECT:-yellowstone-dashboard}" \
  --branch="${CLOUDFLARE_PAGES_BRANCH:-main}" --commit-dirty=true

