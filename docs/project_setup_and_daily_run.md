# Project Setup and Daily Run

This is the complete installation and daily-operation guide for Windows and
macOS. Run commands from the project root.

## GitHub container validation

Before creating AWS resources, run the manual GitHub workflow:

1. Open the repository on GitHub.
2. Select **Actions**.
3. Select **Validate Watchtower Container**.
4. Select **Run workflow** and run it from `main`.

The workflow runs all unit tests, builds the Linux image, and executes the
closed-market `mock-test` inside the image. It does not connect to AWS, Upstox,
or Slack and is manual-only so it does not consume Actions minutes after every
push.

## Publish the image to AWS ECR

The manual **Publish Watchtower Image** workflow validates the project again,
authenticates with short-lived GitHub OIDC credentials, and pushes one image
tagged with the Git commit SHA and workflow run identifiers. It does not create
or run an ECS task.

AWS prerequisites in region `ap-south-1`:

1. Create a private ECR repository named `watchtower`.
2. Configure tag mutability as **Immutable** and encryption as **AES-256**.
3. Add the GitHub OIDC identity provider in IAM:
   - Provider URL: `https://token.actions.githubusercontent.com`
   - Audience: `sts.amazonaws.com`
4. Create an IAM web-identity role named `WatchtowerGitHubEcrPublisher`.
5. Restrict its trust to the exact GitHub owner, repository `watchtower`,
   and branch `main`.
6. Attach this least-privilege permission policy, replacing the account ID:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EcrLogin",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "PublishWatchtowerImage",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:CompleteLayerUpload",
        "ecr:InitiateLayerUpload",
        "ecr:PutImage",
        "ecr:UploadLayerPart"
      ],
      "Resource": "arn:aws:ecr:ap-south-1:AWS_ACCOUNT_ID:repository/watchtower"
    }
  ]
}
```

In GitHub, open **Settings → Secrets and variables → Actions → Variables** and
create this repository variable:

```text
AWS_PUBLISH_ROLE_ARN=arn:aws:iam::AWS_ACCOUNT_ID:role/WatchtowerGitHubEcrPublisher
```

The role ARN is non-secret configuration. Do not create or store AWS access
keys in GitHub.

To publish, open **Actions → Publish Watchtower Image → Run workflow**. On
success, the workflow summary displays the complete immutable ECR image URI.

## Container run

This is the AWS-ready, command-based runtime. It does not schedule or keep any
paid AWS service running by itself.

Build once after cloning or changing dependencies:

```bash
docker build -t watchtower:local .
```

Create a local runtime directory and copy today's watchlist into it:

```bash
mkdir -p runtime
cp watchlist_YYYYMMDD.csv runtime/
```

Run on macOS or Linux:

```bash
docker run --rm --name watchtower \
  -e UPSTOX_ACCESS_TOKEN \
  -e SLACK_WEBHOOK_URL \
  -v "$(pwd)/runtime:/data" \
  watchtower:local
```

Run from Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force .\runtime | Out-Null
Copy-Item .\watchlist_YYYYMMDD.csv .\runtime\
docker run --rm --name watchtower `
  -e UPSTOX_ACCESS_TOKEN `
  -e SLACK_WEBHOOK_URL `
  -v "${PWD}\runtime:/data" `
  watchtower:local
```

The container automatically selects `/data/watchlist_YYYYMMDD.csv`, runs the
isolated mock preflight, and starts live watch mode. Outputs are retained under
`runtime/output` and `runtime/logs` after the container stops. Credentials are
passed from the current shell and are not stored in the image.

### Closed-market container test

The same image has an isolated `mock-test` command for weekends and closed
markets. It uses the bundled alert-producing watchlist, candles, and instrument
list. It does not call Upstox or require `UPSTOX_ACCESS_TOKEN`.

macOS or Linux:

```bash
docker run --rm --name watchtower-mock \
  -e SLACK_WEBHOOK_URL \
  -v "$(pwd)/runtime:/data" \
  watchtower:local mock-test
```

Windows PowerShell:

```powershell
docker run --rm --name watchtower-mock `
  -e SLACK_WEBHOOK_URL `
  -v "${PWD}\runtime:/data" `
  watchtower:local mock-test
```

Expected results:

- `PRE-FLIGHT PASSED` in the console
- one Slack initialization notification
- one cumulative-score Slack alert for `MOTILALOFS`
- mock candle and cumulative-score CSV files under `runtime/output`
- operational logs under `runtime/logs`

The AWS ECS task can run this exact image by overriding its container command
with `mock-test`. A fresh task filesystem should be used for each mock run so a
previous persisted test alert does not suppress the duplicate.

To use a differently named watchlist, pass its container path:

```bash
docker run --rm --name watchtower \
  -e UPSTOX_ACCESS_TOKEN \
  -e SLACK_WEBHOOK_URL \
  -v "$(pwd)/runtime:/data" \
  watchtower:local /data/my_watchlist.csv
