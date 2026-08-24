#!/usr/bin/env bash
# Cloud / long-running geocode chunk: seed from export → geocode → export → optional git push.
# Env:
#   GEOCODE_BUDGET       Nominatim HTTP call budget (default 2000, ~33m at 1 req/s)
#   GEOCODE_RETRY_FAILS  1 = also re-queue status=fail (use once after normalizer)
#   APD_GIT_PUSH         1 = commit+push site/public/data/*
set -euo pipefail
cd "$(dirname "$0")/.."

BUDGET="${GEOCODE_BUDGET:-2000}"
RETRY="${GEOCODE_RETRY_FAILS:-0}"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -e .

apd seed

if [[ "$RETRY" == "1" ]]; then
  apd geocode --budget "$BUDGET" --retry-fails
else
  apd geocode --budget "$BUDGET"
fi

apd export

echo "Geocode chunk done (budget=${BUDGET}, retry_fails=${RETRY})."

if [[ "${APD_GIT_PUSH:-0}" == "1" ]]; then
  git config user.email >/dev/null 2>&1 || git config user.email "apd-bot@users.noreply.github.com"
  git config user.name >/dev/null 2>&1 || git config user.name "apd-incident-map"
  git add site/public/data/incidents.json.gz site/public/data/meta.json
  if git diff --staged --quiet; then
    echo "No data changes to commit."
  else
    git commit -m "data: geocode backfill (budget ${BUDGET})"
    git push
    echo "Pushed data export."
  fi
fi
