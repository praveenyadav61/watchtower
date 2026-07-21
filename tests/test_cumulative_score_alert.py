import csv
import unittest
from decimal import Decimal
from pathlib import Path

from src.cumulative_score_alert import (
    CumulativeScorePolicy,
    CumulativeScoreStore,
    signed_harmonic_mean,
)
from src.execution_engine import cumulative_score_message


class CumulativeScoreAlertTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path("output/test_artifacts")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "cumulative_scores_20990104.csv"
        self.path.unlink(missing_ok=True)
        self.addCleanup(self.path.unlink, missing_ok=True)
        self.policy = CumulativeScorePolicy(Decimal("1"), Decimal("5"), 2)

    def test_signed_harmonic_mean_handles_positive_negative_and_zero(self):
        self.assertEqual(
            Decimal("1.333333333333333333333333333"),
            signed_harmonic_mean(Decimal("1"), Decimal("2")),
        )
        self.assertEqual(
            Decimal("-1.333333333333333333333333333"),
            signed_harmonic_mean(Decimal("-1"), Decimal("2")),
        )
        self.assertEqual(Decimal("0"), signed_harmonic_mean(Decimal("0"), Decimal("2")))

    def test_calculates_score_history_alert_count_and_green_status(self):
        store = CumulativeScoreStore(self.directory, "20990104", self.policy)
        baseline = store.process(
            "special", "ABC",
            ["2099-01-04T09:15:00+05:30", 100, 100, 100, 100, 500, 0],
            "500",
        )
        first = store.process(
            "special", "ABC",
            ["2099-01-04T09:30:00+05:30", 100, 101, 100, 101, 1000, 0],
            "500",
        )
        second = store.process(
            "special", "ABC",
            ["2099-01-04T09:45:00+05:30", 101, 104, 101, 104, 2000, 0],
            "500",
        )

        self.assertTrue(baseline.is_baseline)
        self.assertEqual(Decimal("2.00"), first.score_contribution)
        self.assertEqual(Decimal("2.00"), first.cumulative_score)
        self.assertEqual(1, first.alert_count)
        self.assertTrue(first.is_new_alert)
        self.assertGreater(second.cumulative_score, Decimal("5"))
        self.assertEqual(2, second.alert_count)
        self.assertEqual(2, len(second.score_history))
        self.assertEqual(2, len(second.harmonic_history))
        self.assertIn("🆕 🟡 ABC | CUMULATIVE SCORE 2.00 | Alert #1", cumulative_score_message(first))
        self.assertIn("🟢 ABC | CUMULATIVE SCORE", cumulative_score_message(second))

    def test_restart_restores_state_and_deduplicates_candles(self):
        first_store = CumulativeScoreStore(self.directory, "20990104", self.policy)
        candle_one = ["2099-01-04T09:15:00+05:30", 100, 100, 100, 100, 500, 0]
        candle_two = ["2099-01-04T09:30:00+05:30", 100, 101, 100, 101, 1000, 0]
        first_store.process("special", "ABC", candle_one, "500")
        first_result = first_store.process("special", "ABC", candle_two, "500")

        restarted = CumulativeScoreStore(self.directory, "20990104", self.policy)
        duplicate = restarted.process("special", "ABC", candle_two, "500")
        next_result = restarted.process(
            "special", "ABC",
            ["2099-01-04T09:45:00+05:30", 101, 102, 101, 102, 1000, 0],
            "500",
        )

        self.assertIsNone(duplicate)
        self.assertEqual(2, next_result.alert_count)
        self.assertEqual(first_result.cumulative_score, next_result.score_history[0])
        with self.path.open(newline="", encoding="utf-8") as handle:
            self.assertEqual(3, len(list(csv.DictReader(handle))))


if __name__ == "__main__":
    unittest.main()
