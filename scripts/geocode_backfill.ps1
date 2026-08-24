# Cloud / long-running geocode chunk (Windows).
# Env: GEOCODE_BUDGET (default 2000), GEOCODE_RETRY_FAILS=1, APD_GIT_PUSH=1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$budget = if ($env:GEOCODE_BUDGET) { [int]$env:GEOCODE_BUDGET } else { 2000 }
$retry = $env:GEOCODE_RETRY_FAILS -eq "1"

if (-not (Test-Path .venv)) {
  python -m venv .venv
}
.\.venv\Scripts\pip install -q -e .

.\.venv\Scripts\apd seed
if ($retry) {
  .\.venv\Scripts\apd geocode --budget $budget --retry-fails
} else {
  .\.venv\Scripts\apd geocode --budget $budget
}
.\.venv\Scripts\apd export

Write-Host "Geocode chunk done (budget=$budget, retry_fails=$retry)."

if ($env:APD_GIT_PUSH -eq "1") {
  git add site/public/data/incidents.json.gz site/public/data/meta.json
  git diff --staged --quiet
  if ($LASTEXITCODE -ne 0) {
    git commit -m "data: geocode backfill (budget $budget)"
    git push
    Write-Host "Pushed data export."
  } else {
    Write-Host "No data changes to commit."
  }
}
