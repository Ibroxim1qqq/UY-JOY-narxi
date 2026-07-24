$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$port = 8000
$projectUvicornProcesses = @(
    Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
        Where-Object {
            $_.CommandLine -like "*uyjoy_etl.web_app:app*" -and
            $_.CommandLine -like "*$root*"
        }
)
foreach ($process in $projectUvicornProcesses) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}

$connection = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($connection) {
    Stop-Process -Id $connection.OwningProcess -Force
}
Start-Sleep -Seconds 1

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    py -m venv .venv
}

$python = Join-Path $root ".venv\Scripts\python.exe"
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$env:PYTHONPATH = Join-Path $root "src"

Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "uyjoy_etl.web_app:app", "--host", "127.0.0.1", "--port", "$port") `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "site.out.log") `
    -RedirectStandardError (Join-Path $logs "site.err.log")

Start-Sleep -Seconds 3
$response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/health" -UseBasicParsing -TimeoutSec 15
Write-Host "Dashboard ishlayapti: http://127.0.0.1:$port/ | status=$($response.StatusCode)"
