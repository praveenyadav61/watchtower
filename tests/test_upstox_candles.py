import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from upstox_candles import (
    extract_candles,
    fetch_candles,
    latest_completed_candle,
    load_mock_candles,
)


class LatestCompletedCandleTests(unittest.TestCase):
    @patch("upstox_candles.requests.get")
    def test_live_request_uses_documented_v3_headers_and_path(self, mock_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"status": "success", "data": {"candles": []}}
        mock_get.return_value = response

        fetch_candles("NSE_EQ|INE848E01016", "secret-token")

        url = mock_get.call_args.args[0]
        headers = mock_get.call_args.kwargs["headers"]
        self.assertEqual(
            "https://api.upstox.com/v3/historical-candle/intraday/"
            "NSE_EQ%7CINE848E01016/minutes/15",
            url,
        )
        self.assertEqual("application/json", headers["Content-Type"])
        self.assertEqual("Bearer secret-token", headers["Authorization"])

    def test_excludes_forming_candle_and_ignores_response_order(self):
        candles = [
            ["2026-07-11T10:00:00+05:30", 102, 103, 101, 102, 1000, 0],
            ["2026-07-11T09:30:00+05:30", 100, 101, 99, 100, 800, 0],
            ["2026-07-11T09:45:00+05:30", 100, 102, 100, 102, 900, 0],
        ]

        result = latest_completed_candle(
            candles, datetime.fromisoformat("2026-07-11T10:07:00+05:30")
        )

        self.assertEqual("2026-07-11T09:45:00+05:30", result[0])

    def test_returns_none_before_first_candle_completes(self):
        candles = [
            ["2026-07-11T09:15:00+05:30", 100, 101, 99, 100, 800, 0]
        ]

        result = latest_completed_candle(
            candles, datetime.fromisoformat("2026-07-11T09:20:00+05:30")
        )

        self.assertIsNone(result)

    def test_loads_upstox_format_mock_response(self):
        path = Path(__file__).parent.parent / "examples" / "mock_candles.json"
        candles = load_mock_candles(path)

        self.assertEqual("2026-07-13T10:15:00+05:30", candles[0][0])

    def test_rejects_invalid_mock_response_shape(self):
        with self.assertRaisesRegex(RuntimeError, "candle list"):
            extract_candles({"status": "success", "data": {}})


if __name__ == "__main__":
    unittest.main()
