import unittest
from pathlib import Path

from src.daily_initialization import (
    current_business_date,
    load_watchlist,
    valid_business_date,
    validate_rows,
)


class WatchlistLoaderTests(unittest.TestCase):
    def test_rejects_common_misspelled_alert_headers(self):
        path = Path("output/test_artifacts/misspelled_watchlist.csv")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "symbol,threshold_volume,price_low_limit,ema21\nABC,1000,99,100\n",
            encoding="utf-8",
        )
        self.addCleanup(path.unlink, missing_ok=True)

        with self.assertRaisesRegex(
            ValueError,
            "ema21 -> ema20.*threshold_volume -> volume_threshold",
        ):
            load_watchlist(path, "20260720")

    def test_accepts_valid_row_and_ignores_extra_columns(self):
        rows = [{
            "trading_date": "20260710",
            "strategy_id": "strategy-v1",
            "symbol": " reliance ",
            "entry_decision": "buy",
            "rank": "1",
            "limit_price": "100",
            "regime": "correction",
        }]

        accepted, rejected = validate_rows(rows, "20260710")

        self.assertEqual("RELIANCE", accepted[0].symbol)
        self.assertEqual([], rejected)

    def test_rejects_bad_rows_with_reasons(self):
        rows = [
            {"trading_date": "2026-07-10", "strategy_id": "s1", "symbol": "A", "entry_decision": "BUY", "rank": "1"},
            {"trading_date": "20260710", "strategy_id": "s1", "symbol": "", "entry_decision": "BUY", "rank": "2"},
            {"trading_date": "20260710", "strategy_id": "s1", "symbol": "B", "entry_decision": "SELL", "rank": "3"},
            {"trading_date": "20260710", "strategy_id": "s1", "symbol": "C", "entry_decision": "BUY", "rank": "zero"},
        ]

        accepted, rejected = validate_rows(rows, "20260710")

        self.assertEqual([], accepted)
        self.assertEqual(4, len(rejected))
        self.assertIn("YYYYMMDD", rejected[0].reason)
        self.assertEqual("symbol is missing", rejected[1].reason)
        self.assertEqual("only BUY is supported", rejected[2].reason)
        self.assertIn("positive integer", rejected[3].reason)

    def test_rejects_duplicate_strategy_and_symbol(self):
        row = {"trading_date": "20260710", "strategy_id": "s1", "symbol": "ABC", "entry_decision": "BUY", "rank": "1", "limit_price": "100"}

        accepted, rejected = validate_rows([row, row])

        self.assertEqual(1, len(accepted))
        self.assertEqual("duplicate strategy_id + symbol", rejected[0].reason)

    def test_accepts_minimal_volume_row_and_applies_defaults(self):
        accepted, rejected = validate_rows(
            [{"symbol": " reliance ", "volume_threshold": "500000"}],
            "20260717",
        )

        self.assertEqual([], rejected)
        signal = accepted[0]
        self.assertEqual("20260717", signal.trading_date)
        self.assertEqual("volume_threshold_v1", signal.strategy_id)
        self.assertEqual("RELIANCE", signal.symbol)
        self.assertEqual("BUY", signal.entry_decision)
        self.assertEqual(1, signal.rank)
        self.assertEqual("500000", signal.volume_threshold)

    def test_accepts_multiple_alert_columns_on_one_row(self):
        accepted, rejected = validate_rows(
            [{
                "symbol": "ABC",
                "limit_price": "100",
                "volume_threshold": "500000",
                "price_high_limit": "110",
                "ema20": "104.5",
            }],
            "20260717",
        )

        self.assertEqual([], rejected)
        self.assertEqual("multi_alert_v1", accepted[0].strategy_id)
        self.assertEqual("110", accepted[0].price_high_limit)
        self.assertEqual("104.5", accepted[0].ema20)

    def test_rejects_legacy_and_new_low_price_columns_together(self):
        accepted, rejected = validate_rows(
            [{"symbol": "ABC", "limit_price": "100", "price_low_limit": "99"}],
            "20260717",
        )

        self.assertEqual([], accepted)
        self.assertIn("either limit_price or price_low_limit", rejected[0].reason)

    def test_validates_real_calendar_date(self):
        self.assertTrue(valid_business_date("20260710"))
        self.assertFalse(valid_business_date("20260230"))

    def test_current_business_date_uses_yyyymmdd(self):
        self.assertTrue(valid_business_date(current_business_date()))


if __name__ == "__main__":
    unittest.main()
