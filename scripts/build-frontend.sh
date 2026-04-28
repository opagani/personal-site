#!/usr/bin/env bash
# scripts/build-frontend.sh — install JS deps and produce frontend-spa/dist/.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$here/frontend-spa"

# `npm ci` if a lockfile exists, else `npm install` for first-time setups.
if [[ -f package-lock.json ]]; then
  npm ci
else
  npm install
fi

npm run build
echo "Built SPA → $here/frontend-spa/dist/"
