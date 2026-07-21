# Alert Logic

The watchlist CSV is the alert configuration. Each non-empty supported column
activates an independent rule for that symbol. Multiple rules may be active on
the same row.

## Candle processing

The engine fetches Upstox intraday candles shortly after each 15-minute
boundary and evaluates only the newest completed candle. A forming candle is
never evaluated. Every completed candle is stored once, even after one-time
alerts have fired.

## Supported columns

| CSV column | Trigger condition | Default repeat policy |
| --- | --- | --- |
| `volume_threshold` | candle volume >= threshold | Every matching candle |
| `price_low_limit` | candle low <= limit | Once per day |
| `price_high_limit` | candle high >= limit | Once per day |
| `ema20` | candle low <= EMA20 <= candle high | Once per day |

Every row containing `volume_threshold` also activates the special cumulative
score described below. It uses the same daily watchlist; no separate file or
column is required.

`limit_price` remains a backward-compatible alias for `price_low_limit`. Do not
provide both names on the same row.

## Volume threshold

Volume is the volume of one completed 15-minute candle, not cumulative daily
volume. Every candle meeting the threshold generates a new alert.

Slack includes the threshold multiple:

```text
multiple = candle volume / volume threshold
```

Example:

```text
🔔 HSCL | VOLUME 2,920,156 ≥ 2,068,781 | 1.41x | 09:45
```

## Price low limit

The rule triggers when the candle low touches or falls below the configured
limit. It alerts once per symbol, strategy, and trading day.

```text
🔔 MAPMYINDIA | LOW 1,122.6 ≤ 1,137.86 | 09:45
```

## Price high limit

The rule triggers when the candle high touches or rises above the configured
limit. It alerts once per symbol, strategy, and trading day.

```text
🔔 AEGISLOG | HIGH 1,430.0 ≥ 1,389.57 | 09:45
```

## EMA20 crossing

The engine does not calculate EMA20. The CSV must contain the EMA20 value
calculated from daily candles through the previous trading day. The rule
triggers when that fixed level lies within the completed candle's low-to-high
range.

```text
🔔 INDIGO | EMA20 crossed 5,160.72 | close 5,164.5 | 09:45
```

## Repeat policies and deduplication

Repeat modes are configured in `config/alert_policies.json`:

- `EVERY_MATCHING_CANDLE`: alert on each new candle that matches.
- `ONCE_PER_DAY`: stop that rule after its first alert for the day.

Rules are tracked independently. A volume alert does not disable a price or EMA
rule for the same symbol. Persisted alert keys prevent the same rule and candle
from being sent again after a restart.

## Notifications and failure handling

Successful initialization produces one compact Slack status message. Only
triggered alerts go to Slack; WAIT evaluations remain in console and file logs.
Console, alert CSV, and Slack all use the same evaluated rule result.

An API or candle error for one symbol is logged and isolated. Other symbols
continue processing, and the failed symbol is retried at the next scheduled
cycle.

## Cumulative score

The first completed candle establishes the previous-close baseline. Starting
with the second completed candle, the engine calculates:

```text
delta_p = ((current close - previous close) / previous close) × 100
volume_multiple = candle volume / volume_threshold
score_contribution = delta_p × volume_multiple
cumulative_score = previous cumulative_score + score_contribution
```

All completed candles from the beginning of the session are processed in time
order, including after a late start or restart. Positive price change increases
the score; negative price change reduces it.

The signed harmonic mean for each candle is:

```text
harmonic_magnitude = 2 / ((1 / abs(delta_p)) + (1 / volume_multiple))
harmonic_mean = sign(delta_p) × harmonic_magnitude
```

The harmonic mean is zero when either input is zero.

An alert is sent on every completed candle whose cumulative score is above 1.
The alert count belongs to that symbol and increments only when an alert is
sent. `🆕` marks alert number one, `🟡` marks scores above 1 through 5, and `🟢`
marks scores above 5.

```text
🆕 🟡 ADANIENT | CUMULATIVE SCORE 1.24 | Alert #1 | 10:15
Scores: 0.20 → 0.68 → 1.24
Harmonic: 0.31 → 0.72 → 0.94
```

Both complete morning series are included in every cumulative-score Slack
alert. Every calculation is persisted in
`output/cumulative_scores_YYYYMMDD.csv`. Thresholds and display precision live
in `config/cumulative_score_policy.json`.
