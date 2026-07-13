param(
    [string]$Watchlist = ".\watchlist.csv"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Virtual environment is missing. Run .\setup.ps1 first."
}
if (-not (Test-Path -LiteralPath $Watchlist)) {
    throw "Watchlist not found: $Watchlist"
}

if (-not $env:UPSTOX_ACCESS_TOKEN) {
    $secureToken = Read-Host "Paste the Upstox access token" -AsSecureString
    $tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    try {
        $env:UPSTOX_ACCESS_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
    }
}

Write-Host "Starting live alert engine with $Watchlist..."
& ".\.venv\Scripts\python.exe" -m src.execution_engine $Watchlist --watch
exit $LASTEXITCODE
