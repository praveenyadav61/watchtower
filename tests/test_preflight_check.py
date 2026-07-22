import unittest
from unittest.mock import patch

from src.preflight_check import run_preflight


class PreflightCheckTests(unittest.TestCase):
    @patch("src.execution_engine.send_slack_message")
    @patch.dict(
        "os.environ",
        {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/T/B/SECRET"},
        clear=False,
    )
    def test_preflight_passes_without_sending_slack(self, mock_send):
        run_preflight()

        mock_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
