# Watchtower

A CSV-configured market alert engine using completed 15-minute Upstox candles.
It stores candles and alerts locally, writes daily operational logs, and can
send compact Slack notifications. It does not place orders.

Watchtower can run directly on Windows/macOS or on EC2 as a Docker container.
The primary EC2 flow builds, validates, and runs the Docker image on the
instance. GitHub Actions and ECR remain available as an optional release path.

Documentation:

- [Project setup and daily run](docs/project_setup_and_daily_run.md)
- [Alert logic](docs/alert_logic.md)
- [Optional ECR deployment](docs/ecr_deployment.md)
