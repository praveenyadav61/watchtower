#!/usr/bin/env bash
set -euo pipefail

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required. Run this on an Ubuntu EC2 instance." >&2
  exit 1
fi

TARGET_USER="${SUDO_USER:-$USER}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/../deploy/ec2" && pwd)"

echo "Installing Docker and AWS CLI prerequisites..."
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates curl docker.io unzip
sudo systemctl enable --now docker

if ! command -v aws >/dev/null 2>&1; then
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64) AWS_ARCH="x86_64" ;;
    aarch64|arm64) AWS_ARCH="aarch64" ;;
    *)
      echo "Unsupported CPU architecture: $ARCH" >&2
      exit 1
      ;;
  esac
  TEMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TEMP_DIR"' EXIT
  curl -fsSL \
    "https://awscli.amazonaws.com/awscli-exe-linux-${AWS_ARCH}.zip" \
    -o "$TEMP_DIR/awscliv2.zip"
  unzip -q "$TEMP_DIR/awscliv2.zip" -d "$TEMP_DIR"
  sudo "$TEMP_DIR/aws/install"
fi

if ! getent group watchtower >/dev/null; then
  sudo groupadd --gid 10001 watchtower
fi
sudo usermod -aG docker,watchtower "$TARGET_USER"

sudo mkdir -p /opt/watchtower/data/output /opt/watchtower/data/logs
sudo chown -R 10001:10001 /opt/watchtower/data
sudo chmod -R 2775 /opt/watchtower/data

if [[ ! -f /opt/watchtower/watchtower.env ]]; then
  sudo install -m 0660 -o root -g watchtower \
    "$DEPLOY_DIR/watchtower.env.example" /opt/watchtower/watchtower.env
fi
sudo chown root:watchtower /opt/watchtower/watchtower.env
sudo chmod 0660 /opt/watchtower/watchtower.env

sudo install -m 0755 \
  "$SCRIPT_DIR/ec2_watchtower.sh" /usr/local/bin/watchtower
sudo install -m 0644 \
  "$DEPLOY_DIR/watchtower-start.service" \
  /etc/systemd/system/watchtower-start.service
sudo install -m 0644 \
  "$DEPLOY_DIR/watchtower-start.timer" \
  /etc/systemd/system/watchtower-start.timer
sudo systemctl daemon-reload

echo
echo "EC2 bootstrap complete."
echo "Sign out and back in once so Docker/group access takes effect."
echo "Then edit /opt/watchtower/watchtower.env and run: watchtower mock"
echo "The optional weekday timer is installed but is not enabled automatically."
