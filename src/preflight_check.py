"""Run a fast isolated cumulative-score check before live startup."""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import shutil
import sys

from src.daily_initialization import initialize
from src.execution_engine import DailyOutputStore, evaluate_cycle
from upstox_candles import load_mock_candles


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRADING_DATE = "20260713"


def run_preflight() -> None:
    watchlist = PROJECT_ROOT / "examples" / "cumulative_score_mock_watchlist.csv"
    candle_file = PROJECT_ROOT / "examples" / "cumulative_score_mock_candles.json"
    instrument_file = PROJECT_ROOT / "examples" / "mock_instruments.json"
    output_directory = PROJECT_ROOT / "output" / f"preflight_{os.getpid()}"
    previous_slack = os.environ.pop("SLACK_WEBHOOK_URL", None)
    try:
        with instrument_file.open(encoding="utf-8") as handle:
            instruments = json.load(handle)
        candles = load_mock_candles(candle_file)
        result = initialize(watchlist, TRADING_DATE, instruments)
        if not result.ready or len(result.active_signals) != 1:
            raise RuntimeError("mock watchlist did not initialize exactly one symbol")

        store = DailyOutputStore(output_directory, TRADING_DATE)
        now = datetime.fromisoformat("2026-07-13T10:00:00+05:30")
        evaluations, standard_alerts = evaluate_cycle(
            result,
            lambda _key, _symbol: candles,
            now,
            set(),
            set(),
            store,
        )
        if evaluations or standard_alerts:
            raise RuntimeError("standalone alerts were generated during cumulative-only test")

        with store.cumulative_score_store.path.open(
            newline="", encoding="utf-8"
        ) as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != 3:
            raise RuntimeError(f"expected 3 cumulative rows, received {len(rows)}")
        final = rows[-1]
        if final["alert_sent"] != "true" or int(final["alert_count"]) != 1:
            raise RuntimeError("mock cumulative alert or per-symbol count is incorrect")
        if Decimal(final["cumulative_score"]) <= Decimal("5"):
            raise RuntimeError("mock cumulative score did not exceed 5")
        if not final["harmonic_mean"]:
            raise RuntimeError("mock harmonic mean was not calculated")

        restarted = DailyOutputStore(output_directory, TRADING_DATE)
        evaluate_cycle(
            result,
            lambda _key, _symbol: candles,
            now,
            set(),
            set(),
            restarted,
        )
        with restarted.cumulative_score_store.path.open(
            newline="", encoding="utf-8"
        ) as handle:
            if len(list(csv.DictReader(handle))) != 3:
                raise RuntimeError("restart deduplication created duplicate calculations")
    finally:
        if previous_slack is not None:
            os.environ["SLACK_WEBHOOK_URL"] = previous_slack
        shutil.rmtree(output_directory, ignore_errors=True)


def main() -> int:
    try:
        run_preflight()
    except Exception as exc:
        print(f"PRE-FLIGHT FAILED: {exc}", file=sys.stderr)
        return 1
    print("PRE-FLIGHT PASSED: cumulative-score mock flow is healthy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
