$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$envPath = Join-Path $root ".env"
if (-not (Test-Path $envPath)) {
    throw ".env topilmadi. Avval local konfiguratsiyani yarating."
}

$envText = Get-Content -Raw $envPath
if ($envText -notmatch "(?m)^DASHBOARD_USERNAME=.+$" -or $envText -notmatch "(?m)^DASHBOARD_PASSWORD=.+$") {
    throw "Public tunnel uchun .env ichida DASHBOARD_USERNAME va DASHBOARD_PASSWORD bo'lishi shart."
}

$toolsDir = Join-Path $root "tools"
$logsDir = Join-Path $root "logs"
$cloudflared = Join-Path $toolsDir "cloudflared.exe"
$outLog = Join-Path $logsDir "cloudflared.out.log"
$errLog = Join-Path $logsDir "cloudflared.err.log"
$urlFile = Join-Path $logsDir "public-url.txt"

New-Item -ItemType Directory -Force -Path $toolsDir, $logsDir | Out-Null

& (Join-Path $PSScriptRoot "start_local_postgres.ps1")
& (Join-Path $PSScriptRoot "restart_site.ps1")

if (-not (Test-Path $cloudflared)) {
    Invoke-WebRequest `
        -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
        -OutFile $cloudflared
}

Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item -LiteralPath $outLog, $errLog, $urlFile -ErrorAction SilentlyContinue

Start-Process `
    -FilePath $cloudflared `
    -ArgumentList @("tunnel", "--url", "http://127.0.0.1:8000") `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog

for ($i = 1; $i -le 30; $i++) {
    Start-Sleep -Seconds 1
    $logText = ""
    if (Test-Path $errLog) {
        $logText = Get-Content -Raw $errLog
    }
    $match = [regex]::Match($logText, "https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    if ($match.Success) {
        Set-Content -Path $urlFile -Value $match.Value -Encoding UTF8
        Write-Host "Public URL: $($match.Value)"
        Write-Host "Login: .env ichidagi DASHBOARD_USERNAME / DASHBOARD_PASSWORD"
        exit 0
    }
}

throw "Cloudflare public URL 30 soniyada topilmadi. Logni tekshiring: $errLog"
