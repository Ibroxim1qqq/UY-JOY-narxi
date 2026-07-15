$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

& (Join-Path $PSScriptRoot "start_local_postgres.ps1")

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    py -m venv .venv
}

$python = Join-Path $root ".venv\Scripts\python.exe"
& $python -m pip install -r requirements.txt
& $python -m pip install -e .

$env:PYTHONPATH = Join-Path $root "src"
& $python -m uyjoy_etl.cli migrate
& $python -m uyjoy_etl.cli scrape --max-pages 1 --limit-categories 1 --no-details

& (Join-Path $PSScriptRoot "restart_site.ps1")

Write-Host "Tayyor. Dashboard: http://127.0.0.1:8000"
Write-Host "pgAdmin uchun: host=127.0.0.1 port=55432 db=uyjoy_olx user=uyjoy password=uyjoy_password"
