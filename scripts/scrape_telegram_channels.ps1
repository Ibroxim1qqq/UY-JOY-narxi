$ErrorActionPreference = "Stop"

param(
    [int]$Limit = 100,
    [string[]]$Channels = @(
        "t.me/uybozorim",
        "t.me/UYBOZORI_TOSHKENT_UY_JOY",
        "t.me/tuhfa_estate"
    )
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:PYTHONPATH = Join-Path $root "src"
$env:PYTHONIOENCODING = "utf-8"

& (Join-Path $root ".venv\Scripts\python.exe") -m uyjoy_etl.cli scrape-telegram @Channels --limit $Limit
