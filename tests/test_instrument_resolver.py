import gzip
import json
import unittest
from unittest.mock import Mock, patch

import requests

from src.daily_initialization import (
    AcceptedSignal,
    InitializationResult,
    RejectedRow,
    UnresolvedSymbol,
    download_instruments,
    parse_instrument_bytes,
    resolve_signals,
)


def signal(symbol: str) -> AcceptedSignal:
    return AcceptedSignal(2, "20260710", "s1", symbol, "BUY", 1)


class InstrumentResolverTests(unittest.TestCase):
    def test_resolves_only_nse_equity_by_trading_symbol(self):
        instruments = [
            {"segment": "NSE_EQ", "instrument_type": "EQ", "trading_symbol": "ABC", "instrument_key": "NSE_EQ|ABC1", "tick_size": 5},
            {"segment": "BSE_EQ", "instrument_type": "EQ", "trading_symbol": "ABC", "instrument_key": "BSE_EQ|ABC1"},
            {"segment": "NSE_FO", "instrument_type": "FUT", "trading_symbol": "ABC", "instrument_key": "NSE_FO|1"},
        ]

        resolved, unresolved = resolve_signals([signal("ABC")], instruments)

        self.assertEqual("NSE_EQ|ABC1", resolved[0].instrument_key)
        self.assertEqual(5, resolved[0].tick_size_raw)
        self.assertEqual([], unresolved)

    def test_reports_missing_and_ambiguous_symbols(self):
        instruments = [
            {"segment": "NSE_EQ", "instrument_type": "EQ", "trading_symbol": "ABC", "instrument_key": "NSE_EQ|ONE"},
            {"segment": "NSE_EQ", "instrument_type": "EQ", "trading_symbol": "ABC", "instrument_key": "NSE_EQ|TWO"},
        ]

        resolved, unresolved = resolve_signals(
            [signal("ABC"), signal("MISSING")], instruments
        )

        self.assertEqual([], resolved)
        self.assertIn("multiple", unresolved[0].reason)
        self.assertIn("no matching", unresolved[1].reason)

    def test_reads_compressed_upstox_json(self):
        payload = [{"segment": "NSE_EQ", "instrument_type": "EQ"}]
        content = gzip.compress(json.dumps(payload).encode("utf-8"))

        self.assertEqual(payload, parse_instrument_bytes(content))

    def test_initialization_is_ready_with_warnings_when_one_signal_resolves(self):
        resolved, _ = resolve_signals(
            [signal("ABC")],
            [{"segment": "NSE_EQ", "instrument_type": "EQ", "trading_symbol": "ABC", "instrument_key": "NSE_EQ|ABC"}],
        )
        result = InitializationResult(
            "20260710",
            resolved,
            [RejectedRow(3, "symbol is missing")],
            [UnresolvedSymbol("UNKNOWN", "no matching NSE equity instrument")],
        )

        self.assertTrue(result.ready)

    def test_initialization_is_not_ready_without_active_signals(self):
        result = InitializationResult("20260710", [], [], [])

        self.assertFalse(result.ready)

    @patch("src.daily_initialization.requests.get")
    def test_instrument_download_retries_temporary_failure(self, mock_get):
        payload = [{"segment": "NSE_EQ"}]
        success = Mock(content=gzip.compress(json.dumps(payload).encode("utf-8")))
        success.raise_for_status.return_value = None
        mock_get.side_effect = [requests.Timeout("temporary"), success]

        instruments = download_instruments(max_attempts=3)

        self.assertEqual(payload, instruments)
        self.assertEqual(2, mock_get.call_count)

    @patch("src.daily_initialization.requests.get")
    def test_instrument_download_does_not_retry_permanent_http_error(self, mock_get):
        response = Mock(status_code=403)
        mock_get.side_effect = requests.HTTPError(response=response)

        with self.assertRaisesRegex(ValueError, "HTTP 403"):
            download_instruments(max_attempts=3)

        self.assertEqual(1, mock_get.call_count)


if __name__ == "__main__":
    unittest.main()
