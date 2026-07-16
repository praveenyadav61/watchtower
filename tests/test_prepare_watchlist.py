import csv
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.prepare_watchlist import (
    latest_close_before,
    load_symbols,
    prepare_rows,
    write_watchlist,
)


def instruments():
    return [{
        "segment": "NSE_EQ",
        "instrument_type": "EQ",
        "trading_symbol": "ABC",
        "instrument_key": "NSE_EQ|ABC",
        "tick_size": 5,
    }]


class PrepareWatchlistTests(unittest.TestCase):
    def artifact_path(self, name):
        directory = Path("output/test_artifacts")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.unlink(missing_ok=True)
        path.with_suffix(path.suffix + ".tmp").unlink(missing_ok=True)
        self.addCleanup(path.unlink, missing_ok=True)
        self.addCleanup(path.with_suffix(path.suffix + ".tmp").unlink, missing_ok=True)
        return path

    def test_selects_latest_close_before_trading_date(self):
        candles = [
            ["2026-07-15T00:00:00+05:30", 100, 105, 99, 102.25, 10, 0],
            ["2026-07-14T00:00:00+05:30", 98, 101, 97, 100, 10, 0],
        ]
        self.assertEqual(
            Decimal("102.25"), latest_close_before(candles, "20260716")
        )

    def test_prepares_three_percent_limit(self):
        def fetcher(_key, _token, from_date, to_date):
            self.assertEqual(date(2026, 7, 2).isoformat(), from_date)
            self.assertEqual(date(2026, 7, 15).isoformat(), to_date)
            return [["2026-07-15T00:00:00+05:30", 100, 105, 99, 102.25, 10, 0]]

        rows = prepare_rows(
            ["ABC"], "20260716", "three_percent_drop_v1", Decimal("3"),
            "token", instruments(), fetcher,
        )
        self.assertEqual("102.25", rows[0]["previous_close"])
        self.assertEqual("99.18", rows[0]["limit_price"])

    def test_transactional_write_creates_engine_ready_csv(self):
        path = self.artifact_path("prepared_watchlist.csv")
        path.write_text("symbol\nABC\n", encoding="utf-8")
        write_watchlist(path, [{
            "trading_date": "20260716",
            "strategy_id": "three_percent_drop_v1",
            "symbol": "ABC",
            "entry_decision": "BUY",
            "rank": 1,
            "previous_close": "102.25",
            "limit_discount_percent": "3",
            "limit_price": "99.18",
        }])
        with path.open(newline="", encoding="utf-8") as handle:
            written = list(csv.DictReader(handle))
        self.assertEqual("99.18", written[0]["limit_price"])
        self.assertFalse(path.with_suffix(".csv.tmp").exists())

    def test_load_symbols_rejects_duplicates(self):
        path = self.artifact_path("duplicate_watchlist.csv")
        path.write_text("symbol\nABC\nabc\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate symbols"):
            load_symbols(path)


if __name__ == "__main__":
    unittest.main()
