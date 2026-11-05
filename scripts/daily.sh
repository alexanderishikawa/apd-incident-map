#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' || {
  echo "Python 3.11 or newer is required." >&2
  exit 1
}

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -e .

apd seed

pull_ok() {
  python -c '
import json
import sys

payload = json.load(sys.stdin)
results = payload.get("results", [])
raise SystemExit(not results or any(row.get("status") != "ok" for row in results))
'
}

pull_output=""
for attempt in 1 2; do
  if pull_output="$(apd pull --last-days 7)" && pull_ok <<<"$pull_output"; then
    printf '%s\n' "$pull_output"
    break
  fi

  printf '%s\n' "$pull_output" >&2
  if [[ "$attempt" -eq 1 ]]; then
    echo "APD pull failed; retrying once." >&2
  else
    echo "APD pull failed after two attempts; skipping geocode, export, commit, and push." >&2
    exit 1
  fi
done

apd geocode --budget 300
apd export

if git add site/public/data/incidents.json.gz site/public/data/meta.json \
  && ! git diff --staged --quiet; then
  git commit -m "data: daily APD incident refresh"
  git push origin HEAD
  echo "Pushed data export."
else
  echo "No data changes to commit."
fi

echo "Daily pull complete."
