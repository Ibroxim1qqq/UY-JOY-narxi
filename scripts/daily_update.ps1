param(
    [int]$OlxMaxPages = 2,
    [int]$TelegramLimit = 200,
    [string[]]$TelegramChannels = @(
        "t.me/uybozorim",
        "t.me/UYBOZORI_TOSHKENT_UY_JOY",
        "t.me/tuhfa_estate"
    ),
    [switch]$SkipOlx,
    [switch]$SkipTelegram,
    [switch]$SkipModelTrain,
    [switch]$SkipSiteRestart,
    [switch]$SkipCloudSync,
    [string]$CloudDatabaseUrl = $env:NEON_DATABASE_URL
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$logsDir = Join-Path $root "logs"
$logPath = Join-Path $logsDir ("daily-update-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
Set-Location $root

Start-Transcript -Path $logPath -Append | Out-Null

try {
    Write-Host "Daily update boshlandi: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

    # Lokal Postgres ishlamayotgan bo'lsa, avval uni ko'taramiz.
    & (Join-Path $PSScriptRoot "start_local_postgres.ps1")

    if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
        py -m venv .venv
        & ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
    }

    $python = Join-Path $root ".venv\Scripts\python.exe"
    $env:PYTHONPATH = Join-Path $root "src"
    $env:PYTHONIOENCODING = "utf-8"

    Write-Host "Schema tekshirilmoqda..."
    & $python -m uyjoy_etl.cli migrate

    if (-not $SkipOlx) {
        Write-Host "OLX yangi e'lonlari tekshirilmoqda..."
        & $python -m uyjoy_etl.cli scrape --max-pages $OlxMaxPages --no-details
    }

    if (-not $SkipTelegram) {
        Write-Host "Telegram yangi postlari tekshirilmoqda..."
        & $python -m uyjoy_etl.cli scrape-telegram @TelegramChannels --limit $TelegramLimit

        Write-Host "Telegram postlari clean qilinmoqda..."
        & $python -m uyjoy_etl.cli clean-telegram-real-estate
    }

    Write-Host "Noreal/shubhali e'lonlar quality filterdan o'tkazilmoqda..."
    & $python -m uyjoy_etl.cli mark-suspicious

    Write-Host "OLX va Telegram bitta clean jadvalga yig'ilmoqda..."
    & $python -m uyjoy_etl.cli refresh-unified-listings

    if (-not $SkipModelTrain) {
        Write-Host "Kvartira baholash modeli qayta o'qitilmoqda..."
        & $python -m uyjoy_etl.cli train-valuation-model --days 30
    }

    if (-not $SkipSiteRestart) {
        Write-Host "Lokal site qayta ishga tushirilmoqda..."
        & (Join-Path $PSScriptRoot "restart_site.ps1")
    }

    Write-Host "Daemon data signature yangilanmoqda..."
    & $python -m uyjoy_etl.data_signature |
        Set-Content -LiteralPath (Join-Path $logsDir "uyjoy-data-signature.json") -Encoding UTF8

    if (-not $SkipCloudSync) {
        if ($CloudDatabaseUrl) {
            Write-Host "Cloud Neon database sync qilinmoqda..."
            & (Join-Path $PSScriptRoot "sync_cloud_database.ps1") `
                -CloudDatabaseUrl $CloudDatabaseUrl `
                -SkipModelTrain:$SkipModelTrain
        }
        else {
            Write-Host "Cloud sync o'tkazib yuborildi: NEON_DATABASE_URL berilmagan."
        }
    }

    Write-Host "Daily update tugadi: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    Write-Host "Log fayl: $logPath"
}
finally {
    Stop-Transcript | Out-Null
}
