param(
    [int]$MinAgeHours = 20,
    [int]$OlxMaxPages = 2,
    [int]$TelegramLimit = 200,
    [switch]$SkipSiteRestart
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$logsDir = Join-Path $root "logs"
$dailyScript = Join-Path $PSScriptRoot "daily_update.ps1"
$stateFile = Join-Path $logsDir "daily-update-autostart.txt"

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

if (-not (Test-Path $dailyScript)) {
    throw "Daily update script topilmadi: $dailyScript"
}

function Get-DailyUpdateProcesses {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -in @("powershell.exe", "pwsh.exe") -and
            $_.CommandLine -like "*daily_update.ps1*"
        }
}

function Get-LastSuccessfulDailyUpdate {
    $logs = @(
        Get-ChildItem -LiteralPath $logsDir -Filter "daily-update-*.log" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending
    )

    foreach ($log in $logs) {
        try {
            $tail = Get-Content -LiteralPath $log.FullName -Tail 120 -ErrorAction Stop
            if (($tail -join "`n") -match "Daily update tugadi") {
                return $log.LastWriteTime
            }
        }
        catch {
            continue
        }
    }

    return $null
}

$running = @(Get-DailyUpdateProcesses)
if ($running.Count -gt 0) {
    Write-Host "Daily update allaqachon ishlayapti. PID: $($running[0].ProcessId)"
    return
}

$now = Get-Date
$lastSuccess = Get-LastSuccessfulDailyUpdate

if ($lastSuccess) {
    $ageHours = ($now - $lastSuccess).TotalHours
    if ($ageHours -lt $MinAgeHours) {
        Write-Host ("Daily update o'tkazib yuborildi: oxirgi update {0:yyyy-MM-dd HH:mm}, {1:N1} soat oldin." -f $lastSuccess, $ageHours)
        return
    }
}

$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "`"$dailyScript`"",
    "-OlxMaxPages",
    $OlxMaxPages,
    "-TelegramLimit",
    $TelegramLimit
)

if ($SkipSiteRestart) {
    $arguments += "-SkipSiteRestart"
}

$process = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList $arguments `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -PassThru

$state = @(
    "Started: $($now.ToString('yyyy-MM-dd HH:mm:ss'))",
    "ProcessId: $($process.Id)",
    "LastSuccess: $(if ($lastSuccess) { $lastSuccess.ToString('yyyy-MM-dd HH:mm:ss') } else { 'none' })",
    "MinAgeHours: $MinAgeHours"
)
Set-Content -LiteralPath $stateFile -Value $state -Encoding UTF8

Write-Host "Daily update backgroundda boshlandi. PID: $($process.Id)"
