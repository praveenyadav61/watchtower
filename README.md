# Watchtower

A CSV-configured market alert engine using completed 15-minute Upstox candles.
It stores candles and alerts locally, writes daily operational logs, and can
send compact Slack notifications. It does not place orders.

Watchtower can run directly on Windows/macOS or as a command-started Linux
container. Container support is the first step toward running the same engine
manually on AWS without maintaining an always-on server.

Documentation:

- [Project setup and daily run](docs/project_setup_and_daily_run.md)
- [Alert logic](docs/alert_logic.md)
