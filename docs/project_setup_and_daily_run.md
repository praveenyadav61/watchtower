# Project Setup and Daily Run Guide

This is the primary operating guide for installing and running the Alert Engine
on Windows or macOS.

## Daily run: quick commands

Before running, create today's dated watchlist in the project root:

```text
watchlist_YYYYMMDD.csv
```

For example:

```text
watchlist_20260717.csv
```

### Windows PowerShell

```powershell
cd "C:\path\to\alert-engine"

$env:UPSTOX_ACCESS_TOKEN = "PASTE_TODAYS_UPSTOX_TOKEN"
$env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/..."

.\run_live.ps1
```

### macOS Terminal

```bash
cd /path/to/alert-engine

export UPSTOX_ACCESS_TOKEN="PASTE_TODAYS_UPSTOX_TOKEN"
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."

bash ./run_live.sh
```

Keep the terminal running until the engine stops. Do not commit either secret
to Git or place them in the watchlist.

## One-time installation

Requirements:

- Git
- Python 3.11 or newer
- Internet access
- An Upstox account and access token
- An optional Slack incoming-webhook URL

Clone the repository:

```text
git clone <repository-url> alert-engine
cd alert-engine
```

### Windows setup

Open PowerShell in the repository:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

The setup script:

1. Creates `.venv` if needed.
2. Installs `requirements.txt`.
3. Verifies the `Asia/Kolkata` timezone.
4. Runs the complete automated test suite.

### macOS setup

```bash
bash ./setup.sh
```

The macOS setup performs the same environment, dependency, timezone, and test
checks.

Run the setup script again after pulling dependency changes.

## Prepare the daily watchlist

The launch scripts look for files in this order:

1. `watchlist_YYYYMMDD.csv` for the computer's current date.
2. `watchlist.csv`.

Use the dated filename to make daily operation and review clearer. Ensure the
computer's date and timezone are correct. You can also pass a file explicitly.

### Volume-threshold watchlist

For a volume-only run:

```csv
symbol,volume_threshold
ADANIENT,500000
ADANIGREEN,300000
```

Rules:

- `volume_threshold` must be a positive number.
- Do not use commas inside a number; use `500000`, not `5,00,000`.
- The threshold applies to one completed 15-minute candle.
- The engine alerts when:

```text
completed candle volume >= volume_threshold
```

The engine automatically supplies:

- Trading date
- Strategy ID `volume_threshold_v1`
- BUY decision
- Rank based on CSV row order

### Price-threshold watchlist

Price mode remains supported:

```csv
symbol,limit_price
ADANIENT,3056.08
ADANIGREEN,1508.74
```

The engine alerts when:

```text
completed candle low <= limit_price
```

Do not provide both `limit_price` and `volume_threshold` on the same row.

## Environment variables

### Upstox token

The Upstox token is required for live candles. If it is not exported, both run
scripts securely prompt for it.

Windows:

```powershell
$env:UPSTOX_ACCESS_TOKEN = "PASTE_TODAYS_UPSTOX_TOKEN"
```

macOS:

```bash
export UPSTOX_ACCESS_TOKEN="PASTE_TODAYS_UPSTOX_TOKEN"
```

### Slack webhook

Slack is optional. When configured, the engine sends:

- One initialization summary after watchlist resolution.
- One final notification when a symbol triggers.

It does not send WAIT evaluations or routine candle messages.

Windows:

```powershell
$env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/..."
```

macOS:

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

These commands set variables only in the current terminal. That is preferable
for secrets. Closing the terminal removes them.

Remove variables manually after the run if desired.

Windows:

```powershell
Remove-Item Env:UPSTOX_ACCESS_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:SLACK_WEBHOOK_URL -ErrorAction SilentlyContinue
```

macOS:

```bash
unset UPSTOX_ACCESS_TOKEN SLACK_WEBHOOK_URL
```

## Start the engine

### Windows

Automatic dated-watchlist selection:

```powershell
.\run_live.ps1
```

Explicit watchlist:

```powershell
.\run_live.ps1 -Watchlist .\watchlist_20260717.csv
```

The Windows script prevents automatic system sleep while the engine runs and
restores normal sleep behavior afterward. It cannot prevent manual sleep,
shutdown, or sleep caused by closing the lid. Keep the laptop plugged in and
the lid open. The display may turn off.

### macOS

