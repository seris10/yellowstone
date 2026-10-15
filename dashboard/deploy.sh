#!/usr/bin/env bash
# Publish the scientific explorer and its checked model snapshot.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/work"
STAGE="$(mktemp -d "$ROOT/work/public-site.XXXXXX")"
trap 'trash "$STAGE" >/dev/null 2>&1 || true' EXIT

python3 "$ROOT/dashboard/build_public.py" --out "$STAGE/site"
mkdir -p "$STAGE/node_modules"

: "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN}"
: "${CLOUDFLARE_ACCOUNT_ID:?set CLOUDFLARE_ACCOUNT_ID}"
if [[ "$CLOUDFLARE_ACCOUNT_ID" != "95da8b892c927d6c9a4e8fc9c851d75c" ]]; then
  printf 'The Yellowstone Pages project belongs to the KJR account.\n' >&2
  exit 1
fi
cd "$STAGE"
wrangler pages deploy site --project-name=yellowstone-dashboard --branch=main --commit-dirty=true
