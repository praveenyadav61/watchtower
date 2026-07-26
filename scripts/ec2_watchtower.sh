#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
SOURCE_DIRECTORY="${WATCHTOWER_SOURCE_DIR:-/opt/watchtower/source}"
IMAGE="${WATCHTOWER_IMAGE:-watchtower:local}"
DATA_DIRECTORY="/opt/watchtower/data"
ENV_FILE="/opt/watchtower/watchtower.env"
CONTAINER_NAME="watchtower"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command is missing: $1" >&2
    exit 1
  fi
}

require_source() {
  if [[ ! -f "$SOURCE_DIRECTORY/Dockerfile" ]]; then
    echo "Watchtower source is missing: $SOURCE_DIRECTORY" >&2
    echo "Run the EC2 bootstrap again from the cloned repository." >&2
    exit 1
  fi
}

require_image() {
  if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Local image $IMAGE does not exist." >&2
    echo "Build and test it first with: watchtower release" >&2
    exit 1
  fi
}

validate_live_inputs() {
  local trading_date
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "Missing environment file: $ENV_FILE" >&2
    exit 1
  fi
  if ! grep -Eq '^UPSTOX_ACCESS_TOKEN=.+$' "$ENV_FILE"; then
    echo "UPSTOX_ACCESS_TOKEN is missing from $ENV_FILE" >&2
    exit 1
  fi
  trading_date="$(TZ=Asia/Kolkata date +%Y%m%d)"
  if [[ ! -f "$DATA_DIRECTORY/watchlist_${trading_date}.csv" ]]; then
    echo "Missing watchlist_${trading_date}.csv in $DATA_DIRECTORY" >&2
    exit 1
  fi
}

build_image() {
  require_command docker
  require_source
  echo "Building $IMAGE from $SOURCE_DIRECTORY"
  docker build --pull --tag "$IMAGE" "$SOURCE_DIRECTORY"
}

run_mock() {
  require_command docker
  require_image
  docker rm -f watchtower-mock >/dev/null 2>&1 || true
  echo "Running closed-market test with $IMAGE"
  docker run --rm --name watchtower-mock "$IMAGE" mock-test
}

case "$ACTION" in
  build)
    build_image
    ;;
  test|mock)
    run_mock
    ;;
  release)
    build_image
    run_mock
    echo "Release candidate passed unit and mock-flow validation."
    ;;
  deploy|live)
    require_command docker
    require_image
    validate_live_inputs
    docker stop --time 60 "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
    docker run --detach \
      --name "$CONTAINER_NAME" \
      --restart on-failure:3 \
      --stop-timeout 60 \
      --env-file "$ENV_FILE" \
      --volume "$DATA_DIRECTORY:/data" \
      --log-driver json-file \
      --log-opt max-size=20m \
      --log-opt max-file=5 \
      "$IMAGE"
    echo "Watchtower started with local image $IMAGE"
    echo "Follow logs with: watchtower logs"
    docker logs --tail 30 "$CONTAINER_NAME"
    ;;
  status)
    require_command docker
    docker ps -a --filter "name=^/${CONTAINER_NAME}$"
    ;;
  logs)
    require_command docker
    exec docker logs --tail 200 --follow "$CONTAINER_NAME"
    ;;
  stop)
    require_command docker
    docker stop --time 60 "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
    echo "Watchtower stopped."
    ;;
  schedule)
    systemctl list-timers watchtower-start.timer --no-pager
    ;;
  schedule-logs)
    exec journalctl -u watchtower-start.service -n 100 --no-pager
    ;;
  source)
    echo "$SOURCE_DIRECTORY"
    ;;
  *)
    echo "Usage: watchtower {release|build|test|mock|deploy|status|logs|stop|source|schedule|schedule-logs}" >&2
    exit 2
    ;;
esac
