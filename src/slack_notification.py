"""Slack incoming-webhook sender and standalone connectivity-test command."""

from __future__ import annotations

import argparse
from datetime import datetime
import os
import sys
from urllib.parse import urlparse

import requests


def validate_webhook_url(webhook_url: str) -> None:
    parsed = urlparse(webhook_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "hooks.slack.com"
        or not parsed.path.startswith("/services/")
    ):
        raise ValueError("SLACK_WEBHOOK_URL is not a valid Slack incoming webhook URL")


def send_slack_message(webhook_url: str, message: str, timeout: int = 10) -> None:
    """Send one plain-text Slack message or raise without exposing the URL."""
    validate_webhook_url(webhook_url)
    if not message.strip():
        raise ValueError("Slack message cannot be empty")
    try:
        response = requests.post(
            webhook_url,
            json={"text": message},
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Slack webhook request failed: {exc}") from exc
    if response.text.strip().lower() != "ok":
        raise RuntimeError("Slack webhook returned an unexpected response")


def test_message() -> str:
    return (
        "Alert Engine Slack connectivity test\n"
        f"Sent at: {datetime.now().astimezone().isoformat()}\n"
        "No trading alert was generated."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send a standalone Slack incoming-webhook test message."
    )
    parser.add_argument(
        "--message",
        help="Optional custom test text; defaults to a safe connectivity message.",
    )
    args = parser.parse_args()

    webhook_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("Error: SLACK_WEBHOOK_URL is not set.", file=sys.stderr)
        return 2
    try:
        send_slack_message(webhook_url, args.message or test_message())
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print("Slack test message sent successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
