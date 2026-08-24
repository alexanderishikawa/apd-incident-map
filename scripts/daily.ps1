$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$logDir = Join-Path (Get-Location) "data"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "daily.log"
function Log([string]$msg) {
  $line = "$(Get-Date -Format o) $msg"
  Add-Content -Path $log -Value $line
  Write-Host $line
}

Log "Daily start"
try {
  if (-not (Test-Path .venv)) {
    python -m venv .venv
  }
  .\.venv\Scripts\python -m pip install -q -e ".[dev]"

  .\.venv\Scripts\apd seed
  .\.venv\Scripts\apd pull --last-days 7
  .\.venv\Scripts\apd geocode --budget 300
  .\.venv\Scripts\apd export

  git add site/public/data/incidents.json.gz site/public/data/meta.json
  git diff --staged --quiet
  if ($LASTEXITCODE -ne 0) {
    $stamp = Get-Date -Format yyyy-MM-dd
    git commit -m "data: daily export $stamp"
    git push origin HEAD
    Log "Pushed data export."
  } else {
    Log "No data changes to commit."
  }

  Log "Daily pull complete."
} catch {
  Log "Daily FAILED: $_"
  throw
}
