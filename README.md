# Execution Engine

The first project milestone fetches and displays the latest **completed**
15-minute candle for one Upstox instrument.

Business dates in project inputs and outputs use `YYYYMMDD` (for example,
`20260713`). Upstox candle timestamps remain timezone-aware ISO-8601 values.

For installation, environment variables, daily commands, expected timings,
outputs, and troubleshooting, use the
[Project Setup and Daily Run Guide](docs/project_setup_and_daily_run.md).

## Quick setup and live run

After cloning or copying the project, place the watchlist in the project root.
The live scripts automatically prefer `watchlist_YYYYMMDD.csv` for the current
date and otherwise use `watchlist.csv`.

```text
git clone <repository-url> alert-engine
cd alert-engine
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
powershell -ExecutionPolicy Bypass -File .\run_live.ps1
```

On Windows, `run_live.ps1` prevents automatic system sleep for the lifetime of
the engine and restores the normal sleep policy when the engine exits. It does
not prevent manual sleep or lid-close sleep, so keep the laptop plugged in with
the lid open. The display is still allowed to turn off.

macOS Terminal:

```bash
bash ./setup.sh
bash ./run_live.sh
```

Both live-run scripts securely prompt for the Upstox token when it is not
already set. They start continuous watch mode, and the engine derives today's
trading date in `Asia/Kolkata`. Pass a different watchlist when needed:

```powershell
.\run_live.ps1 -Watchlist .\watchlist_20260714.csv
```

```bash
bash ./run_live.sh ./watchlist_20260714.csv
```

For a volume-only session, the entire watchlist can be:

```csv
symbol,volume_threshold
ADANIENT,500000
ADANIGREEN,300000
```

The engine supplies the trading date, `volume_threshold_v1` strategy, BUY
decision, and row-order rank. It evaluates completed 15-minute candle volume
and alerts once when `candle volume >= volume_threshold`. Price watchlists using
`limit_price` remain supported. Do not put both thresholds on the same row.

Test volume mode without a live market:

```powershell
.\.venv\Scripts\python.exe -m src.execution_engine `
  .\examples\mock_volume_watchlist.csv `
  --trading-date 20260713 `
  --mock-candles .\examples\mock_candles.json `
  --mock-instruments .\examples\mock_instruments.json
```

## Run

Python 3.11 or newer is recommended. Install the one HTTP dependency:

```powershell
python -m pip install -r requirements.txt
```

The requirements also install the IANA timezone database needed by Python's
`zoneinfo` on Windows for `Asia/Kolkata` market scheduling.

In PowerShell:

```powershell
$env:UPSTOX_ACCESS_TOKEN = "your-access-token"
python .\upstox_candles.py "NSE_EQ|INE848E01016"
```

On macOS, create and activate the environment with:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Then use the same Python module commands with `/` paths. The runtime contains
no Windows-specific APIs; `tzdata` supplies consistent `Asia/Kolkata` timezone
support across Windows and macOS.

The access token is read from the environment and is never printed. The script
requests `minutes/15` data, ignores any currently forming candle, and prints the
newest completed candle.

Manually compare the timestamp and OHLC values with the Upstox chart before
adding the next project feature.

## Test without the API

Use the included Upstox-format mock response:

```powershell
python .\upstox_candles.py "NSE_EQ|INE848E01016" --mock-file .\examples\mock_candles.json
```

Mock mode does not need a token. It uses the same response validation,
completed-candle selection, and output formatting as live mode.

## Run daily initialization

Validate the watchlist, download the official Upstox NSE instrument master, and
resolve every accepted symbol through one command:

```powershell
python .\src\daily_initialization.py .\watchlist.csv --trading-date 20260710
```

When initializing for today, omit the date. Today is calculated in the
`Asia/Kolkata` timezone:

```powershell
python .\src\daily_initialization.py .\watchlist.csv
```

The initializer ignores extra CSV columns and reports rejected or unresolved
rows as warnings. It prints `ENGINE READY` when at least one signal resolves
uniquely to an `NSE_EQ` instrument whose type is `EQ`. Failed rows do not block
usable signals from starting.

## Run the basic alert flow

Each watchlist row supplies its BUY `limit_price`. The engine waits while the
completed candle low is above that price and prints an alert once the candle
low reaches or crosses it. Use the bundled fixtures for a fully isolated test:

```powershell
python -m src.execution_engine .\examples\mock_watchlist_single.csv --trading-date 20260713 --mock-candles .\examples\mock_candles.json --mock-instruments .\examples\mock_instruments.json
```

Omit `--mock-candles` to fetch each instrument's live intraday candles using
`UPSTOX_ACCESS_TOKEN`. The command prints WAIT evaluations and actionable
execution alerts; it does not place orders.

### Temporary closed-market mock replay

Use the bundled candle fixture when the market is closed:

```powershell
python -m src.execution_engine .\examples\mock_watchlist.csv --trading-date 20260713 --mock --watch
```

Mock mode is intentionally temporary and prominently identifies itself in the
console. It still downloads the official Upstox NSE instrument master and uses
it to resolve every watchlist symbol. Only intraday candles are mocked, so no
access token or active market is required. Watch mode advances through the
mock trading session once per second. Each symbol has its own 12-candle price
sequence, showing WAIT evaluations followed by a staggered alert when its
configured limit is reached. One mock second represents one completed
15-minute candle; it does not pretend the market produces one-second candles.
Use `--mock-delay 0` for an instant replay.

### Daily operational logs

Every command writes readable console output and appends operational events to
`logs/alert_engine_YYYYMMDD.log`. Errors are also copied to the smaller
`logs/alert_engine_errors_YYYYMMDD.log` for quick review. Each line contains a
timestamp, severity, strategy, symbol, candle, limit, outcome, and reason where
relevant. A candle/API failure for one symbol includes its traceback and does
not stop other symbols from being evaluated. The log directory is fixed for the
current version and can move into shared engine configuration later.

### Daily CSV outputs

The engine appends each completed instrument candle once to
`output/candles_YYYYMMDD.csv`, keyed by instrument key and candle start. An
ENTER alert is appended to `output/execution_alerts_YYYYMMDD.csv` before it is
printed. Every append is flushed immediately. Watch mode handles `Ctrl+C`
cleanly and reports its shutdown reason plus evaluated, alert, and remaining
signal counts.

### Prepare a symbol-only watchlist

Before market start, populate a CSV containing only a `symbol` column from the
latest Upstox daily close before the trading date. The command applies a 3%
discount by default and replaces the input only after every symbol succeeds:

```powershell
$env:UPSTOX_ACCESS_TOKEN = "..."
.\.venv\Scripts\python.exe -m src.prepare_watchlist `
  .\watchlist_20260716.csv --trading-date 20260716
```

The completed file includes `previous_close`, `limit_discount_percent`, and the
engine-required `limit_price`, along with all other required signal columns.
