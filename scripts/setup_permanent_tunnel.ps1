param(
    [string]$Hostname = "dashboard.uysot.uz",
    [string]$TunnelName = "uyjoy-dashboard"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$toolsDir = Join-Path $root "tools"
$logsDir = Join-Path $root "logs"
$infraDir = Join-Path $root "infra\cloudflare"
$cloudflared = Join-Path $toolsDir "cloudflared.exe"
$configPath = Join-Path $infraDir "config.yml"
$urlFile = Join-Path $logsDir "permanent-public-url.txt"

New-Item -ItemType Directory -Force -Path $toolsDir, $logsDir, $infraDir | Out-Null

if (-not (Test-Path $cloudflared)) {
    Write-Host "cloudflared yuklab olinmoqda..."
    Invoke-WebRequest `
        -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
        -OutFile $cloudflared
}

Write-Host "Local Postgres va dashboard ishga tushirilmoqda..."
& (Join-Path $PSScriptRoot "start_local_postgres.ps1")
& (Join-Path $PSScriptRoot "restart_site.ps1")

$certPath = Join-Path $HOME ".cloudflared\cert.pem"
if (-not (Test-Path $certPath)) {
    Write-Host ""
    Write-Host "Cloudflare login kerak. Browser ochilsa, Cloudflare accountga kiring va domenni tanlang."
    Write-Host "Domen Cloudflare accountda bo'lishi kerak: $Hostname"
    & $cloudflared tunnel login
}

Write-Host "Named tunnel tekshirilmoqda/yartilmoqda: $TunnelName"
$tunnelId = $null

try {
    $listJson = & $cloudflared tunnel list --output json 2>$null
    if ($listJson) {
        $tunnels = $listJson | ConvertFrom-Json
        $existing = $tunnels | Where-Object { $_.name -eq $TunnelName } | Select-Object -First 1
        if ($existing) {
            $tunnelId = $existing.id
            Write-Host "Mavjud tunnel topildi: $TunnelName ($tunnelId)"
        }
    }
} catch {
    Write-Host "Tunnel ro'yxatini o'qib bo'lmadi, yangi tunnel yaratishga urinaman."
}

if (-not $tunnelId) {
    $createOutput = (& $cloudflared tunnel create $TunnelName 2>&1) | Out-String
    $match = [regex]::Match($createOutput, "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
    if (-not $match.Success) {
        Write-Host $createOutput
        throw "Tunnel ID topilmadi. Cloudflare login/domen sozlamasini tekshiring."
    }
    $tunnelId = $match.Value
    Write-Host "Yangi tunnel yaratildi: $TunnelName ($tunnelId)"
}

$credentialsFile = Join-Path $HOME ".cloudflared\$tunnelId.json"
if (-not (Test-Path $credentialsFile)) {
    throw "Tunnel credential fayli topilmadi: $credentialsFile"
}

Write-Host "DNS route sozlanmoqda: $Hostname -> $TunnelName"
& $cloudflared tunnel route dns $TunnelName $Hostname

$credentialsYamlPath = $credentialsFile.Replace("\", "/")
$configText = @"
tunnel: $tunnelId
credentials-file: $credentialsYamlPath

ingress:
  - hostname: $Hostname
    service: http://127.0.0.1:8000
  - service: http_status:404
"@

Set-Content -Path $configPath -Value $configText -Encoding UTF8
Set-Content -Path $urlFile -Value "https://$Hostname" -Encoding UTF8

Write-Host ""
Write-Host "Doimiy tunnel sozlandi."
Write-Host "URL: https://$Hostname"
Write-Host "Keyingi safar ishga tushirish:"
Write-Host "powershell -ExecutionPolicy Bypass -File .\scripts\start_permanent_tunnel.ps1"
