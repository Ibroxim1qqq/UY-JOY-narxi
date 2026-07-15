param(
    [int]$MaxPages = 25,
    [int]$MaxVisible = 1000
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

& (Join-Path $PSScriptRoot "start_local_postgres.ps1")

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    py -m venv .venv
}

$python = Join-Path $root ".venv\Scripts\python.exe"
$env:PYTHONPATH = Join-Path $root "src"
$env:PYTHONIOENCODING = "utf-8"

& $python -m uyjoy_etl.full_public_scrape --max-pages $MaxPages --max-visible $MaxVisible

& (Join-Path $PSScriptRoot "restart_site.ps1")
