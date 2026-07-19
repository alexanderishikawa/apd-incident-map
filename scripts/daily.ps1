$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path .venv)) {
  python -m venv .venv
}
.\.venv\Scripts\python -m pip install -q -e ".[dev]"

.\.venv\Scripts\apd seed
.\.venv\Scripts\apd pull --last-days 7
.\.venv\Scripts\apd geocode --budget 300
.\.venv\Scripts\apd export

Write-Host "Daily pull complete."
