#!/usr/bin/env bash
# One-time host setup on Ubuntu 24.04: Docker, Compose, and the kernel setting
# Elasticsearch needs.
set -euo pipefail

sudo apt-get update -y
sudo apt-get install -y docker.io docker-compose-v2 git
sudo systemctl enable --now docker
sudo usermod -aG docker "${SUDO_USER:-$USER}"

echo 'vm.max_map_count=262144' | sudo tee /etc/sysctl.d/99-elasticsearch.conf >/dev/null
sudo sysctl -q --system
