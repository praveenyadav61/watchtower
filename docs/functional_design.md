# Execution Engine - Functional Design (v1)

## Vision

The Execution Engine bridges end-of-day signal generation and manual trade
execution. It loads a daily watchlist, observes completed 15-minute candles,
evaluates a simple entry rule, and produces an actionable execution alert.

Version 1 does not place orders. A person reviews and executes each alert.

## Delivery Approach

Development is feature-by-feature. Each feature is implemented, tested with
mock data, and manually validated before the next feature begins. Components are
introduced only when the current milestone needs them.

## Implemented Milestones

The first milestone retrieves the latest completed 15-minute candle for one
Upstox instrument.

It supports:

- Live Upstox Intraday Candle Data V3.
- Upstox-format mock JSON when the API or market is unavailable.
- Rejection of malformed API responses.
- Exclusion of a candle until its full 15-minute interval has ended.
- Clear display of timestamp, OHLC, volume, and open interest.

The daily initializer loads and validates `watchlist.csv`.

It supports:

- Required-column and non-empty-file validation.
- `YYYYMMDD` calendar-date validation.
- Optional validation against an intended trading session.
- BUY-only, positive-rank, required-value, and duplicate checks.
- Ignoring additional columns not required by the execution engine.
- Separate accepted-signal and rejected-row output with reasons.

The same initializer resolves accepted symbols using the official Upstox daily
NSE instrument JSON file.

It supports:

- Automatic download of the official daily NSE JSON.GZ file.
- Exact `trading_symbol` matching after symbol normalization.
- Filtering to `segment=NSE_EQ` and `instrument_type=EQ`.
- Reporting missing or ambiguous symbols instead of guessing.
- Preserving the Upstox instrument key and raw tick-size field.

## V1 Responsibilities

- Read the daily `watchlist.csv`.
- Validate the file and its rows.
- Activate supported BUY signals.
- Resolve each symbol to an Upstox instrument key.
- Retrieve previous close and tick size.
- Retrieve completed 15-minute candles from Upstox.
- Calculate a discounted limit price from previous close.
- Decide WAIT, ENTER, REJECT, or EXPIRE.
- Generate at most one execution alert per signal.
- Maintain an auditable evaluation history.
- Email execution alerts after alert generation is manually validated.

## Out of Scope

- Signal generation.
- Automatic broker order placement, modification, or cancellation.
- Position sizing.
- Portfolio-level risk.
- Exit management.
- Order and fill tracking.
- Multiple entry policies in v1.
- A database, REST API, dashboard, or distributed scheduler.

## Daily Input

All business dates use the compact `YYYYMMDD` format throughout the execution
engine. For example, July 13, 2026 is written as `20260713`.

This rule applies to CSV date fields, command-line session dates, logs, and
dated output filenames. Upstox candle timestamps remain ISO-8601 because they
include the time and timezone supplied by the external API.

The initialization command accepts an optional session date. When omitted, it
uses the current date in the `Asia/Kolkata` timezone.

### `watchlist.csv`

Required columns:

- `trading_date`
- `strategy_id`
- `symbol`
- `entry_decision`
- `final_score`
- `rank`

Future columns may be present and are ignored by v1:

- `regime`
- `position_size_multiplier`
- `decision_reason`

### Strategy configuration

Configuration will be added when entry-policy work begins. V1 requires:

- `strategy_id`
- `entry_policy`
- `limit_discount_percent`
- `timeframe` (15 minutes)
- `entry_start_time`
- `entry_cutoff_time`
- `output_directory`
- `email_enabled`

## Validation

### File-level validation

- File exists.
- Required columns are present.
- File is not empty.
- Trading date matches the intended session.

A file-level error stops initialization.

### Row-level validation

- `trading_date` contains exactly eight digits in `YYYYMMDD` format and is a
  valid calendar date.
- `strategy_id` and `symbol` are present.
- `entry_decision` is BUY.
- `strategy_id + symbol` is not duplicated.

Invalid rows are skipped and recorded with a reason.

Initialization may continue with partial success. Rejected or unresolved rows
are warnings. The engine is ready when at least one valid signal resolves to an
instrument key; it is not ready when no usable signal remains.

## Signal Lifecycle

```text
ACTIVE -> WAIT -> ENTERED
   |         |
   |         +-> REJECTED
   +------------> EXPIRED
```

A signal may receive multiple WAIT evaluations but can produce only one
execution alert.

## Entry Policy v1

Policy: buy at a configured percentage below the previous close.

```text
limit_price = previous_close * (1 - discount_percent / 100)
```

The price is rounded to the instrument tick size before evaluation.

Evaluation:

- Candle low is above limit price: WAIT.
- Candle low is at or below limit price: ENTER.

Assumed entry price:

- Candle opens above or at limit: use the limit price.
- Candle opens below limit: use the candle open.

## Evaluation Window

- Use only completed 15-minute candles.
- Evaluate from 09:30 through 14:45 IST.
- A candle is complete when `candle_start + 15 minutes <= current time`.
- Remaining ACTIVE signals expire at the cutoff.

## Minimum Trade Validation

- Signal is ACTIVE.
- No alert has already been generated.
- Trigger candle is complete and valid.
- Evaluation is inside the entry window.
- Previous close and calculated limit price are valid.

## Outputs

### Execution alert

- `trading_date`
- `strategy_id`
- `symbol`
- `side`
- `alert_time`
- `limit_price`
- `assumed_entry_price`
- `trigger_candle`
- `final_score`
- `rank`
- `status`

Output file: `execution_alerts_YYYYMMDD.csv`.

### Evaluation log

- `evaluation_time`
- `strategy_id`
- `symbol`
- `candle_start`
- `candle_low`
- `limit_price`
- `outcome`
- `reason`

Output file: `signal_evaluations_YYYYMMDD.csv`.

## Upstox Access

- Use the read-only Upstox Analytics Token for market-data GET requests.
- Pass it as `Authorization: Bearer <token>`.
- Store it outside source code in an environment variable.
- Never log or write the token to project files.
- Mock mode requires no token.

## Feature Sequence

1. Fetch one completed 15-minute candle from live or mock Upstox data. Done.
2. Load and validate `watchlist.csv`. Done.
3. Resolve watchlist symbols to Upstox instrument keys. Done.
4. Fetch previous close and tick size.
5. Calculate the v1 limit price.
6. Evaluate one signal against one completed candle.
7. Evaluate all active signals and prevent duplicate alerts.
8. Write evaluation and alert CSVs.
9. Run after each completed 15-minute interval and recover missed intervals.
10. Add email notification.

## Design Principles

- Keep v1 small and manually verifiable.
- Use completed candles only.
- Keep policy decisions separate from Upstox communication.
- Make every decision explainable and auditable.
- Add infrastructure only when a validated feature requires it.
