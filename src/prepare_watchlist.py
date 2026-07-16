"""Populate a symbol-only daily watchlist using Upstox previous closes."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
from pathlib import Path
import sys
from typing import Any, Callable
from urllib.parse import quote

import requests

from src.daily_initialization import (
    AcceptedSignal,
    current_business_date,
    download_instruments,
    resolve_signals,
    valid_business_date,
)
from upstox_candles import extract_candles


HISTORICAL_CANDLES_URL = "https://api.upstox.com/v3/historical-candle"
OUTPUT_FIELDS = [
    "trading_date",
    "strategy_id",
    "symbol",
    "entry_decision",
    "rank",
    "previous_close",
    "limit_discount_percent",
    "limit_price",
]


def load_symbols(path: Path) -> list[str]:
    if not path.is_file():
        raise ValueError(f"watchlist file does not exist: {path}")
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if "symbol" not in (reader.fieldnames or []):
                raise ValueError("input watchlist must contain a symbol column")
            symbols = [str(row.get("symbol") or "").strip().upper() for row in reader]
    except OSError as exc:
        raise ValueError(f"could not read watchlist: {exc}") from exc
    if not symbols:
        raise ValueError("watchlist contains no symbols")
    if any(not symbol for symbol in symbols):
        raise ValueError("watchlist contains an empty symbol")
    seen: set[str] = set()
    duplicates: set[str] = set()
    for symbol in symbols:
        if symbol in seen:
            duplicates.add(symbol)
        seen.add(symbol)
    if duplicates:
        raise ValueError("duplicate symbols: " + ", ".join(sorted(duplicates)))
    return symbols


def fetch_daily_candles(
    instrument_key: str,
    access_token: str,
    from_date: str,
    to_date: str,
) -> list[list[Any]]:
    encoded_key = quote(instrument_key, safe="")
    url = f"{HISTORICAL_CANDLES_URL}/{encoded_key}/days/1/{to_date}/{from_date}"
    try:
        response = requests.get(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            timeout=20,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Upstox returned HTTP {response.status_code}: {response.text}"
        ) from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"could not connect to Upstox: {exc}") from exc
    try:
        return extract_candles(response.json())
    except requests.JSONDecodeError as exc:
        raise RuntimeError("Upstox returned invalid JSON") from exc


def latest_close_before(candles: list[list[Any]], trading_date: str) -> Decimal:
    cutoff = datetime.strptime(trading_date, "%Y%m%d").date()
    eligible: list[tuple[datetime, Decimal]] = []
    for candle in candles:
        if not isinstance(candle, list) or len(candle) < 7:
            raise RuntimeError(f"unexpected daily candle format: {candle!r}")
        try:
            start = datetime.fromisoformat(str(candle[0]))
            close = Decimal(str(candle[4]))
        except (ValueError, InvalidOperation) as exc:
            raise RuntimeError(f"invalid daily candle: {candle!r}") from exc
        if start.date() < cutoff and close > 0:
            eligible.append((start, close))
    if not eligible:
        raise RuntimeError("no previous trading-day close was returned")
    return max(eligible, key=lambda item: item[0])[1]


def _price(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def prepare_rows(
    symbols: list[str],
    trading_date: str,
    strategy_id: str,
    discount_percent: Decimal,
    access_token: str,
    instruments: list[dict[str, Any]],
    candle_fetcher: Callable[[str, str, str, str], list[list[Any]]] = fetch_daily_candles,
) -> list[dict[str, Any]]:
    if discount_percent <= 0 or discount_percent >= 100:
        raise ValueError("discount percent must be greater than 0 and less than 100")
    signals = [
        AcceptedSignal(
            index + 2, trading_date, strategy_id, symbol, "BUY", index + 1, "", "1"
        )
        for index, symbol in enumerate(symbols)
    ]
    resolved, unresolved = resolve_signals(signals, instruments)
    if unresolved:
        details = "; ".join(f"{item.symbol}: {item.reason}" for item in unresolved)
        raise ValueError(f"could not resolve all symbols: {details}")

    session_date = datetime.strptime(trading_date, "%Y%m%d").date()
    to_date = session_date - timedelta(days=1)
    from_date = session_date - timedelta(days=14)
    multiplier = (Decimal("100") - discount_percent) / Decimal("100")
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    by_symbol = {item.signal.symbol: item for item in resolved}
    for rank, symbol in enumerate(symbols, start=1):
        item = by_symbol[symbol]
        try:
            candles = candle_fetcher(
                item.instrument_key,
                access_token,
                from_date.isoformat(),
                to_date.isoformat(),
            )
            previous_close = latest_close_before(candles, trading_date)
            limit_price = previous_close * multiplier
            rows.append(
                {
                    "trading_date": trading_date,
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                    "entry_decision": "BUY",
                    "rank": rank,
                    "previous_close": _price(previous_close),
                    "limit_discount_percent": format(discount_percent, "f"),
                    "limit_price": _price(limit_price),
                }
            )
            print(
                f"Prepared {symbol} | previous_close={_price(previous_close)} "
                f"| limit_price={_price(limit_price)}"
            )
        except (RuntimeError, ValueError) as exc:
            errors.append(f"{symbol}: {exc}")
    if errors:
        raise RuntimeError(
            "watchlist was not changed because preparation failed:\n- "
            + "\n- ".join(errors)
        )
    return rows


def write_watchlist(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
        temporary_path.replace(path)
    except OSError as exc:
        temporary_path.unlink(missing_ok=True)
        raise ValueError(f"could not write prepared watchlist: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Populate a symbol watchlist from Upstox previous-day closes."
    )
    parser.add_argument("watchlist", type=Path)
    parser.add_argument(
        "--trading-date",
        help="Session date in YYYYMMDD; defaults to today in Asia/Kolkata.",
    )
    parser.add_argument("--discount-percent", default="3")
    parser.add_argument("--strategy-id", default="three_percent_drop_v1")
    args = parser.parse_args()

    trading_date = args.trading_date or current_business_date()
    if not valid_business_date(trading_date):
        parser.error("--trading-date must be a valid date in YYYYMMDD format")
    try:
        discount_percent = Decimal(args.discount_percent)
    except InvalidOperation:
        parser.error("--discount-percent must be a number")
    if not args.strategy_id.strip():
        parser.error("--strategy-id cannot be empty")

    access_token = os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip()
    if not access_token:
        print("Error: UPSTOX_ACCESS_TOKEN is not set.", file=sys.stderr)
        return 2
    try:
        symbols = load_symbols(args.watchlist)
        print(f"Resolving {len(symbols)} symbols using the Upstox NSE master...")
        rows = prepare_rows(
            symbols,
            trading_date,
            args.strategy_id.strip(),
            discount_percent,
            access_token,
            download_instruments(),
        )
        write_watchlist(args.watchlist, rows)
        print(f"Prepared {args.watchlist} with {len(rows)} signals.")
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
