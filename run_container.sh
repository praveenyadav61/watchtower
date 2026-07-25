#!/usr/bin/env bash
set -euo pipefail

cd /app

if [[ "${1:-}" == "mock-test" ]]; then
  shift
  echo "Running Watchtower AWS mock test..."
  python -m src.preflight_check
  exec python -m src.execution_engine \
    /app/examples/cumulative_score_mock_watchlist.csv \
    --trading-date 20260713 \
    --mock-candles /app/examples/cumulative_score_mock_candles.json \
    --mock-instruments /app/examples/mock_instruments.json \
    "$@"
fi

TRADING_DATE="$(
  python -c 'from src.daily_initialization import current_business_date; print(current_business_date())'
)"

if [[ $# -ge 1 && "${1:0:1}" != "-" ]]; then
  WATCHLIST="$1"
  shift
elif [[ -n "${WATCHTOWER_WATCHLIST:-}" ]]; then
  WATCHLIST="$WATCHTOWER_WATCHLIST"
elif [[ -f "/data/watchlist_${TRADING_DATE}.csv" ]]; then
  WATCHLIST="/data/watchlist_${TRADING_DATE}.csv"
else
  WATCHLIST="/data/watchlist.csv"
fi

if [[ ! -f "$WATCHLIST" ]]; then
  echo "Watchlist not found: $WATCHLIST" >&2
  echo "Mount today's watchlist under /data or set WATCHTOWER_WATCHLIST." >&2
  exit 1
fi

if [[ -z "${UPSTOX_ACCESS_TOKEN:-}" ]]; then
  echo "UPSTOX_ACCESS_TOKEN is not set." >&2
  exit 1
fi

echo "Running isolated cumulative-score mock preflight..."
python -m src.preflight_check

echo "Starting Watchtower with $WATCHLIST..."
exec python -m src.execution_engine "$WATCHLIST" --watch "$@"
