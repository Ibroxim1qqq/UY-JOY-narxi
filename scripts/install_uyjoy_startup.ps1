$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $root "scripts\uyjoy_daemon.ps1"
$taskName = "UYJOY Core Daemon"
$oldTaskNames = @("UYJOY Core Start", "UYJOY Metabase Deploy", "UyJoyDailyUpdate")
$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "UYJOY Core Daemon.lnk"
$oldShortcutPaths = @(
    (Join-Path $startupDir "UYJOY Core Start.lnk"),
    (Join-Path $startupDir "UYJOY Metabase Deploy.lnk")
)

if (-not (Test-Path $scriptPath)) {
    throw "Start script topilmadi: $scriptPath"
}

foreach ($oldShortcutPath in $oldShortcutPaths) {
    if (Test-Path $oldShortcutPath) {
        Remove-Item -LiteralPath $oldShortcutPath -Force
    }
}

foreach ($oldTaskName in $oldTaskNames) {
    $oldTask = Get-ScheduledTask -TaskName $oldTaskName -ErrorAction SilentlyContinue
    if ($oldTask) {
        try {
            Unregister-ScheduledTask -TaskName $oldTaskName -Confirm:$false
        }
        catch {
            Write-Host "Eski scheduled task o'chirilmadi ($oldTaskName): $($_.Exception.Message)"
        }
    }
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "UY-JOY core daemon: Postgres, Metabase va ML formani doimiy sog'lom ushlab turadi." `
        -Force | Out-Null

    Write-Host "Scheduled task o'rnatildi: $taskName"
}
catch {
    Write-Host "Scheduled task o'rnatilmadi, Startup shortcut ishlatiladi: $($_.Exception.Message)"
    New-Item -ItemType Directory -Force -Path $startupDir | Out-Null
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "powershell.exe"
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""
    $shortcut.WorkingDirectory = $root
    $shortcut.Description = "UY-JOY core daemon"
    $shortcut.Save()
    Write-Host "Startup shortcut o'rnatildi: $shortcutPath"
}

Write-Host "Hozir ishga tushirish: powershell -ExecutionPolicy Bypass -File `"$scriptPath`""
