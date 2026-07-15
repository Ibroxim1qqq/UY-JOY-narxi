param(
    [string]$PostgresPassword
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $root ".env"
$examplePath = Join-Path $root ".env.example"

if (Test-Path $envPath) {
    Write-Host ".env already exists: $envPath"
    exit 0
}

if (-not $PostgresPassword) {
    $secure = Read-Host "Postgres password" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $PostgresPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
}

$content = Get-Content $examplePath -Raw
$content = $content.Replace("CHANGE_ME", $PostgresPassword)
Set-Content -Path $envPath -Value $content -Encoding UTF8
Write-Host ".env created: $envPath"
