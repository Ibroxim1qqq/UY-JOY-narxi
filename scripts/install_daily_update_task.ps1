param(
    [string]$TaskName = "UyJoyDailyUpdate",
    [string]$At = "10:00",
    [int]$OlxMaxPages = 2,
    [int]$OlxMaxSources = 250,
    [switch]$UseOlxDiscovery,
    [int]$TelegramLimit = 200,
    [int]$CloudOlxUpdatedSinceDays = 1,
    [string]$CloudDatabaseUrl = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$dailyScript = Join-Path $PSScriptRoot "daily_update.ps1"

if (-not (Test-Path $dailyScript)) {
    throw "daily_update.ps1 topilmadi: $dailyScript"
}

$time = [DateTime]::ParseExact($At, "HH:mm", $null)
$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$dailyScript`"",
    "-OlxMaxPages", $OlxMaxPages,
    "-OlxMaxSources", $OlxMaxSources,
    "-TelegramLimit", $TelegramLimit,
    "-CloudOlxUpdatedSinceDays", $CloudOlxUpdatedSinceDays
) -join " "

if ($CloudDatabaseUrl) {
    $arguments = "$arguments -CloudDatabaseUrl `"$CloudDatabaseUrl`""
}

if ($UseOlxDiscovery) {
    $arguments = "$arguments -UseOlxDiscovery"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $time
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "UY-JOY OLX va Telegram daily ETL update" `
    -Force | Out-Null

Write-Host "Scheduled Task yaratildi: $TaskName"
Write-Host "Har kuni ishga tushish vaqti: $At"
Write-Host "Script: $dailyScript"
Write-Host "Loglar: $(Join-Path $root 'logs')"
