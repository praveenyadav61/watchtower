# Alert Logic

The daily watchlist CSV is the alert configuration. Each supported non-empty
column activates its rule for that symbol.

## Candle processing

Watchtower fetches Upstox intraday candles shortly after every 15-minute
boundary. It evaluates completed candles only and stores each completed candle
once. On a late start or restart, it processes missing completed candles in
chronological order.

An API or candle error for one symbol is isolated and logged. Other symbols
continue, and the failed symbol is tried again during the next cycle.

## Watchlist columns

| Column | Purpose | Alert behavior |
| --- | --- | --- |
| `symbol` | Exchange trading symbol | Required |
| `volume_threshold` | Volume input for cumulative score | Cumulative alerts |
| `price_low_limit` | Candle low is at or below the value | Once per day |
| `price_high_limit` | Candle high is at or above the value | Once per day |
| `ema20` | EMA20 lies inside the candle range | Once per day |

`limit_price` is a backward-compatible alias for `price_low_limit`. Do not put
both names in the same CSV.

To receive cumulative-score alerts only, use:

```csv
symbol,volume_threshold
ADANIENT,500000
```

Adding a price or EMA column activates that additional alert independently.

## Cumulative score

The first completed candle establishes the previous-close baseline. For each
later completed candle:

```text
delta_p = ((current_close - previous_close) / previous_close) * 100
volume_multiple = candle_volume / volume_threshold
score_contribution = delta_p * volume_multiple
cumulative_score = previous_cumulative_score + score_contribution
```

`delta_p` is the percentage price change from the previous completed candle.
Positive changes increase the cumulative score and negative changes reduce it.

The signed harmonic mean is:

```text
harmonic_magnitude =
    2 / ((1 / abs(delta_p)) + (1 / volume_multiple))

harmonic_mean = sign(delta_p) * harmonic_magnitude
```

It is zero when either input is zero.

The current configuration sends an alert on every completed candle whose
cumulative score is strictly greater than 5. The per-symbol alert count
increases only when an alert is sent. The first alert is marked as new.

Every cumulative alert includes:

- symbol;
- current cumulative score;
- alert count;
- candle time;
- cumulative-score history from the morning;
- harmonic-mean history from the morning.

All calculations are stored in:

```text
output/cumulative_scores_YYYYMMDD.csv
```

Threshold and display settings are in:

```text
config/cumulative_score_policy.json
```

## Price-low alert

Triggers when:

```text
candle_low <= price_low_limit
```

It alerts once per symbol, strategy, and trading day.

## Price-high alert

Triggers when:

```text
candle_high >= price_high_limit
```

It alerts once per symbol, strategy, and trading day.

## EMA20 alert

Watchtower does not calculate EMA20. Supply the EMA20 calculated from daily
candles through the previous trading day.

It triggers when:

```text
candle_low <= ema20 <= candle_high
```

It alerts once per symbol, strategy, and trading day.

## Repeat and deduplication

Rule repetition is configured in:

```text
config/alert_policies.json
```

Supported modes:

- `ONCE_PER_DAY`: the rule stops after its first alert that day.
- `EVERY_MATCHING_CANDLE`: every new matching completed candle alerts.
- `DISABLED`: the standalone rule does not alert.

Rules are tracked independently. Persisted alert and candle keys prevent the
same event from being sent again after a restart.

`volume_threshold` is currently `DISABLED` as a standalone volume alert. It is
still used by the cumulative-score calculation.

## Notifications

Slack receives:

1. One compact successful-initialization message.
2. Each cumulative-score alert above its configured threshold.
3. Price or EMA alerts only when those columns are present and enabled.

WAIT evaluations are written to console and operational logs, not Slack.
Slack failure is logged and does not stop candle processing or CSV output.
