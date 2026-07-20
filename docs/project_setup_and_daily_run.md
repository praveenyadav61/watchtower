# Project Setup and Daily Run

This is the complete installation and daily-operation guide for Windows and
macOS. Run commands from the project root.

## Watchlist

Create the daily CSV in the project root using the current India-market date:

```text
watchlist_YYYYMMDD.csv
```

Example:

```csv
symbol,volume_threshold,price_low_limit,price_high_limit,ema20
ADANIENT,500000,2950,3150,3025.40
```

At least one alert value is required per row. Unused alert cells may be blank.
The launch scripts prefer today's dated file and otherwise use `watchlist.csv`.

## First-time setup

Windows PowerShell:

```powershell
git clone <repository-url> alert-engine
cd alert-engine
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

macOS Terminal:

```bash
git clone <repository-url> alert-engine
cd alert-engine
bash ./setup.sh
```

Python 3.11 or newer is recommended. `tzdata` is installed automatically so
`Asia/Kolkata` scheduling works consistently on Windows and macOS.

## Set credentials

Credentials are read only from environment variables. The scripts never prompt
for or store them. Set them in every new terminal session.

Windows PowerShell:

```powershell
$env:UPSTOX_ACCESS_TOKEN = "your-current-upstox-token"
$env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/..."
```

macOS Terminal:

```bash
export UPSTOX_ACCESS_TOKEN="your-current-upstox-token"
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

`UPSTOX_ACCESS_TOKEN` is required. Slack is optional; without its webhook the
engine continues with console, CSV, and file logging.

Test Slack independently:

```powershell
.\.venv\Scripts\python.exe -m src.slack_notification
```

```bash
.venv/bin/python -m src.slack_notification
```

## Start the day

Windows:

```powershell
.\run_live.ps1
```

macOS:

```bash
bash ./run_live.sh
```

To select a different file explicitly:

```powershell
.\run_live.ps1 -Watchlist .\watchlist_YYYYMMDD.csv
```

```bash
bash ./run_live.sh ./watchlist_YYYYMMDD.csv
```

The engine initializes immediately, waits when started before market time, and
checks shortly after every 15-minute candle boundary. Windows sleep prevention
and macOS `caffeinate` remain active while the launch script is running. Keep a
laptop powered and do not close its lid.

Stop cleanly with `Ctrl+C`.

## Outputs

Daily files are written automatically:

```text
output/candles_YYYYMMDD.csv
output/execution_alerts_YYYYMMDD.csv
logs/alert_engine_YYYYMMDD.log
logs/alert_engine_errors_YYYYMMDD.log
```

Candles and alerts are deduplicated when the engine restarts. A failure for one
symbol is logged without terminating the remaining symbols.

## Closed-market test

Windows:

```powershell
.\.venv\Scripts\python.exe -m src.execution_engine `
  .\examples\multi_alert_watchlist.csv `
  --trading-date 20260713 `
  --mock-candles .\examples\mock_candles.json `
  --mock-instruments .\examples\mock_instruments.json
```

macOS:

```bash
.venv/bin/python -m src.execution_engine \
  ./examples/multi_alert_watchlist.csv \
  --trading-date 20260713 \
  --mock-candles ./examples/mock_candles.json \
  --mock-instruments ./examples/mock_instruments.json
```

## Quick troubleshooting

- Missing token: export `UPSTOX_ACCESS_TOKEN` before starting.
- No Slack: export `SLACK_WEBHOOK_URL`, then run the standalone Slack test.
- No candles yet: wait until a 15-minute candle has completed.
- Watchlist error: use the exact column names shown above and positive numbers.
- API failure: inspect the error-only log for the HTTP status and request ID.
- Laptop slept: restart the script; persisted candle and alert keys prevent
  duplicate output.
