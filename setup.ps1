$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.11 or newer is required and was not found on PATH."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}

Write-Host "Installing dependencies..."
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host "Verifying Asia/Kolkata timezone..."
& ".\.venv\Scripts\python.exe" -c "from zoneinfo import ZoneInfo; print(ZoneInfo('Asia/Kolkata'))"

Write-Host "Running tests..."
& ".\.venv\Scripts\python.exe" -m unittest discover -s tests

if ($LASTEXITCODE -ne 0) {
    throw "Setup stopped because the test suite failed."
}

Write-Host "Setup complete. Run .\run_live.ps1 to start the engine."
