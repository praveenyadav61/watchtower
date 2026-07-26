# Setup and Daily Run

Watchtower builds, tests, and runs its production Docker image directly on the
EC2 instance. This guide is ordered by the commands a team member uses most
often.

## Daily run - start here

You need:

- `watchtower.pem` on your computer;
- the EC2 public IP;
- today's `watchlist_YYYYMMDD.csv`;
- today's Upstox token.

Use the India-market date in place of `YYYYMMDD`.

### 1. Upload today's watchlist

Run from Windows PowerShell in the directory containing `watchtower.pem` and
the CSV:

```powershell
scp -i watchtower.pem `
  .\watchlist_YYYYMMDD.csv `
  ubuntu@EC2_PUBLIC_IP:/tmp/
```

Replace `YYYYMMDD` and `EC2_PUBLIC_IP` with real values.

### 2. Connect to EC2

Run from Windows PowerShell:

```powershell
ssh -i watchtower.pem ubuntu@EC2_PUBLIC_IP
```

All following `bash` commands run inside this SSH session.

### 3. Install today's watchlist

```bash
sudo mv /tmp/watchlist_YYYYMMDD.csv /opt/watchtower/data/
sudo chown 10001:10001 \
  /opt/watchtower/data/watchlist_YYYYMMDD.csv
```

### 4. Update today's token

```bash
nano /opt/watchtower/watchtower.env
```

The file must contain:

```text
UPSTOX_ACCESS_TOKEN=current-daily-token
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
MARKET_CUTOFF_TIME=15:30
```

Save with `Ctrl+O`, press Enter, and exit with `Ctrl+X`.

### 5. Verify inputs

```bash
TZ=Asia/Kolkata date
ls -lh /opt/watchtower/data/watchlist_$(TZ=Asia/Kolkata date +%Y%m%d).csv
```

### 6. Start Watchtower

```bash
watchtower deploy
watchtower status
watchtower logs
```

Use `Ctrl+C` to stop following logs. The container continues running in the
background, and closing SSH does not stop it.

When no code changed, do not run another Docker build. The daily commands end
here.

## After code changes

Developers make changes locally, review them, and merge them into `main`. Do
not edit production code directly on EC2.

Connect to EC2:

```powershell
ssh -i watchtower.pem ubuntu@EC2_PUBLIC_IP
```

Pull, build, and validate:

```bash
cd ~/watchtower
git pull --ff-only origin main
watchtower release
```

`watchtower release`:

1. builds `watchtower:local`;
2. runs all Python unit tests during the Docker build;
3. runs the bundled mock watchlist and mock candles;
4. fails without replacing the running container if validation fails.

Deploy only after this message:

```text
Release candidate passed unit and mock-flow validation.
```

Then deploy:

```bash
watchtower deploy
watchtower logs
```

The complete code-change sequence is:

```bash
cd ~/watchtower
git pull --ff-only origin main
watchtower release
watchtower deploy
watchtower logs
```

## Useful production commands

```bash
watchtower status    # Show the live or stopped container
watchtower logs      # Follow the latest 200 container log lines
watchtower stop      # Stop and remove the live container
watchtower mock      # Test the existing image with mock data
watchtower release   # Rebuild, run unit tests, and run mock data
watchtower source    # Show the repository used for Docker builds
```

Expected market-day behavior:

- initialization occurs immediately;
- the first completed 15-minute candle is checked shortly after 09:30;
- checks continue shortly after each 15-minute boundary;
- the final check occurs at 15:30;
- the engine exits cleanly after the final check.

The EC2 instance must remain running throughout the market session.

## One-time setup on a new EC2 instance

Recommended instance:

- Ubuntu 24.04 LTS, x86_64;
- `t3.micro` initially;
- 15-20 GB `gp3` EBS;
- public IP enabled;
- SSH port 22 restricted to approved IP addresses;
- no HTTP or HTTPS inbound rules.

Use `t3.small` if the Docker build is killed because it lacks memory.

