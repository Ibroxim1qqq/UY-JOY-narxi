$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

& (Join-Path $PSScriptRoot "start_local_postgres.ps1")

$env:PYTHONPATH = Join-Path $root "src"
$env:PYTHONIOENCODING = "utf-8"

& (Join-Path $root ".venv\Scripts\python.exe") -m uyjoy_etl.cli export-cloud-csv "backups/uyjoy-cloud-listings.csv"

Write-Host "Cloud warehouse CSV tayyor: backups\uyjoy-cloud-listings.csv"
