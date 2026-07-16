param(
    [string]$Watchlist = ""
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $Watchlist) {
    $datedWatchlist = ".\watchlist_$((Get-Date).ToString('yyyyMMdd')).csv"
    $Watchlist = if (Test-Path -LiteralPath $datedWatchlist) {
        $datedWatchlist
    }
    else {
        ".\watchlist.csv"
    }
}

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

Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class AlertEngineSleepGuard
{
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint flags);
}
"@

$ES_CONTINUOUS = [uint32]2147483648
$ES_SYSTEM_REQUIRED = [uint32]1
$sleepGuardFlags = [uint32]($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)
$engineExitCode = 1

try {
    $previousState = [AlertEngineSleepGuard]::SetThreadExecutionState($sleepGuardFlags)
    if ($previousState -eq 0) {
        throw "Windows sleep prevention could not be enabled."
    }

    Write-Host "Windows automatic sleep prevention is active for this run."
    Write-Host "The display may turn off; keep the laptop plugged in and lid open."
    Write-Host "Starting live alert engine with $Watchlist..."
    & ".\.venv\Scripts\python.exe" -m src.execution_engine $Watchlist --watch
    $engineExitCode = $LASTEXITCODE
}
finally {
    [AlertEngineSleepGuard]::SetThreadExecutionState($ES_CONTINUOUS) | Out-Null
    Write-Host "Windows automatic sleep prevention released."
}

exit $engineExitCode
