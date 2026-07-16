param(
    [int]$OlxMaxPages = 2,
    [int]$OlxMaxSources = 250,
    [int]$OlxMaxVisible = 1000,
    [switch]$UseOlxDiscovery,
    [int]$TelegramLimit = 200,
    [string[]]$TelegramChannels = @(
        "t.me/uybozorim",
        "t.me/UYBOZORI_TOSHKENT_UY_JOY",
        "t.me/tuhfa_estate"
    ),
    [string]$CloudDatabaseUrl = "",
    [int]$CloudOlxUpdatedSinceDays = 1,
    [switch]$SkipOlx,
    [switch]$SkipTelegram,
    [switch]$SkipCloudSync,
    [switch]$SkipSiteRestart
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$logsDir = Join-Path $root "logs"
$logPath = Join-Path $logsDir ("daily-update-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
Set-Location $root

function Resolve-CloudDatabaseUrl {
    param(
        [string]$ExplicitValue,
        [string]$RootDir
    )

    if ($ExplicitValue) {
        return $ExplicitValue
    }

    if ($env:NEON_DATABASE_URL) {
        return $env:NEON_DATABASE_URL
    }

    if ($env:CLOUD_DATABASE_URL) {
        return $env:CLOUD_DATABASE_URL
    }

    $envPath = Join-Path $RootDir ".env"
    if (-not (Test-Path $envPath)) {
        return ""
    }

    foreach ($line in Get-Content $envPath) {
        if ($line -match "^\s*(NEON_DATABASE_URL|CLOUD_DATABASE_URL)\s*=\s*(.+)\s*$") {
            return $Matches[2].Trim().Trim('"').Trim("'")
        }
    }

    return ""
}

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
        if ($UseOlxDiscovery) {
            # Chuqur scan: source discovery sekinroq, lekin ko'proq segmentlarni tekshiradi.
            & $python -m uyjoy_etl.cli scrape-discovered `
                --max-pages $OlxMaxPages `
                --max-sources $OlxMaxSources `
                --max-visible $OlxMaxVisible
        }
        else {
            # Daily mode: categorylarning oxirgi sahifalarini tekshiradi.
            # Yangi e'lonlar odatda shu yerga tushadi, shuning uchun har kungi update uchun tezroq.
            & $python -m uyjoy_etl.cli scrape --max-pages $OlxMaxPages --no-details
        }
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

    $resolvedCloudDatabaseUrl = Resolve-CloudDatabaseUrl -ExplicitValue $CloudDatabaseUrl -RootDir $root
    if (-not $SkipCloudSync -and $resolvedCloudDatabaseUrl) {
        Write-Host "Neon/cloud Postgres yangilanmoqda..."
        & $python -m uyjoy_etl.cli sync-cloud `
            $resolvedCloudDatabaseUrl `
            --olx-updated-since-days $CloudOlxUpdatedSinceDays
    }
    elseif (-not $SkipCloudSync) {
        Write-Host "Cloud sync o'tkazib yuborildi: NEON_DATABASE_URL yoki CLOUD_DATABASE_URL topilmadi."
    }

    if (-not $SkipSiteRestart) {
        Write-Host "Lokal site qayta ishga tushirilmoqda..."
        & (Join-Path $PSScriptRoot "restart_site.ps1")
    }

    Write-Host "Daily update tugadi: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    Write-Host "Log fayl: $logPath"
}
finally {
    Stop-Transcript | Out-Null
}
