param(
    [string]$CloudMetabaseDatabaseUrl = $env:METABASE_DATABASE_URL,
    [string]$CloudWarehouseDatabaseUrl = $env:NEON_DATABASE_URL,
    [string]$LocalHost,
    [int]$LocalPort = 0,
    [string]$LocalUser,
    [string]$LocalPassword
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$logsDir = Join-Path $root "logs"
$dumpPath = Join-Path $logsDir ("uyjoy-cloud-metabase-{0}.dump" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

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

function Convert-WarehouseUrlToMetabaseDetails([string]$Url) {
    $uri = [Uri]$Url
    $userInfo = $uri.UserInfo.Split(":", 2)
    if ($userInfo.Count -lt 2) {
        throw "NEON_DATABASE_URL ichida user/password bo'lishi kerak."
    }

    $port = if ($uri.Port -gt 0) { $uri.Port } else { 5432 }
    $database = $uri.AbsolutePath.TrimStart("/")
    if (-not $database) {
        $database = "postgres"
    }

    return [ordered]@{
        ssl = $true
        password = [Uri]::UnescapeDataString($userInfo[1])
        port = $port
        "advanced-options" = $true
        "schema-filters-type" = "all"
        dbname = $database
        host = $uri.Host
        "tunnel-enabled" = $false
        "json-unfolding" = $true
        user = [Uri]::UnescapeDataString($userInfo[0])
    } | ConvertTo-Json -Compress -Depth 4
}

if (-not $CloudMetabaseDatabaseUrl) {
    throw "METABASE_DATABASE_URL env varga Metabase app database URL yozilmagan."
}
if (-not $CloudWarehouseDatabaseUrl) {
    throw "NEON_DATABASE_URL env varga UY-JOY warehouse database URL yozilmagan."
}

$LocalHost = if ($LocalHost) { $LocalHost } else { Get-DotEnvValue "POSTGRES_HOST" "localhost" }
$LocalPort = if ($LocalPort -gt 0) { $LocalPort } else { [int](Get-DotEnvValue "POSTGRES_PORT" "5432") }
$LocalUser = if ($LocalUser) { $LocalUser } else { Get-DotEnvValue "POSTGRES_USER" "postgres" }
$LocalPassword = if ($LocalPassword) { $LocalPassword } else { Get-DotEnvValue "POSTGRES_PASSWORD" "" }
$localDsn = "host=$LocalHost port=$LocalPort dbname=metabase_app user=$LocalUser password=$LocalPassword"

$pgDump = Resolve-PgTool "pg_dump"
$pgRestore = Resolve-PgTool "pg_restore"
$psql = Resolve-PgTool "psql"

Write-Host "Lokal Metabase metadata dump qilinmoqda: $dumpPath"
& $pgDump "--dbname=$localDsn" "--format=custom" "--no-owner" "--no-acl" "--file=$dumpPath"

Write-Host "Cloud Metabase app database restore qilinmoqda..."
& $pgRestore "--dbname=$CloudMetabaseDatabaseUrl" "--clean" "--if-exists" "--no-owner" "--no-acl" $dumpPath

Write-Host "Metabase ichidagi UY-JOY Postgres connection Neon warehousega yo'naltirilmoqda..."
$detailsJson = Convert-WarehouseUrlToMetabaseDetails $CloudWarehouseDatabaseUrl
$escapedDetails = $detailsJson.Replace("'", "''")
$sqlPath = Join-Path $env:TEMP ("uyjoy-metabase-patch-{0}.sql" -f ([Guid]::NewGuid().ToString("N")))
@"
update metabase_database
set details = '$escapedDetails',
    updated_at = now()
where engine = 'postgres'
  and name = 'UY-JOY Postgres';
"@ | Set-Content -LiteralPath $sqlPath -Encoding UTF8

try {
    & $psql "--dbname=$CloudMetabaseDatabaseUrl" "--set=ON_ERROR_STOP=1" "--file=$sqlPath"
}
finally {
    Remove-Item -LiteralPath $sqlPath -Force -ErrorAction SilentlyContinue
}

Write-Host "Cloud Metabase metadata sync tayyor."
