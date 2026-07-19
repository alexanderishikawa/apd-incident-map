# Keep geocoding until pending addresses are low or max rounds hit.
# Env: GEOCODE_BUDGET (default 5000), GEOCODE_MAX_ROUNDS (default 20),
#      GEOCODE_RETRY_FAILS=1 on first round (default), APD_GIT_PUSH=1 to commit/push export each round
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$budget = if ($env:GEOCODE_BUDGET) { [int]$env:GEOCODE_BUDGET } else { 5000 }
$maxRounds = if ($env:GEOCODE_MAX_ROUNDS) { [int]$env:GEOCODE_MAX_ROUNDS } else { 20 }
$retryFirst = $env:GEOCODE_RETRY_FAILS -ne "0"

if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\pip install -q -e .

New-Item -ItemType Directory -Force -Path data | Out-Null

for ($round = 1; $round -le $maxRounds; $round++) {
  Write-Host "=== marathon round $round / $maxRounds (budget=$budget) ==="
  if ($retryFirst -and $round -eq 1) {
    .\.venv\Scripts\apd geocode --budget $budget --retry-fails
  } else {
    .\.venv\Scripts\apd geocode --budget $budget
  }
  .\.venv\Scripts\apd export
  $status = .\.venv\Scripts\python scripts\_geo_status.py
  $status | Tee-Object -FilePath data\geocode_marathon_status.log -Append
  Write-Host $status

  $pendingLine = ($status | Select-String "^pending_est ").ToString()
  $pending = [int]($pendingLine -replace "pending_est ", "")
  if ($pending -lt 50) {
    Write-Host "Pending low ($pending); stopping."
    break
  }

  if ($env:APD_GIT_PUSH -eq "1") {
    git add site/public/data/incidents.json site/public/data/meta.json
    git diff --staged --quiet
    if ($LASTEXITCODE -ne 0) {
      git commit -m "data: geocode marathon round $round"
      git push origin HEAD
    }
  }
}

Write-Host "Marathon complete."
