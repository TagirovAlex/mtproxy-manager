#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="https://github.com/TagirovAlex/mtproxy-manager.git"
REPO_BRANCH="main"

APP_USER="mtproxy"
APP_GROUP="mtproxy"
APP_DIR="/opt/mtproxy-manager"
VENV_DIR="${APP_DIR}/.venv"

MANAGER_SERVICE="mtproxy-manager"
MTG_SERVICE="mtg-proxy"
MANAGER_BIND="127.0.0.1:5000"
GUNICORN_WORKERS="2"

MTG_DOMAIN="${MTG_DOMAIN:-example.com}"
MTG_BIND_PORT="${MTG_BIND_PORT:-443}"
MTG_CONFIG_DIR="${APP_DIR}/mtg"
MTG_TOML="${MTG_CONFIG_DIR}/mtg.toml"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash install.sh"
  exit 1
fi

detect_arch() {
  case "$(uname -m)" in
    x86_64) echo "amd64" ;;
    aarch64|arm64) echo "arm64" ;;
    *) echo "Unsupported arch"; exit 1 ;;
  esac
}

apt-get update -y
apt-get install -y git curl jq tar ca-certificates python3 python3-venv python3-pip build-essential pkg-config libssl-dev

getent group "${APP_GROUP}" >/dev/null || groupadd --system "${APP_GROUP}"
id -u "${APP_USER}" >/dev/null 2>&1 || useradd --system --gid "${APP_GROUP}" --create-home --home-dir "/home/${APP_USER}" --shell /usr/sbin/nologin "${APP_USER}"

mkdir -p "${APP_DIR}"
if [[ ! -d "${APP_DIR}/.git" ]]; then
  git clone --branch "${REPO_BRANCH}" "${REPO_URL}" "${APP_DIR}"
else
  git -C "${APP_DIR}" fetch --all --prune
  git -C "${APP_DIR}" checkout "${REPO_BRANCH}"
  git -C "${APP_DIR}" pull --ff-only
fi

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip setuptools wheel
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"

for d in data logs backups scripts mtg; do
  mkdir -p "${APP_DIR}/${d}"
done

[[ -f "${APP_DIR}/.env" ]] || cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"

# MTG install
ARCH="$(detect_arch)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
ASSET_URL="$(curl -fsSL https://api.github.com/repos/9seconds/mtg/releases/latest \
  | jq -r --arg a "${ARCH}" '.assets[] | select(.name | test("linux-" + $a + "\\.tar\\.gz$")) | .browser_download_url' | head -n1)"
curl -fsSL "${ASSET_URL}" -o "${TMP}/mtg.tar.gz"
tar -xzf "${TMP}/mtg.tar.gz" -C "${TMP}"
install -m 0755 "$(find "${TMP}" -type f -name mtg | head -n1)" /usr/local/bin/mtg

mkdir -p "${MTG_CONFIG_DIR}"
if [[ ! -f "${MTG_TOML}" ]]; then
  SECRET="$(/usr/local/bin/mtg generate-secret --hex "${MTG_DOMAIN}")"
  cat > "${MTG_TOML}" <<EOF
secret = "${SECRET}"
bind-to = "0.0.0.0:${MTG_BIND_PORT}"

[stats.prometheus]
bind-to = "127.0.0.1:3129"
EOF
fi

cat > "/etc/systemd/system/${MANAGER_SERVICE}.service" <<EOF
[Unit]
Description=MTProxy Manager (Gunicorn)
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
Environment=FLASK_CONFIG=production
ExecStart=${VENV_DIR}/bin/gunicorn -w ${GUNICORN_WORKERS} -b ${MANAGER_BIND} run:app
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=${APP_DIR}

[Install]
WantedBy=multi-user.target
EOF

cat > "/etc/systemd/system/${MTG_SERVICE}.service" <<EOF
[Unit]
Description=MTG Proxy
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
ExecStart=/usr/local/bin/mtg run ${MTG_TOML}
Restart=always
RestartSec=3
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"
chmod 640 "${APP_DIR}/.env" || true

systemctl daemon-reload
systemctl enable --now "${MANAGER_SERVICE}"
systemctl enable --now "${MTG_SERVICE}"

echo "Done"