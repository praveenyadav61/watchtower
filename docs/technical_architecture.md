# Execution Engine - Technical Architecture (v1)

## Goal

Implement the execution-alert workflow in small, independently verifiable
features. Python is used for v1. Upstox supplies reference data and intraday
candles, while entry logic remains independent of the API response format.

The system does not place broker orders.

## Architecture by Phase

### Daily initialization

Runs once for each trading day:

```text
watchlist.csv
      |
      v
Watchlist loader -> Validation -> Active signal registry
                                      |
                         +------------+------------+
                         |                         |
                         v                         v
                  Strategy config          Reference data
                                          (instrument key,
                                       previous close, tick size)
                         |                         |
                         +------------+------------+
                                      |
                                      v
                                 Engine ready
```

Initialization produces valid ACTIVE signals with the configuration and
reference data needed for runtime evaluation. Invalid rows are retained only as
auditable rejection records.

### Runtime evaluation

Runs after a 15-minute candle has completed:

```text
Upstox candle response or mock JSON
                 |
                 v
Response validation -> Candle normalization -> Completed-candle filter
                                                   |
                                                   v
Feature calculation -> Entry setup logic -> Trade validation
                                                   |
                         +-------------------------+------------------+
                         |                                            |
                         v                                            v
                  Evaluation log                           Execution alert
                                                               |
                                                        CSV, then email
```

## Current Implementation Boundary

The first vertical slice is implemented in `upstox_candles.py`:

1. Read one instrument key from the command line.
2. Fetch `/v3/historical-candle/intraday/{instrument_key}/minutes/15`, or load
   the same JSON structure from `--mock-file`.
3. Validate the response envelope.
4. Parse timezone-aware candle timestamps.
5. exclude candles whose 15-minute interval has not ended.
6. Print the latest completed candle.

This remains a single script intentionally. It should be split only when the
next features create clear reusable boundaries.

The once-per-day flow is implemented in the single file
`src/daily_initialization.py`:

1. Read a watchlist path and optional expected `YYYYMMDD` session date.
2. Validate required columns and reject an empty file.
3. Validate each row independently.
4. Normalize symbols and BUY decisions to uppercase.
5. Reject invalid dates, missing values, non-BUY decisions, invalid ranks, and
   duplicate `strategy_id + symbol` pairs.
6. Print accepted signals and rejected rows without making an Upstox request.

7. Download the official Upstox daily NSE JSON.GZ file.
8. Filter records to `segment=NSE_EQ` and `instrument_type=EQ`.
9. Match normalized watchlist symbols to `trading_symbol` exactly.
10. Return the stable `instrument_key` and raw `tick_size` value.
11. Report missing and ambiguous symbols without selecting a fallback.
12. Return a reusable `InitializationResult` for runtime processing.
13. Print `ENGINE READY` when at least one signal resolves. Rejected and
    unresolved records remain warnings and do not block usable signals.

## Upstox Integration

### Authentication

- Live requests use a read-only Upstox Analytics Token.
- The token is sent in the `Authorization: Bearer` header.
- The token is read from `UPSTOX_ACCESS_TOKEN` for the current milestone.
- Credentials must never be hard-coded, logged, or committed.
- Mock mode bypasses authentication and network access.

The environment-variable name may later become `UPSTOX_ANALYTICS_TOKEN` when
configuration is introduced; this does not change the HTTP contract.

### Intraday candle request

```text
GET https://api.upstox.com/v3/historical-candle/intraday/
    {url_encoded_instrument_key}/minutes/15
```

Response candle positions:

| Index | Value |
|---:|---|
| 0 | Candle start timestamp |
| 1 | Open |
| 2 | High |
| 3 | Low |
| 4 | Close |
| 5 | Volume |
| 6 | Open interest |

The timestamp is the candle start. The normalized candle end is start plus 15
minutes. A candle is eligible only when its end is not later than the current
time.

### Live and mock parity

