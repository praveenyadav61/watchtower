# Watchtower

A CSV-configured market alert engine using completed 15-minute Upstox candles.
It stores candles and alerts locally, writes daily operational logs, and can
send compact Slack notifications. It does not place orders.

Watchtower can run directly on Windows/macOS or on EC2 as a Docker container.
GitHub Actions validates and publishes immutable images to ECR. A single EC2
command pulls and runs the newest image for the market session.

Documentation:

- [Project setup and daily run](docs/project_setup_and_daily_run.md)
- [Alert logic](docs/alert_logic.md)
