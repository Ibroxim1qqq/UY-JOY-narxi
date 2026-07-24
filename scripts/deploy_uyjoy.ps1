param(
    [switch]$SkipTests,
    [switch]$SkipDailyCheck
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$logsDir = Join-Path $root "logs"
$python = Join-Path $root ".venv\Scripts\python.exe"
$daemonScript = Join-Path $PSScriptRoot "uyjoy_daemon.ps1"
$statusPath = Join-Path $logsDir "uyjoy-deploy-status.json"

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
Set-Location $root

function Write-Step([string]$Message) {
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message)
}

function Test-HttpOk([string]$Url) {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 15
    if ($response.StatusCode -ne 200) {
        throw "$Url status=$($response.StatusCode)"
    }
}

function Stop-UyJoyDaemon {
    $daemons = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -in @("powershell.exe", "pwsh.exe") -and
                $_.CommandLine -like "*uyjoy_daemon.ps1*" -and
                $_.CommandLine -notmatch "\s-Command\s"
            }
    )

    foreach ($daemon in $daemons) {
        Stop-Process -Id $daemon.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Start-UyJoyDaemon {
    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            "`"$daemonScript`""
        ) `
        -WorkingDirectory $root `
        -WindowStyle Hidden | Out-Null
}

function Get-DeploySummary {
    $env:PYTHONPATH = Join-Path $root "src"
    $dbJson = (& $python -m uyjoy_etl.data_signature).Trim() | ConvertFrom-Json
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 15
    $daemonCount = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -in @("powershell.exe", "pwsh.exe") -and
                $_.CommandLine -like "*uyjoy_daemon.ps1*" -and
                $_.CommandLine -notmatch "\s-Command\s"
            }
    ).Count

    [ordered]@{
        deployed_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss zzz")
        postgres = "127.0.0.1:55432"
        metabase = "http://127.0.0.1:3000"
        ml_form = "http://127.0.0.1:8000"
        daemon_count = $daemonCount
        model_available = $health.model.available
        model_training_window_days = $health.model.training_window_days
        model_rows_used = $health.model.rows_used
        model_mape_percent = $health.model.mape_percent
        olx_count = $dbJson.olx_count
        telegram_post_count = $dbJson.telegram_post_count
        telegram_clean_count = $dbJson.telegram_clean_count
        unified_count = $dbJson.unified_count
        unified_updated_at = $dbJson.unified_updated_at
    }
}

if (-not (Test-Path $python)) {
    throw "Python venv topilmadi: $python"
}

Write-Step "Core servislar ishga tushirilmoqda"
if ($SkipDailyCheck) {
    & (Join-Path $PSScriptRoot "start_uyjoy.ps1") -SkipDailyCheck
}
else {
    & (Join-Path $PSScriptRoot "start_uyjoy.ps1")
}

Write-Step "Schema va BI view migration tekshirilmoqda"
& $python -m uyjoy_etl.cli migrate

if (-not $SkipTests) {
    Write-Step "Unit/regression testlar ishlatilmoqda"
    & $python -m unittest discover -s tests
}

Write-Step "HTTP smoke tekshirilmoqda"
Test-HttpOk "http://127.0.0.1:8000/health"
Test-HttpOk "http://127.0.0.1:8000/"
Test-HttpOk "http://127.0.0.1:3000/api/health"

Write-Step "Data signature yangilanmoqda"
& $python -m uyjoy_etl.data_signature |
    Set-Content -LiteralPath (Join-Path $logsDir "uyjoy-data-signature.json") -Encoding UTF8

Write-Step "Startup daemon o'rnatilmoqda"
& (Join-Path $PSScriptRoot "install_uyjoy_startup.ps1")

Write-Step "Daemon fresh restart qilinmoqda"
Stop-UyJoyDaemon
Start-UyJoyDaemon
Start-Sleep -Seconds 5

Write-Step "Deploy summary yozilmoqda"
$summary = Get-DeploySummary
$summary | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statusPath -Encoding UTF8
$summary | ConvertTo-Json -Depth 4

Write-Step "Deploy tayyor: $statusPath"