Automatic dated-watchlist selection:

```bash
bash ./run_live.sh
```

Explicit watchlist:

```bash
bash ./run_live.sh ./watchlist_20260717.csv
```

The macOS script uses `caffeinate` for the lifetime of the engine. Keep the Mac
plugged in and the lid open.

## Expected daily timeline

You can start the engine before the market opens. It initializes immediately
and then waits.

Expected completed-candle checks are approximately:

```text
09:30:05  evaluates the 09:15–09:30 candle
09:45:05  evaluates the 09:30–09:45 candle
10:00:05  evaluates the 09:45–10:00 candle
...
15:00:05  evaluates the 14:45–15:00 candle and stops
```

The five-second delay gives the candle provider time to publish the completed
candle.

The candle CSV is created only when the first candle is successfully stored.
Therefore, it is normal not to see today's candle file before approximately
`09:30:05`.

## Expected startup output

Confirm the terminal or daily log contains:

```text
Initialization complete | active=<count> rejected=0 unresolved=0
Slack initialization notification sent
Live watch started
Next candle check at <timestamp>
```

If rejected or unresolved counts are nonzero, inspect the following log before
leaving the engine unattended.

## Daily output files

Operational logs:

```text
logs/alert_engine_YYYYMMDD.log
logs/alert_engine_errors_YYYYMMDD.log
```

Completed candles:

```text
output/candles_YYYYMMDD.csv
```

Triggered alerts:

```text
output/execution_alerts_YYYYMMDD.csv
```

The candle file contains timestamp, symbol, instrument key, OHLC, volume, and
open interest. The alert file records the alert type and the relevant price or
volume threshold.

## Safe shutdown

To stop manually, press:

```text
Ctrl+C
```

The engine logs a clean shutdown summary. Windows sleep prevention is released
when `run_live.ps1` exits.

Do not start a second instance while one engine is already running.

## Pre-run checklist

- [ ] Today's dated watchlist exists in the project root.
- [ ] Every symbol is an NSE equity trading symbol.
- [ ] Every threshold is a positive number.
- [ ] Each row contains exactly one threshold type.
- [ ] Upstox token is available or ready to paste.
- [ ] Slack webhook is exported if notifications are required.
- [ ] Laptop is plugged in with the lid open.
- [ ] Internet connection is stable.
- [ ] The terminal remains open.
- [ ] Initialization shows the expected number of active signals.
- [ ] The next candle-check timestamp is visible.

## Troubleshooting

### No candle CSV before 09:30

This is expected. The first 15-minute market candle is complete at 09:30, and
the engine checks it at approximately 09:30:05.

### No candle CSV after 09:31

Inspect:

```powershell
$date = (Get-Date).ToString("yyyyMMdd")
Get-Content ".\logs\alert_engine_$date.log" | Select-Object -Last 100
Get-Content ".\logs\alert_engine_errors_$date.log" | Select-Object -Last 100
```

On macOS:

```bash
RUN_DATE="$(date +%Y%m%d)"
tail -n 100 "logs/alert_engine_${RUN_DATE}.log"
tail -n 100 "logs/alert_engine_errors_${RUN_DATE}.log"
```

Look for token, DNS, Upstox API, unresolved-symbol, or candle-date errors.

### Slack initialization arrives but no BUY alert

That normally means no completed candle has crossed its configured threshold.
Check the candle CSV and compare its volume or low against the watchlist.

### Engine was restarted

The current version is not fully restart-safe. Existing candles are protected
from duplicate CSV writes, but prior alerts are not yet reloaded to suppress
duplicate alerts or Slack messages after a restart.

### Laptop slept or internet was disconnected

The current version retrieves the latest completed candle on the next check but
does not recover every missed intermediate candle. Review the logs and output
after connectivity returns.

## Closed-market test

Test the volume flow without live market data:

```powershell
.\.venv\Scripts\python.exe -m src.execution_engine `
  .\examples\mock_volume_watchlist.csv `
  --trading-date 20260713 `
  --mock-candles .\examples\mock_candles.json `
  --mock-instruments .\examples\mock_instruments.json
```

macOS:

```bash
.venv/bin/python -m src.execution_engine \
  ./examples/mock_volume_watchlist.csv \
  --trading-date 20260713 \
  --mock-candles ./examples/mock_candles.json \
  --mock-instruments ./examples/mock_instruments.json
```
