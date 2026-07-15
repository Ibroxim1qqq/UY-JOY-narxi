$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

& (Join-Path $PSScriptRoot "start_docker_stack.ps1")

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    py -m venv .venv
}

$python = Join-Path $root ".venv\Scripts\python.exe"
& $python -m pip install -r requirements.txt
& $python -m pip install -e .

$env:PYTHONPATH = Join-Path $root "src"
& $python -m uyjoy_etl.cli migrate
& $python -m uyjoy_etl.cli scrape --max-pages 1 --limit-categories 1 --no-details

Write-Host "Sample data tushdi. Dashboard: http://127.0.0.1:8000"
Write-Host "pgAdmin: http://127.0.0.1:5050"
