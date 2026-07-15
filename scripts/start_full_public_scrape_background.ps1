param(
    [int]$MaxPages = 25,
    [int]$MaxVisible = 1000
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

$outLog = Join-Path $logs "full_public_scrape.out.log"
$errLog = Join-Path $logs "full_public_scrape.err.log"

$running = Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -notlike "*-Command*" -and
        (
            ($_.CommandLine -like "*-File*" -and $_.CommandLine -like "*scrape_all_public_sources.ps1*") -or
            ($_.CommandLine -like "*uyjoy_etl.full_public_scrape*")
        )
    }
if ($running) {
    Write-Host "Full scrape allaqachon ishlayapti:"
    $running | Select-Object ProcessId, CommandLine
    exit 0
}

$scrapeScript = Join-Path $PSScriptRoot "scrape_all_public_sources.ps1"
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$scrapeScript`" -MaxPages $MaxPages -MaxVisible $MaxVisible"

Start-Process `
    -FilePath "powershell" `
    -ArgumentList $arguments `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog

Write-Host "Full public scrape backgroundda boshlandi."
Write-Host "Progress: logs\\full_public_scrape_progress.txt"
Write-Host "Output:   logs\\full_public_scrape.out.log"
Write-Host "Errors:   logs\\full_public_scrape.err.log"
