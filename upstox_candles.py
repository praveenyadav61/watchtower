"""Fetch the latest completed 15-minute candle from Upstox."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import quote

import requests


INTERVAL_MINUTES = 15
BASE_URL = "https://api.upstox.com/v3/historical-candle/intraday"


def extract_candles(payload: Any) -> list[list[Any]]:
    """Validate an Upstox-format response and return its candle rows."""
    if not isinstance(payload, dict):
        raise RuntimeError("Upstox response must be a JSON object")
    if payload.get("status") != "success":
        raise RuntimeError(f"Upstox request was not successful: {payload}")
    candles = payload.get("data", {}).get("candles")
    if not isinstance(candles, list):
        raise RuntimeError("Upstox response does not contain a candle list")
    return candles


def fetch_candles(instrument_key: str, access_token: str) -> list[list[Any]]:
    encoded_key = quote(instrument_key, safe="")
    url = f"{BASE_URL}/{encoded_key}/minutes/{INTERVAL_MINUTES}"
    try:
        response = requests.get(
            url,
            headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            },
            timeout=15,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Upstox returned HTTP {response.status_code}: {response.text}"
        ) from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not connect to Upstox: {exc}") from exc

    try:
        payload = response.json()
    except requests.JSONDecodeError as exc:
        raise RuntimeError("Upstox returned an invalid JSON response") from exc

    return extract_candles(payload)


def load_mock_candles(path: Path) -> list[list[Any]]:
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except OSError as exc:
        raise RuntimeError(f"Could not read mock file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Mock file is not valid JSON: {exc}") from exc
    return extract_candles(payload)


def latest_completed_candle(
    candles: list[list[Any]], now: datetime | None = None
) -> list[Any] | None:
    """Return the newest candle whose 15-minute period has ended."""
    parsed: list[tuple[datetime, list[Any]]] = []

    for candle in candles:
        if not isinstance(candle, list) or len(candle) < 7:
            raise RuntimeError(f"Unexpected candle format: {candle!r}")
        try:
            start = datetime.fromisoformat(str(candle[0]))
        except ValueError as exc:
            raise RuntimeError(f"Invalid candle timestamp: {candle[0]!r}") from exc
        if start.tzinfo is None:
            raise RuntimeError(f"Candle timestamp has no timezone: {candle[0]!r}")
        parsed.append((start, candle))

    if not parsed:
        return None

    reference_time = now or datetime.now(parsed[0][0].tzinfo)
    if reference_time.tzinfo is None:
        raise ValueError("now must include timezone information")

    completed = [
        (start, candle)
        for start, candle in parsed
        if start + timedelta(minutes=INTERVAL_MINUTES) <= reference_time
    ]
    return max(completed, key=lambda item: item[0])[1] if completed else None


def print_candle(instrument_key: str, candle: list[Any]) -> None:
    start = datetime.fromisoformat(str(candle[0]))
    end = start + timedelta(minutes=INTERVAL_MINUTES)
    print(f"Instrument:    {instrument_key}")
    print(f"Candle start:  {start.isoformat()}")
    print(f"Candle end:    {end.isoformat()}")
    print(f"Open:          {candle[1]}")
    print(f"High:          {candle[2]}")
    print(f"Low:           {candle[3]}")
    print(f"Close:         {candle[4]}")
    print(f"Volume:        {candle[5]}")
    print(f"Open interest: {candle[6]}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print the latest completed Upstox 15-minute candle."
    )
    parser.add_argument("instrument_key", help='For example: "NSE_EQ|INE848E01016"')
    parser.add_argument(
        "--mock-file",
        type=Path,
        help="Read an Upstox-format JSON response instead of calling the API.",
    )
    args = parser.parse_args()

    try:
        if args.mock_file:
            candles = load_mock_candles(args.mock_file)
        else:
            access_token = os.environ.get("UPSTOX_ACCESS_TOKEN")
            if not access_token:
                print("Error: UPSTOX_ACCESS_TOKEN is not set.", file=sys.stderr)
                return 2
            candles = fetch_candles(args.instrument_key, access_token)
        candle = latest_completed_candle(candles)
        if candle is None:
            print("No completed 15-minute candle is available yet.")
            return 0
        print_candle(args.instrument_key, candle)
        return 0
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
