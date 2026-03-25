#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/mtproxy-manager}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root"
  exit 1
fi

case "$(uname -m)" in
  x86_64) ARCH="amd64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *) echo "Unsupported arch"; exit 1 ;;
esac

apt-get update -y
apt-get install -y curl jq tar ca-certificates

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

URL="$(curl -fsSL https://api.github.com/repos/9seconds/mtg/releases/latest \
  | jq -r --arg a "${ARCH}" '.assets[] | select(.name | test("linux-" + $a + "\\.tar\\.gz$")) | .browser_download_url' | head -n1)"

curl -fsSL "${URL}" -o "${TMP}/mtg.tar.gz"
tar -xzf "${TMP}/mtg.tar.gz" -C "${TMP}"
install -m 0755 "$(find "${TMP}" -type f -name mtg | head -n1)" /usr/local/bin/mtg

mkdir -p "${APP_DIR}/mtg/instances"
install -m 0644 "${APP_DIR}/deploy/systemd/mtg@.service" /etc/systemd/system/mtg@.service

systemctl daemon-reload
echo "MTG multi-instance runtime installed"
echo "Use: systemctl start mtg@<instance_id>.service"