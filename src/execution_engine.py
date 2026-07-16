"""Run the basic watchlist-to-alert execution flow."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import os
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, Callable

from src.daily_initialization import (
    InitializationResult,
    MARKET_TIMEZONE,
    ResolvedInstrument,
    current_business_date,
    initialize,
)
from src.slack_notification import send_slack_message
from upstox_candles import fetch_candles, latest_completed_candle, load_mock_candles


LOGGER = logging.getLogger("alert_engine")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MOCK_CANDLES = PROJECT_ROOT / "examples" / "mock_candles_by_symbol.json"
CANDLE_FETCH_DELAY_SECONDS = 5


def send_slack_execution_alert(alert: ExecutionAlert) -> bool:
    """Post one final BUY alert when a Slack webhook is configured."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return False
    send_slack_message(
        webhook_url,
        (
            "BUY EXECUTION ALERT\n"
            f"Trading date: {alert.trading_date}\n"
            f"Strategy: {alert.strategy_id}\n"
            f"Symbol: {alert.symbol}\n"
            f"Side: {alert.side}\n"
            f"Limit price: {alert.limit_price}\n"
            f"Assumed entry price: {alert.assumed_entry_price}\n"
            f"Trigger candle: {alert.trigger_candle}\n"
            f"Rank: {alert.rank}\n"
            f"Status: {alert.status}"
        ),
        timeout=5,
    )
    return True


