param(
    [Parameter(Mandatory = $true)]
    [string]$DatabaseUrl,

    [string]$DumpPath = ""
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $DumpPath) {
    $DumpPath = Join-Path $root "backups\uyjoy-render-data.dump"
}

$psql = "C:\Program Files\PostgreSQL\17\bin\psql.exe"
$pgRestore = "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe"

if (-not (Test-Path $psql)) {
    throw "psql topilmadi: $psql"
}
if (-not (Test-Path $pgRestore)) {
    throw "pg_restore topilmadi: $pgRestore"
}
if (-not (Test-Path $DumpPath)) {
    throw "Dump fayl topilmadi: $DumpPath. Avval scripts\export_render_dump.ps1 ni ishlating."
}

# Render external Postgres odatda SSL talab qiladi.
$env:PGSSLMODE = "require"

Write-Host "Render schema yaratilmoqda..."
& $psql $DatabaseUrl -v ON_ERROR_STOP=1 -f (Join-Path $root "sql\schema.sql")

Write-Host "Eski data tozalanmoqda..."
& $psql $DatabaseUrl -v ON_ERROR_STOP=1 -c "truncate table olx_fetch_logs, etl_runs, olx_listing_raw restart identity cascade;"

Write-Host "Dump Render Postgresga yozilmoqda..."
& $pgRestore `
    --dbname $DatabaseUrl `
    --data-only `
    --no-owner `
    --no-acl `
    --verbose `
    $DumpPath

Write-Host "Restore tugadi. Tekshiruv:"
& $psql $DatabaseUrl -c "select count(*) as listings from olx_listing_raw;"
