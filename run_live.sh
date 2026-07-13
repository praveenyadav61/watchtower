#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

WATCHLIST="${1:-./watchlist.csv}"
if [[ ! -x .venv/bin/python ]]; then
  echo "Virtual environment is missing. Run: bash ./setup.sh" >&2
  exit 1
fi
if [[ ! -f "$WATCHLIST" ]]; then
  echo "Watchlist not found: $WATCHLIST" >&2
  exit 1
fi

if [[ -z "${UPSTOX_ACCESS_TOKEN:-}" ]]; then
  read -r -s -p "Paste the Upstox access token: " UPSTOX_ACCESS_TOKEN
  echo
  export UPSTOX_ACCESS_TOKEN
fi

echo "Starting live alert engine with $WATCHLIST..."
exec caffeinate -dimsu .venv/bin/python -m src.execution_engine "$WATCHLIST" --watch
