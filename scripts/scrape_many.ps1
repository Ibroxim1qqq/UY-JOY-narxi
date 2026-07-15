$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

& (Join-Path $PSScriptRoot "start_local_postgres.ps1")

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    py -m venv .venv
}

$python = Join-Path $root ".venv\Scripts\python.exe"
$env:PYTHONPATH = Join-Path $root "src"

& $python -m uyjoy_etl.cli migrate
& $python -m uyjoy_etl.cli scrape-discovered --limit-categories 2 --max-pages 25
& (Join-Path $PSScriptRoot "restart_site.ps1")
