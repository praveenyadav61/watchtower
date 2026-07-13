#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.11 or newer is required and was not found." >&2
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating virtual environment..."
  "$PYTHON_BIN" -m venv .venv
fi

echo "Installing dependencies..."
.venv/bin/python -m pip install -r requirements.txt

echo "Verifying Asia/Kolkata timezone..."
.venv/bin/python -c "from zoneinfo import ZoneInfo; print(ZoneInfo('Asia/Kolkata'))"

echo "Running tests..."
.venv/bin/python -m unittest discover -s tests

echo "Setup complete. Run: bash ./run_live.sh"
