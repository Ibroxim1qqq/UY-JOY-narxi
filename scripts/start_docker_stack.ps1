$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Test-DockerReady {
    try {
        docker info *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Wait-Docker {
    for ($i = 1; $i -le 60; $i++) {
        if (Test-DockerReady) {
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "Docker daemon ishga tushmadi. Docker Desktopni ochib qayta urinib ko'ring."
}

if (-not (Test-DockerReady)) {
    $dockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerDesktop) {
        Start-Process -FilePath $dockerDesktop -WindowStyle Hidden
    }
    Wait-Docker
}

docker compose up -d

for ($i = 1; $i -le 60; $i++) {
    $status = docker inspect --format "{{json .State.Health.Status}}" uyjoy-postgres 2>$null
    if ($status -match "healthy") {
        Write-Host "Postgres tayyor: 127.0.0.1:55432"
        Write-Host "pgAdmin tayyor: http://127.0.0.1:5050"
        exit 0
    }
    Start-Sleep -Seconds 2
}

throw "Postgres container healthy bo'lmadi."
