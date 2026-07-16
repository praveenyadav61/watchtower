import unittest
from unittest.mock import Mock, patch

from src.slack_notification import send_slack_message, validate_webhook_url


class SlackNotificationTests(unittest.TestCase):
    def test_rejects_non_slack_webhook_url(self):
        with self.assertRaisesRegex(ValueError, "valid Slack"):
            validate_webhook_url("https://example.com/services/secret")

    @patch("src.slack_notification.requests.post")
    def test_sends_plain_text_payload(self, mock_post):
        response = Mock(text="ok")
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        send_slack_message(
            "https://hooks.slack.com/services/T000/B000/SECRET",
            "Connectivity test",
        )

        mock_post.assert_called_once_with(
            "https://hooks.slack.com/services/T000/B000/SECRET",
            json={"text": "Connectivity test"},
            timeout=10,
        )

    @patch("src.slack_notification.requests.post")
    def test_rejects_unexpected_slack_response(self, mock_post):
        response = Mock(text="invalid_payload")
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        with self.assertRaisesRegex(RuntimeError, "unexpected response"):
            send_slack_message(
                "https://hooks.slack.com/services/T000/B000/SECRET",
                "Connectivity test",
            )


if __name__ == "__main__":
    unittest.main()
