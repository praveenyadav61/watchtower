#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-mock}"
EXPLICIT_IMAGE="${2:-}"
AWS_REGION="${AWS_REGION:-ap-south-1}"
ECR_REPOSITORY="${ECR_REPOSITORY:-watchtower}"
DATA_DIRECTORY="/opt/watchtower/data"
ENV_FILE="/opt/watchtower/watchtower.env"
CONTAINER_NAME="watchtower"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command is missing: $1" >&2
    exit 1
  fi
}

latest_image() {
  local account_id digest
  account_id="$(
    aws sts get-caller-identity \
      --query Account --output text --region "$AWS_REGION"
  )"
  digest="$(
    aws ecr describe-images \
      --repository-name "$ECR_REPOSITORY" \
      --region "$AWS_REGION" \
      --query 'sort_by(imageDetails,&imagePushedAt)[-1].imageDigest' \
      --output text
  )"
  if [[ -z "$digest" || "$digest" == "None" ]]; then
    echo "No image exists in ECR repository $ECR_REPOSITORY." >&2
    exit 1
  fi
  printf '%s.dkr.ecr.%s.amazonaws.com/%s@%s' \
    "$account_id" "$AWS_REGION" "$ECR_REPOSITORY" "$digest"
}

login_and_pull() {
  local image="$1" registry="${1%%/*}"
  aws ecr get-login-password --region "$AWS_REGION" |
    docker login --username AWS --password-stdin "$registry"
  docker pull "$image"
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

require_command aws
require_command docker
IMAGE="${EXPLICIT_IMAGE:-$(latest_image)}"
login_and_pull "$IMAGE"

case "$ACTION" in
  mock|test)
    docker rm -f watchtower-mock >/dev/null 2>&1 || true
    echo "Running ECR image mock test with $IMAGE"
    exec docker run --rm --name watchtower-mock "$IMAGE" mock-test
    ;;
  deploy|live)
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
    echo "Watchtower started with ECR image $IMAGE"
    echo "Follow logs with: watchtower logs"
    docker logs --tail 30 "$CONTAINER_NAME"
    ;;
  *)
    echo "Usage: watchtower-ecr {mock|test|deploy|live} [IMAGE_URI]" >&2
    exit 2
    ;;
esac
