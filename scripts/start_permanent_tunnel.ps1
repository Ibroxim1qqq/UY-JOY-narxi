$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$toolsDir = Join-Path $root "tools"
$logsDir = Join-Path $root "logs"
$cloudflared = Join-Path $toolsDir "cloudflared.exe"
$configPath = Join-Path $root "infra\cloudflare\config.yml"
$outLog = Join-Path $logsDir "cloudflared-permanent.out.log"
$errLog = Join-Path $logsDir "cloudflared-permanent.err.log"
$urlFile = Join-Path $logsDir "permanent-public-url.txt"

if (-not (Test-Path $cloudflared)) {
    throw "cloudflared.exe topilmadi. Avval scripts\setup_permanent_tunnel.ps1 ni ishlating."
}

if (-not (Test-Path $configPath)) {
    throw "Permanent tunnel config topilmadi: $configPath. Avval scripts\setup_permanent_tunnel.ps1 ni ishlating."
}

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

& (Join-Path $PSScriptRoot "start_local_postgres.ps1")
& (Join-Path $PSScriptRoot "restart_site.ps1")

Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item -LiteralPath $outLog, $errLog -ErrorAction SilentlyContinue

Start-Process `
    -FilePath $cloudflared `
    -ArgumentList @("tunnel", "--config", $configPath, "run") `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog

Start-Sleep -Seconds 3

if (Test-Path $urlFile) {
    $url = Get-Content -Raw $urlFile
    Write-Host "Permanent tunnel ishga tushdi: $($url.Trim())"
} else {
    Write-Host "Permanent tunnel ishga tushdi. URL infra\cloudflare\config.yml ichidagi hostname."
}
