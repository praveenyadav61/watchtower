# Slack Notification Test

The Slack utility can be run as a standalone connectivity test. In the engine,
Slack sends one successful initialization summary and final BUY execution
alerts when `SLACK_WEBHOOK_URL` is set. WAIT evaluations and routine candle
prices are not sent.

## Create the webhook

1. Create or select a Slack app for your workspace.
2. Enable Incoming Webhooks.
3. Add a webhook to a dedicated test channel.
4. Treat the generated URL as a secret.

Do not commit the webhook URL to Git, put it in a watchlist, or paste it into
logs or screenshots.

## Windows PowerShell

Set the secret only for the current PowerShell process:

```powershell
$env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/..."
.\.venv\Scripts\python.exe -m src.slack_notification
```

Optional custom test text:

```powershell
.\.venv\Scripts\python.exe -m src.slack_notification `
  --message "Alert Engine manual Slack test"
```

Remove it from the current process afterward:

```powershell
Remove-Item Env:SLACK_WEBHOOK_URL
```

## macOS Terminal

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
.venv/bin/python -m src.slack_notification
unset SLACK_WEBHOOK_URL
```

## Expected result

Terminal:

```text
Slack test message sent successfully.
```

Slack channel:

```text
Alert Engine Slack connectivity test
Sent at: <timestamp>
No trading alert was generated.
```

This standalone command only proves webhook connectivity.

## Engine notifications

After successful initialization, the engine sends one summary containing the
trading date, readiness status, active-signal count, rejected-row count, and
unresolved-symbol count. It then sends another message only when a completed
candle triggers a BUY alert. The alert CSV and console output are written first.
Slack failures are logged and do not stop the engine.

Windows PowerShell:

```powershell
$env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/..."
.\run_live.ps1
```

macOS:

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
./run_live.sh
```

Disable it after testing:

```powershell
Remove-Item Env:SLACK_WEBHOOK_URL
```

```bash
unset SLACK_WEBHOOK_URL
```
