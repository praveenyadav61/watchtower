# Setup and Daily Run

This is the single operations guide for Watchtower. EC2 with Docker is the
primary shared runtime. Windows and macOS commands are included for local
development.

## Daily EC2 run

Before market hours:

1. Create today's CSV as `watchlist_YYYYMMDD.csv` using the India-market date.
2. Upload it to `/opt/watchtower/data`.
3. Update the daily Upstox token.
4. Start Watchtower.

From your local computer, upload the watchlist:

```bash
scp -i your-key.pem watchlist_YYYYMMDD.csv \
  ubuntu@EC2_PUBLIC_IP:/opt/watchtower/data/
```

Connect to EC2:

```bash
ssh -i your-key.pem ubuntu@EC2_PUBLIC_IP
```

Update credentials:

```bash
nano /opt/watchtower/watchtower.env
```

The file must contain:

```text
UPSTOX_ACCESS_TOKEN=current-daily-token
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
MARKET_CUTOFF_TIME=15:30
```

Start the newest tested image:

```bash
watchtower deploy
```

Useful commands:

```bash
watchtower status
watchtower logs
watchtower stop
```

The engine initializes immediately. It evaluates completed 15-minute candles
shortly after each boundary, beginning after 09:30, and stops cleanly after the
15:30 check. The EC2 instance must remain running throughout the session.

## Validate a new release

Every push to `main` runs the **Publish Watchtower Image** GitHub workflow. It:

1. Installs dependencies.
2. Runs all unit tests.
3. validates the shell scripts.
4. Builds the Linux Docker image.
5. Runs the bundled mock watchlist and mock candles.
6. Publishes the successful immutable image to ECR.

Nothing is deployed to EC2 automatically when code is published. Test the
newest image safely from EC2:

```bash
watchtower mock
```

This test does not call Upstox and does not require an Upstox token. After it
passes, start the live engine with:

```bash
watchtower deploy
```

To validate from GitHub without publishing, open:

```text
Actions > Validate Watchtower Container > Run workflow
```

## One-time AWS and EC2 setup

Required AWS resources:

- Private ECR repository `watchtower` in `ap-south-1`
- GitHub OIDC publisher role configured in `AWS_PUBLISH_ROLE_ARN`
- Ubuntu 24.04 LTS x86_64 EC2 instance
- 15-20 GB `gp3` EBS volume
- EC2 IAM role with `AmazonEC2ContainerRegistryReadOnly`
- Security group allowing SSH only from approved IP addresses

Watchtower requires no inbound application port.

Clone and bootstrap the EC2 instance:

```bash
ssh -i your-key.pem ubuntu@EC2_PUBLIC_IP
git clone https://github.com/praveenyadav61/watchtower.git
cd watchtower
bash ./scripts/ec2_bootstrap.sh
exit
```

Reconnect once so the new Docker group membership is active:

```bash
ssh -i your-key.pem ubuntu@EC2_PUBLIC_IP
```

The bootstrap:

- installs Docker and AWS CLI v2;
- creates `/opt/watchtower/data`, `output`, and `logs`;
- installs the `watchtower` command;
- creates `/opt/watchtower/watchtower.env`;
- installs the optional weekday timer.

Configure credentials, upload a dated watchlist, and verify:

```bash
nano /opt/watchtower/watchtower.env
watchtower mock
watchtower deploy
watchtower logs
```

## Optional automatic morning start

The bootstrap installs a timer for 08:45 Asia/Kolkata, Monday through Friday.
Enable it only when daily tokens and watchlists will be ready before 08:45:

```bash
sudo systemctl enable --now watchtower-start.timer
watchtower schedule
```

For manual morning starts, disable it:

```bash
sudo systemctl disable --now watchtower-start.timer
```

Inspect timer failures:

```bash
watchtower schedule-logs
```

## Local setup

Python 3.11 or newer is recommended. `tzdata` is installed from
`requirements.txt`, so India-market scheduling works on Windows and macOS.

Windows PowerShell:

```powershell
git clone https://github.com/praveenyadav61/watchtower.git
cd watchtower
powershell -ExecutionPolicy Bypass -File .\setup.ps1
$env:UPSTOX_ACCESS_TOKEN = "current-daily-token"
$env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/..."
.\run_live.ps1
```

macOS:

```bash
git clone https://github.com/praveenyadav61/watchtower.git
cd watchtower
bash ./setup.sh
export UPSTOX_ACCESS_TOKEN="current-daily-token"
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
bash ./run_live.sh
```

Place `watchlist_YYYYMMDD.csv` in the repository root before starting. Both
launchers run the isolated cumulative-score preflight before connecting to
Upstox.

Run only the local preflight:

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

## Watchlist

The simplest cumulative-score watchlist is:

```csv
symbol,volume_threshold
ADANIENT,500000
```

Optional alert columns are documented in
[Alert logic](alert_logic.md). Empty optional cells are allowed.

## Outputs

Persistent daily files:

```text
output/candles_YYYYMMDD.csv
output/execution_alerts_YYYYMMDD.csv
output/cumulative_scores_YYYYMMDD.csv
logs/alert_engine_YYYYMMDD.log
logs/alert_engine_errors_YYYYMMDD.log
```

On EC2 these are under:

```text
/opt/watchtower/data/output
/opt/watchtower/data/logs
```

## Troubleshooting

- `UPSTOX_ACCESS_TOKEN is missing`: update `watchtower.env`.
- `Missing watchlist_YYYYMMDD.csv`: upload the correctly dated file.
- No candles before 09:30: the first 15-minute candle is not checked until it
  is completed.
- No Slack messages: verify `SLACK_WEBHOOK_URL`; the engine continues writing
  console, CSV, and file logs without Slack.
- One symbol fails: inspect the error log; other symbols continue and the
  failed symbol is retried during the next cycle.
- EC2 stopped or slept: start it and run `watchtower deploy`; persisted state
  prevents duplicate processing.
