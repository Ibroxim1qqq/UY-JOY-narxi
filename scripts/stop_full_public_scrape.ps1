$ErrorActionPreference = "Stop"

function Stop-ProcessTree {
    param([int]$ProcessId)

    $children = Get-CimInstance Win32_Process |
        Where-Object { $_.ParentProcessId -eq $ProcessId }

    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId $child.ProcessId
    }

    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

$running = Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -notlike "*-Command*" -and
        (
            ($_.CommandLine -like "*-File*" -and $_.CommandLine -like "*scrape_all_public_sources.ps1*") -or
            ($_.CommandLine -like "*uyjoy_etl.full_public_scrape*")
        )
    }

if (-not $running) {
    Write-Host "Full public scrape hozir ishlamayapti."
    exit 0
}

foreach ($process in $running) {
    Stop-ProcessTree -ProcessId $process.ProcessId
}

Write-Host "Full public scrape to'xtatildi."
