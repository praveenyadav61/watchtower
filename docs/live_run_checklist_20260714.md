# Live Run Checklist - 20260714

Use this checklist to install and run the alert engine on Windows or macOS on
Tuesday, July 14, 2026.

## Tomorrow command sequence

Before running these commands, copy the complete project to the target system,
open a terminal in the project directory, and place the prepared
`watchlist_20260714.csv` in the project root. Run the live process around
08:45-09:00 IST and keep its terminal open.

### Simplest supported path

Clone and enter the project first:

```text
git clone <repository-url> alert-engine
cd alert-engine
```

Then place `watchlist_20260714.csv` in that directory.

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
powershell -ExecutionPolicy Bypass -File .\run_live.ps1 `
  -Watchlist .\watchlist_20260714.csv
```

macOS Terminal:

```bash
bash ./setup.sh
bash ./run_live.sh ./watchlist_20260714.csv
```

The setup scripts create `.venv`, install dependencies, verify timezone data,
and run the tests. The live scripts securely request the token when necessary,
use today's `Asia/Kolkata` trading date, and start continuous watch mode. The
detailed individual commands remain below for troubleshooting.

### Windows PowerShell - setup and verification

```powershell
python --version
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -c "from zoneinfo import ZoneInfo; print(ZoneInfo('Asia/Kolkata'))"
python -m unittest discover -s tests
```

Expected timezone output:

```text
Asia/Kolkata
```

Expected test result:

```text
Ran 23 tests
OK
```

### Windows PowerShell - fast mock rehearsal

```powershell
python -m src.execution_engine .\examples\mock_watchlist.csv `
  --trading-date 20260713 `
  --mock `
  --watch `
  --mock-delay 0
```

### Windows PowerShell - validate tomorrow's watchlist

```powershell
python .\src\daily_initialization.py .\watchlist_20260714.csv `
  --trading-date 20260714
```

Do not continue until this prints `ENGINE READY` and all unexpected rejected or
unresolved rows are fixed.

### Windows PowerShell - start the live day

Use the same activated PowerShell window:

```powershell
$env:UPSTOX_ACCESS_TOKEN = "paste-current-token-here"

python -m src.execution_engine .\watchlist_20260714.csv `
  --trading-date 20260714 `
  --watch
```

### Windows PowerShell - monitor from a second window

Open another PowerShell window in the project directory:

```powershell
Get-Content .\logs\alert_engine_20260714.log -Wait
```

For errors only:

```powershell
Get-Content .\logs\alert_engine_errors_20260714.log -Wait
```

### macOS Terminal - setup and verification

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -c "from zoneinfo import ZoneInfo; print(ZoneInfo('Asia/Kolkata'))"
python -m unittest discover -s tests
```

Expected timezone output:

```text
Asia/Kolkata
```

Expected test result:

```text
Ran 23 tests
OK
```

### macOS Terminal - fast mock rehearsal

```bash
python -m src.execution_engine ./examples/mock_watchlist.csv \
  --trading-date 20260713 \
  --mock \
  --watch \
  --mock-delay 0
```

### macOS Terminal - validate tomorrow's watchlist

```bash
python ./src/daily_initialization.py ./watchlist_20260714.csv \
  --trading-date 20260714
```

Do not continue until this prints `ENGINE READY` and all unexpected rejected or
unresolved rows are fixed.

### macOS Terminal - start the live day

Use the same activated Terminal window. `caffeinate` prevents sleep while the
engine is running:

```bash
export UPSTOX_ACCESS_TOKEN="paste-current-token-here"

caffeinate -dimsu python -m src.execution_engine ./watchlist_20260714.csv \
  --trading-date 20260714 \
  --watch
```

### macOS Terminal - monitor from a second window

Open another Terminal window in the project directory:

```bash
tail -f ./logs/alert_engine_20260714.log
```

For errors only:

```bash
tail -f ./logs/alert_engine_errors_20260714.log
```

### End of day