def send_slack_initialization(result: InitializationResult) -> bool:
    """Post one successful initialization summary when Slack is configured."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return False
    send_slack_message(
        webhook_url,
        (
            "ALERT ENGINE INITIALIZED\n"
            f"Trading date: {result.trading_date}\n"
            f"Status: {'READY' if result.ready else 'NOT READY'}\n"
            f"Active signals: {len(result.active_signals)}\n"
            f"Rejected rows: {len(result.rejected_rows)}\n"
            f"Unresolved symbols: {len(result.unresolved_symbols)}"
        ),
        timeout=5,
    )
    return True


def configure_logging(trading_date: str, log_directory: Path) -> tuple[Path, Path]:
    """Write readable operational logs to both the console and a daily file."""
    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = log_directory / f"alert_engine_{trading_date}.log"
    error_log_path = log_directory / f"alert_engine_errors_{trading_date}.log"
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
    LOGGER.handlers.clear()
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    daily_file = logging.FileHandler(log_path, encoding="utf-8")
    daily_file.setFormatter(formatter)
    error_file = logging.FileHandler(error_log_path, encoding="utf-8")
    error_file.setLevel(logging.ERROR)
    error_file.setFormatter(formatter)
    LOGGER.addHandler(console)
    LOGGER.addHandler(daily_file)
    LOGGER.addHandler(error_file)
    return log_path, error_log_path


def load_mock_candles_by_symbol(path: Path) -> dict[str, list[list[Any]]]:
    try:
        with path.open(encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except OSError as exc:
        raise ValueError(f"could not read symbol candle file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"symbol candle file is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("candles_by_symbol"), dict):
        raise ValueError("symbol candle file must contain a candles_by_symbol object")
    result = payload["candles_by_symbol"]
    for symbol, candles in result.items():
        if not isinstance(candles, list):
            raise ValueError(f"mock candles for {symbol} must be a list")
    return result


@dataclass(frozen=True)
class Evaluation:
    symbol: str
    outcome: str
    reason: str
    limit_price: Decimal
    assumed_entry_price: Decimal | None = None


@dataclass(frozen=True)
class ExecutionAlert:
    trading_date: str
    strategy_id: str
    symbol: str
    side: str
    alert_time: str
    limit_price: Decimal
    assumed_entry_price: Decimal
    trigger_candle: str
    final_score: str
    rank: int
    status: str = "ENTERED"


class DailyOutputStore:
    """Append completed candles and alerts to fixed daily CSV files."""

    CANDLE_FIELDS = [
        "received_at",
        "strategy_id",
        "symbol",
        "instrument_key",
        "candle_start",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "open_interest",
    ]
    ALERT_FIELDS = [
        "trading_date",
        "strategy_id",
        "symbol",
        "side",
        "alert_time",
        "limit_price",
        "assumed_entry_price",
        "trigger_candle",
        "final_score",
        "rank",
        "status",
    ]

    def __init__(self, directory: Path, trading_date: str) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.candle_path = directory / f"candles_{trading_date}.csv"
        self.alert_path = directory / f"execution_alerts_{trading_date}.csv"
        self._candle_keys = self._load_candle_keys()

    def _load_candle_keys(self) -> set[tuple[str, str]]:
        if not self.candle_path.exists():
            return set()
        try:
            with self.candle_path.open(newline="", encoding="utf-8-sig") as handle:
                return {
                    (row["instrument_key"], row["candle_start"])
                    for row in csv.DictReader(handle)
                    if row.get("instrument_key") and row.get("candle_start")
                }
        except (OSError, KeyError) as exc:
            raise ValueError(f"could not read candle output {self.candle_path}: {exc}") from exc

    @staticmethod
    def _append(path: Path, fields: list[str], row: dict[str, Any]) -> None:
        needs_header = not path.exists() or path.stat().st_size == 0
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            if needs_header:
                writer.writeheader()
            writer.writerow(row)
            handle.flush()

    def record_candle(
        self, instrument: ResolvedInstrument, candle: list[Any], received_at: datetime
    ) -> bool:
        key = (instrument.instrument_key, str(candle[0]))
        if key in self._candle_keys:
            return False
        self._append(
            self.candle_path,
            self.CANDLE_FIELDS,
            {
                "received_at": received_at.isoformat(),
                "strategy_id": instrument.signal.strategy_id,
                "symbol": instrument.signal.symbol,
                "instrument_key": instrument.instrument_key,
                "candle_start": candle[0],
                "open": candle[1],
                "high": candle[2],
                "low": candle[3],
                "close": candle[4],
                "volume": candle[5],
                "open_interest": candle[6],
            },
        )
        self._candle_keys.add(key)
        return True

    def record_alert(self, alert: ExecutionAlert) -> None:
        self._append(
            self.alert_path,
            self.ALERT_FIELDS,
            {
                "trading_date": alert.trading_date,
                "strategy_id": alert.strategy_id,
                "symbol": alert.symbol,
                "side": alert.side,
                "alert_time": alert.alert_time,
                "limit_price": alert.limit_price,
                "assumed_entry_price": alert.assumed_entry_price,
                "trigger_candle": alert.trigger_candle,
                "final_score": alert.final_score,
                "rank": alert.rank,
                "status": alert.status,
            },
        )


def evaluate(instrument: ResolvedInstrument, candle: list[Any]) -> Evaluation:
    signal = instrument.signal
    try:
        limit = Decimal(signal.limit_price)
        candle_open = Decimal(str(candle[1]))
        candle_low = Decimal(str(candle[3]))
    except (IndexError, InvalidOperation) as exc:
        raise ValueError(
            f"{signal.symbol} has an invalid limit price, candle open, or candle low"
        ) from exc
    if limit <= 0:
        raise ValueError(f"{signal.symbol} limit_price must be positive")
    if candle_low > limit:
        return Evaluation(signal.symbol, "WAIT", "candle low is above limit price", limit)
    return Evaluation(
        signal.symbol,
        "ENTER",
        "candle low reached limit price",
        limit,
        min(candle_open, limit),
    )


def build_alert(
    instrument: ResolvedInstrument, candle: list[Any], evaluation: Evaluation
) -> ExecutionAlert:
    if evaluation.outcome != "ENTER" or evaluation.assumed_entry_price is None:
        raise ValueError("an alert can only be built for an ENTER evaluation")
    signal = instrument.signal
    start = datetime.fromisoformat(str(candle[0]))
    return ExecutionAlert(
        signal.trading_date,
        signal.strategy_id,
        signal.symbol,
        "BUY",
        datetime.now(start.tzinfo).isoformat(),
        evaluation.limit_price,
        evaluation.assumed_entry_price,
        start.isoformat(),
        signal.final_score,
        signal.rank,
    )


def print_alert(alert: ExecutionAlert) -> None:
    print("\nEXECUTION ALERT")
    print(f"Trading date:        {alert.trading_date}")
    print(f"Strategy:            {alert.strategy_id}")
    print(f"Symbol:              {alert.symbol}")
    print(f"Side:                {alert.side}")
    print(f"Limit price:         {alert.limit_price}")
    print(f"Assumed entry price: {alert.assumed_entry_price}")
    print(f"Trigger candle:      {alert.trigger_candle}")
    print(f"Rank:                {alert.rank}")
    print(f"Status:              {alert.status}")


def log_initialization(result: InitializationResult) -> None:
    LOGGER.info(
        "Initialization complete | active=%d rejected=%d unresolved=%d",
        len(result.active_signals),
        len(result.rejected_rows),
        len(result.unresolved_symbols),
    )
    for row in result.rejected_rows:
        LOGGER.warning("Rejected watchlist row %d | %s", row.line_number, row.reason)
    for item in result.unresolved_symbols:
        LOGGER.warning("Unresolved symbol %s | %s", item.symbol, item.reason)


def report_initialization(result: InitializationResult) -> None:
    """Log initialization and send its optional Slack summary safely."""
    log_initialization(result)
    try:
        if send_slack_initialization(result):
            LOGGER.info(
                "Slack initialization notification sent | trading_date=%s",
                result.trading_date,
            )
    except Exception:
        LOGGER.exception(
            "Slack initialization notification failed; startup continues | "
            "trading_date=%s",
            result.trading_date,
        )


def evaluate_cycle(
    result: InitializationResult,
    candle_loader: Callable[[str, str], list[list[Any]]],
    now: datetime,
    alerted: set[tuple[str, str]],
    processed: set[tuple[str, str, str]],
    output_store: DailyOutputStore | None = None,
) -> tuple[list[Evaluation], list[ExecutionAlert]]:
    evaluations: list[Evaluation] = []
    alerts: list[ExecutionAlert] = []
    for instrument in result.active_signals:
        identity = (instrument.signal.strategy_id, instrument.signal.symbol)
        if identity in alerted:
            continue
        try:
            LOGGER.info(
                "Loading candles | strategy=%s | symbol=%s | instrument=%s",
                instrument.signal.strategy_id,
                instrument.signal.symbol,
                instrument.instrument_key,
            )
            candles = candle_loader(instrument.instrument_key, instrument.signal.symbol)
            candle = latest_completed_candle(candles, now)
            if candle is None:
                LOGGER.info("No completed candle | symbol=%s", instrument.signal.symbol)
                continue
            candle_start = str(candle[0])
            processed_key = (*identity, candle_start)
            if processed_key in processed:
                continue
            if datetime.fromisoformat(candle_start).strftime("%Y%m%d") != result.trading_date:
                raise ValueError(
                    f"candle date does not match trading date {result.trading_date}"
                )
            processed.add(processed_key)
            if output_store is not None:
                written = output_store.record_candle(instrument, candle, now)
                LOGGER.info(
                    "Candle CSV %s | symbol=%s | candle=%s | path=%s",
                    "appended" if written else "already stored",
                    instrument.signal.symbol,
                    candle_start,
                    output_store.candle_path,
                )
            item = evaluate(instrument, candle)
            evaluations.append(item)
            LOGGER.info(
                "Signal evaluated | strategy=%s | symbol=%s | candle=%s | "
                "limit=%s | outcome=%s | reason=%s",
                instrument.signal.strategy_id,
                item.symbol,
                candle_start,
                item.limit_price,
                item.outcome,
                item.reason,
            )
            if item.outcome == "ENTER":
                alert = build_alert(instrument, candle, item)
                if output_store is not None:
                    output_store.record_alert(alert)
                    LOGGER.info("Alert CSV appended | path=%s", output_store.alert_path)
                alerts.append(alert)
                alerted.add(identity)
                LOGGER.info(
                    "ALERT generated | strategy=%s | symbol=%s | limit=%s | "
                    "assumed_entry=%s | trigger_candle=%s",
                    alert.strategy_id,
                    alert.symbol,
                    alert.limit_price,
                    alert.assumed_entry_price,
                    alert.trigger_candle,
                )
                print_alert(alert)
                try:
                    if send_slack_execution_alert(alert):
                        LOGGER.info(
                            "Slack BUY alert sent | strategy=%s | symbol=%s",
                            alert.strategy_id,
                            alert.symbol,
                        )
                except Exception:
                    LOGGER.exception(
                        "Slack BUY alert failed; engine continues | strategy=%s | "
                        "symbol=%s",
                        alert.strategy_id,
                        alert.symbol,
                    )
            else:
                print(f"{item.symbol}: {item.outcome} - {item.reason}")
        except Exception:
            LOGGER.exception(
                "Symbol evaluation failed; continuing | strategy=%s | symbol=%s | "
                "instrument=%s",
                instrument.signal.strategy_id,
                instrument.signal.symbol,
                instrument.instrument_key,
            )
    return evaluations, alerts


def run(
    watchlist: Path,
    trading_date: str,
    candle_loader: Callable[[str, str], list[list[Any]]],
    now: datetime | None = None,
    instruments: list[dict[str, Any]] | None = None,
    output_store: DailyOutputStore | None = None,
) -> tuple[list[Evaluation], list[ExecutionAlert]]:
    LOGGER.info("Loading watchlist: %s", watchlist)
    result = initialize(watchlist, trading_date, instruments)
    report_initialization(result)
    alerted: set[tuple[str, str]] = set()
    reference_time = now or datetime.now(MARKET_TIMEZONE)
    evaluations, alerts = evaluate_cycle(
        result, candle_loader, reference_time, alerted, set(), output_store
    )
    LOGGER.info("Run complete | evaluated=%d alerts=%d", len(evaluations), len(alerts))
    return evaluations, alerts


def watch(
    watchlist: Path,
    trading_date: str,
    candle_loader: Callable[[str, str], list[list[Any]]],
    instruments: list[dict[str, Any]] | None = None,
    mock_replay_candles: list[list[Any]] | None = None,
    mock_delay: float = 1.0,
    output_store: DailyOutputStore | None = None,
) -> tuple[list[Evaluation], list[ExecutionAlert]]:
    LOGGER.info("Loading watchlist: %s", watchlist)
    result = initialize(watchlist, trading_date, instruments)
    report_initialization(result)
    alerted: set[tuple[str, str]] = set()
    processed: set[tuple[str, str, str]] = set()
    all_evaluations: list[Evaluation] = []
    all_alerts: list[ExecutionAlert] = []
    shutdown_reason = "unknown"
    try:
        if mock_replay_candles is not None:
            starts = sorted(
                {datetime.fromisoformat(str(row[0])) for row in mock_replay_candles}
            )
            for start in starts:
                simulated_now = start + timedelta(minutes=15)
                LOGGER.info("Mock clock advanced | now=%s", simulated_now.isoformat())
                evaluations, alerts = evaluate_cycle(
                    result,
                    candle_loader,
                    simulated_now,
                    alerted,
                    processed,
                    output_store,
                )
                all_evaluations.extend(evaluations)
                all_alerts.extend(alerts)
                if len(alerted) == len(result.active_signals):
                    shutdown_reason = "all_signals_alerted"
                    break
                if mock_delay:
                    time.sleep(mock_delay)
            else:
                shutdown_reason = "mock_replay_complete"
        else:
            LOGGER.info("Live watch started | checks run after each 15-minute boundary")
            while True:
                now = datetime.now(MARKET_TIMEZONE)
                if now.strftime("%Y%m%d") != trading_date:
                    raise ValueError("live watch trading date must be today in Asia/Kolkata")
                cutoff = now.replace(hour=15, minute=0, second=0, microsecond=0)
                if now.hour > 9 or (now.hour == 9 and now.minute >= 30):
                    evaluations, alerts = evaluate_cycle(
                        result, candle_loader, now, alerted, processed, output_store
                    )
                    all_evaluations.extend(evaluations)
                    all_alerts.extend(alerts)
                    if len(alerted) == len(result.active_signals):
                        shutdown_reason = "all_signals_alerted"
                        break
                    if now >= cutoff:
                        shutdown_reason = "market_cutoff"
                        break
                next_minute = ((now.minute // 15) + 1) * 15
                next_check = now.replace(
                    second=CANDLE_FETCH_DELAY_SECONDS, microsecond=0
                )
                if next_minute == 60:
                    next_check = next_check.replace(minute=0) + timedelta(hours=1)
                else:
                    next_check = next_check.replace(minute=next_minute)
                seconds = max(1.0, (next_check - now).total_seconds())
                LOGGER.info("Next candle check at %s", next_check.isoformat())
                time.sleep(seconds)
    except KeyboardInterrupt:
        shutdown_reason = "user_interrupt"
        LOGGER.warning("Ctrl+C received; shutting down cleanly")
    finally:
        remaining = max(0, len(result.active_signals) - len(alerted))
        summary = (
            f"Watch stopped | reason={shutdown_reason} | "
            f"evaluated={len(all_evaluations)} | alerts={len(all_alerts)} | "
            f"remaining={remaining}"
        )
        print(f"\n{summary}")
        LOGGER.info(summary)
    return all_evaluations, all_alerts


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the basic execution-alert flow.")
    parser.add_argument("watchlist", type=Path)
    parser.add_argument(
        "--trading-date",
        help="Session date in YYYYMMDD; defaults to today in Asia/Kolkata.",
    )
    parser.add_argument("--mock-candles", type=Path)
    parser.add_argument("--watch", action="store_true", help="Keep evaluating new candles.")
    parser.add_argument(
        "--mock-delay",
        type=float,
        default=1.0,
        help="Seconds between simulated candles in mock watch mode.",
    )
    parser.add_argument(
        "--mock-instruments",
        type=Path,
        help="Read a JSON instrument list instead of downloading the Upstox master.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help=(
            "Temporary closed-market mode using bundled mock candles and the "
            "live instrument-master download."
        ),
    )
    args = parser.parse_args()
    trading_date = args.trading_date or current_business_date()
    log_path, error_log_path = configure_logging(
        trading_date, PROJECT_ROOT / "logs"
    )
    LOGGER.info("=" * 78)
    LOGGER.info("Alert engine starting | trading_date=%s", trading_date)
    LOGGER.info("Daily log file | path=%s", log_path)
    LOGGER.info("Error-only log file | path=%s", error_log_path)
    if os.environ.get("SLACK_WEBHOOK_URL", "").strip():
        LOGGER.info("Slack initialization and BUY alert notifications active")
    if args.mock and args.mock_candles:
        parser.error("--mock already supplies its own candle replay file")

    mock_candles = MOCK_CANDLES if args.mock else args.mock_candles
    mock_instruments = args.mock_instruments
    if args.mock:
        LOGGER.warning(
            "MOCK CANDLE MODE ACTIVE | candles are mocked; "
            "instrument master will be downloaded"
        )

    if mock_candles:
        LOGGER.info("Candle source: mock file %s", mock_candles)
        if args.mock:
            mock_sets = load_mock_candles_by_symbol(mock_candles)
            loader = lambda _key, symbol: mock_sets.get(symbol, [])
        else:
            loader = lambda _key, _symbol: load_mock_candles(mock_candles)
    else:
        LOGGER.info("Candle source: live Upstox API")
        token = os.environ.get("UPSTOX_ACCESS_TOKEN")
        if not token:
            print("Error: UPSTOX_ACCESS_TOKEN is not set.", file=sys.stderr)
            return 2
        loader = lambda key, _symbol: fetch_candles(key, token)
    try:
        output_store = DailyOutputStore(PROJECT_ROOT / "output", trading_date)
        LOGGER.info("Candle CSV | path=%s", output_store.candle_path)
        LOGGER.info("Alert CSV | path=%s", output_store.alert_path)
        instruments = None
        if mock_instruments:
            LOGGER.info("Instrument source: mock file %s", mock_instruments)
            with mock_instruments.open(encoding="utf-8") as handle:
                instruments = json.load(handle)
            if not isinstance(instruments, list):
                raise ValueError("mock instrument file must contain a JSON list")
        else:
            LOGGER.info("Instrument source: official Upstox NSE master")
        if args.watch:
            replay_candles = (
                [row for candles in mock_sets.values() for row in candles]
                if args.mock
                else None
            )
            evaluations, alerts = watch(
                args.watchlist,
                trading_date,
                loader,
                instruments=instruments,
                mock_replay_candles=replay_candles,
                mock_delay=args.mock_delay,
                output_store=output_store,
            )
        else:
            evaluations, alerts = run(
                args.watchlist,
                trading_date,
                loader,
                instruments=instruments,
                output_store=output_store,
            )
        print(f"\nEvaluated: {len(evaluations)} | Alerts: {len(alerts)}")
        LOGGER.info(
            "Engine finished normally | evaluated=%d | alerts=%d",
            len(evaluations),
            len(alerts),
        )
        return 0
    except KeyboardInterrupt:
        LOGGER.warning("Ctrl+C received outside watch loop; shutdown complete")
        print("\nEngine stopped by user before the run completed.")
        return 130
    except (OSError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
        LOGGER.error("Run failed | %s", exc)
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
