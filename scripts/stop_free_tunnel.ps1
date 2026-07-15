$ErrorActionPreference = "Stop"

$processes = Get-Process cloudflared -ErrorAction SilentlyContinue
if (-not $processes) {
    Write-Host "cloudflared tunnel ishlamayapti."
    exit 0
}

$processes | Stop-Process -Force
Write-Host "cloudflared tunnel to'xtatildi."
