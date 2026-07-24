$ErrorActionPreference = "Stop"

$taskNames = @("UYJOY Core Daemon", "UYJOY Core Start", "UYJOY Metabase Deploy", "UyJoyDailyUpdate")
$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPaths = @(
    (Join-Path $startupDir "UYJOY Core Daemon.lnk"),
    (Join-Path $startupDir "UYJOY Core Start.lnk"),
    (Join-Path $startupDir "UYJOY Metabase Deploy.lnk")
)
$removed = $false

foreach ($taskName in $taskNames) {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Scheduled task o'chirildi: $taskName"
        $removed = $true
    }
}

foreach ($shortcutPath in $shortcutPaths) {
    if (Test-Path $shortcutPath) {
        Remove-Item -LiteralPath $shortcutPath -Force
        Write-Host "Startup shortcut o'chirildi: $shortcutPath"
        $removed = $true
    }
}

if (-not $removed) {
    Write-Host "Autostart yozuvi topilmadi."
}
