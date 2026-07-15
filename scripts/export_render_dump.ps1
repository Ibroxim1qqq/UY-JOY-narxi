$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$backupDir = Join-Path $root "backups"
$dumpPath = Join-Path $backupDir "uyjoy-render-data.dump"
$pgDump = "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe"

if (-not (Test-Path $pgDump)) {
    throw "pg_dump topilmadi: $pgDump"
}

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

& (Join-Path $PSScriptRoot "start_local_postgres.ps1")

$env:PGPASSWORD = "uyjoy_password"

& $pgDump `
    -h 127.0.0.1 `
    -p 55432 `
    -U uyjoy `
    -d uyjoy_olx `
    --format=custom `
    --compress=9 `
    --data-only `
    --no-owner `
    --no-acl `
    --file $dumpPath

Write-Host "Render uchun data dump tayyor: $dumpPath"
