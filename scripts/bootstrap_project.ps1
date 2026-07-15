param(
    [string]$PostgresPassword
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    py -m venv .venv
}

$python = Join-Path $root ".venv\Scripts\python.exe"

& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.txt
& $python -m pip install -e .

if (-not (Test-Path ".\.env")) {
    if ($PostgresPassword) {
        & (Join-Path $PSScriptRoot "create_env_from_example.ps1") -PostgresPassword $PostgresPassword
    }
    else {
        & (Join-Path $PSScriptRoot "create_env_from_example.ps1")
    }
}

$env:PYTHONPATH = Join-Path $root "src"
& $python -m uyjoy_etl.cli migrate
& $python -m uyjoy_etl.cli ping-db
