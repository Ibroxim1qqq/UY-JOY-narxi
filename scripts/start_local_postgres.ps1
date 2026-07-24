$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$postgresBin = "C:\Program Files\PostgreSQL\17\bin"
$initDb = Join-Path $postgresBin "initdb.exe"
$pgCtl = Join-Path $postgresBin "pg_ctl.exe"
$psql = Join-Path $postgresBin "psql.exe"
$dataDir = Join-Path $root ".postgres-data"
$logsDir = Join-Path $root "logs"
$logFile = Join-Path $logsDir "postgres-local.log"
$password = "uyjoy_password"
$port = "55432"

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

if (-not (Test-Path $initDb)) {
    throw "PostgreSQL initdb topilmadi: $initDb"
}

if (-not (Test-Path $dataDir)) {
    $pwFile = Join-Path $logsDir "postgres_pw.tmp"
    Set-Content -Path $pwFile -Value $password -NoNewline -Encoding ASCII
    & $initDb -D $dataDir -U uyjoy --pwfile=$pwFile -A scram-sha-256 -E UTF8
    Remove-Item -LiteralPath $pwFile -Force
}

$isRunning = $false
try {
    & $pgCtl -D $dataDir status *> $null
    $isRunning = $LASTEXITCODE -eq 0
}
catch {
    $isRunning = $false
}

if (-not $isRunning) {
    & $pgCtl -D $dataDir -o "-p $port -c listen_addresses=127.0.0.1" -l $logFile start
}

$env:PGPASSWORD = $password
for ($i = 1; $i -le 40; $i++) {
    try {
        & $psql -h 127.0.0.1 -p $port -U uyjoy -d postgres -c "select 1;" *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Local Postgres tayyor: 127.0.0.1:$port"
            return
        }
    }
    catch {
    }
    Start-Sleep -Seconds 1
}

throw "Local Postgres 127.0.0.1:$port tayyor bo'lmadi."
