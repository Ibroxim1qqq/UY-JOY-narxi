$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$dashboardUrl = "http://127.0.0.1:8000"
$toolsDir = Join-Path $root "tools"
$localCloudflared = Join-Path $toolsDir "cloudflared.exe"

Write-Host "Lokal Postgres tekshirilmoqda..."
& (Join-Path $PSScriptRoot "start_local_postgres.ps1")

Write-Host "Dashboard qayta ishga tushirilmoqda..."
& (Join-Path $PSScriptRoot "restart_site.ps1")

$cloudflaredCommand = Get-Command cloudflared -ErrorAction SilentlyContinue
if ($cloudflaredCommand) {
    $cloudflaredPath = $cloudflaredCommand.Source
}
else {
    New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
    if (-not (Test-Path $localCloudflared)) {
        Write-Host "cloudflared yuklab olinmoqda..."
        Invoke-WebRequest `
            -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
            -OutFile $localCloudflared
    }
    $cloudflaredPath = $localCloudflared
}

Write-Host ""
Write-Host "Bepul public tunnel ishga tushmoqda."
Write-Host "Quyida chiqadigan https://...trycloudflare.com linkni browserda ochasiz."
Write-Host "Bu oynani yopmang, yopilsa public link ham to'xtaydi."
Write-Host ""

& $cloudflaredPath tunnel --url $dashboardUrl
