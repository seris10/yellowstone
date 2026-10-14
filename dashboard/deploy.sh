#!/usr/bin/env bash
# Rebuilds the dashboard data, stages the page with the fixes documents it links to, and publishes the stage to Cloudflare Pages.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$(mktemp -d)"
trap 'trash "$STAGE" >/dev/null 2>&1 || true' EXIT

python3 "$ROOT/dashboard/build_data.py"
mkdir -p "$STAGE/dashboard/data" "$STAGE/yellowstone_python_spec/fixes"
cp "$ROOT/dashboard/index.html" "$STAGE/dashboard/"
cp "$ROOT/dashboard/data/dashboard-data.js" "$STAGE/dashboard/data/"
cp "$ROOT"/yellowstone_python_spec/fixes/fixes-*.md "$STAGE/yellowstone_python_spec/fixes/"
printf '/ /dashboard/ 302\n' > "$STAGE/_redirects"
printf '/yellowstone_python_spec/*\n  Content-Type: text/plain; charset=utf-8\n' > "$STAGE/_headers"

: "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN}"
: "${CLOUDFLARE_ACCOUNT_ID:?set CLOUDFLARE_ACCOUNT_ID}"
cd "$STAGE"
wrangler pages deploy . --project-name=yellowstone-dashboard --branch=main --commit-dirty=true