The engine should stop after its market cutoff. To stop it manually, focus the
engine terminal and press `Ctrl+C` once. Confirm the final shutdown summary,
then preserve these files:

```text
logs/alert_engine_20260714.log
logs/alert_engine_errors_20260714.log
output/candles_20260714.csv
output/execution_alerts_20260714.csv
```

## Current readiness

- [x] Watchlist validation exists.
- [x] Official Upstox NSE instrument resolution exists.
- [x] Live 15-minute candle retrieval exists.
- [x] The engine can start before market hours and remain in `--watch` mode.
- [x] BUY evaluation compares completed candle low with `limit_price`.
- [x] One failing symbol does not stop other symbols.
- [x] Combined and error-only daily logs exist.
- [x] Candle CSV persistence is implemented.
- [x] Alert CSV persistence is implemented.
- [ ] Restart-safe alert deduplication is not implemented yet.
- [x] Graceful Ctrl+C/end-of-day summary handling is implemented.

The engine writes operational logs, completed-candle CSV rows, and execution
alert CSV rows. It does not yet reload prior alerts after a restart.

## 1. Prepare the project on the source system

- [ ] Ensure all intended changes are saved.
- [ ] Run the automated tests:

```powershell
python -m unittest discover -s tests
```

- [ ] Confirm all tests pass.
- [ ] Prepare `watchlist_20260714.csv`.
- [ ] Confirm every row has `trading_date=20260714`.
- [ ] Confirm every row has a positive `limit_price`.
- [ ] Confirm only intended rows have `entry_decision=BUY`.
- [ ] Confirm each `strategy_id + symbol` pair is unique.
- [ ] Copy the complete project directory to the target system.
- [ ] Do not copy `.venv`, `logs`, `__pycache__`, or `.env` files.

Minimum watchlist columns:

```csv
trading_date,strategy_id,symbol,entry_decision,rank,limit_price
20260714,base_recovery_strategy_v1,MOTILALOFS,BUY,1,100.50
```

## 2. Prepare the target system

### Windows

- [ ] Install Python 3.11 or newer.
- [ ] Confirm Python is available:

```powershell
python --version
```

- [ ] Open PowerShell in the copied project directory.
- [ ] Create a fresh virtual environment:

```powershell
python -m venv .venv
```

- [ ] If script activation is blocked, allow it for this PowerShell session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

- [ ] Activate the environment and install dependencies:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

- [ ] Run tests on the target system:

```powershell
python -m unittest discover -s tests
```

- [ ] Prevent Windows sleep/hibernate during market hours.
- [ ] Confirm the internet connection is stable.
- [ ] Confirm the system clock is synchronized. Market logic uses
      `Asia/Kolkata`, but an accurate system clock is still required.

### macOS

- [ ] Install Python 3.11 or newer. If needed, install it through Homebrew or
      the official Python installer.
- [ ] Confirm Python is available:

```bash
python3 --version
```

- [ ] Open Terminal in the copied project directory.
- [ ] Create and activate a fresh virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

- [ ] Verify timezone support:

```bash
python -c "from zoneinfo import ZoneInfo; print(ZoneInfo('Asia/Kolkata'))"
```

- [ ] Run tests:

```bash
python -m unittest discover -s tests
```

- [ ] Confirm all tests pass.
- [ ] In System Settings, prevent automatic sleep during the market session,
      or launch the live command through `caffeinate` as shown below.
- [ ] Confirm the internet connection and system clock are reliable.

## 3. Run the mock rehearsal

- [ ] Run a fast mock session before using the live token:

```powershell
python -m src.execution_engine .\examples\mock_watchlist.csv `
  --trading-date 20260713 `
  --mock `
  --watch `
  --mock-delay 0
```

macOS:

```bash
python -m src.execution_engine ./examples/mock_watchlist.csv \
  --trading-date 20260713 \
  --mock \
  --watch \
  --mock-delay 0
```

- [ ] Confirm initialization completes.
- [ ] Confirm WAIT evaluations appear.
- [ ] Confirm execution alerts appear.
- [ ] Confirm these log files are created:

```text
logs/alert_engine_20260713.log
logs/alert_engine_errors_20260713.log
```

## 4. Validate the live watchlist

- [ ] Run initialization without starting candle monitoring:

```powershell
python .\src\daily_initialization.py .\watchlist_20260714.csv `
  --trading-date 20260714
```

macOS:

```bash
python ./src/daily_initialization.py ./watchlist_20260714.csv \
  --trading-date 20260714
```

- [ ] Confirm `ENGINE READY` is printed.
- [ ] Review every rejected row.
- [ ] Review every unresolved symbol.
- [ ] Confirm the active-signal count matches expectations.

Do not proceed until unexpected rejected or unresolved signals are fixed.

## 5. Obtain and set the Upstox token

- [ ] Obtain a current valid read-only Upstox token on the morning of the run.
- [ ] Set it only in the current PowerShell process:

```powershell
$env:UPSTOX_ACCESS_TOKEN = "paste-token-here"
```

macOS:

```bash
export UPSTOX_ACCESS_TOKEN="paste-token-here"
```

- [ ] Do not place the token in source code, CSV files, command arguments,
      screenshots, or log files.

## 6. Start the live engine before market hours

Recommended start time: 08:45–09:00 IST.

- [ ] Activate the virtual environment if it is not already active:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS activation:

```bash
source .venv/bin/activate
```

- [ ] Start the engine:

```powershell
python -m src.execution_engine .\watchlist_20260714.csv `
  --trading-date 20260714 `
  --watch
```

macOS live command, with sleep prevention for the lifetime of the process:

```bash
caffeinate -dimsu python -m src.execution_engine ./watchlist_20260714.csv \
  --trading-date 20260714 \
  --watch
```

- [ ] Keep the PowerShell window open.
- [ ] Confirm the instrument master downloads successfully.
- [ ] Confirm initialization shows the expected active signals.
- [ ] Confirm the engine reports its next candle-check time.
- [ ] Confirm the access token does not appear in console or file logs.

Expected schedule:

```text
Before 09:30  Initialization complete; engine waits
09:30          Evaluate completed 09:15 candle
09:45          Evaluate completed 09:30 candle
10:00          Evaluate completed 09:45 candle
...            Continue every 15 minutes
15:00          Evaluate completed 14:45 candle and stop
```

## 7. Monitor during market hours

- [ ] Keep the computer powered and connected.
- [ ] Check that a new evaluation appears after each completed interval.
- [ ] Review warnings without stopping the process unnecessarily.
- [ ] Use the error-only log for quick failures:

```powershell
Get-Content .\logs\alert_engine_errors_20260714.log -Wait
```

macOS:

```bash
tail -f ./logs/alert_engine_errors_20260714.log
```

- [ ] Use the combined log for full activity:

```powershell
Get-Content .\logs\alert_engine_20260714.log -Wait
```

macOS:

```bash
tail -f ./logs/alert_engine_20260714.log
```

- [ ] Manually compare at least one completed candle with the Upstox chart.
- [ ] Manually verify any printed alert before acting on it.

## 8. Shutdown and end-of-day review

- [ ] Allow the engine to stop at its cutoff when possible.
- [ ] If manual shutdown is required, press `Ctrl+C` once.
- [ ] Keep the logs from the entire session.
- [ ] Review `alert_engine_errors_20260714.log` first.
- [ ] Review every alert and its preceding WAIT evaluations in the combined log.
- [ ] Record any missing interval, API failure, unresolved symbol, or unexpected
      price decision for the next development iteration.

## Required code changes for safer live operation

These should be implemented before treating the engine as restart-safe:

1. Load the existing alert CSV at startup so restarting the process cannot
   produce the same alert again.
2. Process all unseen completed candles after a late start or temporary outage,
   rather than evaluating only the latest candle.

Until these are complete, avoid restarting the engine after an alert unless you
manually verify that the same signal is not alerted twice.
