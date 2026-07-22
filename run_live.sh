#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ $# -ge 1 ]]; then
  WATCHLIST="$1"
elif [[ -f "./watchlist_$(date +%Y%m%d).csv" ]]; then
  WATCHLIST="./watchlist_$(date +%Y%m%d).csv"
else
  WATCHLIST="./watchlist.csv"
fi
if [[ ! -x .venv/bin/python ]]; then
  echo "Virtual environment is missing. Run: bash ./setup.sh" >&2
  exit 1
fi
if [[ ! -f "$WATCHLIST" ]]; then
  echo "Watchlist not found: $WATCHLIST" >&2
  exit 1
fi

if [[ -z "${UPSTOX_ACCESS_TOKEN:-}" ]]; then
  echo 'UPSTOX_ACCESS_TOKEN is not set. Export it before running:' >&2
  echo 'export UPSTOX_ACCESS_TOKEN="your-token"' >&2
  exit 1
fi

echo "Running isolated cumulative-score mock preflight..."
if ! .venv/bin/python -m src.preflight_check; then
  echo "Mock preflight failed. Live engine was not started." >&2
  exit 1
fi

echo "Starting live alert engine with $WATCHLIST..."
exec caffeinate -dimsu .venv/bin/python -m src.execution_engine "$WATCHLIST" --watch
