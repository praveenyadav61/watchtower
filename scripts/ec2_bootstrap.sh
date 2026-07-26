#!/usr/bin/env bash
set -euo pipefail

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required. Run this on an Ubuntu EC2 instance." >&2
  exit 1
fi

TARGET_USER="${SUDO_USER:-$USER}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/../deploy/ec2" && pwd)"

echo "Installing Docker and deployment prerequisites..."
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates docker.io git
sudo systemctl enable --now docker

if ! getent group watchtower >/dev/null; then
  sudo groupadd --gid 10001 watchtower
fi
sudo usermod -aG docker,watchtower "$TARGET_USER"

sudo mkdir -p /opt/watchtower/data/output /opt/watchtower/data/logs
sudo ln -sfn "$REPOSITORY_ROOT" /opt/watchtower/source
sudo chown -R 10001:10001 /opt/watchtower/data
sudo chmod -R 2775 /opt/watchtower/data

if [[ ! -f /opt/watchtower/watchtower.env ]]; then
  sudo install -m 0660 -o root -g watchtower \
    "$DEPLOY_DIR/watchtower.env.example" /opt/watchtower/watchtower.env
fi
sudo chown root:watchtower /opt/watchtower/watchtower.env
sudo chmod 0660 /opt/watchtower/watchtower.env

sudo chmod 0755 \
  "$SCRIPT_DIR/ec2_watchtower.sh" "$SCRIPT_DIR/ec2_watchtower_ecr.sh"
sudo ln -sfn "$SCRIPT_DIR/ec2_watchtower.sh" /usr/local/bin/watchtower
sudo ln -sfn "$SCRIPT_DIR/ec2_watchtower_ecr.sh" /usr/local/bin/watchtower-ecr
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
echo "Then build and test the local image with: watchtower release"
echo "The optional weekday timer is installed but is not enabled automatically."
