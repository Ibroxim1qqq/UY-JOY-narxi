param(
    [switch]$SkipDailyCheck
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$metabaseUrl = "http://127.0.0.1:3000"
$siteUrl = "http://127.0.0.1:8000"
$metabaseRun = Join-Path $root "tools\metabase\run-metabase.cmd"
$logsDir = Join-Path $root "logs"

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

function Test-HttpOk([string]$Url) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Wait-HttpOk([string]$Url, [int]$Seconds) {
    for ($i = 1; $i -le $Seconds; $i++) {
        if (Test-HttpOk $Url) {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Get-MetabaseProcesses {
    Get-CimInstance Win32_Process -Filter "name = 'java.exe'" |
        Where-Object { $_.CommandLine -like "*metabase.jar*" }
}

function Start-Metabase {
    if (-not (Test-Path $metabaseRun)) {
        throw "Metabase runner topilmadi: $metabaseRun"
    }

    Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList @("/c", "`"$metabaseRun`"") `
        -WorkingDirectory $root `
        -WindowStyle Hidden
}

function Ensure-Postgres {
    & (Join-Path $PSScriptRoot "start_local_postgres.ps1")
}

function Ensure-Metabase {
    if (Wait-HttpOk "$metabaseUrl/api/health" 20) {
        Write-Host "Metabase tayyor: $metabaseUrl"
        return
    }

    $processes = @(Get-MetabaseProcesses)
    if ($processes.Count -gt 0) {
        Write-Host "Metabase process bor, lekin health javob bermadi. Qayta ishga tushirilmoqda..."
        $processes | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 3
    }
    else {
        Write-Host "Metabase ishga tushirilmoqda..."
    }

    Start-Metabase
    if (Wait-HttpOk "$metabaseUrl/api/health" 120) {
        Write-Host "Metabase tayyor: $metabaseUrl"
        return
    }

    throw "Metabase $metabaseUrl sog'lom holatga kelmadi. logs\metabase.err.log va logs\metabase.out.log ni tekshiring."
}

function Ensure-UyJoySite {
    if (Test-HttpOk "$siteUrl/health") {
        Write-Host "UY-JOY ML forma tayyor: $siteUrl"
        return
    }

    $restartSite = Join-Path $PSScriptRoot "restart_site.ps1"
    if (-not (Test-Path $restartSite)) {
        throw "UY-JOY site runner topilmadi: $restartSite"
    }

    Write-Host "UY-JOY ML forma ishga tushirilmoqda..."
    & $restartSite
    if (Test-HttpOk "$siteUrl/health") {
        Write-Host "UY-JOY ML forma tayyor: $siteUrl"
        return
    }

    throw "UY-JOY ML forma $siteUrl sog'lom holatga kelmadi. logs\site.err.log va logs\site.out.log ni tekshiring."
}

Ensure-Postgres
Ensure-Metabase
Ensure-UyJoySite

$dailyCheck = Join-Path $PSScriptRoot "start_daily_update_if_due.ps1"
if (-not $SkipDailyCheck -and (Test-Path $dailyCheck)) {
    & $dailyCheck -MinAgeHours 20
}

Write-Host "Metabase local: $metabaseUrl"
Write-Host "Metabase login: admin@uyjoy.local"
Write-Host "ML forma: $siteUrl"
