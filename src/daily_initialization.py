"""Run the Execution Engine's once-per-day initialization flow."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import gzip
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

import requests


REQUIRED_COLUMNS = {"symbol"}
ALERT_COLUMNS = {
    "limit_price",
    "volume_threshold",
    "price_low_limit",
    "price_high_limit",
    "ema20",
}
COMMON_COLUMN_MISTAKES = {
    "threshold_volume": "volume_threshold",
    "ema21": "ema20",
}
NSE_INSTRUMENTS_URL = (
    "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
)
MARKET_TIMEZONE = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class AcceptedSignal:
    line_number: int
    trading_date: str
    strategy_id: str
    symbol: str
    entry_decision: str
    rank: int
    final_score: str = ""
    limit_price: str = ""
    volume_threshold: str = ""
    price_low_limit: str = ""
    price_high_limit: str = ""
    ema20: str = ""


@dataclass(frozen=True)
class RejectedRow:
    line_number: int
    reason: str


@dataclass(frozen=True)
class ResolvedInstrument:
    signal: AcceptedSignal
    instrument_key: str
    tick_size_raw: float | int | None


@dataclass(frozen=True)
class UnresolvedSymbol:
    symbol: str
    reason: str


@dataclass(frozen=True)
class InitializationResult:
    trading_date: str
    active_signals: list[ResolvedInstrument]
    rejected_rows: list[RejectedRow]
    unresolved_symbols: list[UnresolvedSymbol]

    @property
    def ready(self) -> bool:
        return bool(self.active_signals)


def valid_business_date(value: str) -> bool:
    if len(value) != 8 or not value.isdigit():
        return False
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return False
    return True


def current_business_date() -> str:
    return datetime.now(MARKET_TIMEZONE).strftime("%Y%m%d")


def validate_rows(
    rows: Iterable[Mapping[str, str]], expected_date: str | None = None
) -> tuple[list[AcceptedSignal], list[RejectedRow]]:
    accepted: list[AcceptedSignal] = []
    rejected: list[RejectedRow] = []
    seen: set[tuple[str, str]] = set()

    for line_number, row in enumerate(rows, start=2):
        limit_price = (row.get("limit_price") or "").strip()
        volume_threshold = (row.get("volume_threshold") or "").strip()
        price_low_limit = (row.get("price_low_limit") or "").strip()
        price_high_limit = (row.get("price_high_limit") or "").strip()
        ema20 = (row.get("ema20") or "").strip()
        configured_values = {
            "limit_price": limit_price,
            "volume_threshold": volume_threshold,
            "price_low_limit": price_low_limit,
            "price_high_limit": price_high_limit,
            "ema20": ema20,
        }
        configured_count = sum(bool(value) for value in configured_values.values())
        if configured_count == 1 and volume_threshold:
            default_strategy = "volume_threshold_v1"
        elif configured_count == 1:
            default_strategy = "price_threshold_v1"
        else:
            default_strategy = "multi_alert_v1"
        trading_date = (row.get("trading_date") or expected_date or current_business_date()).strip()
        strategy_id = (row.get("strategy_id") or default_strategy).strip()
        symbol = (row.get("symbol") or "").strip().upper()
        decision = (row.get("entry_decision") or "BUY").strip().upper()
        rank_text = (row.get("rank") or str(line_number - 1)).strip()
        final_score = (row.get("final_score") or "").strip()

        if not valid_business_date(trading_date):
            rejected.append(RejectedRow(line_number, "invalid trading_date; expected YYYYMMDD"))
            continue
        if expected_date and trading_date != expected_date:
            rejected.append(RejectedRow(line_number, f"trading_date does not match {expected_date}"))
            continue
        if not strategy_id:
            rejected.append(RejectedRow(line_number, "strategy_id is missing"))
            continue
        if not symbol:
            rejected.append(RejectedRow(line_number, "symbol is missing"))
            continue
        if decision != "BUY":
            rejected.append(RejectedRow(line_number, "only BUY is supported"))
            continue
        try:
            rank = int(rank_text)
            if rank < 1:
                raise ValueError
        except ValueError:
            rejected.append(RejectedRow(line_number, "rank must be a positive integer"))
            continue
        if not configured_count:
            rejected.append(
                RejectedRow(line_number, "provide at least one supported alert value")
            )
            continue
        if limit_price and price_low_limit:
            rejected.append(
                RejectedRow(
                    line_number,
                    "use either limit_price or price_low_limit, not both",
                )
            )
            continue
        invalid_column = None
        for column, value in configured_values.items():
            if not value:
                continue
            try:
                if float(value) <= 0:
                    raise ValueError
            except ValueError:
                invalid_column = column
                break
        if invalid_column:
            rejected.append(
                RejectedRow(line_number, f"{invalid_column} must be a positive number")
            )
            continue

        key = (strategy_id, symbol)
        if key in seen:
            rejected.append(RejectedRow(line_number, "duplicate strategy_id + symbol"))
            continue
        seen.add(key)
        accepted.append(
            AcceptedSignal(
                line_number,
                trading_date,
                strategy_id,
                symbol,
                decision,
                rank,
                final_score,
                limit_price,
                volume_threshold,
                price_low_limit,
                price_high_limit,
                ema20,
            )
        )

    return accepted, rejected


def load_watchlist(
    path: Path, expected_date: str | None = None
) -> tuple[list[AcceptedSignal], list[RejectedRow]]:
    if not path.is_file():
        raise ValueError(f"watchlist file does not exist: {path}")
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    "watchlist is missing required columns: "
                    + ", ".join(sorted(missing))
                )
            mistaken = COMMON_COLUMN_MISTAKES.keys() & set(reader.fieldnames or [])
            if mistaken:
                corrections = ", ".join(
                    f"{name} -> {COMMON_COLUMN_MISTAKES[name]}"
                    for name in sorted(mistaken)
                )
                raise ValueError(f"watchlist contains unsupported alert columns: {corrections}")
            threshold_columns = ALERT_COLUMNS & set(reader.fieldnames or [])
            if not threshold_columns:
                raise ValueError(
                    "watchlist must contain at least one supported alert column: "
                    + ", ".join(sorted(ALERT_COLUMNS))
                )
            rows = list(reader)
    except OSError as exc:
        raise ValueError(f"could not read watchlist: {exc}") from exc
    if not rows:
        raise ValueError("watchlist contains no data rows")
    return validate_rows(rows, expected_date)


def parse_instrument_bytes(content: bytes) -> list[dict[str, Any]]:
    try:
        payload = json.loads(gzip.decompress(content).decode("utf-8"))
    except (gzip.BadGzipFile, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Upstox instrument file: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("Upstox instrument file must contain a JSON list")
    return payload


def download_instruments(max_attempts: int = 3) -> list[dict[str, Any]]:
    """Download the public instrument master, retrying temporary failures."""
    last_error: requests.RequestException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(NSE_INSTRUMENTS_URL, timeout=30)
            response.raise_for_status()
            return parse_instrument_bytes(response.content)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status is not None and status < 500:
                raise ValueError(
                    f"Upstox instrument download returned HTTP {status}"
                ) from exc
            last_error = exc
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
        except requests.RequestException as exc:
            raise ValueError(f"could not download Upstox instruments: {exc}") from exc

        if attempt < max_attempts:
            print(
                f"Warning: Upstox instrument download failed; retrying "
                f"({attempt}/{max_attempts})...",
                file=sys.stderr,
            )

    raise ValueError(
        f"could not download Upstox instruments after {max_attempts} attempts: {last_error}"
    )


def resolve_signals(
    signals: list[AcceptedSignal], instruments: list[dict[str, Any]]
) -> tuple[list[ResolvedInstrument], list[UnresolvedSymbol]]:
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for instrument in instruments:
        if not isinstance(instrument, dict):
            continue
        if instrument.get("segment") != "NSE_EQ" or instrument.get("instrument_type") != "EQ":
            continue
        symbol = str(instrument.get("trading_symbol") or "").strip().upper()
        instrument_key = str(instrument.get("instrument_key") or "").strip()
        if symbol and instrument_key:
            by_symbol.setdefault(symbol, []).append(instrument)

    resolved: list[ResolvedInstrument] = []
    unresolved: list[UnresolvedSymbol] = []
    for signal in signals:
        matches = by_symbol.get(signal.symbol, [])
        if not matches:
            unresolved.append(UnresolvedSymbol(signal.symbol, "no matching NSE equity instrument"))
            continue
        unique_keys = {str(item["instrument_key"]) for item in matches}
        if len(unique_keys) != 1:
            unresolved.append(UnresolvedSymbol(signal.symbol, "multiple NSE equity instruments matched"))
            continue
        instrument = matches[0]
        resolved.append(
            ResolvedInstrument(
                signal,
                str(instrument["instrument_key"]),
                instrument.get("tick_size"),
            )
        )
    return resolved, unresolved


def initialize(
    watchlist: Path,
    trading_date: str,
    instruments: list[dict[str, Any]] | None = None,
) -> InitializationResult:
    """Build the usable daily signal registry or raise on a fatal setup error."""
    if not valid_business_date(trading_date):
        raise ValueError("trading_date must be a valid date in YYYYMMDD format")
    accepted, rejected = load_watchlist(watchlist, trading_date)
    if not accepted:
        return InitializationResult(trading_date, [], rejected, [])
    resolved, unresolved = resolve_signals(
        accepted, instruments if instruments is not None else download_instruments()
    )
    return InitializationResult(trading_date, resolved, rejected, unresolved)


def print_summary(result: InitializationResult) -> None:
    print(f"Initialization summary for {result.trading_date}")
    print(f"Active signals: {len(result.active_signals)}")
    print(f"Rejected rows: {len(result.rejected_rows)}")
    print(f"Unresolved symbols: {len(result.unresolved_symbols)}")

    print("\nActive signals:")
    if result.active_signals:
        for item in result.active_signals:
            print(
                f"{item.signal.symbol} | {item.instrument_key} | "
                f"rank {item.signal.rank} | tick_size_raw {item.tick_size_raw}"
            )
    else:
        print("None")

    if result.rejected_rows:
        print("\nWarnings - rejected rows:")
        for row in result.rejected_rows:
            print(f"Line {row.line_number} | {row.reason}")
    if result.unresolved_symbols:
        print("\nWarnings - unresolved symbols:")
        for item in result.unresolved_symbols:
            print(f"{item.symbol} | {item.reason}")

    if result.ready:
        print("\nENGINE READY")
    else:
        print("\nENGINE NOT READY")


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize the Execution Engine for one day.")
    parser.add_argument("watchlist", type=Path, help="Path to watchlist.csv")
    parser.add_argument(
        "--trading-date",
        help="Session date in YYYYMMDD format; defaults to today in Asia/Kolkata.",
    )
    args = parser.parse_args()

    trading_date = args.trading_date or current_business_date()
    if not valid_business_date(trading_date):
        parser.error("--trading-date must be a valid date in YYYYMMDD format")

    try:
        result = initialize(args.watchlist, trading_date)
        print_summary(result)
        return 0 if result.ready else 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