The normal local-build deployment does not require ECR permissions, an EC2 IAM
role, or AWS credentials.

Connect:

```powershell
ssh -i watchtower.pem ubuntu@EC2_PUBLIC_IP
```

Clone and bootstrap:

```bash
git clone https://github.com/praveenyadav61/watchtower.git
cd watchtower
bash ./scripts/ec2_bootstrap.sh
exit
```

Reconnect once so Docker group membership is active:

```powershell
ssh -i watchtower.pem ubuntu@EC2_PUBLIC_IP
```

Build and validate the first image:

```bash
watchtower release
```

Configure credentials:

```bash
nano /opt/watchtower/watchtower.env
```

Then follow the daily-run section to upload the dated watchlist and start the
engine.

## One-time upgrade from the older ECR-first setup

Run this once if `watchtower deploy` still tries to contact ECR:

```powershell
ssh -i watchtower.pem ubuntu@EC2_PUBLIC_IP
```

On EC2:

```bash
cd ~/watchtower
git pull --ff-only origin main
bash ./scripts/ec2_bootstrap.sh
exit
```

Reconnect and build:

```powershell
ssh -i watchtower.pem ubuntu@EC2_PUBLIC_IP
```

```bash
watchtower release
```

After this upgrade, `watchtower deploy` uses only the image built on EC2.

## Optional automatic morning start

Manual morning start is the default. The bootstrap installs, but does not
enable, an optional systemd timer.

Enable the 08:45 Asia/Kolkata weekday timer only when the daily token and
watchlist will always be ready before 08:45:

```bash
sudo systemctl enable --now watchtower-start.timer
watchtower schedule
```

Disable it:

```bash
sudo systemctl disable --now watchtower-start.timer
```

Inspect timer failures:

```bash
watchtower schedule-logs
```

## Local Windows and macOS run

Docker is not required for local development.

Windows one-time setup:

```powershell
git clone https://github.com/praveenyadav61/watchtower.git
cd watchtower
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Windows daily run:

```powershell
$env:UPSTOX_ACCESS_TOKEN = "current-daily-token"
$env:SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/..."
.\run_live.ps1
```

macOS one-time setup:

```bash
git clone https://github.com/praveenyadav61/watchtower.git
cd watchtower
bash ./setup.sh
```

macOS daily run:

```bash
export UPSTOX_ACCESS_TOKEN="current-daily-token"
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
bash ./run_live.sh
```

Place `watchlist_YYYYMMDD.csv` in the repository root before starting.

Run only the local mock preflight:

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

Optional columns are documented in [Alert logic](alert_logic.md).

## Persistent outputs

```text
/opt/watchtower/data/output/candles_YYYYMMDD.csv
/opt/watchtower/data/output/execution_alerts_YYYYMMDD.csv
/opt/watchtower/data/output/cumulative_scores_YYYYMMDD.csv
/opt/watchtower/data/logs/alert_engine_YYYYMMDD.log
/opt/watchtower/data/logs/alert_engine_errors_YYYYMMDD.log
```

Inspect them:

```bash
ls -lh /opt/watchtower/data/output
ls -lh /opt/watchtower/data/logs
```

These files are stored on EBS and survive container replacement and EC2
stop/start operations.

## Troubleshooting

- `Local image watchtower:local does not exist`: run `watchtower release`.
- `Missing watchlist_YYYYMMDD.csv`: upload the correctly dated file.
- `UPSTOX_ACCESS_TOKEN is missing`: update `watchtower.env`.
- Repeated restart messages: run `watchtower stop`, fix the input, and deploy.
- Docker permission denied: sign out and reconnect after bootstrap.
- Docker build is killed or freezes: resize the instance to `t3.small`.
- No candle before 09:30: no completed 15-minute candle is available yet.
- One symbol/API failure: inspect the error log; other symbols continue.

## Optional ECR deployment

The normal `watchtower` command does not contact ECR. The preserved ECR
alternative uses `watchtower-ecr` and is documented in
[Optional ECR deployment](ecr_deployment.md).
