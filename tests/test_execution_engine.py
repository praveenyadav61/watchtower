import csv
import unittest
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from src.daily_initialization import AcceptedSignal, InitializationResult, ResolvedInstrument
from src.execution_engine import (
    DailyOutputStore,
    build_alert,
    evaluate,
    evaluate_cycle,
    watch,
)


def instrument(limit_price="99.95"):
    signal = AcceptedSignal(
        2,
        "20260710",
        "strategy-v1",
        "ABC",
        "BUY",
        1,
        "88.5",
        limit_price,
    )
    return ResolvedInstrument(signal, "NSE_EQ|ABC", 5)


class ExecutionEngineTests(unittest.TestCase):
    def test_enters_at_limit_when_candle_opens_above_limit(self):
        result = evaluate(
            instrument(),
            ["2026-07-10T09:30:00+05:30", 101, 102, 99.5, 100, 1000, 0],
        )
        self.assertEqual("ENTER", result.outcome)
        self.assertEqual(Decimal("99.95"), result.assumed_entry_price)

    def test_enters_at_open_after_gap_below_limit(self):
        result = evaluate(
            instrument(),
            ["2026-07-10T09:30:00+05:30", 99, 100, 98, 99.5, 1000, 0],
        )
        self.assertEqual(Decimal("99"), result.assumed_entry_price)

    def test_waits_when_low_does_not_reach_limit(self):
        result = evaluate(
            instrument(),
            ["2026-07-10T09:30:00+05:30", 101, 103, 100, 102, 1000, 0],
        )
        self.assertEqual("WAIT", result.outcome)
        self.assertIsNone(result.assumed_entry_price)

    def test_rejects_missing_limit_price(self):
        with self.assertRaisesRegex(ValueError, "invalid limit price"):
            evaluate(
                instrument(""),
                ["2026-07-10T09:30:00+05:30", 101, 103, 100, 102, 1000, 0],
            )

    def test_one_symbol_failure_does_not_stop_other_symbols(self):
        broken = instrument()
        working_signal = AcceptedSignal(
            3, "20260710", "strategy-v1", "XYZ", "BUY", 2, "", "99.95"
        )
        working = ResolvedInstrument(working_signal, "NSE_EQ|XYZ", 5)
        result = InitializationResult("20260710", [broken, working], [], [])
        candle = ["2026-07-10T09:30:00+05:30", 101, 102, 99.5, 100, 1000, 0]

        def loader(key, _symbol):
            if key == "NSE_EQ|ABC":
                raise RuntimeError("temporary API failure")
            return [candle]

        evaluations, alerts = evaluate_cycle(
            result,
            loader,
            datetime.fromisoformat("2026-07-10T09:45:00+05:30"),
            set(),
            set(),
        )

        self.assertEqual(["XYZ"], [item.symbol for item in evaluations])
        self.assertEqual(["XYZ"], [item.symbol for item in alerts])

    def test_daily_output_stores_candle_once_and_appends_alert(self):
        candle = ["2026-07-10T09:30:00+05:30", 101, 102, 99.5, 100, 1000, 0]
        item = instrument()
        alert = build_alert(item, candle, evaluate(item, candle))
        directory = Path("output/test_artifacts")
        store = DailyOutputStore(directory, "20990101")
        store.candle_path.unlink(missing_ok=True)
        store.alert_path.unlink(missing_ok=True)
        store = DailyOutputStore(directory, "20990101")
        self.addCleanup(store.candle_path.unlink, missing_ok=True)
        self.addCleanup(store.alert_path.unlink, missing_ok=True)
        received = datetime.fromisoformat("2026-07-10T09:45:00+05:30")

        self.assertTrue(store.record_candle(item, candle, received))
        self.assertFalse(store.record_candle(item, candle, received))
        store.record_alert(alert)

        with store.candle_path.open(newline="", encoding="utf-8") as handle:
            self.assertEqual(1, len(list(csv.DictReader(handle))))
        with store.alert_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual("ABC", rows[0]["symbol"])

    @patch("src.execution_engine.time.sleep", side_effect=KeyboardInterrupt)
    def test_watch_handles_ctrl_c_and_returns_counts(self, _mock_sleep):
        candle = ["2026-07-13T09:15:00+05:30", 101, 102, 100.6, 101, 1000, 0]
        instruments = [{
            "segment": "NSE_EQ",
            "instrument_type": "EQ",
            "trading_symbol": "MOTILALOFS",
            "instrument_key": "NSE_EQ|MOCK_MOTILALOFS",
            "tick_size": 5,
        }]

        evaluations, alerts = watch(
            Path("examples/mock_watchlist_single.csv"),
            "20260713",
            lambda _key, _symbol: [candle],
            instruments=instruments,
            mock_replay_candles=[candle],
            mock_delay=1,
        )

        self.assertEqual(1, len(evaluations))
        self.assertEqual([], alerts)


if __name__ == "__main__":
    unittest.main()
