#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -e ".[dev]"

apd seed
apd pull --last-days 7
apd geocode --budget 300
apd export

if git add site/public/data/incidents.json.gz site/public/data/meta.json \
  && ! git diff --staged --quiet; then
  git commit -m "data: daily export $(date +%F)"
  git push origin HEAD
  echo "Pushed data export."
else
  echo "No data changes to commit."
fi

echo "Daily pull complete."
