#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL="${REPO_URL:-https://github.com/TagirovAlex/mtproxy-manager.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"

APP_USER="${APP_USER:-mtproxy}"
APP_GROUP="${APP_GROUP:-mtproxy}"
APP_DIR="${APP_DIR:-/opt/mtproxy-manager}"
VENV_DIR="${APP_DIR}/.venv"
MANAGER_SERVICE="mtproxy-manager"

MANAGER_BIND_HOST="${MANAGER_BIND_HOST:-127.0.0.1}"
MANAGER_BIND_PORT="${MANAGER_BIND_PORT:-5000}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"

TMP_DIR=""

cleanup() {
  if [[ -n "${TMP_DIR:-}" && -d "${TMP_DIR:-}" ]]; then
    rm -rf "${TMP_DIR}"
  fi
}
trap cleanup EXIT

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash install.sh"
  exit 1
fi

detect_arch() {
  case "$(uname -m)" in
    x86_64) echo "amd64" ;;
    aarch64|arm64) echo "arm64" ;;
    *) echo "Unsupported architecture"; exit 1 ;;
  esac
}

install_mtg_secure() {
  local arch release_json asset_url checksums_url file_name expected_sha

  arch="$(detect_arch)"
  TMP_DIR="$(mktemp -d)"

  release_json="$(curl -fsSL https://api.github.com/repos/9seconds/mtg/releases/latest)"
  asset_url="$(echo "${release_json}" \
    | jq -r --arg a "${arch}" '.assets[] | select(.name | test("linux-" + $a + "\\.tar\\.gz$")) | .browser_download_url' \
    | head -n1)"
  checksums_url="$(echo "${release_json}" \
    | jq -r '.assets[] | select(.name | test("sha256|checksums"; "i")) | .browser_download_url' \
    | head -n1)"

  if [[ -z "${asset_url}" || "${asset_url}" == "null" ]]; then
    echo "Failed to resolve MTG release asset"
    exit 1
  fi

  file_name="$(basename "${asset_url}")"
  curl -fsSL "${asset_url}" -o "${TMP_DIR}/${file_name}"

  expected_sha="${MTG_SHA256:-}"
  if [[ -z "${expected_sha}" && -n "${checksums_url}" && "${checksums_url}" != "null" ]]; then
    curl -fsSL "${checksums_url}" -o "${TMP_DIR}/checksums.txt"
    expected_sha="$(grep " ${file_name}\$" "${TMP_DIR}/checksums.txt" | awk '{print $1}' | head -n1 || true)"
  fi

  if [[ -z "${expected_sha}" ]]; then
    echo "MTG checksum is not available. Set MTG_SHA256=<sha256> for secure install."
    exit 1
  fi

  echo "${expected_sha}  ${TMP_DIR}/${file_name}" | sha256sum -c -
  tar -xzf "${TMP_DIR}/${file_name}" -C "${TMP_DIR}"
  install -m 0755 "$(find "${TMP_DIR}" -type f -name mtg | head -n1)" /usr/local/bin/mtg
}

echo "[1/8] Installing packages"
apt-get update -y
apt-get install -y git curl jq tar ca-certificates sudo sqlite3 \
  python3 python3-venv python3-pip build-essential pkg-config libssl-dev

echo "[2/8] Creating user/group"
getent group "${APP_GROUP}" >/dev/null || groupadd --system "${APP_GROUP}"
id -u "${APP_USER}" >/dev/null 2>&1 || useradd --system --gid "${APP_GROUP}" --create-home --home-dir "/home/${APP_USER}" --shell /usr/sbin/nologin "${APP_USER}"

echo "[3/8] Deploying code"
mkdir -p "${APP_DIR}"
if [[ ! -d "${APP_DIR}/.git" ]]; then
  git clone --branch "${REPO_BRANCH}" "${REPO_URL}" "${APP_DIR}"
else
  git -C "${APP_DIR}" fetch --all --prune
  git -C "${APP_DIR}" checkout "${REPO_BRANCH}"
  git -C "${APP_DIR}" pull --ff-only
fi

echo "[4/8] Python venv"
python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip setuptools wheel
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo "[5/8] Directories"
for d in data logs backups scripts mtg mtg/instances; do
  mkdir -p "${APP_DIR}/${d}"
done

if [[ ! -f "${APP_DIR}/.env" && -f "${APP_DIR}/app/.env.example" ]]; then
  cp "${APP_DIR}/app/.env.example" "${APP_DIR}/.env"
elif [[ ! -f "${APP_DIR}/.env" && -f "${APP_DIR}/.env.example" ]]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
fi

echo "[6/8] MTG"
install_mtg_secure

echo "[7/8] systemd units"
install -m 0644 "${APP_DIR}/app/deploy/systemd/mtg@.service" /etc/systemd/system/mtg@.service

cat >"/etc/systemd/system/${MANAGER_SERVICE}.service" <<EOF
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
ExecStart=/bin/sh -c '${VENV_DIR}/bin/gunicorn -w \${GUNICORN_WORKERS:-${GUNICORN_WORKERS}} -b \${MANAGER_BIND_HOST:-${MANAGER_BIND_HOST}}:\${MANAGER_BIND_PORT:-${MANAGER_BIND_PORT}} run:app'
Restart=always
RestartSec=3
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=${APP_DIR}

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/sudoers.d/mtproxy-systemctl <<'EOF'
mtproxy ALL=(root) NOPASSWD: /usr/bin/systemctl start mtg@*.service
mtproxy ALL=(root) NOPASSWD: /usr/bin/systemctl stop mtg@*.service
mtproxy ALL=(root) NOPASSWD: /usr/bin/systemctl restart mtg@*.service
mtproxy ALL=(root) NOPASSWD: /usr/bin/systemctl enable mtg@*.service
mtproxy ALL=(root) NOPASSWD: /usr/bin/systemctl disable mtg@*.service
mtproxy ALL=(root) NOPASSWD: /usr/bin/systemctl is-active mtg@*.service
mtproxy ALL=(root) NOPASSWD: /usr/bin/systemctl show mtg@*.service --property=MainPID
mtproxy ALL=(root) NOPASSWD: /usr/bin/systemctl daemon-reload
EOF
chmod 440 /etc/sudoers.d/mtproxy-systemctl
visudo -cf /etc/sudoers.d/mtproxy-systemctl

echo "[8/8] Permissions and start"
chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"
chmod 640 "${APP_DIR}/.env" || true

systemctl daemon-reload
systemctl enable --now "${MANAGER_SERVICE}"

echo "Install complete."
echo "Next: run init script (init_app.sh)"