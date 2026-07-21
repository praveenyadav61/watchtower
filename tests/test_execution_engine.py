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
    evaluate_all,
    evaluate_cycle,
    send_slack_execution_alert,
    send_slack_initialization,
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


def volume_instrument(volume_threshold="1000"):
    signal = AcceptedSignal(
        2,
        "20260710",
        "volume_threshold_v1",
        "ABC",
        "BUY",
        1,
        "",
        "",
        volume_threshold,
    )
    return ResolvedInstrument(signal, "NSE_EQ|ABC", 5)


class ExecutionEngineTests(unittest.TestCase):
    @patch("src.execution_engine.send_slack_message")
    @patch.dict(
        "os.environ",
        {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T/B/SECRET"},
        clear=False,
    )
    def test_slack_initialization_contains_summary(self, mock_send):
        result = InitializationResult("20260716", [instrument()], [], [])

        sent = send_slack_initialization(result)

        self.assertTrue(sent)
        message = mock_send.call_args.args[1]
        self.assertEqual(
            "✅ Engine ready | 20260716 | symbols 1 | rejected 0 | unresolved 0",
            message,
        )

    @patch("src.execution_engine.send_slack_message")
    @patch.dict(
        "os.environ",
        {
            "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T/B/SECRET",
        },
        clear=False,
    )
    def test_slack_message_contains_final_buy_alert(self, mock_send):
        candle = ["2026-07-10T09:30:00+05:30", 101, 102, 99.5, 100.25, 1000, 0]
        alert = build_alert(instrument(), candle, evaluate(instrument(), candle))
        sent = send_slack_execution_alert(alert)

        self.assertTrue(sent)
        message = mock_send.call_args.args[1]
        self.assertEqual("🔔 ABC | LOW 99.5 ≤ 99.95 | 09:30", message)

    @patch("src.execution_engine.send_slack_message")
    @patch.dict("os.environ", {}, clear=True)
    def test_slack_buy_alert_is_disabled_without_webhook(self, mock_send):
        candle = ["2026-07-10T09:30:00+05:30", 101, 102, 99.5, 100.25, 1000, 0]
        alert = build_alert(instrument(), candle, evaluate(instrument(), candle))
        sent = send_slack_execution_alert(alert)

        self.assertFalse(sent)
        mock_send.assert_not_called()

    @patch("src.execution_engine.send_slack_message")
    @patch.dict(
        "os.environ",
        {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T/B/SECRET"},
        clear=False,
    )
    def test_wait_evaluation_does_not_send_slack(self, mock_send):
        result = InitializationResult("20260710", [instrument()], [], [])
        candle = ["2026-07-10T09:30:00+05:30", 101, 103, 100, 102, 1000, 0]

        evaluate_cycle(
            result,
            lambda _key, _symbol: [candle],
            datetime.fromisoformat("2026-07-10T09:45:00+05:30"),
            set(),
            set(),
        )

        mock_send.assert_not_called()

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

    def test_volume_threshold_triggers_on_completed_candle_volume(self):
        result = evaluate(
            volume_instrument("1000"),
            ["2026-07-10T09:30:00+05:30", 101, 103, 100, 102, 1250, 0],
        )

        self.assertEqual("ENTER", result.outcome)
        self.assertEqual("VOLUME", result.alert_type)
        self.assertEqual(Decimal("1000"), result.volume_threshold)
        self.assertEqual(Decimal("1250"), result.candle_volume)

    def test_volume_threshold_waits_below_threshold(self):
        result = evaluate(
            volume_instrument("1000"),
            ["2026-07-10T09:30:00+05:30", 101, 103, 100, 102, 999, 0],
        )

        self.assertEqual("WAIT", result.outcome)
        self.assertEqual("VOLUME", result.alert_type)

    @patch("src.execution_engine.send_slack_message")
    @patch.dict(
        "os.environ",
        {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T/B/SECRET"},
        clear=False,
    )
    def test_slack_volume_alert_contains_threshold_and_actual_volume(self, mock_send):
        candle = ["2026-07-10T09:30:00+05:30", 101, 103, 100, 102, 1250, 0]
        item = volume_instrument("1000")
        alert = build_alert(item, candle, evaluate(item, candle))

        self.assertTrue(send_slack_execution_alert(alert))
        message = mock_send.call_args.args[1]
        self.assertEqual(
            "🔔 ABC | VOLUME 1,250 ≥ 1,000 | 1.25x | 09:30",
            message,
        )

    def test_rejects_signal_without_any_rule(self):
        with self.assertRaisesRegex(ValueError, "no configured alert rule"):
            evaluate(
                instrument(""),
                ["2026-07-10T09:30:00+05:30", 101, 103, 100, 102, 1000, 0],
            )

    def test_evaluates_all_configured_rules_independently(self):
        signal = AcceptedSignal(
            2, "20260710", "multi", "ABC", "BUY", 1, "", "", "1000",
            "100", "102", "101",
        )
        item = ResolvedInstrument(signal, "NSE_EQ|ABC", 5)
        candle = ["2026-07-10T09:30:00+05:30", 101, 103, 99, 101.5, 1200, 0]

        evaluations = evaluate_all(item, candle)

        self.assertEqual(4, len(evaluations))
        self.assertEqual(
            {"volume_threshold", "price_low_limit", "price_high_limit", "ema20"},
            {evaluation.rule_id for evaluation in evaluations},
        )
        self.assertTrue(all(evaluation.outcome == "ENTER" for evaluation in evaluations))

    def test_volume_repeats_but_price_and_ema_alert_only_once(self):
        signal = AcceptedSignal(
            2, "20260710", "multi", "ABC", "BUY", 1, "", "", "1000",
            "100", "102", "101",
        )
        item = ResolvedInstrument(signal, "NSE_EQ|ABC", 5)
        result = InitializationResult("20260710", [item], [], [])
        candles = [
            ["2026-07-10T09:30:00+05:30", 101, 103, 99, 101.5, 1200, 0],
            ["2026-07-10T09:45:00+05:30", 101, 104, 98, 102, 1400, 0],
        ]
        triggered_once = set()
        processed = set()

        _, first_alerts = evaluate_cycle(
            result, lambda _key, _symbol: candles,
            datetime.fromisoformat("2026-07-10T09:45:00+05:30"),
            triggered_once, processed,
        )
        _, second_alerts = evaluate_cycle(
            result, lambda _key, _symbol: candles,
            datetime.fromisoformat("2026-07-10T10:00:00+05:30"),
            triggered_once, processed,
        )

        self.assertEqual(4, len(first_alerts))
        self.assertEqual(["volume_threshold"], [alert.rule_id for alert in second_alerts])

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
        self.assertTrue(store.record_alert(alert))
        self.assertFalse(store.record_alert(alert))

        with store.candle_path.open(newline="", encoding="utf-8") as handle:
            self.assertEqual(1, len(list(csv.DictReader(handle))))
        with store.alert_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual("ABC", rows[0]["symbol"])
        restarted = DailyOutputStore(directory, "20990101")
        self.assertIn(
            ("strategy-v1", "ABC", "price_low_limit"),
            restarted.triggered_once,
        )

    def test_volume_alert_csv_contains_volume_details(self):
        candle = ["2026-07-10T09:30:00+05:30", 101, 103, 100, 102, 1250, 0]
        item = volume_instrument("1000")
        alert = build_alert(item, candle, evaluate(item, candle))
        directory = Path("output/test_artifacts")
        store = DailyOutputStore(directory, "20990102")
        store.alert_path.unlink(missing_ok=True)
        store = DailyOutputStore(directory, "20990102")
        self.addCleanup(store.alert_path.unlink, missing_ok=True)

        store.record_alert(alert)

        with store.alert_path.open(newline="", encoding="utf-8") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual("VOLUME", row["alert_type"])
        self.assertEqual("1000", row["volume_threshold"])
        self.assertEqual("1250", row["candle_volume"])

    @patch.dict("os.environ", {}, clear=True)
    def test_cycle_backfills_cumulative_score_from_all_completed_candles(self):
        directory = Path("output/test_artifacts")
        paths = [
            directory / "candles_20260710.csv",
            directory / "execution_alerts_20260710.csv",
            directory / "cumulative_scores_20260710.csv",
        ]
        for path in paths:
            path.unlink(missing_ok=True)
            self.addCleanup(path.unlink, missing_ok=True)
        store = DailyOutputStore(directory, "20260710")
        item = volume_instrument("1000")
        result = InitializationResult("20260710", [item], [], [])
        candles = [
            ["2026-07-10T09:15:00+05:30", 100, 100, 100, 100, 1000, 0],
            ["2026-07-10T09:30:00+05:30", 100, 101, 100, 101, 2000, 0],
            ["2026-07-10T09:45:00+05:30", 101, 104, 101, 104, 4000, 0],
        ]

        evaluate_cycle(
            result,
            lambda _key, _symbol: candles,
            datetime.fromisoformat("2026-07-10T10:00:00+05:30"),
            set(),
            set(),
            store,
        )

        with store.candle_path.open(newline="", encoding="utf-8") as handle:
            self.assertEqual(3, len(list(csv.DictReader(handle))))
        with store.cumulative_score_store.path.open(
            newline="", encoding="utf-8"
        ) as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(3, len(rows))
        self.assertEqual("2", rows[-1]["alert_count"])
        self.assertEqual("true", rows[-1]["alert_sent"])

    def test_legacy_alert_csv_is_backed_up_and_migrated(self):
        directory = Path("output/test_artifacts")
        path = directory / "execution_alerts_20990103.csv"
        backup = directory / "execution_alerts_20990103_legacy.csv"
        path.unlink(missing_ok=True)
        backup.unlink(missing_ok=True)
        self.addCleanup(path.unlink, missing_ok=True)
        self.addCleanup(backup.unlink, missing_ok=True)
        directory.mkdir(parents=True, exist_ok=True)
        fields = [
            "trading_date", "strategy_id", "symbol", "side", "alert_time",
            "limit_price", "assumed_entry_price", "trigger_candle",
            "final_score", "rank", "status",
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow({
                "trading_date": "20990103",
                "strategy_id": "legacy",
                "symbol": "ABC",
                "side": "BUY",
                "alert_time": "2099-01-03T09:45:00+05:30",
                "limit_price": "100",
                "assumed_entry_price": "99.5",
                "trigger_candle": "2099-01-03T09:30:00+05:30",
                "rank": "1",
                "status": "ENTERED",
            })

        store = DailyOutputStore(directory, "20990103")

        self.assertTrue(backup.exists())
        self.assertIn(("legacy", "ABC", "price_low_limit"), store.triggered_once)
        with path.open(newline="", encoding="utf-8") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual("price_low_limit", row["rule_id"])
        self.assertEqual("ONCE_PER_DAY", row["repeat_mode"])

    @patch("src.execution_engine.time.sleep", side_effect=KeyboardInterrupt)
    def test_watch_handles_ctrl_c_and_returns_counts(self, _mock_sleep):
        candle = ["2026-07-13T09:15:00+05:30", 101, 102, 100.6, 101, 1000, 0]
        watchlist = Path("output/test_artifacts/watch_test_watchlist.csv")
        watchlist.parent.mkdir(parents=True, exist_ok=True)
        watchlist.write_text("symbol,limit_price\nMOTILALOFS,99.95\n", encoding="utf-8")
        self.addCleanup(watchlist.unlink, missing_ok=True)
        instruments = [{
            "segment": "NSE_EQ",
            "instrument_type": "EQ",
            "trading_symbol": "MOTILALOFS",
            "instrument_key": "NSE_EQ|MOCK_MOTILALOFS",
            "tick_size": 5,
        }]

        evaluations, alerts = watch(
            watchlist,
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
