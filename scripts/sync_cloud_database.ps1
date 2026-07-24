param(
    [string]$CloudDatabaseUrl = $env:NEON_DATABASE_URL,
    [string]$LocalHost,
    [int]$LocalPort = 0,
    [string]$LocalDatabase,
    [string]$LocalUser,
    [string]$LocalPassword,
    [int]$RecentDays = 90,
    [switch]$FullRaw,
    [switch]$SkipModelTrain
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$logsDir = Join-Path $root "logs"
$python = Join-Path $root ".venv\Scripts\python.exe"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dumpPath = Join-Path $logsDir ("uyjoy-cloud-data-{0}.dump" -f $timestamp)
$marketCsvPath = Join-Path $logsDir ("uyjoy-cloud-market-{0}.csv" -f $timestamp)
$coreTables = @(
    "public.etl_runs",
    "public.olx_fetch_logs",
    "public.olx_listing_raw",
    "public.telegram_channels",
    "public.telegram_posts",
    "public.telegram_real_estate_posts",
    "public.real_estate_listings"
)

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
Set-Location $root

function Get-DotEnvValue([string]$Name, [string]$Default = "") {
    $processValue = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ($processValue) {
        return $processValue
    }

    $envPath = Join-Path $root ".env"
    if (-not (Test-Path $envPath)) {
        return $Default
    }

    foreach ($line in Get-Content -LiteralPath $envPath) {
        if ($line -match "^\s*#") {
            continue
        }
        if ($line -match "^\s*([^=]+?)\s*=\s*(.*)\s*$") {
            $key = $matches[1].Trim()
            if ($key -ne $Name) {
                continue
            }
            $value = $matches[2].Trim()
            if (
                ($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))
            ) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            return $value
        }
    }

    return $Default
}

function Resolve-PgTool([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        "C:\Program Files\PostgreSQL\18\bin\$Name.exe",
        "C:\Program Files\PostgreSQL\17\bin\$Name.exe",
        "C:\Program Files\PostgreSQL\16\bin\$Name.exe",
        "C:\Program Files\PostgreSQL\15\bin\$Name.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "$Name topilmadi. PostgreSQL client tools PATHga qo'shilsin yoki lokal PostgreSQL o'rnatilgan bo'lsin."
}

function Invoke-Native([string]$FilePath, [string[]]$Arguments) {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath exit code $LASTEXITCODE bilan tugadi."
    }
}

function Require-CloudDatabaseUrl {
    if (-not $CloudDatabaseUrl) {
        throw "Cloud database URL berilmagan. NEON_DATABASE_URL env varga Neon Postgres URLni yozing."
    }
}

Require-CloudDatabaseUrl
if (-not (Test-Path $python)) {
    throw "Python venv topilmadi: $python"
}

$LocalHost = if ($LocalHost) { $LocalHost } else { Get-DotEnvValue "POSTGRES_HOST" "localhost" }
$LocalPort = if ($LocalPort -gt 0) { $LocalPort } else { [int](Get-DotEnvValue "POSTGRES_PORT" "5432") }
$LocalDatabase = if ($LocalDatabase) { $LocalDatabase } else { Get-DotEnvValue "POSTGRES_DB" "uyjoy_olx" }
$LocalUser = if ($LocalUser) { $LocalUser } else { Get-DotEnvValue "POSTGRES_USER" "postgres" }
$LocalPassword = if ($LocalPassword) { $LocalPassword } else { Get-DotEnvValue "POSTGRES_PASSWORD" "" }
$localDsn = "host=$LocalHost port=$LocalPort dbname=$LocalDatabase user=$LocalUser password=$LocalPassword"

$pgDump = Resolve-PgTool "pg_dump"
$pgRestore = Resolve-PgTool "pg_restore"
$psql = Resolve-PgTool "psql"

function Convert-ToPsqlPath([string]$Path) {
    return $Path.Replace("\", "/").Replace("'", "''")
}

Write-Host "Cloud schema migration bajarilmoqda..."
$previousDatabaseUrl = $env:DATABASE_URL
$env:DATABASE_URL = $CloudDatabaseUrl
$env:PYTHONPATH = Join-Path $root "src"
Invoke-Native $python @("-m", "uyjoy_etl.cli", "migrate")

if ($FullRaw) {
    Write-Host "Lokal core raw data dump qilinmoqda: $dumpPath"
    $dumpArgs = @(
        "--dbname=$localDsn",
        "--format=custom",
        "--data-only",
        "--no-owner",
        "--no-acl",
        "--file=$dumpPath"
    )
    foreach ($table in $coreTables) {
        $dumpArgs += "--table=$table"
    }
    Invoke-Native $pgDump $dumpArgs

    Write-Host "Cloud raw data jadvallari tozalanmoqda..."
    $truncateTables = ($coreTables -join ", ")
    Invoke-Native $psql @("--dbname=$CloudDatabaseUrl", "--set=ON_ERROR_STOP=1", "--command=truncate table $truncateTables restart identity cascade;")

    Write-Host "Cloud raw data restore qilinmoqda..."
    Invoke-Native $pgRestore @("--dbname=$CloudDatabaseUrl", "--data-only", "--no-owner", "--no-acl", $dumpPath)

    Write-Host "Unified listing view/table refresh qilinmoqda..."
    Invoke-Native $python @("-m", "uyjoy_etl.cli", "refresh-unified-listings")
}
else {
    $csvPathForPsql = Convert-ToPsqlPath $marketCsvPath
    $copyOutSql = Join-Path $logsDir ("uyjoy-cloud-copy-out-{0}.sql" -f $timestamp)
    $copyInSql = Join-Path $logsDir ("uyjoy-cloud-copy-in-{0}.sql" -f $timestamp)

$copyOutQuery = "select * from public.real_estate_listings where coalesce(posted_at, first_seen_at, updated_at, last_seen_at) >= now() - interval '$RecentDays days'"
"\copy ($copyOutQuery) to '$csvPathForPsql' with (format csv, header true);" |
    Set-Content -LiteralPath $copyOutSql -Encoding UTF8

@"
truncate table public.real_estate_listings restart identity cascade;
\copy public.real_estate_listings from '$csvPathForPsql' with (format csv, header true);
select setval(
    pg_get_serial_sequence('public.real_estate_listings', 'id'),
    coalesce((select max(id) from public.real_estate_listings), 1),
    true
);
"@ | Set-Content -LiteralPath $copyInSql -Encoding UTF8

    try {
        Write-Host "Lokal market data export qilinmoqda: last $RecentDays days -> $marketCsvPath"
        Invoke-Native $psql @("--dbname=$localDsn", "--set=ON_ERROR_STOP=1", "--file=$copyOutSql")

        Write-Host "Cloud market data import qilinmoqda..."
        Invoke-Native $psql @("--dbname=$CloudDatabaseUrl", "--set=ON_ERROR_STOP=1", "--file=$copyInSql")
    }
    finally {
        Remove-Item -LiteralPath $copyOutSql -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $copyInSql -Force -ErrorAction SilentlyContinue
    }
}

if (-not $SkipModelTrain) {
    Write-Host "Cloud data bo'yicha 30 kunlik ML model train qilinmoqda..."
    Invoke-Native $python @("-m", "uyjoy_etl.cli", "train-valuation-model", "--days", "30")
}

if ($null -ne $previousDatabaseUrl) {
    $env:DATABASE_URL = $previousDatabaseUrl
}
else {
    Remove-Item Env:\DATABASE_URL -ErrorAction SilentlyContinue
}

Write-Host "Cloud data sync tayyor."
