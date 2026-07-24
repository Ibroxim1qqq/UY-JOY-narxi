param(
    [int]$HealthCheckSeconds = 300,
    [int]$DataCheckMinutes = 15,
    [int]$DailyUpdateMinAgeHours = 20,
    [switch]$RunOnce
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$logsDir = Join-Path $root "logs"
$daemonLog = Join-Path $logsDir "uyjoy-daemon.log"
$signatureFile = Join-Path $logsDir "uyjoy-data-signature.json"
$python = Join-Path $root ".venv\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
Set-Location $root

function Write-DaemonLog([string]$Message) {
    $line = "{0} | {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $daemonLog -Value $line -Encoding UTF8
    Write-Host $line
}

function Get-DaemonProcesses {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -in @("powershell.exe", "pwsh.exe") -and
            $_.CommandLine -like "*uyjoy_daemon.ps1*" -and
            $_.CommandLine -notmatch "\s-Command\s"
        }
}

function Test-DailyUpdateRunning {
    $running = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -in @("powershell.exe", "pwsh.exe") -and
                $_.CommandLine -like "*daily_update.ps1*"
            }
    )
    return $running.Count -gt 0
}

function Invoke-CoreStart {
    $startScript = Join-Path $PSScriptRoot "start_uyjoy.ps1"
    & $startScript -SkipDailyCheck 2>&1 | ForEach-Object { Write-DaemonLog $_.ToString() }
}

function Invoke-DailyUpdateIfDue {
    $dailyScript = Join-Path $PSScriptRoot "start_daily_update_if_due.ps1"
    & $dailyScript -MinAgeHours $DailyUpdateMinAgeHours 2>&1 | ForEach-Object { Write-DaemonLog $_.ToString() }
}

function Get-DataSignature {
    if (-not (Test-Path $python)) {
        throw "Python topilmadi: $python"
    }

    $env:PYTHONPATH = Join-Path $root "src"
    return (& $python -m uyjoy_etl.data_signature).Trim()
}

function Invoke-ModelRefreshIfDataChanged {
    if (Test-DailyUpdateRunning) {
        Write-DaemonLog "Daily update ishlayapti, data-change sync o'tkazib turildi."
        return
    }

    $currentSignature = Get-DataSignature
    if (-not (Test-Path $signatureFile)) {
        Set-Content -LiteralPath $signatureFile -Value $currentSignature -Encoding UTF8
        Write-DaemonLog "Data signature baseline yozildi."
        return
    }

    $previousSignature = (Get-Content -Raw -LiteralPath $signatureFile).Trim()
    if ($currentSignature -eq $previousSignature) {
        Write-DaemonLog "Data o'zgarmagan, model sync kerak emas."
        return
    }

    Write-DaemonLog "Data o'zgardi: unified table va ML model yangilanadi."
    $env:PYTHONPATH = Join-Path $root "src"
    & $python -m uyjoy_etl.cli refresh-unified-listings 2>&1 | ForEach-Object { Write-DaemonLog $_.ToString() }
    & $python -m uyjoy_etl.cli train-valuation-model --days 30 2>&1 | ForEach-Object { Write-DaemonLog $_.ToString() }
    & (Join-Path $PSScriptRoot "restart_site.ps1") 2>&1 | ForEach-Object { Write-DaemonLog $_.ToString() }

    $updatedSignature = Get-DataSignature
    Set-Content -LiteralPath $signatureFile -Value $updatedSignature -Encoding UTF8
    Write-DaemonLog "Data-change sync tugadi."
}

$otherDaemons = @(Get-DaemonProcesses | Where-Object { $_.ProcessId -ne $PID })
if ($otherDaemons.Count -gt 0) {
    Write-DaemonLog "Daemon allaqachon ishlayapti. PID: $($otherDaemons[0].ProcessId)"
    return
}

Write-DaemonLog "UY-JOY daemon boshlandi. HealthCheckSeconds=$HealthCheckSeconds DataCheckMinutes=$DataCheckMinutes"

$nextDataCheck = Get-Date
while ($true) {
    try {
        Invoke-CoreStart

        if ((Get-Date) -ge $nextDataCheck) {
            Invoke-DailyUpdateIfDue
            Invoke-ModelRefreshIfDataChanged
            $nextDataCheck = (Get-Date).AddMinutes($DataCheckMinutes)
        }
    }
    catch {
        Write-DaemonLog "Xato: $($_.Exception.Message)"
    }

    if ($RunOnce) {
        Write-DaemonLog "RunOnce tugadi."
        return
    }

    Start-Sleep -Seconds $HealthCheckSeconds
}
