$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
}

$python = if (Test-Path ".\.venv\Scripts\python.exe") {
    ".\.venv\Scripts\python.exe"
}
else {
    "python"
}

$env:PYTHONPATH = Join-Path $root "src"
& $python -m compileall src
& $python -m unittest discover -s tests -p "test_*.py"