Live and mock sources return their JSON payload to the same validation and
candle-selection path:

```text
Live HTTP response --+
                     +-> extract candles -> validate rows -> select completed
Mock JSON file ------+
```

This allows weekend and offline testing without creating a separate fake domain
model.

## Planned Runtime Concepts

These concepts will be added only when their feature is implemented.

### Signal

- `trading_date`
- `strategy_id`
- `symbol`
- `entry_decision`
- `final_score`
- `rank`
- `limit_price`
- `status`

### Completed candle

- `instrument_key`
- `symbol`
- `start`
- `end`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `open_interest`

### Entry decision

- `outcome`: WAIT, ENTER, REJECT, or EXPIRE.
- `reason`.
- `assumed_entry_price`, when outcome is ENTER.

### Execution alert

- Signal identity and strategy attribution.
- Trigger candle.
- Limit and assumed entry prices.
- Alert time and status.

## Processing Flow

The completed v1 flow will be:

1. Load the daily watchlist.
2. Validate file and rows.
3. Build the ACTIVE signal registry.
4. Load strategy configuration.
5. Resolve Upstox instrument keys.
6. Fetch previous close and tick size.
7. Calculate tick-size-aligned limit prices.
8. After each interval, retrieve completed 15-minute candles.
9. Calculate the small set of values required by the v1 policy.
10. Evaluate each ACTIVE signal.
11. Record every evaluation and its reason.
12. Generate at most one alert for each entered signal.
13. Expire remaining signals at the cutoff.
14. Email generated alerts after CSV output is validated.

## State Model

Signal statuses:

```text
ACTIVE  ENTERED  REJECTED  EXPIRED
```

Evaluation outcomes:

```text
WAIT  ENTER  REJECT  EXPIRE
```

The in-memory registry is sufficient initially. Before automated scheduling is
added, the engine must be able to read the current day's alert file so a restart
cannot create duplicate alerts. A database is not required for v1.

## Entry Logic Boundary

Entry logic receives a normalized active signal, completed candle, reference
data, and strategy configuration. It returns a decision and reason.

Entry logic must not:

- Call Upstox.
- Read or write files.
- Send email.
- Mutate the active registry directly.

## Scheduling

Scheduling is not part of the current milestone. When introduced, a simple
single-process loop or operating-system scheduled task is sufficient.

The scheduler must:

- Run only during the configured entry window.
- Trigger after candle completion, not at candle start.
- Process completed candles missed after a restart.
- Avoid evaluating the same signal and candle twice.

## Output and Logging

Planned files:

- `execution_alerts_YYYYMMDD.csv`
- `signal_evaluations_YYYYMMDD.csv`

Log only operational and decision information:

- Input loading and validation failures.
- Upstox request failures without credentials.
- Candle selection.
- Policy outcome and reason.
- Generated alerts.
- Email result.

## Testing Strategy

Each feature receives focused automated tests plus a manual acceptance check.

Current candle-provider checks:

- Upstox-format mock response is accepted.
- Invalid response shape is rejected.
- Response order does not affect latest-candle selection.
- A forming candle is excluded.
- No completed candle produces a clear non-error result.

Future tests are added alongside their corresponding feature, not in advance.

## Constraints

- Python 3.11 or newer.
- `requests` is the only current runtime dependency.
- Business dates use `YYYYMMDD` everywhere, including CSV fields, command-line
  values, logs, and filenames.
- An omitted initialization date defaults to today in `Asia/Kolkata`.
- All timestamps are timezone-aware; market behavior uses IST.
- Upstox candle timestamps remain ISO-8601 because they carry time and timezone
  information; they are not business-date fields.
- Price calculations will use decimal arithmetic.
- No database, web service, queue, or dependency-injection framework in v1.

## Next Feature

Fetch the previous trading-day close for each resolved instrument key. This
feature should not calculate the entry limit or evaluate entry rules. Its
manual result is a clear symbol, instrument-key, previous-close mapping plus
failures with reasons.
