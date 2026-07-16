$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:PYTHONPATH = Join-Path $root "src"
$env:PYTHONIOENCODING = "utf-8"

& (Join-Path $root ".venv\Scripts\python.exe") -m uyjoy_etl.cli telegram-login
