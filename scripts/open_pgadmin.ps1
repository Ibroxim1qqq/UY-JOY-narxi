$pgAdminPath = "C:\Program Files\PostgreSQL\17\pgAdmin 4\runtime\pgAdmin4.exe"

if (-not (Test-Path $pgAdminPath)) {
    Write-Error "pgAdmin topilmadi: $pgAdminPath"
    exit 1
}

Start-Process -FilePath $pgAdminPath
