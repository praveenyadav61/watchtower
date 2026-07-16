# Tomorrow: Volume Threshold Run

Create `watchlist_20260717.csv` in the project root:

```csv
symbol,volume_threshold
ADANIENT,500000
ADANIGREEN,300000
```

Use plain positive numbers without Indian-style commas. Each threshold applies
to one completed 15-minute candle, not cumulative daily volume.

## Windows

```powershell
cd "C:\Users\Praveen Yadav\Projects\alert-engine"
$env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/..."
.\run_live.ps1
```

`run_live.ps1` automatically selects `watchlist_20260717.csv`, prompts for the
Upstox token if needed, and prevents automatic system sleep while it runs.

## macOS

```bash
cd /path/to/alert-engine
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
./run_live.sh
```

The macOS script also automatically selects the dated watchlist and runs through
`caffeinate`.

## Expected behavior

- Initialization Slack message after all symbols resolve.
- First completed-candle check at approximately `09:30:05` IST.
- A local `output/candles_20260717.csv`.
- One Slack and CSV alert per symbol when:

```text
completed 15-minute candle volume >= volume_threshold
```

- No Slack message for WAIT evaluations or routine candles.
- Price preparation and `limit_price` are not required for this run.
