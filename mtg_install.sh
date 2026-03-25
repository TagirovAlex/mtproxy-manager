#!/usr/bin/env bash
set -Eeuo pipefail

MTG_DOMAIN="${MTG_DOMAIN:-example.com}"
MTG_BIND_PORT="${MTG_BIND_PORT:-443}"
MTG_TOML="${MTG_TOML:-/etc/mtg/mtg.toml}"

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

mkdir -p "$(dirname "${MTG_TOML}")"
if [[ ! -f "${MTG_TOML}" ]]; then
  SECRET="$(/usr/local/bin/mtg generate-secret --hex "${MTG_DOMAIN}")"
  cat > "${MTG_TOML}" <<EOF
secret = "${SECRET}"
bind-to = "0.0.0.0:${MTG_BIND_PORT}"

[stats.prometheus]
bind-to = "127.0.0.1:3129"
EOF
fi

cat > /etc/systemd/system/mtg-proxy.service <<EOF
[Unit]
Description=MTG Proxy
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/mtg run ${MTG_TOML}
Restart=always
RestartSec=3
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now mtg-proxy
systemctl status mtg-proxy --no-pager || true