```

## Watchlist

Create the daily CSV in the project root using the current India-market date:

```text
watchlist_YYYYMMDD.csv
```

Example:

```csv
symbol,volume_threshold,price_low_limit,price_high_limit,ema20
ADANIENT,500000,2950,3150,3025.40
```

At least one alert value is required per row. Unused alert cells may be blank.
The launch scripts prefer today's dated file and otherwise use `watchlist.csv`.

## First-time setup

Windows PowerShell:

```powershell
git clone <repository-url> alert-engine
cd alert-engine
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

macOS Terminal:

```bash
git clone <repository-url> alert-engine
cd alert-engine
bash ./setup.sh
```

Python 3.11 or newer is recommended. `tzdata` is installed automatically so
`Asia/Kolkata` scheduling works consistently on Windows and macOS.

## Set credentials

Credentials are read only from environment variables. The scripts never prompt
for or store them. Set them in every new terminal session.

Windows PowerShell:

```powershell
$env:UPSTOX_ACCESS_TOKEN = "your-current-upstox-token"
$env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/..."
```

macOS Terminal:

```bash
export UPSTOX_ACCESS_TOKEN="your-current-upstox-token"
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

`UPSTOX_ACCESS_TOKEN` is required. Slack is optional; without its webhook the
engine continues with console, CSV, and file logging.

Test Slack independently:

```powershell
.\.venv\Scripts\python.exe -m src.slack_notification
```

```bash
.venv/bin/python -m src.slack_notification
```

## Start the day

Windows:

```powershell
.\run_live.ps1
```

macOS:

```bash
bash ./run_live.sh
```

To select a different file explicitly:

```powershell
.\run_live.ps1 -Watchlist .\watchlist_YYYYMMDD.csv
```

```bash
bash ./run_live.sh ./watchlist_YYYYMMDD.csv
```

The engine initializes immediately, waits when started before market time, and
checks shortly after every 15-minute candle boundary. Windows sleep prevention
and macOS `caffeinate` remain active while the launch script is running. Keep a
laptop powered and do not close its lid.

Before connecting to Upstox, both launch scripts automatically run an isolated
cumulative-score mock preflight. It validates candle ordering, score and
harmonic calculations, the score-above-5 alert, per-symbol alert count,
persistence, and restart deduplication. It cannot send Slack or modify live
daily output. A failed preflight stops the live launch.

Run the same preflight manually at any time:

```powershell
.\.venv\Scripts\python.exe -m src.preflight_check
```

```bash
.venv/bin/python -m src.preflight_check
```

Expected result:

```text
PRE-FLIGHT PASSED: cumulative-score mock flow is healthy.
```

Stop cleanly with `Ctrl+C`.

## Outputs

Daily files are written automatically:

```text
output/candles_YYYYMMDD.csv
output/execution_alerts_YYYYMMDD.csv
output/cumulative_scores_YYYYMMDD.csv
logs/alert_engine_YYYYMMDD.log
logs/alert_engine_errors_YYYYMMDD.log
```

Candles, alerts, cumulative scores, histories, and per-symbol alert counts are
restored when the engine restarts. A failure for one symbol is logged without
terminating the remaining symbols.

## Closed-market test

Windows:

```powershell
.\.venv\Scripts\python.exe -m src.execution_engine `
  .\examples\multi_alert_watchlist.csv `
  --trading-date 20260713 `
  --mock-candles .\examples\mock_candles.json `
  --mock-instruments .\examples\mock_instruments.json
```

macOS:

```bash
.venv/bin/python -m src.execution_engine \
  ./examples/multi_alert_watchlist.csv \
  --trading-date 20260713 \
  --mock-candles ./examples/mock_candles.json \
  --mock-instruments ./examples/mock_instruments.json
```

## Quick troubleshooting

- Missing token: export `UPSTOX_ACCESS_TOKEN` before starting.
- No Slack: export `SLACK_WEBHOOK_URL`, then run the standalone Slack test.
- No candles yet: wait until a 15-minute candle has completed.
- Watchlist error: use the exact column names shown above and positive numbers.
- API failure: inspect the error-only log for the HTTP status and request ID.
- Laptop slept: restart the script; persisted candle and alert keys prevent
  duplicate output.
